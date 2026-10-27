# Stage 1 第三轮：第二轮外部复验后的定向修复（短复验说明）

- 日期：2026-10-26（晚）
- 触发：《GeoAcceptance-Stage1-第二轮Codex外部复验.md》——结论"上一轮整改主要路径通过，
  但 Stage 1 整体仍暂不通过；剩余两项定向修复，不进入 Stage 2，不重做已验证成果"。
  原文、外部探针与修复前结果见 `external-round2/`。
- 修复提交：**`93d3d0b`**（父提交 `a2b5797`）
- 用户约定：**只修这两个缺口**，保留已通过成果；参数校验是原有 Stage 1 门槛，
  不能延期后同时宣告整阶段通过；修好后做一轮短复验。
- 本文件是**执行方自验说明**，不是外部验收结论；关闭状态待外部复审确认。

## 1. 范围与边界（先说没做什么）

做了：S1-R2-01（逐规则参数 Schema 接入正式执行入口）与 S1-R2-02（删除干净实体阻断）
两条 P1 的定向修复，及其正式回归与短复验。

没做（保持未决，不视为完成 Stage 1）：

| 项 | 说明 |
|---|---|
| Docker 冒烟（S1-01） | 本机无 docker / WSL 被安全策略阻止；替代证据＝干净克隆 + 全新 venv |
| 外部方 Stage 0 探针迁移（S1-02） | 仓库侧不保留第二判定路径 |
| 完整输入格式 / 任意复杂包实测 | 外部复核 §七门槛的其余后续项，本轮仍未做 |
| 锁文件 3.11 版（S1-07） | 已声明实测范围（3.13.14 可装、3.11.9 装不上 numpy==2.5.4） |
| 批准删除通道（S1-08） | 政策未落地前维持"一律 removed_pending_review 阻断" |
| 重新批准阻断（S1-09） | 保守口径待业务确认 |
| geopandas 入判定链路（S1-06） | 仅运行验证 |
| Stage 2（条款提取与人工确认、模型调用） | 未开始；等外部复审结论 |

## 2. S1-R2-01：逐规则参数 Schema 接入正式执行入口（P1）

**外部反例**：clean 副本把 `R01.parameters.fields` 设为 `[]`、并从 `poi.csv` 删除 `name` 列
⇒ `validate_bundle` 实测 `aggregate_verdict=PASS`、`config_rejections=[]`（已声明契约未执行）。

**修复**（`tools/input_models.py` 重写）：

- 新增十类规则的 **strict 参数判别联合**，与 `schemas/rule.schema.json` 的 anyOf 分支
  逐条对齐：必填键、空必需数组（`minItems`）、错误类型（strict，`"yes"` 不收敛成 `True`、
  `123` 不当字符串）、非法枚举、数值范围（`max_age_days >= 0` 等）、模式（ISO 时间戳、
  CRS 串）、**未知参数键禁止**（`additionalProperties: false` 的等价实现）；
- `rule_type` 收敛为十类白名单（Literal），**未知 rule_type 受控拒绝**；
- `parameters` 缺失一律拒绝：**不忽略参数后按默认值继续执行**（那等于换一把没人批准过的尺子）；
- `validate_inputs()` 逐规则校验并把 target 定位到 `rule_id`（不再是笼统的文件名），
  使 `Kernel.rejected_rule_ids()` 能把非法规则挡在业务结论之外、compare 能识别
  "该规则被配置校验拒绝"；
- **单一入口**：validate / compare / regress 三个入口都经
  `Kernel.collect_config_rejections() → reject_input_schema()` 走同一套校验，不维护三套宽严；
- 拒绝后结构化报告**保留应检查的条款数量**：`counts.clauses_required` 来自
  `requirements.yaml`（不再是 0），并新增 `clauses_pending` 条款清单，
  Schema 版本升 `stage1-validate-2`。

**回归**（`tools/compare_probes.py` PARAM-00～12，走正式 `validate_bundle`）：

| 用例 | 实测 |
|---|---|
| PARAM-01 `required_field_present` `fields=[]` | `executed=false`、`INDETERMINATE`、`INPUT_SCHEMA_INVALID/R01`、`clauses_required=10` |
| PARAM-02 `non_empty` `trim='yes'` | 同上（target=R02） |
| PARAM-03 `type_parse` `fields` 非数组 | 同上（R03） |
| PARAM-04 `enum_value` 缺 `allow_alias` | 同上（R04） |
| PARAM-05 `id_unique` `field=123` | 同上（R05） |
| PARAM-06 `coord_range` `lon_range` 少于 2 | 同上（R06，另触发来源对不上） |
| PARAM-07 `crs_declaration` 非法 CRS 串 | 同上（R07） |
| PARAM-08 `within_project_area` 非法枚举 | 同上（R08） |
| PARAM-09 `freshness` `max_age_days=-1` | 同上（R09） |
| PARAM-10 `duplicate_candidate` 未知参数键 | 同上（R10） |
| PARAM-11 未知 `rule_type= magic_check` | 同上（R05） |
| PARAM-12 缺 `parameters` | 同上（R01） |
| PARAM-00 **有效输入正向对照**（未篡改 clean） | `executed=true`、`PASS`、零拒绝（不误杀） |

六个示例包在新校验下**零新增拒绝**（全部照常执行，结论不变）。

## 3. S1-R2-02：删除"原本干净"的交付实体不再整体放行（P1）

**外部反例**：clean→clean 副本，after 只删 `SD-0001` ⇒ `scope.entities_removed_after=[SD-0001]`
但 `overall=LEDGER_CLOSED_ACCEPTED`（干净实体不进台账，其消失只披露、不阻断）。

**修复**（`geoacceptance/compare.py`）：

- `removed_pending_review` 条目改在**全量 before/after 实体清单差集**上统一生成：
  每个缺失实体**一条**（该实体在整改前的失败/未知码合并进去，多条规则不重复计实体）；
- 删除**干净**实体与删除**带缺陷**实体同样阻断（`BLOCKING_UNKNOWN` ⇒ `LEDGER_INDETERMINATE`）；
  当前没有批准删除通道，"原本没问题"不构成放行业务依据；
- 新增实体保持披露（`entities_added_after`，不参与关闭判定）；
- Schema 版本升 `stage1-compare-3`，`scope.closure_rule` 写明实体缺失口径。

**回归**（实体清单差异五组，外部报告 §3 要求齐全）：

| 组 | 用例 | 实测 |
|---|---|---|
| 干净实体删除 | `R202-1` | `removed_pending_review=1`、`LEDGER_INDETERMINATE`、`scope.entities_removed_after=[SD-0001]` |
| 故障实体删除 | `EXT02-1` | 同上（该实体整改前的失败码并入同一条待审核条目） |
| 仅新增 | `EXT02-2` | `entities_added_after` 非空披露，`LEDGER_CLOSED_ACCEPTED`（新增不阻断） |
| 无变化 | `C00-identical` | `LEDGER_CLOSED_ACCEPTED`、无差异 |
| 行序打乱 | `R202-2` | 身份按 record_id，结论与无变化完全一致 |

## 4. 口径更新（如实登记，不是回退）

`recheck_probes.py` 的 `S1_uncovered_coverage_branches` ①原构造是"把 R09 的 rule_type
改成内核未实现的类型"以触发 `NO_IMPLEMENTATION` 正例。入口校验收紧后，未知 rule_type
**先**被 `INPUT_SCHEMA_INVALID` 受控拒绝（S1-R2-01 的明确要求），条款级走 `CONFIG_REJECTED`
（比 `NO_IMPLEMENTATION` 更早、更严）。schema 十类与内核实现同步时 `NO_IMPLEMENTATION`
无输入可触发，保留给"schema 先行扩展、实现未跟上"的场景。该探针期望已同步更新并保持 30/30。

## 5. 短复验（干净克隆 + 全新 venv）

方式：仓库外 `git clone` 检出 `93d3d0b`，Python 3.13.14 全新 venv 按
`requirements.lock.txt` 安装（rc=0），不设置 `PYTHONUTF8`/`PYTHONIOENCODING`
（编码固定在脚本入口，GBK 终端/重定向不再断链）。

| 命令 | 结果 |
|---|---|
| `tools/make_examples.py` | 六包确定性再生，与提交内容零漂移 |
| `tools/stage0_gate.py` | 六包 `ALL_OK=true`（PASS/FAIL/PASS/INDETERMINATE/FAIL/FAIL） |
| `tools/recheck_probes.py` | `RECHECK_PROBES_OK=true`（30/30） |
| `tools/compare_probes.py` | `COMPARE_PROBES_OK=true`（33/33，含 Schema 校验） |
| `tools/selfcheck_guards.py` / `check_schema_consistency.py` / `verify_env.py` | 全绿 |
| `-m geoacceptance.cli validate --bundle examples/clean` | `PASS`（executed=true） |
| `-m geoacceptance.cli regress --html` | `ALL_OK=true` |
| `-m geoacceptance.cli compare --before defective --after corrected` | `LEDGER_INDETERMINATE`（退出码 2，不可比项不得宣称整改完成） |
| `tools/snapshot_results.py` + `compare_snapshots.py` | 冻结快照判定层零差异（几何层仍为已登记的 7 处有依据差异） |

**外部两个反例原样复跑**（`external-round2/stage1_round2_codex_probes.py`，不改一字）：

| 反例 | 修复前 | 修复后 |
|---|---|---|
| `delete_clean_entity` | `LEDGER_CLOSED_ACCEPTED` | **`LEDGER_INDETERMINATE`**，缺失实体 `SD-0001` 阻断 |
| `empty_required_field_config` | `PASS`、`config_rejections=[]` | **`INDETERMINATE`**、`INPUT_SCHEMA_INVALID/R01`、executed=false |

第一轮外部五反例同时复跑，结论全部保持（`LEDGER_OPEN` / `LEDGER_CLOSED_NOT_ACCEPTED` /
`LEDGER_INDETERMINATE` / `LEDGER_INDETERMINATE` / `LEDGER_CLOSED_ACCEPTED`）——上轮成果未回退。

原始输出见 `raw-round3/01～08` 与 `raw-round3/00-install.txt`。

## 6. 未决问题

维持 OPEN_ISSUES 登记口径：S1-01、S1-02、S1-06、S1-07（部分关闭）、S1-08（本轮起阻断
覆盖全量实体差集）、S1-09；完整输入格式与任意复杂包实测未做。**本轮补做参数校验只是
把原门槛做齐，不因此宣告整个 Stage 1 通过**；Stage 2（条款提取与人工确认）待外部复审
结论后再启动，仍不开展模型、多 Agent、网关或 Web。
