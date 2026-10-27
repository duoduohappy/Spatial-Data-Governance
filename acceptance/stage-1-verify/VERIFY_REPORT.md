# GeoAcceptance Stage 1（第一批）独立验收

日期：2026-10-26　｜　本轮验收对象：`e4e849a`

## 0. 结论

**有条件通过**：Stage 1 第一批六项工作完成度可验证，未发现阻断级（P1）缺陷。

通过范围＝**已实现的语义原型 + 本轮 13 项独立探针 + 28 项回归 + 六组示例包的冻结比对**，
**不代表**生产系统、AI 链路、模型能力或完整项目验收通过。

### 独立性声明（必须读）

本轮验收与实现在**同一会话**内完成，**独立性弱于上一轮外部验收**。为压低自证偏差，做了四件事：

1. 在**仓库外**做干净克隆（`git clone` + 检出固定 commit），不在原工作树上跑；
2. **全新虚拟环境**安装（不是复用实现时那个 `.venv`），并额外用 **Python 3.11.9** 交叉验证；
3. 预期值全部来自**独立参考**（精确有理数算术、解析公式、手写结构），不取自被测实现；
4. 复用上一轮**外部探针脚本**做交叉对拍（见 §5.5）。

仍建议由外部方复审 commit 与 `raw/` 下的原始输出。**不得**把本轮结论当作"外部独立验收已通过"。

## 1. 验收对象与固定 commit

| 项 | 值 |
|---|---|
| 仓库 | `C:/Users/TempAdmin/WorkBuddy/2026-10-26-13-17-35/geoacceptance` |
| 本轮验收 commit | **`e4e849a`** |
| 提交链 | `31d43a8`（标签 `stage0-frozen`）→ `5a4b5ca` → `5e0654d` → `3b8d7ba` → `3738b93` → `6c30e5b` → `cca01c8` → `af1381a` → `2239547` → **`e4e849a`（验收对象）** → `e7a2daa`（本报告与原始输出归档，**仅文档，不含代码改动**） |
| 复验方式 | 干净克隆到 `C:\Users\TempAdmin\AppData\Local\Temp\ga-final`，检出 `e4e849a`，全程不改原仓库 |

## 2. 干净环境安装记录与版本（交付要求：可执行命令 + 真实输出）

| # | 命令 | 结果 | 证据 |
|---|---|---|---|
| 1 | `python -m venv .venv313 && ./.venv313/Scripts/python.exe -m pip install -r requirements.lock.txt` | **rc=0**，22 个包全部按锁定版本装上（Python 3.13.14 / pip 26.1.2） | `raw/09-install-py313-lock.txt` |
| 2 | `py -3.11 -m venv .venv311 && ./.venv311/Scripts/python.exe -m pip install -r requirements.lock.txt` | **rc=1**：`ERROR: No matching distribution found for numpy==2.5.4`（3.11 无该 wheel） | `raw/10-install-py311-lock-failed.txt` |
| 3 | `py -3.11 -m venv .venv311b && pip install shapely pyproj PyYAML pydantic jsonschema`（不锁版本） | **rc=0**，随后门禁 `ALL_OK=true`、回归 `28/28` | `raw/11-install-py311-unpinned.txt`、`raw/12-gate-py311.txt`、`raw/13-recheck-probes-py311.txt` |

运行版本（真实 import 取得的 `__version__`，非文件扫描）：

| 库 | Python 3.13.14（锁定） | Python 3.11.9（不锁定） |
|---|---|---|
| shapely | 2.2.0 | 2.2.0 |
| pyproj | 3.8.0 | 3.7.2 |
| PyYAML | 6.0.3 | 6.0.3 |
| pydantic | 2.14.1 | 2.14.1 |
| jsonschema | 4.26.0 | 4.26.0 |
| geopandas / pandas / numpy | 1.2.0 / 3.1.0 / 2.5.4 | 未装（本轮 3.11 只装核心五件） |

**结论**：代码本身不依赖精确小版本（3.11 + pyproj 3.7.2 同样全绿）；
但**锁定文件无法在 3.11 上复现**，且 `requirements.txt` / `ENV.md` 均未声明 Python 下限 ⇒ 登记 **S1-07**（见 §6）。

## 3. 逐条对照《最终复验报告：Stage 1 的进入条件与顺序》

| # | 要求 | 实测 | 判定 |
|---|---|---|---|
| 1 | 固定通过版本、保留回归基线与两轮验收历史 | `stage0-frozen` 标签 + `baseline-frozen.json` + `acceptance/stage-0-recheck/` 归档 | 通过 |
| 2 | 第一批＝.venv、依赖锁定、库安装与运行验证；记录实际解释器与库版本 | `ENV.md` + `raw/09~13`；解释器 3.13.14 与 3.11.9 均记录 | 通过（附 S1-07） |
| 3 | Docker 冒烟；不可用则记录环境原因与替代复现方法 | **未做**：本机无 docker、无 Docker Desktop，`wsl.exe` 被安全策略阻止；替代方法＝本报告的全新 venv + 双解释器复现 | **未做（如实登记，不写成通过）** |
| 4 | 用专业库替换射线法/球面近似/极简 YAML，逐项比较且差异有依据 | Shapely / pyproj / PyYAML 已替换；冻结快照比对：判定层**零差异**，几何层 7 处差异全部给依据（见 §4 P12） | 通过 |
| 5 | 执行入口用标准 Schema/Pydantic 校验；收敛旧二参兼容路径；测试迁到唯一接口 | 入口 strict 校验生效（P04），二参路径已删且调用抛 `TypeError`（P05） | 通过 |
| 6 | 最小模块内核与 CLI，再补 compare、报告、输入防护 | CLI 四子命令实测；跨 cwd 可跑、路径穿越被拒（P06）、HTML 转义（P07） | 通过 |
| 7 | 补 `NO_IMPLEMENTATION` / `UNAPPROVED` / 缺证据等未覆盖分支 | 28 项回归含这三类分支，且均无正例洗白 | 通过 |
| 8 | compare 身份不靠行号；缺标识/规则版本不同 ⇒ `not_comparable` | 乱序后 counts 完全一致；重复 ID ⇒ `not_comparable` + `INDETERMINATE`（P08） | 通过 |

## 4. 独立探针（13 项，全新编写，不复用 `tools/recheck_probes.py`）

脚本：`acceptance/stage-1-verify/stage1_independent_probes.py`
结果：`acceptance/stage-1-verify/stage1-independent-results.json`
原始输出：`raw/08-stage1-independent-probes.txt`
**总计：13/13 通过（`STAGE1_PROBES_OK=true`）**

| ID | 依据（预期从哪来） | 输入 | 关键实测 | 判定 |
|---|---|---|---|---|
| P01 | 多边形边界定义 + **精确有理数算术**（叉积=0 且落包围盒＝在边界；射线法精确比较） | 单位正方形 13 点 + 凹多边形（L 形）10 点，含顶点、边中点、凹顶点、±1e-13 内外扰动 | 23 点**零不一致**；`边界外侧1e-13` 判为外部（旧 1e-12 容差会误纳 ⇒ 替换是纠正，不是回归） | PASS |
| P02 | 赤道弧长＝`a·Δλ`（解析）；子午线弧长＝`∫M(φ)dφ`（Simpson 独立积分） | (0,0)→(1,0)、(0,0)→(0,1) + 冻结三对点 | 赤道 111319.490793 m，相对误差 **1.3e-16**；子午线 110574.388558 m，相对误差 **7.1e-15**；与 haversine 相对差 0.2271% / 0.0032% / 0.5582% | PASS |
| P03 | YAML 1.1 语义：锚点、合并键、块标量、引号保留字符串；空值归一（GA-09） | 自造 tricky.yaml + 多文档 multi.yaml | 解析结果 == 手写期望；多文档抛 `ComposerError`（**未**静默取首文档） | PASS |
| P04 | 零隐式收敛：strict 拒 `"yes"`→bool；枚举越界必拒；lax 会收敛（反向确认） | clean 包两变体：`required_for_release:"yes"` / `support_status:"MAYBE"` | 均登记 `INPUT_SCHEMA_INVALID` 且总体 `INDETERMINATE`；lax 反向确认 `"yes"`→`True` | PASS |
| P05 | 接口唯一性 | `inspect.signature` / `hasattr` / 二参调用 | 签名 `(clause_coverage, config_rejections, n_rows=None)`；`_coverage_from_results` 不存在；二参调用抛 `TypeError` | PASS |
| P06 | CLI 应以绝对 ROOT 定位；越界/不存在必失败关闭 | 仓库外目录跑 `run clean` / `run ../clean` / `run no_such_bundle` | 正常包 rc=0（且 `ALL_OK=true`）；穿越与不存在均 rc=2 并打印 `[ERR] 输入不合规：…` | PASS |
| P07 | 报告来自外部文件，渲染必须转义（S0-09） | 注入 `<script>alert("x")</script> & 'q' "d"` | 输出无未转义 `<script`，含 `&lt;script&gt;` 与 `&amp;` | PASS |
| P08 | 身份按 `record_id`，不按行号 | defective→corrected；整改后批次**行序打乱**；再复制一行造重复 ID | 打乱前后均为 `fixed=8 / not_comparable=1 / INDETERMINATE`（**完全一致** ⇒ 与行序无关）；重复 ID ⇒ 2 条 `not_comparable`，总体 `INDETERMINATE` | PASS |
| P09 | 运行局部状态须在 `run()` 复位（RC-04） | defective 包同实例两次 + 新实例一次 | 三者 `stable_key` 排序完全相同 | PASS |
| P10 | 依赖缺失若静默回退＝拿近似结果冒充权威结果 | PYTHONPATH 注入 `shapely.py`/`pyproj.py`/`yaml.py`，import 即抛 `ImportError` | 三者均 rc=1、输出含 `pip install -r requirements.txt`、无 `ALL_OK=true` | PASS |
| P11 | 脚本不得依赖调用方设 `PYTHONUTF8`（最终复验 A 项） | 不设环境变量、stdout 重定向到管道跑回归套件 | **修复后** rc=0、`28/28`；修复前 rc=1 且中途 `UnicodeEncodeError` | PASS（修复见 §5.1） |
| P12 | 替换后逐项比较，差异须有依据 | `baseline-frozen.json` vs 新生成快照，自实现比对 | 六包规则/条款/总体/findings **零差异**；边界差异＝2 个扰动点（4 个字段翻转）；距离差异＝3 组（椭球 vs 球，0.003%~0.56%） | PASS |
| P13 | 材料之间不得互相矛盾（最终复验 B 项同源） | README / OPEN_ISSUES / `TOOL_VERSION` | 五项一致性检查全部无矛盾（修复后） | PASS（修复见 §5.4） |

## 5. 本轮发现并已修的缺陷（5 项，含修复前后证据）

| ID | 级别 | 问题 | 修复 | 证据 |
|---|---|---|---|---|
| S1-A1 | **P2** | 不设 `PYTHONUTF8` 且 stdout 重定向（GBK）时，`recheck_probes.py` 打印含 `⇒` 的用例说明处抛 `UnicodeEncodeError`，**rc=1 且结果 JSON 未写出** ⇒ 证据链断在中途 | `tools/*.py` 与 `geoacceptance/cli.py` 入口统一 `stdout/stderr.reconfigure(encoding="utf-8", errors="strict")` | 修复前 `raw/`（见 §6 记录）／修复后 `raw/03-recheck-probes.txt` rc=0、28/28 |
| S1-A2 | P3 | pyproj 缺失只提示"请安装 requirements.txt"，没给可执行命令（与 shapely / PyYAML 不一致） | 统一给出 `python -m venv .venv && ... pip install -r requirements.txt` | P10 三项 `mentions_install_cmd=true` |
| S1-A3 | P3 | 外部探针交叉对拍：wrapper 只认 `independent-results.json`，而外部脚本输出 `new-independent-results.json` ⇒ 实际跑了却被记 `ran=false`，只剩 stdout 尾 400 字符 | 改为**按内容识别**结果文件，并新增 RC-01/RC-02 签名用例断言 | 现记录 `ran=true`、两签名用例均 `INDETERMINATE`、`all_ok=true` |
| S1-A4 | P3 | 文档与实现矛盾：README「零第三方依赖」「五个示例包」「版本号 0.1.0」；`TOOL_VERSION` 仍标 `(stdlib)`；S0 OPEN_ISSUES / architecture §2 旧口径 | README 改写现状段与版本号 0.2.0；`TOOL_VERSION` 去 `(stdlib)`；归档材料加 Stage 1 注释 | P13 复验无矛盾 |
| S1-A5 | P3 | CLI 冒烟探针依赖上一次运行残留在 `work/` 的 `defective/report.json` ⇒ 干净克隆首次跑误报 `S1_cli_smoke` 失败（27/28）；CLI 输入不合规时直接甩栈 | 探针改用当场产出的 `clean/report.json`；CLI 捕获 `InputGuardError` 打一行错误并返回 2 | 干净克隆 28/28；`[ERR] 输入不合规：…` rc=2 |

> 上述修复落在 `af1381a`、`2239547`、`e4e849a` 三个提交；判定语义未改动，冻结快照的判定层仍为零差异。

## 6. 未解决 / 新登记问题（不写成已通过）

| ID | 级别 | 问题 | 现状 |
|---|---|---|---|
| S1-01 | P2 | Docker 冒烟 | **未做**。本机无 docker、无 Docker Desktop，`wsl.exe` 被安全策略阻止。替代复现：全新 venv + 双解释器（本报告 §2、§3） |
| S1-02 | P3 | 外部独立探针仍用已删除的二参接口 | 本轮已能按内容识别其结果文件并完成 RC-01/RC-02 对拍；**迁移仍待外部方改脚本**（仓库侧不得为兼容保留第二判定路径） |
| S1-03 | P3 | `compare` 只比 **FAIL 类** finding | 候选/缺证据类未进整改台账，语义已写在 `geoacceptance/compare.py` docstring |
| S1-04 | P3 | CLI 只支持 `examples/` 下的包名 | 未支持任意路径输入（当前由 `safe_bundle_path` 强制约束） |
| S1-05 | P3 | compare 产物无 Schema | 只有 `schema_version: stage1-compare-1`，未落 JSON Schema 文件 |
| S1-06 | P3 | geopandas 未进入判定链路 | 本批只做运行验证（`verify_env.py` 真读 GeoJSON），矢量 IO 尚未替换自研读取 |
| **S1-07** | **P3（新）** | `requirements.lock.txt` 未声明 Python 下限；在 Python 3.11 上不可安装（`numpy==2.5.4` 无 3.11 wheel） | 实测记录见 §2 第 2 行；建议在 `requirements.txt` / `ENV.md` 写明 `python >= 3.13`（或提供 3.11 分支锁定） |

## 7. 交付物与可执行命令

固定 commit：**`e4e849a`**

```bash
git clone <repo> ga && cd ga && git checkout e4e849a
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt    # 精确锁定 requirements.lock.txt（需 Python ≥3.13）
./.venv/Scripts/python.exe tools/make_examples.py                # 六组示例包（确定性，重跑无 diff）
./.venv/Scripts/python.exe tools/stage0_gate.py                  # 六包门禁 → ALL_OK=true
./.venv/Scripts/python.exe tools/recheck_probes.py \
    --probes-script <外部 stage0_recheck_independent_probes.py>   # 28/28 + 外部探针交叉对拍
./.venv/Scripts/python.exe tools/selfcheck_guards.py             # GUARDS_OK=true
./.venv/Scripts/python.exe tools/check_schema_consistency.py     # SCHEMA_CONSISTENT=true
./.venv/Scripts/python.exe tools/verify_env.py                   # ENV_VERIFY_OK=true
./.venv/Scripts/python.exe -m geoacceptance.cli run --html       # CLI：门禁 + HTML 报告
./.venv/Scripts/python.exe -m geoacceptance.cli compare --before defective --after corrected
./.venv/Scripts/python.exe acceptance/stage-1-verify/stage1_independent_probes.py . --out r.json
```

产物索引：

| 路径 | 内容 |
|---|---|
| `acceptance/stage-1-verify/VERIFY_REPORT.md` | 本报告 |
| `acceptance/stage-1-verify/stage1_independent_probes.py` | 独立探针（13 项） |
| `acceptance/stage-1-verify/stage1-independent-results.json` | 探针结构化结果 |
| `acceptance/stage-1-verify/raw/01~13*.txt` | 各项真实原始输出（门禁、回归、护栏、环境、CLI、双解释器、三次安装） |
| `acceptance/stage-1/` | Stage 1 第一批进度材料（ENV / GEOMETRY_REPLACE / INPUT_AND_API / KERNEL_CLI_REPORT_COMPARE / 冻结基线） |
| `acceptance/stage-0-recheck/` | Stage 0 两轮外部验收与修复历史（§0 为当前状态，其余归档） |

## 8. 六包门禁实测（干净克隆，`raw/02-gate.txt`）

| 包 | 总体结论 | findings |
|---|---|---|
| clean | PASS | 1 |
| defective | FAIL | 11 |
| corrected | PASS | 1 |
| ambiguous | INDETERMINATE | 1 |
| blocked | FAIL | 1 |
| crs_same_unit_wrong | FAIL | 1 |

`ALL_OK=true`（"通过"指**与登记期望一致**，不是"数据没问题"；三个 FAIL 包本就应当 FAIL）。
