# Stage 1：自研几何与 YAML 的替换 + 冻结样例逐项比对

- 日期：2026-10-26　对应最终复验报告《Stage 1 的进入条件与顺序》第 4 条
- 替换前基线：`acceptance/stage-1/baseline-frozen.json`（Stage 0 冻结提交 `31d43a8` 的真实跑分）
- 替换后快照：`after-replace.json`（同口径重跑，工作区产物，可用 `tools/snapshot_results.py` 重新生成）

## 1. 替换清单

| 项 | 替换前（Stage 0 自研） | 替换后（Stage 1 专业库） | 版本 |
|---|---|---|---|
| 点在多边形（内部） | 射线法奇偶判定 | Shapely `Polygon.contains` | shapely 2.2.0 |
| 点在多边形（含边界） | 先判边界（1e-12 容差）再射线法 | Shapely `Polygon.covers` | shapely 2.2.0 |
| 边界判定 | 点到线段距离 + 1e-12 绝对容差 | `covers(p) ∧ ¬contains(p)`（精确谓词） | shapely 2.2.0 |
| 距离 | haversine 球近似（R=6371008.8） | `pyproj.Geod(ellps="WGS84").inv` 测地距离 | pyproj 3.8.0 |
| YAML 解析 | 自研极简解析器（不支持锚点/多行/深层嵌套） | PyYAML `safe_load` + 序列键空值归一 | PyYAML 6.0.3 |

依赖缺失时 `stage0_gate.py` **启动即失败**并给出安装命令（不再静默回退到另一套实现）。

## 2. 替换前的对拍证据（不是"改完再比对"）

`tools/verify_env.py` 第 5 节对 `examples/*` 全部 **12 个 YAML** 逐文件做
「PyYAML vs 自研解析器」对拍：**12/12 完全一致**。因此 YAML 替换不存在结构差异风险。

## 3. 逐项比对结果（六包 + 边界矩阵 12 点 + 距离 3 组）

```
python -X utf8 tools/compare_snapshots.py \
    acceptance/stage-1/baseline-frozen.json work/stage1/after-replace.json
```

**六包全部规则结果与条款覆盖：零差异**（`aggregate` 仍为 PASS/FAIL/PASS/INDETERMINATE/FAIL/FAIL，
findings 集合、config_rejections、risk_signals 全部一致）。

差异共 **7 处，全部在几何层**，逐条依据如下：

### 3.1 距离（3 处，数学依据：椭球 vs 球近似）

| 点对 | 替换前 haversine | 替换后 测地(pyproj) | 相对差 |
|---|---|---|---|
| (116.3912,39.9075)→(116.3975,39.9087) | 553.676964 m | 554.934580 m | 0.2271% |
| (116.0,39.0)→(117.0,40.0) | 140447.461861 m | 140442.947740 m | 0.0032% |
| (0.0,0.0)→(0.0,1.0) | 111195.080234 m | 110574.388558 m | 0.5582% |

依据：WGS84 椭球（长半轴 6378137 m、扁率 1/298.257）上的大地线，与半径 6371008.8 m 的球面近似
必然不同；pyproj 用 Karney 算法求解，是测绘口径的正确值。**采纳新值**。
业务影响：R10 重复候选的 `max_distance_m` 阈值附近可能翻转，本轮六包无翻转（findings 一致）。

### 3.2 边界扰动点（4 处，数学+业务依据：取消人为容差）

| 点 | 替换前 | 替换后 | 依据 |
|---|---|---|---|
| 内侧 1e-13 | `on_boundary=True`、`exclusive=False` | `on_boundary=False`、`exclusive=True` | 该点在多边形**内部**（距边 1e-13 度 ≈ 1e-8 m），精确谓词判内部；旧实现按 1e-12 容差误判为边界 |
| 外侧 1e-13 | `on_boundary=True`、`inclusive=True` | `on_boundary=False`、`inclusive=False` | 该点在多边形**外部**；旧实现把外部点纳入 inclusive 范围，属**错误放行倾向**，必须修正 |

依据：1e-12 度约合 1.1e-7 m，远大于坐标的有效精度（double 在 116 度附近的 ULP 约 3e-14 度 ≈ 3 nm），
是人为放宽而非数值必需。Shapely 使用鲁棒方向判定（exact predicate），
在 1e-13 度尺度上仍可精确判别内外。**采纳新值**（更严格，且消除了"外侧点被算作内部"的放行风险）。

### 3.3 未变化但要留档的点

- 四边中点 / 顶点 / 内点 / 外点的 `inclusive`、`exclusive`：替换前后一致（契约 §8.1 语义保持）。
- 实现过程中发现并纠正的坑：`boundary.touches(p)` 对**线段内部**的点返回 False
  （Shapely 的 `touches` 要求公共点只落在两者边界上），若直接用作边界谓词会让四边中点全部判 False。
  最终采用 `covers(p) ∧ ¬contains(p)`。

## 4. 重跑的回归范围

| 套件 | 结果 |
|---|---|
| `tools/stage0_gate.py`（六包记录级比对） | `ALL_OK=true`，退出 0，逐包结论与冻结基线一致 |
| `tools/recheck_probes.py` | `RECHECK_PROBES_OK=true`，24/24（含 GA-08 边界对称、GA-07 候选统计） |
| 原独立探针对拍（五 P1） | 全部不再产出 PASS |
| `tools/selfcheck_guards.py` | `GUARDS_OK=true` |
| `tools/check_schema_consistency.py` | `SCHEMA_CONSISTENT=true` |

命令（均在项目虚拟环境内）：

```bash
./.venv/Scripts/python.exe -X utf8 tools/stage0_gate.py
./.venv/Scripts/python.exe -X utf8 tools/snapshot_results.py --out work/stage1/after-replace.json
./.venv/Scripts/python.exe -X utf8 tools/compare_snapshots.py \
    acceptance/stage-1/baseline-frozen.json work/stage1/after-replace.json
./.venv/Scripts/python.exe -X utf8 tools/recheck_probes.py \
    --probes-script <原独立探针 stage0_independent_probes.py>
```

## 5. 未解决 / 遗留

- 带孔、MultiPolygon、非闭合环仍 `NOT_IMPLEMENTED`（Shapely 能算，但契约要求**不静默按另一政策执行**，
  需 Stage 1 后续按 ADR 走批准流程后再放开）。
- geopandas 仅做运行验证，尚未接入判定链路。
- Docker 冒烟仍未做（见 `ENV.md` §5）。
