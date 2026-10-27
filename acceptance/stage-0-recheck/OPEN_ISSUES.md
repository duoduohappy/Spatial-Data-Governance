# Stage 0 重验：开放问题清单

- 日期：2026-10-26　编制：严过关（QA）
- 严重度沿用原定义：P0 泄露/未授权写/任意代码/伪造结果；P1 错误放行/遗漏条款/版本错配/证据丢失或不可复现；
  P2 可恢复但影响效率/统计/关键交互；P3 非关键文案与视觉。

## 0. 当前状态（2026-10-26 最终独立复验后，**以本节为准**；下文的历史结论已归档）

- **P0 = 0，P1 = 0**。三轮独立验收发现的 P1（首轮 5 条 + 二次验收 RC-01/RC-02）**全部关闭并有可运行回归**；
  最终复验报告已确认在独立复现范围内关闭，并给出「Stage 0 有条件通过，允许进入 Stage 1」。
- **通过范围**：已实现的语义原型与本轮回归；**不代表**生产系统、AI 链路或完整项目验收通过，
  也不宣称完整系统不存在未知 P1。
- **冻结**：提交 `31d43a8`（标签 `stage0-frozen`）。冻结后 Stage 0 语义不再改动。
- 以下 §1 起为 **P2/P3 与阶段缺口**，其中带「归档」标记的行是过程中的历史结论，不作为现状说明：
  - 归档：原验收包「P1 = 0」结论曾被撤回（见 `../stage-0/RETRACTED.md`）；
  - 归档：二次验收轮期间「独立复验确认前不重立 P1 = 0」——该条件**已满足**，条件解除。
- Stage 1 需处理的两条收尾事项（最终复验报告 A/B）已在提交 `5a4b5ca` 中完成：
  A 编码探针改用 bytes 显式解码并在当前线程断言 `UnicodeDecodeError`；B 本文档与 HANDOFF 现状统一。
- **Stage 1 第一批已完成**（提交 `5e0654d` / `3b8d7ba` / `3738b93` / `6c30e5b`），
  进度与原始输出见 `../stage-1/`：
  ① 项目 `.venv` + 依赖锁定 + 空间库运行验证（`ENV.md`）；
  ② Shapely/pyproj/PyYAML 替换自研几何与 YAML，冻结样例逐项比对（`GEOMETRY_REPLACE.md`）；
  ③ 执行入口 Pydantic 校验 + 判定接口收敛到唯一正式路径（`INPUT_AND_API.md`）；
  ④ 最小模块 CLI / HTML 报告 / 整改 compare + 补齐无正例分支（`KERNEL_CLI_REPORT_COMPARE.md`）。
  Stage 1 期间**未新增业务模块**（未进入模型、Web、多 Agent、网关）。
- **P1 仍为 0**：Stage 1 第一批未发现新的错误放行类问题；下述新增项均为 P2/P3 或阶段缺口。
- **外部复核轮（2026-10-26，Codex）**：外部复核判定 Stage 1 **暂不通过**，登记 EXT-01/EXT-02/EXT-04 三条 P1
  与 EXT-03 一条 P2，**全部集中在 compare**（另有一项"正式入口与 expected 回归未分离"）。
  第二轮已定向修复并有 18 例反例回归（`tools/compare_probes.py`）+ 2 项新增内联探针，
  详见 §1.2 与 `../stage-1-verify/ROUND2.md`；**关闭状态待外部复审确认，不自行宣称 P1=0 已确认**。
- **第二轮外部复验（2026-10-26 晚，Codex）**：上轮主要路径通过，但整体仍暂不通过——
  登记两条 P1：**S1-R2-01**（逐规则参数 Schema 未接入正式执行入口）与 **S1-R2-02**
  （删除"原本干净"实体仍可整体放行）。第三轮已定向修复（详见 §1.3 与
  `../stage-1-verify/ROUND3.md`；`compare_probes.py` 扩到 33/33，
  含十类参数反例 + 有效对照 + 实体差异五组）。**关闭状态待外部复审确认**；
  参数校验是原有 Stage 1 门槛，**不因本轮补做而同时宣告整阶段通过**。
- 库替换成果（Shapely / pyproj / PyYAML / Pydantic / 判定接口收敛）**未被撤销**，外部复核也确认保留。

---

## 1. Stage 1 第一批新增的开放问题

| ID | 级别 | 问题 | 证据 | 计划 |
|---|---|---|---|---|
| **S1-01** | P2 | ** Docker 冒烟仍未做**：本机无 `docker`（PATH 与默认安装路径均无，未装 Docker Desktop），WSL 被安全策略阻止，无法作为替代后端 | `../stage-1/ENV.md` §5 | 在有 Docker 的机器上补 `docker build` + `docker run` 并记录镜像 digest；在此之前不得声称容器化完成 |
| **S1-02** | P2 | **独立验收方的原探针需迁移**：`stage0_independent_probes.py` 第 9、47 行仍用已删除的 `aggregate(results, n_rows)`，现在抛 `TypeError`。本仓库**不**为它保留第二条判定路径，对拍环节如实报 `[SKIP]` | `recheck-probes.txt` 对拍段 | 迁移写法见 `../stage-1/INPUT_AND_API.md` §2；迁移后重跑对拍 |
| **S1-03** | P3 | ~~整改 compare 只比较 FAIL 类 finding~~ **（第二轮关闭）**：台账现在同时收 FAIL 与**缺证据/未知**两类，候选类单列披露不参与关闭 | `geoacceptance/compare.py` `_ledger` | 关闭方式见 §1.2 EXT-01；候选仍是"仅供参考"，不进关闭判定 |
| **S1-04** | P3 | ~~CLI 只接受 `examples/` 下的包名~~ **（第二轮关闭）**：新增正式入口 `validate --bundle <任意目录>`；`compare --before/--after` 也接受目录 | `geoacceptance/cli.py` `_resolve_batch` / `cmd_validate` | 目录走真实路径，非目录才按 `examples/` 包名解析并保留穿越防护 |
| **S1-05** | P3 | ~~compare 产物没有 Schema 校验~~ **（第二轮关闭）**：新增 `schemas/stage1_compare.schema.json` 与 `schemas/stage1_validate.schema.json` | `tools/compare_probes.py` | 18 例 compare 输出 + validate 输出全部用仓库子集校验器实测通过 |
| **S1-06** | P3 | **geopandas 仅做运行验证**，未进入判定链路（矢量 IO 仍走标准库 + json） | `../stage-1/ENV.md` §6 | Stage 1 后续接入时须重跑冻结样例比对 |
| **S1-07** | P3 | **`requirements.lock.txt` 未声明 Python 版本下限**：在 Python 3.11.9 上安装失败（`ERROR: No matching distribution found for numpy==2.5.4`）；同样的代码用不锁定版本的核心五库在 3.11 上跑通（门禁 `ALL_OK=true`、回归 28/28） | `../stage-1-verify/raw/10-install-py311-lock-failed.txt`、`raw/12-gate-py311.txt`、`raw/13-recheck-probes-py311.txt` | **部分关闭**：README 依赖段与 `requirements.txt` 已写明实测范围（3.13.14 可装、3.11.9 装不上）并强调"代码兼容 ≠ 锁文件可复现"；**仍未出 3.11 专用锁定**，在此之前不得声称"任意 Python 3 可复现" |
| **S1-08** | P3 | **删除实体没有"批准删除"政策通道**：整改后缺失的实体一律 `removed_pending_review`（阻断关闭），系统里没有可追溯的批准删除记录机制。**第三轮起该阻断覆盖全量实体差集**（含"原本干净"的实体，S1-R2-02），不再是只拦"带缺陷被删" | `geoacceptance/compare.py` 实体差集块 | 需要业务先给出"谁可以批准删除交付对象、凭证如何留痕"的政策；在政策与审核记录落地前，保持一律阻断（不默认放行） |
| **S1-09** | P3（政策待确认） | **规则被重新批准（reviewer / approved_at 变化）会阻断关闭**：语义指纹含批准来源，数据修好了但规则换人重批 ⇒ `not_comparable` | 探针 `EXT04-8` | 这是按外部复核 §六"批准来源纳入指纹"实现的**保守**口径。若业务认为"同一内容重新批准仍属同一把尺子"，需把批准来源降为"仅披露不阻断"——**待业务确认，未确认前维持阻断** |

### 1.2 外部复核轮（Codex 独立复核，2026-10-26）——compare 与入口分离

来源：`C:\Users\TempAdmin\Documents\Codex\2026-10-26\mu\outputs\GeoAcceptance-Stage1-Codex外部复核报告.md`
（结论：Stage 1 **暂不通过**，阻断点集中在 compare 的关闭证据与身份；不撤销已验证的库替换成果）。
本轮按"保留库替换成果、只做定向修复"处理，**未扩展架构、未加业务模块**。
逐条整改与实测见 `../stage-1-verify/ROUND2.md`，反例回归见 `tools/compare_probes.py`（18/18）。

| ID | 级别 | 外部复核的问题 | 修复 | 回归（输入 / 预期 / 实测） |
|---|---|---|---|---|
| **EXT-01** | P1 | **没有有效复验通过证据也能显示 COMPLETE**：三个反例（blocked→blocked、clean→ambiguous、单条过期记录 + R09 改 DRAFT）；只比 FAIL finding、忽略运行与条款覆盖；数据集级 finding 因无 `record_id` 从台账消失 | ① `closed` 改为需**正面证据**（规则仍存在 ∧ APPROVED ∧ 未被配置拒绝 ∧ 有结果 ∧ `execution_status=COMPLETED` ∧ 规则结论 PASS ∧ 所映射条款 `COVERED`+PASS）；② 数据集级问题用「规则身份 + 证据域 file」追踪；③ 未知/缺证据一律 `unresolved_unknown`；④ 总体拆成 `ledger` + `after_acceptance`，不再叫"整改完成" | `EXT01-1`：blocked→blocked ⇒ `still_open`、`ledger=OPEN`、条目 `identity_kind=dataset`（不再消失）；`EXT01-2`：clean→ambiguous ⇒ `LEDGER_CLOSED_NOT_ACCEPTED`，`scope.unknown_after` 列出未 PASS 条款；`EXT01-3`：R09 改 DRAFT ⇒ `unresolved_unknown`、`ledger=INDETERMINATE` |
| **EXT-02** | P1 | **删除缺陷实体被直接算作修复**（clean 首条改过期后删除 ⇒ `fixed=1`、`COMPLETE`） | 先核对两批**全量实体清单**；缺失实体 ⇒ `removed_pending_review`（阻断关闭），新增实体单独披露 | `EXT02-1`：删实体 ⇒ `removed_pending_review`、`scope.entities_removed_after=["SD-0001"]`、`ledger=INDETERMINATE`；`EXT02-2`：新增实体 ⇒ `entities_added_after` 非空 |
| **EXT-03** | P2 | **把 finding 数量当成实体重复次数**（同一 `record_id` 两条 finding ⇒ 判定 ID 重复 ⇒ `not_comparable=2`） | 身份唯一性从**全量输入记录**建索引（唯一/重复/无标识）；findings 只是挂在该索引上的证据 | `EXT03-1`：唯一实体两条 finding（R04+R09）⇒ 两批 `duplicated=[]`、两条均 `closed`（`closure_evidence.execution_status=COMPLETED`） |
| **EXT-04** | P1 | **版本比较不足以证明尺子相同**：`_rule_versions` 只取 `rule.version`，不比类型/参数/来源/依赖/字典/区域/基准时间；规则被移除无专门不可比判定 | 建立**规则语义指纹**（rule_type / status / version / 参数 / 参数来源 / 依赖 / 条款映射 / 批准来源）+ **批次制品指纹**（数据字典 / 项目范围 / 规范原文 / 基准时间）；指纹不同 ⇒ `not_comparable`；规则移除 ⇒ `not_comparable`（尺子被撤走）；新增规则披露 | `EXT04-1` 同版本改 `trim`；`EXT04-2` 改 `max_age_days`（同时触发配置拒绝）；`EXT04-3` 改字典；`EXT04-4` 改项目范围；`EXT04-5` 改基准时间；`EXT04-6` 删规则；`EXT04-7` 上游改 DRAFT；`EXT04-8` 批准来源变化；`EXT04-9` 新增规则披露 —— **全部不得 closed** |
| **§七** | P1 | **正式检查入口与 expected 回归未分离**：`cli run` 必须比对 examples 的 expected，没有 expected 的新包无法验收 | 新增 `validate`（任意包目录，**不需要 expected**，含输入防护与三类 findings 统计）；原 `run` 改名 `regress`（明确是回归工具）；`run` 子命令已删除 | 探针 `S1_validate_entry_new_bundle`：新包干净副本 ⇒ PASS（`expected_used=false`），注入过期 ⇒ FAIL 且 `findings_by_class.FAIL≥1`，缺文件 ⇒ `InputGuardError`；`S1_cli_smoke` 断言旧 `run` 已不存在 |

> 说明：EXT-01 的第三个反例（"仅一条过期记录 + R09 改 DRAFT"）与 EXT-04 的"规则资格变化"是同一处代码路径，
> 本轮按**资格问题**（`unresolved_unknown`）与**尺子内容变化**（`not_comparable`）分开报，原因必须能区分。

> **S1-02 状态更新（2026-10-26 独立复验轮）**：wrapper 已改为**按内容识别**外部探针结果文件
> （不再只认 `independent-results.json`），现可结构化登记对拍结论：
> `ran=true`、`results_file=new-independent-results.json`、RC-01/RC-02 两个签名用例均为
> `INDETERMINATE`（不再 PASS）、`all_ok=true`。**脚本侧迁移仍待外部方完成**，仓库侧不为兼容保留第二判定路径。

### 1.3 第二轮外部复验（Codex，2026-10-26 晚）——S1-R2-01 / S1-R2-02

来源：`C:\Users\TempAdmin\Documents\Codex\2026-10-26\mu\outputs\GeoAcceptance-Stage1-第二轮Codex外部复验.md`
（结论：上轮整改主要路径通过，但 Stage 1 整体**仍暂不通过**；剩余两项定向修复，不重做已验证成果）。
本轮按报告「只修这两个缺口」处理：**保留库替换与上轮 compare/入口成果，未新增架构**。

| ID | 级别 | 外部复验的问题 | 修复 | 回归（输入 / 预期 / 实测） |
|---|---|---|---|---|
| **S1-R2-01** | P1 | **逐规则参数 Schema 未接入正式执行入口**：`Rule.parameters` 只是 `Dict[str, Any]`；反例＝R01 `fields=[]` + 删 `name` 列 ⇒ `validate_bundle` 仍 `PASS`、`config_rejections=[]` | `tools/input_models.py` 增加十类规则的 **strict 参数判别联合**（与 `rule.schema.json` anyOf 分支逐条对齐：必填键 / 空必需数组 / 错误类型 / 非法枚举 / 未知参数键 / 未知 rule_type / 缺 parameters 一律受控拒绝，**不忽略参数按默认值执行**）；`validate_inputs` 逐规则定位 target；validate / compare / regress 均经 `collect_config_rejections` 走**同一套**校验；拒绝后结构化报告保留应检查条款（`counts.clauses_required` + `clauses_pending`） | `compare_probes.py` PARAM-00～12：十类非法参数 + 未知 rule_type + 缺 parameters 全部 `executed=false`、`INDETERMINATE`、`INPUT_SCHEMA_INVALID`（target 定位到规则）、`clauses_required=10`；有效对照 clean 照常 `PASS`。外部原反例复跑：`INDETERMINATE` + `INPUT_SCHEMA_INVALID/R01` |
| **S1-R2-02** | P1 | **删除"原本干净"的交付实体仍可整体放行**：`removed_pending_review` 只在 finding 台账循环中生成，干净实体不进台账 ⇒ `LEDGER_CLOSED_ACCEPTED` | `geoacceptance/compare.py` 在**全量 before/after 实体清单差集**上统一生成 `removed_pending_review`（每实体一条、多规则失败码合并去重）；干净实体与故障实体同样阻断；新增实体保持披露；Schema 版本升 `stage1-compare-3` | `compare_probes.py` 实体差异五组：干净删除 `R202-1` ⇒ `removed_pending_review=1`、`LEDGER_INDETERMINATE`；故障删除 `EXT02-1`；仅新增 `EXT02-2`；无变化 `C00`；行序打乱 `R202-2` ⇒ 结论不变。外部原反例复跑：`LEDGER_INDETERMINATE`（SD-0001 缺失阻断） |

> 口径变化说明：`n_uncovered_coverage_branches` ①（未知 rule_type）原构造走 `NO_IMPLEMENTATION`，
> 入口校验收紧后改走 `CONFIG_REJECTED`（更早更严，受控拒绝优先）。
> schema 十类与内核实现同步时 `NO_IMPLEMENTATION` 无输入可触发，保留给「schema 先行扩展」场景，不算回退。

---

## 1.0 本轮新发现的开放问题（**QA 独立发现，工程师未报告**）

### 1.0 已解决（最终回归轮关闭）

| ID | 级别 | 问题 | 关闭方式 | 关闭提交 |
|---|---|---|---|---|
| **S0-R1** | P2 | 条款级 `reason_code` 在 FAIL 时是 `OK`，与契约 §3.3/§3.5 不一致 | 工程师扩大为**规则级 + 条款级全链路** I7–I9 断言（`assert_reason_compat()`）：FAIL 取第一条 FAIL 类 finding 的码；INDETERMINATE 走「缺证据类码 → 上游码/ALL_RECORDS_BLOCKED → 候选类码 → CONTRACT_VIOLATION」取值链，禁止回退 `OK`。QA 已把 24 条 expected 差异同步并逐条登记进 `examples/TRUTH_REVIEW.md` §3.9，并自建反例验证断言真的会拦 | `9af939b`（条款级）、`f433286`（规则级 + 兼容条目 + Schema 登记）、`1fd2b21`（兼容路径兜底断言）；expected 同步见本轮 T05-d 提交 |
| **S0-R2** | P2 | `TIMEZONE_UNDECLARED` 归位后若分支可达会触发 I4 违约 | 缺证据类 finding 所在行改计入 `records_uninterpretable`（不再计入 `records_failed`），规则级落成 `INDETERMINATE / PARTIAL / TIMEZONE_UNDECLARED`。QA 用放宽解析的注入用例独立复测通过，并把探针预期**收紧**到 `execution_status == PARTIAL` + `records_uninterpretable >= 1` | `9af939b` |
| **S0-R3** | P2 | `INPUT_MANIFEST.json` 在 `core.autocrlf=true` 检出下哈希全数失配 | 仓库根新增 `.gitattributes` 固定 LF | `2a22ff3` |

### 1.0b 二次验收轮（独立验收方 2026-10-26 第二轮报告）的 RC-01～RC-04

第二轮验收结论：**不通过**，登记两条 P1（RC-01、RC-02）与两条 P2（RC-03、RC-04）。
本轮按报告「只做针对性修复」的要求处理，**未新增业务模块、未扩展分类与兼容层**。

| ID | 级别 | 问题（独立验收方原话要点） | 修复 | 回归用例（输入/预期/实测） |
|---|---|---|---|---|
| **RC-01** | P1 | `build_clause_coverage` 只在 `clause_results` **完全为空**时才标 `MISSING_RESULT`；一条条款映射多条规则、只丢其中一条结果时仍 `COVERED + PASS` | 判定改为**规则身份集合比对**：`expected`（未被拒 ∧ APPROVED ∧ 有实现）⊄ `actual` ⇒ `MISSING_RESULT`；同一 rule_id 多条结果 ⇒ 结果集不可信 ⇒ `INDETERMINATE / FAILED / CONTRACT_VIOLATION`（登记 `conflicting_rule_ids`，禁止后一条覆盖前一条）；已有 FAIL 且缺结果 ⇒ 保留 `FAIL`（`status=PARTIAL`）并显式登记 `missing_rule_ids` | 探针 `RC01_clause_coverage_result_set`：六组故障注入（全齐 / 部分缺失 / 零结果 / 重复 / 冲突 / 已知 FAIL+缺结果），实测①`COVERED+PASS`、②`MISSING_RESULT+INDETERMINATE`+`missing=[R09b]`、③`missing=[R09,R09b]`、④⑤`CONTRACT_VIOLATION`+`conflicting=[R09]`、⑥`FAIL+STALE_RECORD`+`missing=[R09b]` |
| **RC-02** | P1 | 只对 `NEEDS_CLARIFICATION`（且只在规则声明必检时）查批准冲突，`UNSUPPORTED` 的条款仍可挂 APPROVED 规则并整体 PASS；`support_status` 枚举只靠单独跑 Schema 脚本校验 | `reject_reference_integrity()` 改为：非 `SUPPORTED`（含 `UNSUPPORTED` / `NEEDS_CLARIFICATION` / 未知取值 / 字段缺失）的条款，其 APPROVED 规则一律登记 `APPROVED_RULE_FOR_UNSUPPORTED_CLAUSE`；未知/缺失另报 `CLAUSE_SUPPORT_STATUS_UNKNOWN`（**执行入口**校验）；`build_clause_coverage()` 增设 support_status 一致性前提（兜底网） | 探针 `RC02_unsupported_clause_approved_rule`：四种状态全部非 PASS 且含该码；改回 `SUPPORTED` 的反向确认仍 PASS（证明不是"一律拒绝"） |
| **RC-03** | P2 | 子进程用 `text=True`（调用方 locale 解码），Windows 默认 cp936 下中文输出抛 `UnicodeDecodeError`，导致 `NEW_schema_registry_parity` 基线退出 0 却被判失败 | 新增 `_run_utf8()` / `_py()`：`sys.executable -X utf8` + env 固定 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8` + 显式 `encoding="utf-8"` 解码（`errors="strict"`，不用 `ignore` 掩盖）；三处子进程调用全部改走该通道 | 探针 `RC03_subprocess_encoding`：从环境删掉两个变量后仍可完整解码中文，`sys.stdout.encoding=utf-8`，校验器退出 0 且含 `SCHEMA_CONSISTENT=true` |
| **RC-04** | P2 | 同一 Kernel 实例 `run()` 两次：results 相同但 **findings 不同**（`finding_seq` 未复位，finding_id 从上一轮末尾继续编号） | `run()` 开头复位运行局部状态（finding 序号、依赖状态表、阻断表），并按"配置期信号长度"裁掉上一轮的运行期风险信号；配置期信号不重复登记 | 探针 `RC04_repeat_run_determinism`：clean / defective 两个实例各跑两次，`results / findings / risk_signals` 三次比较全等，且两次规则级结论一致 |

**修复提交**：`e567d4a5e160bd17dbbd4d448dff443f8db0bcbf`（分支 `main`）。

> ~~**P1 口径**：RC-01 / RC-02 已修复并有独立回归用例，但在**独立验收方重跑确认之前**，本文件不重立「P1 = 0」。~~
> **（归档，条件已解除）** 2026-10-26 最终独立复验已在独立复制工作区内复现并确认两条 P1 关闭
> （`partial_mapped_result_missing` / `unsupported_clause_approved_rule` 均由 PASS → INDETERMINATE），
> 故「不重立 P1=0」的限制解除。当前 P1 口径见 §0。
> 第二轮报告的原文与结论见 `C:\Users\TempAdmin\Documents\Codex\2026-10-26\mu\outputs\GeoAcceptance-Stage0-二次验收报告.md`。

### 1.1b git 历史事故（**如实登记，不渲染也不淡化**）

| 项 | 内容 |
|---|---|
| 事故 | 工程师在 amend 提交 `c83539c` 时**误吞了架构师的契约提交 `c582648`**（该提交从历史中消失） |
| 修复方式 | 软回退后重做：用原提交内容 + 正确提交信息重建两个提交 |
| SHA 对应关系 | `dedc2f9` ≡ 原 `c83539c`（内容一致）；`8048245` ≡ 原 `c582648`（内容一致，沿用架构师原始提交信息） |
| 验证 | 工程师用 `git diff` 验证两次树完全相同；**QA 独立复核**：`git show --stat dedc2f9` / `8048245` 与转告的提交说明一致，当前 HEAD 链为 `1fd2b21 → dedc2f9 → 8048245 → e2e9124` |
| 为什么登记 | 这份交付物的核心价值是**可审计性**。历史里发生过改写而不留痕，比事故本身更伤可信度。故按事实记一条，措辞平实 |

> 注：`c83539c` 与 `c582648` 已不存在于历史中。若在其他材料里看到这两个 SHA，以 `dedc2f9` / `8048245` 替换。

### 1.1 仍未解决

| ID | 级别 | 问题 | 证据 | 建议 |
|---|---|---|---|---|
| ~~**S0-R4**~~ | ~~P2~~ | **护栏 D 此前用错了 `aggregate()` 的签名**：`selfcheck_guards.py` 调的是 `aggregate(results, n_rows)`（二参数旧签名），而现行签名是 `aggregate(clause_coverage, config_rejections, n_rows)`。它之所以还绿，是因为 `n_rows=0` 恰好落到「零记录」分支——属于**绿得不对**。`_coverage_from_results()` 兼容分支也没被真正验证过 | 旧代码 `tools/selfcheck_guards.py:91`：`g.aggregate(results, len(k.rows))` | 本轮已改为三参数正确调用（`build_clause_coverage` + `collect_config_rejections`）。建议 Stage 1 删除二参数兼容分支 —— 保留两套签名意味着 GA-01 那种"未映射条款凭空消失"的漏洞形态可能从后门回来。**（2026-10-26 归档关闭）Stage 1 已删除二参签名与 `_coverage_from_results()`，旧调用抛 TypeError 并给迁移写法；见 `../stage-1/INPUT_AND_API.md`** |
| **S0-R5** | P3 | `examples/crs_same_unit_wrong/` 是手写包，`requirements.yaml` 的 A3 `interpretation` 由**人工**补（其余 5 包由 `make_examples.py` 生成）。若将来改了 `CLAUSE_INTERPRETATIONS` 常量，这个包不会自动跟上 | 本轮已人工补齐并核对 | 在 `make_examples.py` 里加一条"手写包与生成包字段一致性"的自检，或把该包纳入生成（但那会牺牲"手写真值"的独立性——倾向于前者） |
| **S0-R6** | P3（覆盖缺口） | **`advisory_reason_codes` 六个示例包全为空数组 `[]`**：六包没有任何「缺证据类」finding（`CRS_MISSING_DECLARATION` / `TIMEZONE_UNDECLARED`），六包里所有规则级 INDETERMINATE 都由「上游阻断 / 全批阻断 / 候选 / 未映射」产生。因此 §3.5.1 取值链中「缺证据类码」这一档、以及 §3.5.2「去重 + 首次出现顺序」的**多元素**情形，**在示例包中没有正例** | `work/stage0/*/report.json` 全扫：非空 `failure_reason_codes` 9 处，非空 `advisory_reason_codes` **0 处** | 新增一个「缺 CRS 声明」或「无时区时间戳」示例包可补齐正例，但那属于**输入变更**，超出 T05 授权。本轮选择如实登记而非编造假包。**（2026-10-26 归档关闭）Stage 1 已补探针级正例：删除 CRS 声明 ⇒ `advisory_reason_codes` 非空（探针 `S1_uncovered_coverage_branches`）** |
| **S0-R8** | P3（双路径发散） | **兼容路径与权威路径在 FAIL 条款的列举顺序上不一致**：`aggregate(results, n_rows)`（两参兼容路径）按**结果出现顺序**枚举 FAIL 条款，`aggregate(coverage, rejections, n_rows)`（权威路径）按**条款定义顺序**枚举。`defective` 包实测：兼容路径是 `A2,A3,A4,A5,C1,B1,B3`，权威路径是 `A2,A3,A4,A5,B1,B3,C1`。
**结论（FAIL）、失败条款集合、每个条款的原因码全部一致**，只有字符串中的顺序不同 | 探针 `NEW_compat_path_i7_i9_failclosed` 的 `bundles.defective`：`verdict_same=true`、`reason_same=false`；六包中只有 defective 这一处 | 若后续有按字符串比较总体理由的测试，会被这个顺序差异绊到。建议 Stage 1 让兼容路径复用权威口径的排序，或明确"总体理由字符串不参与契约比对"。本轮**未**改实现（超出 T05 授权），按现状如实登记 |
| **S0-R7** | P3（覆盖缺口） | **`coverage_state` 六态中只有两态有示例包级正例**：`COVERED`（六包）与 `UNMAPPED`（ambiguous 的 D1/D2）；`CONFIG_REJECTED` / `MISSING_RESULT` / `NO_IMPLEMENTATION` / `UNAPPROVED` **四态无示例包级正例**（**2026-10-26 归档关闭**：二次验收轮补上 `CONFIG_REJECTED`/`MISSING_RESULT` 探针级正例；Stage 1 第一批又补上 `NO_IMPLEMENTATION`/`UNAPPROVED` 探针级正例（探针 `S1_uncovered_coverage_branches`）。六态至此**全部有可执行正例**，但仍无示例包级正例）。另：契约 §3.2 说 D1/D2 这类"授权不完整"应落 `UNAPPROVED`，而实测落 `UNMAPPED`（两者都能推出 INDETERMINATE，但口径标签不一致） | 扫 `work/stage0/*/report.json` 的 `clause_coverage.coverage_state`：只出现 `COVERED`、`UNMAPPED` | 本轮**未声称**覆盖模型已被完整验证。Stage 1 已补四态的可执行用例；剩余两项：为六态各补**示例包级**正例、裁决 `UNAPPROVED` 与 `UNMAPPED` 的边界（`D1/D2` 实测落 `UNMAPPED`） |

---

## 2. 沿用原验收包的开放问题（未在本轮解决，也不声称已解决）

| ID | 级别 | 问题 | 计划 |
|---|---|---|---|
| S0-01 | P2 | `compare`（整改复验对比）未实现，`corrected` 包备好但用不上 | Stage 1 CLI |
| S0-02 | P2 | 24 项必测挑战集未实现，本轮只覆盖其中约 4 项语义 | Stage 1 起按 `docs/evaluation.md` 逐条建成可执行用例 |
| S0-03 | P2 | Haversine 与自研射线法为近似实现，与 pyproj/shapely 可能有边界差异 | Stage 1 替换后必须**冻结本轮全部边界用例并重跑对比**，未对比不得删除 ADR-004 |
| S0-04 | P2 | 极简 YAML 解析器自研（不支持锚点/多行/深层嵌套） | Stage 1 改用 PyYAML 并锁定版本 |
| S0-06 | P2 | 未完成人工工作流对照，任何提效数字都不可用 | Stage 4；在此之前对外材料不得出现提效数字 |
| S0-07 | P2 | 标准库 CSV 读取缺少编码容错与恶意文件防护 | Stage 1 ingestion 层 |
| S0-08 | P3 | 示例数据全为合成数据 | Stage 4 引入许可明确的真实公开数据 |
| ~~S0-09~~ | ~~P3~~ | ~~报告 Markdown 渲染未做 HTML 转义~~ | **（2026-10-26 关闭）Stage 1 的 HTML 报告（`geoacceptance/reporting.py`）文本全部 `html.escape`；Markdown 渲染层仍待 Stage 3** |
| S0-10 | P3 | 尚无 LICENSE / THIRD_PARTY.md | Stage 5 |

已关闭：S0-05（git 仓库与 commit 历史，已于 2026-10-26 初始化）；原「待用户确认」三项中的
"是否接受 blocked 包"与"是否允许安装第三方依赖"已由独立验收方给出处理建议（接受增项；
Stage 1 用项目 `.venv` 锁定依赖，不污染全局环境）。

---

## 3. 阶段缺口（**不得声称已完成**）

| 缺口 | 现状 | Stage 1 计划 |
|---|---|---|
| **目标空间依赖安装验证** | **未做**。本轮 Stage 0 严格零第三方依赖，`tools/smoke_deps.py` 只**报告**不安装；geopandas / shapely / pyproj / pydantic / jsonschema / pandas / pytest 全部 MISSING（见 `deps-smoke.txt`） | 用**项目 `.venv`** 安装并锁定版本，不污染全局环境 |
| **目标空间依赖运行验证** | **未做**。本轮所有结论都来自标准库实现，未在目标依赖上做过一次重跑对比 | Stage 1 替换后必须重跑六个包并与本轮结论逐条对比（沿用 S0-03） |
| **Docker 冒烟** | **未做**。本轮没有构建任何镜像，也没有在容器里跑过一次 | Stage 1/2 随交付物一起做，并记录镜像 digest 与运行输出 |
| 评测与指标 | 未做，无任何指标数字 | Stage 4 |

---

## 4. 契约 §6.3 明示的能力边界（不得拔高表述）

**参数来源护栏在 Stage 0 只实现到「字面可追溯」，未实现「语义正确可证」。**

能验证：文档哈希一致、引用行内容逐字一致、参数值在批准引用中的 token 级字面出现、
参数↔条款↔规则的绑定自洽、来源记录字段完整。

不能验证：「人工是否真的读过并认可」（只记录 `reviewer`）、`interpretation` 的解释是否正确、
同一文档别处是否存在冲突表述、文档版本历史与批准版本的关系、参数变更是否真的走了重新批准流程
（Stage 0 无 AuditEvent 落地）。
