# Stage 1 第一批：项目虚拟环境、依赖锁定与空间库运行验证

- 日期：2026-10-26
- 对应最终复验报告《Stage 1 的进入条件与顺序》第 1–3 条
- 冻结基线：Stage 0 提交 `31d43a8`（标签 `stage0-frozen`）

---

## 1. 虚拟环境与解释器

```bash
python -m venv .venv                       # 由 3.13.14 建立，不污染全局环境
./.venv/Scripts/python.exe -V              # Python 3.13.14
./.venv/Scripts/python.exe -m pip --version # pip 26.1.2
```

- 解释器路径：`C:\Users\TempAdmin\WorkBuddy\2026-10-26-13-17-35\geoacceptance\.venv\Scripts\python.exe`
- 版本：Python **3.13.14**；平台：Windows（`platform.platform()` 见 `env-verify.txt`）
- `.venv/` 已在 `.gitignore` 中，不随仓库分发；复现靠 `requirements.txt` + `requirements.lock.txt`

## 2. 安装命令与真实输出

```bash
./.venv/Scripts/python.exe -m pip install "shapely>=2.0" "pyproj>=3.6" "pyyaml>=6.0" \
                                          "pydantic>=2.7" "jsonschema>=4.22"
./.venv/Scripts/python.exe -m pip install "geopandas>=1.0"
./.venv/Scripts/python.exe -m pip freeze > requirements.lock.txt
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # 复现用（已缓存）
./.venv/Scripts/python.exe -m pip check                          # No broken requirements found.
```

原始输出：`pip-install.txt`（末段 + `pip check`）。首次安装为真实下载安装，耗时约 7 分钟。

## 3. 依赖与运行版本（`tools/verify_env.py` 真实 import，非文件扫描）

| 库 | 版本 | Stage 1 用途 |
|---|---|---|
| shapely | **2.2.0** | 替换自研射线法（点在多边形内 / 边界判定） |
| pyproj | **3.8.0** | 替换自研 haversine 球面近似（WGS84 测地距离） |
| PyYAML | **6.0.3** | 替换自研极简 YAML 解析器 |
| pydantic | **2.14.1** | 执行入口结构化校验（**strict** 模式，禁止隐式类型收敛） |
| jsonschema | **4.26.0** | 标准 Schema 校验，替代自研子集校验器 |
| geopandas | **1.2.0** | 矢量 IO（本批仅运行验证，未进入判定链路） |
| pandas | 3.1.0 | geopandas 依赖 |
| numpy | 2.5.4 | shapely / pandas 依赖 |

完整输出见 `env-verify.txt`。

## 4. 运行验证要点（真的跑过，不是只报存在性）

1. **Shapely**（单位正方形，四种点位）：`contains` = 严格内部；`touches` = 边界（含顶点）；
   `covers` = 内部 ∪ 边界。
   ⇒ 与 Stage 0 口径的映射：`inclusive=True ⇔ covers`、`inclusive=False ⇔ contains`，
   Stage 0 的 `point_on_ring_boundary`（1e-12 绝对容差）由 Shapely 的精确谓词取代。
2. **pyproj 测地距离 vs Stage 0 haversine**（三组点对，相对差）：
   - 554.935 m vs 553.676 m（0.23%）
   - 140442.948 m vs 140447.268 m（0.003%）
   - 110574.389 m vs 111194.927 m（0.56%）
   ⇒ 椭球 vs 球近似，差异**有数学依据**（WGS84 椭球 vs R=6371000 球）；
   替换后阈值判定结果可能变化，逐条差异必须给依据（见后续 `GEOMETRY_REPLACE.md`）。
3. **GeoPandas**：读入 `examples/clean/area.geojson`（Polygon，bounds 116.3/39.9–116.32/39.92），
   质心 `contains=True`、`boundary.touches=False`。
4. **PyYAML vs 自研解析器**：对 `examples/*` 全部 12 个 YAML 逐文件对拍，**全部一致**（替换无结构风险）。
5. **Pydantic**：lax 会把 `"yes"` 收敛成 `True` ⇒ **执行入口必须用 strict 模式**（已实测拦下）。
6. **jsonschema**：标准 Draft 校验可用。

## 5. Docker 冒烟：**未做**（如实记录）

- 事实：`docker` 不在 PATH；`C:\Program Files\Docker\Docker\resources\bin\docker.exe` 不存在（未安装 Docker Desktop）。
- 替代尝试受阻：本机 `wsl.exe` 被安全策略（程序黑名单）阻止，无法用 WSL 后端作为替代。
- **不把未做写成已通过**。当前可复现的方法是：本目录的 `requirements.txt` + `requirements.lock.txt`
  + 上面的解释器/库版本 + `tools/verify_env.py` 在任意 Python 3.13 环境重跑。
- Stage 1 后续在有 Docker 的机器上补：`docker build` + `docker run`（记录镜像 digest 与运行输出）；
  在此之前任何材料不得声称容器化已完成。

## 6. 未解决的问题

| 项 | 状态 |
|---|---|
| Docker 冒烟 | 未做（原因见 §5） |
| geopandas 仅做运行验证 | 未进入判定链路，Stage 1 后续接入矢量 IO 时需再验证 |
| 依赖安装耗时/网络 | 首次约 7 分钟；离线环境需预先缓存 wheel |
