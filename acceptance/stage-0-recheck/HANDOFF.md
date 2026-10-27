# Stage 0 重验包：交接说明（HANDOFF）

- 日期：2026-10-26
- 编制：严过关（QA，Stage 0 重验 T05）
- 上一轮结论：独立验收《GeoAcceptance Stage 0 独立验收报告》判定 **不通过**
- 本轮结论：五个 P1 与五个 P2 **已修复并有可运行回归用例**；原验收包的「P1 = 0」已撤回
  （见 `../stage-0/RETRACTED.md`）
- 契约唯一来源：`docs/stage0-recheck-contract.md`（本轮未修改其结论）
- 零第三方依赖：全部实现只用 Python 3 标准库（核验命令见第 6 节）

## 0. 冻结与最新状态（2026-10-26 最终独立复验后，**以本节为准**）

- 独立验收方《GeoAcceptance Stage 0 最终针对性复验》结论：**Stage 0 有条件通过，允许进入 Stage 1**。
  通过范围＝**已实现的语义原型与本轮回归**，不代表生产系统、AI 链路或完整项目验收通过。
- **冻结提交**：`31d43a8`（标签 `stage0-frozen`）。冻结后 Stage 0 语义不再改动；Stage 1 替换自研几何
  与 YAML 实现时，必须以本轮的**六包 + 边界用例 + 反例**为回归基线，差异须给数学或业务依据。
- **P1 状态（当前）**：P0 = 0、P1 = 0 —— 三轮独立验收发现的 P1 均已关闭并有可运行回归。
  历史表述（原验收包「P1=0」被撤回、以及"独立复验确认前不重立 P1=0"）均为**归档状态**，
  见 `../stage-0/RETRACTED.md` 与本文件 §8 末尾；不再作为现状说明。
- **覆盖缺口（当前）**：二次验收轮后 `CONFIG_REJECTED` / `MISSING_RESULT` 已有探针级正例；
  `NO_IMPLEMENTATION` / `UNAPPROVED` 与「缺证据类 finding」仍无正例 → 列入 Stage 1 第一批补齐。
  §6 中"六态中四态无正例"是 **Stage 0 冻结时的状态**，已归档。
- 本文件其余各节记录 Stage 0 重验轮的过程与结论，**不随 Stage 1 改写**（历史归档）。

## 本包六项内容

| # | 内容 | 文件 |
|---|---|---|
| 1 | HANDOFF（本文件，含偏差项） | `HANDOFF.md` |
| 2 | 实际执行的命令与结果 | `COMMANDS.md` |
| 3 | 开放问题（含本轮新发现） | `OPEN_ISSUES.md` |
| 4 | 修复提交 SHA | 本文件第 4 节 |
| 5 | 独立反例逐项结果（含修复前后对照 + 对拍） | `independent-results.json`、`baseline-independent-results.json` |
| 6 | Schema 一致性结果 / 目标依赖冒烟 | `schema-consistency.txt`、`DEPS_SMOKE.md`、`deps-smoke.txt` |

---

## 1. 这一轮改了什么（一句话版）

把「能判 FAIL 的证据」这件事做成机器可校验的结构，并把「缺证据」从 FAIL 里彻底分离出来：

- **缺证据一律 INDETERMINATE**（契约公理 A2），不再用"看起来不对"代替证据；
- **信号一律不参与判定**（公理 A3）：坐标量级、模型自报置信度只能落成 risk signal；
- **未实现/被拒绝一律显形**：`REJECTED` / `NOT_IMPLEMENTED` / `INDETERMINATE`，禁止静默降级；
- **比对升级到记录级**：命中错行但数量相同不再算一致。

逐条见 `../stage-0/RETRACTED.md` 第 2 节（5 个 P1 + 5 个 P2 + 验收方六条意见的处理）。

---

## 2. 偏差项（本轮相对原始方案**新增/变更**的东西，逐项列出）

验收方点名要求写清偏差，以下五项均为主理人/架构师已裁决的增项，不是实现者自行加戏：

| # | 偏差 | 理由 | 影响面 |
|---|---|---|---|
| **D1** | 新增示例包 `examples/crs_same_unit_wrong/` | 契约 §4.5 明确要求：证明「单位相同救不回错误声明」——数据内容与 clean **完全相同**，仅 `crs.json` 声明改为 `EPSG:4490`/`degree`。若某个实现让本包 PASS，说明它退化成了"只看单位"或"按量级猜 CRS" | 门禁包数 **5 → 6** |
| **D2** | 该包为**手写反例包**，不参与 `make_examples.py` 生成 | 生成脚本会同时重写数据与期望，"重生成全绿"不构成真值证明；手写包的 expected 是**先手写再跑实现** | 只在 `INPUT_MANIFEST.json` 登记哈希 |
| **D3** | 新增中间产物 `work/stage0/<bundle>/expected_diff.json` | 记录级差异底稿（含每条规则的 10 个字段全量实际值），供 QA 逐条登记 expected，不是对外证据 | 6 个文件，`work/` 下 |
| **D4** | `expected/` 新增两个文件：`findings.json`、`clause_coverage.json` | 验收方「自检证据的限制」第 2 条：只比数量不足以证明命中的是**正确的那一条** | 已登记进 `INPUT_MANIFEST.json`，真值文件本身也被哈希冻结 |
| **D5** | `TIMEZONE_UNDECLARED` 由 FAIL 类原因码移到「缺证据」类 | `docs/rule-semantics.md` R09 写「按未定处理」，与契约公理 A2 一致，与实现不一致。**主理人裁决**（2026-10-26） | 一行代码；对六包零影响（该分支在严格 RFC3339 子集下不可达，已验证） |

**未发生的偏差**（防止误读）：六个包的总体结论与缺陷数**完全没变**
（PASS / FAIL / PASS / INDETERMINATE / FAIL / FAIL，1 / 11 / 1 / 1 / 1 / 1）；
交付数据一行未改；`docs/stage0-recheck-contract.md` 的契约结论未改。

---

## 3. 真值是怎么定的（不是"重跑一遍全绿"）

1. **先手写期望，再跑实现**：每个数字都能回溯到具体数据行号与条款行
   （如 defective 的 11 条缺陷对应 `poi.csv` 第 3/4/6/7/8/10/11/12/13/14/15 行）。
2. **独立交叉验证**：用一次性脚本直接读 `poi.csv` 重算空值/重复 ID/枚举越界/数值不可解析/
   经纬度越界/时间格式/超时阈值，得到的事实集合与门禁输出逐条一致——这只是**核对**，不是真值来源。
3. **逐条登记**：`examples/TRUTH_REVIEW.md` §3 是本轮 expected 改动的**唯一授权来源**，共 8 类
   （前 6 类 + §3.9 的 24 条 `reason_code` 全链路取值 + §3.10 的 18 处 `failure_reason_codes`）；
   **表外无改动**。可用 `git diff --numstat examples/*/expected/` + 登记表逐条核对。
   §3.9/§3.10 的每一条都标注了「是否放松结论」，结论均为**否**（只换字段值，不换判定语义）。
4. **重生成只用于重建输入包**：`make_examples.py` 的真值字典已同步到记录级，
   重跑后 `git diff` 只出现已登记的那些行（实测：5 个包 `requirements.yaml` 各 +1 行、6 个
   `aggregate.json` 结构升级、`INPUT_MANIFEST.json` 重算）。

---

## 4. 修复提交 SHA（分支 `main`，含 d057c0a 之后的全部修复提交）

| 顺序 | SHA | 说明 |
|---|---|---|
| 原始 Stage 0（修复前基准） | `d057c0ad2b910e339105ac1c5ee46f18663b007c` | 「docs: record stage-0 commit hash in acceptance package」；本轮修复前基准就是用这份工作树重跑原探针得到的 |
| 1 | `a9497bc30f0cffa789fb974a3aa4c4e504737de8` | fix(GA-05,GA-09)：引入 ParameterSource 与标准库 Schema 一致性校验 |
| 2 | `24ed8108e550838e5be4e3defaa749b9d8c89f71` | fix(GA-06,GA-07,GA-08)：统一三态词汇、统计口径与边界政策 |
| 3 | `8a3d2708b42f3673279b35424dc6a458f2e13a29` | fix(GA-01,GA-02,GA-04)：条款级覆盖聚合、条款授权派生与依赖图状态传播 |
| 4 | `65259dc9fc701fa56cf127d2076f4b2b9c1c618f` | fix(GA-03)：CRS 四类判定分离，blocked 真值改为可证明的声明冲突 |
| 5 | `65e773ddcb229d64e8ac936a24d2afc7886417c2` | fix(recheck)：compare_expected 升级记录级、risk signal 注册表、原因码强制三分类 |
| 6 | `f4c289d62193dd620d62dd34334a20b84d3fec1c` | T05-a：expected 真值同步到记录级 + `examples/TRUTH_REVIEW.md` + A3 interpretation + TEST_RESULTS 作废标注 |
| 7 | `05503a38b1375abda9618acbc8ee90bf2efcab00` | T05-b：护栏七项真负面 + `TIMEZONE_UNDECLARED` 归位 + `tools/recheck_probes.py` 回归套件 + 本验收包 |
| 8 | `0a458e2e8b2c461829507b1ad797fbb6e015c16e` | T05-c：回填 T05 两次提交（f4c289d、05503a3）的 SHA 到 HANDOFF 第 4 节 |
| 9 | `4c5b6f283cabdea0529b4ce2e204279da6b00a36` | docs(arch)：契约统一设计与任务分解入库、ADR-006 降级、ADR-010 增补 §3.2 勘误与覆盖缺口 |
| 10 | `c16397fc8a6a25fd9328b261c3874f9f282fdeaa` | docs(arch)：明确 reason_code 取值链——第一条定义、附带字段去重、候选类与 CONTRACT_VIOLATION 兜底 |
| 11 | `9af939bd8ecd5c010637a190a9fdd86f35b1523d` | fix(S0-R1,S0-R2)：条款级 reason_code 指向失败原因、缺证据类 finding 归入 uninterpretable |
| 12 | `2a22ff3b05c5e2c47b8710f058dec5cf6ab3da50` | chore(S0-R3)：`.gitattributes` 固定 LF，保障 INPUT_MANIFEST 哈希证据跨环境稳定 |
| 13 | `f4332862ad1388e01ee93f7b0a3be81e1cd3e58f` | fix(recheck)：规则级与条款级 reason_code 全面遵守 I7-I9，兼容条目与 clause_coverage 权威口径对齐 |
| 14 | `1fd2b21d1d1376adc90df625e7e2806b17b9aa3c` | fix(recheck)：reason_code 全链路遵守 I7-I9，去重与取值链按契约 §3.5.1/§3.5.2，新字段入 Schema |
| 15 | `dedc2f9ca2bbad8ef12ae6ec4ed990c7c6627a3c` | fix(recheck)：兼容路径接入 I7-I9 断言、FAIL 取值链源头去掉 OK 兜底 |
| 16 | `8048245b5d1111321076fb6e00ebd68598d47037` | docs(arch)：I7-I9 违反处置统一为 fail-closed 且不丢失结论 |
| 17 | `e2e9124b53029e12f28dbfba5bda110bfafa7ef2` | fix(recheck)：aggregate 兼容分支捕获契约违规，返回 INDETERMINATE 而非抛栈 |
| 18 | `da1d9460387cdd441bce34950ffc94d7206ffd75` | T05-d（最终回归）：expected 同步 reason_code 全链路取值（24 条）+ 两个新字段（18 处）+ 16 项判据终验 + 验收材料刷新 |
| 19 | `dd78876b6dc4e52dbcd824392d3aba0dbf3fd88c` | T05-f：判据 15 双路径（权威 + 兼容）与判据 17（兼容路径失败关闭）的独立复现 + git 历史改写如实登记 |
| 20 | `a4cd617f67af9acd7026c03beb81061eaec6c2a9` | T05-g：回填 T05-d/T05-f 提交 SHA 到 HANDOFF |
| 21 | `e567d4a5e160bd17dbbd4d448dff443f8db0bcbf` | fix（二次验收轮）：RC-01/RC-02 两条 P1 与 RC-03/RC-04 两条 P2 定向修复 + 4 项新回归（24/24）+ 契约 §2.4/§3.2 同步 |

分支 `main`；`570c1b7ae47ac3d5fd54b6a070c0b4fc1cbd889e` 为最早的 Stage 0 主体提交。

> 说明：第 6–8、18 项的 SHA 是在各自提交完成后回填的（提交时本表还不知道自己的 SHA），
> 因此 HANDOFF 的第 4 节会被后续提交更新。各提交的内容不变。

### 4.1 一处 git 历史改写（如实登记）

工程师在 amend `c83539c` 时**误吞了架构师的契约提交 `c582648`**，随后用软回退修复：

| 新 SHA | 等价于 | 内容 |
|---|---|---|
| `dedc2f9ca2bbad8ef12ae6ec4ed990c7c6627a3c` | 原 `c83539c` | 兼容路径接入 I7–I9 断言、FAIL 取值链源头去掉 OK 兜底 |
| `8048245b5d1111321076fb6e00ebd68598d47037` | 原 `c582648` | 契约：I7–I9 违反处置统一为 fail-closed 且不丢失结论 |

`c83539c` 与 `c582648` **已不存在于历史中**。工程师已用 `git diff` 验证两次树完全相同；
QA 独立复核了 `git show --stat` 与提交说明的对应关系。登记理由：本交付物的核心价值是可审计性，
历史里发生过改写而不留痕比事故本身更伤可信度。详见 `OPEN_ISSUES.md` §1.1b。


---

## 5. 怎么复验（给二次验收方的最短路径）

```bash
python tools/stage0_gate.py          # 六包记录级比对，退出码 0
python tools/check_schema_consistency.py   # 退出码 0
python tools/selfcheck_guards.py     # 7 项护栏（含 C2 真注入 live 负面），退出码 0
python tools/recheck_probes.py --probes-script <原独立探针路径>   # 20 项回归 + 对拍，退出码 0
git diff --numstat examples/*/expected/    # 逐条对 TRUTH_REVIEW.md §3 核对
```

预期结果、实际输出与逐项对照见 `COMMANDS.md`。

---

## 6. 能力边界（不得被解读为"已验证"）

- 本轮**没有**执行任何评测，没有任何指标数字，也没有提效数字。
- 本轮**没有**做目标空间依赖（geopandas/shapely/pyproj/pydantic/jsonschema/pandas/pytest）
  的安装与运行验证，**没有**做 Docker 冒烟 —— 这两项作为**阶段缺口**记录在 `DEPS_SMOKE.md`。
  Stage 1 计划用**项目 `.venv`** 锁定依赖，不污染全局环境。
- 参数来源护栏在 Stage 0 只做到「**字面可追溯**」，**未**做到「语义正确可证」
  （契约 §6.3，结论表述不得被拔高）。
- 边界判定为自研射线法 + 1e-12 绝对容差，仅支持单个简单 Polygon 外环；Stage 1 换 Shapely 后
  必须冻结本轮全部边界用例重跑对比（沿用 OPEN_ISSUES S0-03）。
- **`coverage_state` 六态中只有两态有正例**（`COVERED`、`UNMAPPED`）；
  `CONFIG_REJECTED` / `MISSING_RESULT` / `NO_IMPLEMENTATION` / `UNAPPROVED` **四态无正例覆盖**。
  本轮**未声称**覆盖模型已被完整验证（判据 13；详见 `OPEN_ISSUES.md` S0-R7）。
  > **归档注（2026-10-26 最终复验后）**：以上是 **Stage 0 冻结时**的状态。二次验收轮已为
  > `CONFIG_REJECTED`、`MISSING_RESULT` 补上探针级正例（RC-01/RC-02 探针）；
  > `NO_IMPLEMENTATION`、`UNAPPROVED` 仍无正例 → Stage 1 第一批补齐。当前状态以 §0 为准。
- **`advisory_reason_codes` 在六个示例包中全部为空数组**：六包没有任何「缺证据类」finding，
  §3.5.1 取值链中「缺证据类码」这一档**无正例**。本轮未为了让文件好看而编造假包
  （新增示例包属输入变更，超出 T05 授权）。详见 `OPEN_ISSUES.md` S0-R6。

---

## 7. 最终回归轮的 16 项判据终验（逐项）

| # | 判据 | 结果 | 证据 |
|---|---|---|---|
| 1 | 五个 P1 反例在 `recheck_probes.py` 逐项通过，且原独立探针对应项不再产出 PASS | ✅ | `independent-results.json`：GA01/GA03×2/GA04/GA05×2 全 PASS，对拍 7 项均不再 PASS |
| 2 | 全库无 `UNKNOWN` verdict；`check_result.schema.json` 枚举与实际产出一致 | ✅ | `grep -rn UNKNOWN examples/*/expected/` 空；`check_schema_consistency.py` 退出 0 |
| 3 | clean 包 R10 统计口径符合 §7.2 | ✅ | 探针 `GA07_candidate_counts`：total=12 / evaluated=12 / failed=0 / indeterminate=2 |
| 4 | `blocked` 结论仍 FAIL，finding evidence 不含量级理由 | ✅ | 探针 `NEW_crs_magnitude_only_signal`：R07=PASS 仅出 risk signal；blocked 包 `CRS_DECLARATION_MISMATCH` 的 evidence 是声明 vs 要求 |
| 5 | `missing_crs_declaration` 总体 INDETERMINATE（非 FAIL） | ✅ | 探针 `GA03_missing_crs_declaration` |
| 6 | 六包 expected 每处 diff 都能在 `TRUTH_REVIEW.md` 找到条目 | ✅ | §3.1–§3.10 共 8 类；`git diff --numstat` 逐条对得上 |
| 7 | `check_schema_consistency.py` 与 `selfcheck_guards.py`（含 C2 真负面）退出码均 0 | ✅ | `schema-consistency.txt`、`selfcheck-guards.txt` |
| 8 | `acceptance/stage-0-recheck/` 六项齐备；`RETRACTED.md` 已撤回「P1=0」 | ✅ | 本目录 + `../stage-0/RETRACTED.md` |
| 9 | 目标依赖与 Docker 冒烟作为阶段缺口记录，未声称完成 | ✅ | `DEPS_SMOKE.md` 保持「阶段缺口」表述 |
| 10 | 无第三方依赖 import | ✅ | `grep -rE "^\s*(import|from)\s+(geopandas\|...)"` 空 |
| 11 | 全库无 `verdict != PASS 且 reason_code == "OK"`（规则级 + 条款级） | ✅ | 扫 `work/stage0/*/report.json` 全部 check_results + clause_coverage，违反数 0 |
| 12 | D1/D2 在 check_results 与 clause_coverage 的 reason_code 一致 | ✅ | ambiguous 包两处均为 `CLAUSE_NOT_COVERED_BY_RULE` |
| 13 | 验收材料载明「coverage_state 六态中四态无正例覆盖」，未声称完整验证 | ✅ | 本文件第 6 节 + `OPEN_ISSUES.md` S0-R7 |
| 14 | `failure_reason_codes` / `advisory_reason_codes` 无重复、与 findings 原因码集合一致 | ✅ | 探针 `NEW_reason_code_arrays`；另扫全部 report.json 比对集合，问题 0 |
| 15 | FAIL/INDETERMINATE 的 reason_code 分类正确（I7–I9，规则级 + 条款级）；**双路径一致** | ✅ | 探针 `NEW_i7_i9_counterexamples`（12 组 + 3 组 make_result + 端到端）+ 全库扫描 0 违反；双路径见下 |
| 16 | 两个新字段已在 `check_result.schema.json` 声明且 `check_schema_consistency` 覆盖 | ✅ | 探针 `NEW_schema_registry_parity`：声明 + `uniqueItems=true`；删掉一个枚举码后报 `[REGISTRY_PARITY]`、退出码 1 |
| 17 | 对拍时若原独立探针抛栈，不得记为"工具缺陷"；I7–I9 违规输入必须返回 INDETERMINATE 而非抛栈 | ✅ | 探针 `NEW_compat_path_i7_i9_failclosed`：I9 违反 / I7 违反 / I8 违反三例**均返回** `INDETERMINATE` +「兼容路径输入的 reason_code 违反 I7–I9」说明，**无 traceback**（实现提交 `e2e9124`） |

**判据 11/14/15 的自建反例**（未复用工程师输出）：见 `COMMANDS.md` C11–C13 与
`independent-results.json` 的 `NEW_i7_i9_counterexamples` / `NEW_reason_code_arrays` /
`NEW_schema_registry_parity` 三条。

**判据 15 的双路径验证（权威 + 兼容）**：`NEW_compat_path_i7_i9_failclosed`。
手工构造 results 走两参兼容路径 `aggregate(results, n_rows)`：

| 场景 | 输入 | 实测 |
|---|---|---|
| 仅候选 finding 的规则 | `R02→A2`、`INDETERMINATE + OK`、`records_indeterminate=2` | 兼容路径产出 `A2(COVERED/DUPLICATE_CANDIDATE)`，**不是** `INDETERMINATE + OK`；与权威路径 `build_clause_coverage()` 的判定字段（`coverage_state / verdict / execution_status / reason_code`）**逐字段一致** |
| 无码可取的兜底 | `INDETERMINATE + OK`、无 indeterminate、无 advisory | `CONTRACT_VIOLATION`（不回退 OK） |
| 六包对拍 | 真实 `run()` 结果 | 六包 verdict 全部一致；`defective` 的总体理由**条款列举顺序**不同（结论与码集合相同）——如实登记为 `OPEN_ISSUES.md` **S0-R8** |

**判据 17**：I9 违反（`INDETERMINATE + EMPTY_VALUE`）、I7 违反（`PASS + EMPTY_VALUE`）、
I8 违反（`FAIL + OK`）三例走兼容路径，**均返回** `INDETERMINATE` +
「兼容路径输入的 reason_code 违反 I7–I9（契约 §3.5.1）：…」说明，**无 traceback**。

---

## 8. 本轮提交

最终回归轮（T05-d）的提交 SHA 在提交完成后回填到本行：

**`da1d9460387cdd441bce34950ffc94d7206ffd75`** —— `test(recheck): expected 同步 reason_code 全链路取值、16 项判据终验、验收材料刷新`

**`dd78876b6dc4e52dbcd824392d3aba0dbf3fd88c`** —— `test(recheck): 判据 15 双路径与判据 17 兼容路径失败关闭的独立复现、git 历史改写如实登记`

**`e567d4a5e160bd17dbbd4d448dff443f8db0bcbf`** —— `fix(recheck): 二次验收 RC-01~RC-04 定向修复与回归`

> 二次验收轮说明：独立验收方第二轮报告判定**不通过**，登记 RC-01/RC-02 两条 P1 与 RC-03/RC-04 两条 P2。
> 本轮只做这四条的定向修复与回归（新增 4 项用例，`recheck_probes` 24/24），
> **未新增业务模块、未扩展分类与兼容层**。逐条的输入/预期/实测见 `OPEN_ISSUES.md` §1.0b
> 与 `independent-results.json` 中 RC01–RC04 四个 case。
> 在独立验收方重跑确认之前，**不重立「P1 = 0」**。
