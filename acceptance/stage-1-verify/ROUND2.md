# Stage 1 第二轮：外部复核后的定向整改说明

> **归档注（2026-10-26 第三轮）**：第二轮外部复验（Codex）在本轮整改后判定
> "主要路径通过，但整体仍暂不通过"，登记 S1-R2-01 / S1-R2-02 两条 P1。
> 第三轮已定向修复，**现行口径见 `ROUND3.md`**；本文件保留为第二轮的历史记录。
> 本文件中"逐规则参数约束列为后续项"的说法**已过时**（第三轮已接入正式执行入口）。

- 日期：2026-10-26
- 触发：《GeoAcceptance-Stage1-Codex外部复核报告.md》——结论 **Stage 1 暂不通过**，
  阻断点集中在 compare；并要求"保留已通过的空间库替换和回归成果，先定向修复，不进入 Stage 2"。
  原文与本轮复跑见 `external/`。
- 修复提交：**`f593630`**（父提交 `b183849`）
- 本文件是**执行方自验说明**，不是外部验收结论；关闭状态待外部复审确认。

## 0. 范围与边界（先说没做什么）

做了：compare 的关闭证据 / 实体身份 / 规则可比性；正式检查入口与 expected 回归分离；
compare 与 validate 的输出 Schema；两批输入的同等防护；文档现状表述与依赖声明的 Python 范围。

**没有做**（外部复核与用户均要求不扩展）：模型调用、Web、多智能体、网关 —— 未新增任何业务模块；
未新增原因码分类；未改动内核判定口径（六包结论与冻结快照判定层**零差异**，见 §4）。

## 1. 验收对象与复现方式

```bash
git clone <repo> /tmp/ga-r2 && cd /tmp/ga-r2 && git checkout f593630
python -m venv /tmp/ga-r2-venv
/tmp/ga-r2-venv/Scripts/python.exe -m pip install -r requirements.lock.txt   # rc=0
# 全程不设置 PYTHONUTF8 / PYTHONIOENCODING（验证不依赖调用方环境）
PY=/tmp/ga-r2-venv/Scripts/python.exe
$PY tools/make_examples.py && $PY tools/stage0_gate.py
$PY tools/recheck_probes.py --probes-script <外部 stage0 探针>
$PY tools/compare_probes.py
$PY tools/selfcheck_guards.py && $PY tools/check_schema_consistency.py && $PY tools/verify_env.py
$PY -m geoacceptance.cli validate --bundle examples/clean --json work/stage1/validate-clean.json --html work/stage1/validate-clean.html
$PY -m geoacceptance.cli regress --html
$PY -m geoacceptance.cli compare --before defective --after corrected --out work/stage1/compare.json
```

- 环境：**Python 3.13.14 + 全新 venv**（不是复用实现时的 `.venv`），按锁定文件安装 `rc=0`，
  22 个包（含 shapely 2.2.0 / pyproj 3.8.0 / PyYAML 6.0.3 / pydantic 2.14.1 / jsonschema 4.26.0 / geopandas 1.2.0）。
- 原始输出：`raw-round2/00~14`（安装日志、门禁、两套回归、护栏、Schema、ENV、CLI×3、
  外部探针复跑、冻结快照比对）。
- 未执行 Docker（本机无 docker，WSL 被安全策略阻止；S1-01 维持未决）。

## 2. 外部复核逐条整改

### EXT-01（P1）没有有效复验通过证据也能显示 COMPLETE

| 反例 | 修复前 | 修复后（实测） |
|---|---|---|
| blocked → blocked（CRS 声明错误没改） | `COMPLETE`，`counts={}` | `LEDGER_OPEN`，`still_open=1`，条目 `dataset:crs.json｜R07` |
| clean → ambiguous（整改后缺阈值/精度依据） | `COMPLETE`，`counts={}` | `LEDGER_CLOSED_NOT_ACCEPTED`，`after_acceptance=INDETERMINATE`，`scope.unknown_after` 列出未 PASS 条款 |
| 单条过期记录 + R09 改 DRAFT | `fixed=1`、`COMPLETE` | `unresolved_unknown=1`、`LEDGER_INDETERMINATE` |

改了什么：

1. **`closed` 必须有正面证据**：规则仍存在 ∧ `status == APPROVED` ∧ 未被配置校验拒绝 ∧ 有结果 ∧
   `execution_status == COMPLETED` ∧ 规则结论 PASS ∧ 所映射条款 `coverage_state == COVERED` 且 PASS。
   缺任何一条 ⇒ `unresolved_unknown`（**未知不得当成已关闭，也不得当成"没有失败"**）。
2. **数据集级问题不再消失**：身份用「规则身份 + 证据域（file）」，如 `dataset:crs.json｜R07`。
3. **台账同时收"未知"**：整改后仍有缺证据/INDETERMINATE 类码的条目单独判 `unresolved_unknown`。
4. **总体不再叫"整改完成"**：拆成 `ledger`（台账：`CLOSED`/`OPEN`/`INDETERMINATE`）与
   `after_acceptance`（整改后批次自身验收）；`overall` 取四值之一，只有
   `LEDGER_CLOSED_ACCEPTED` 才是"全部验收通过"，`LEDGER_CLOSED_NOT_ACCEPTED`
   只表示"所选失败台账已处理"，**不等于**这批交付可放行。CLI 退出码同理。
5. **候选与未知必须可见**：`DUPLICATE_CANDIDATE` 进 `scope.advisory_after`（不参与关闭）；
   整改后未取得 PASS 的条款进 `scope.unknown_after`。

### EXT-02（P1）删除有缺陷的实体被直接算作修复

- 身份索引改为**全量输入记录**比对：先核对两批实体清单，
  整改后缺失 ⇒ `removed_pending_review`（阻断关闭），新增 ⇒ `entities_added_after` 披露。
- 实测：删实体 ⇒ `removed_pending_review=1`、`entities_removed_after=["SD-0001"]`、`LEDGER_INDETERMINATE`。
- **未实现"批准删除"通道**（S1-08）：没有可追溯的批准政策与审核记录前，一律阻断，不默认放行。

### EXT-03（P2）把 finding 数量当成实体重复次数

- 唯一性只看**输入记录**里 `record_id` 的出现次数；同一实体的多条 finding 挂在同一索引项上。
- 实测：唯一实体同时有 `R04 ENUM_VIOLATION` + `R09 STALE_RECORD` ⇒ 两批 `duplicated=[]`，
  修复后两条均 `closed`（`closure_evidence.rule_execution_status=COMPLETED`），`LEDGER_CLOSED_ACCEPTED`。

### EXT-04（P1）版本比较不足以证明尺子相同

- **规则语义指纹**：`rule_type / status / version / required_for_release / requirement_ids /
  parameters / parameter_sources / preconditions / reviewer / approved_at`（排除 `bundle`、`notes`）。
- **批次制品指纹**：`dictionary.csv`、`area.geojson`、`delivery_spec.md`、
  条款集合与 `support_status`、基准时间 `reference_time`
  （`crs.json` 与 `poi.csv` 是被测数据，不进尺子指纹）。
- 指纹不同 ⇒ `not_comparable`；规则被撤走 ⇒ 单独判定；新增规则 ⇒ 单独披露；
  资格问题（`status != APPROVED`）与尺子变化**分开报**（前者 `unresolved_unknown`，后者 `not_comparable`）。

| 尺子变化用例 | 实测 |
|---|---|
| 同版本改参数：`R02.trim` true→false | `not_comparable`（指纹变化） |
| 改判定阈值：`R09.max_age_days` 30→365 | `not_comparable` + 配置拒绝（来源对不上） |
| 改数据字典：把非法类别加进枚举 | `not_comparable`（`artifacts_changed=dictionary.csv`） |
| 改项目范围：area.geojson 放大 4 倍 | `not_comparable`（`artifacts_changed=area.geojson`） |
| 改基准时间：`R09.reference_time` 前移 | `not_comparable`（12 条全部不可比） |
| 规则删除：整改后没有 R09 | `not_comparable`（`rules_removed_after=R09`） |
| 依赖失效：上游 R03 改 DRAFT | `unresolved_unknown`（下游未 COMPLETED） |
| 批准来源变化：reviewer/approved_at 改 | `not_comparable`（S1-09：该保守口径待业务确认） |
| 新增规则 R11 | 仅披露 `rules_added_after=R11`，R09 仍正常 `closed` |

### §七 正式检查入口与 expected 回归分离

- 新增 `geoacceptance/validate.py` + CLI `validate`：**任意包目录，不需要 expected**，
  含输入防护（存在性 / 20 MiB 上限 / UTF-8）与 findings 三类计数，可出 JSON + HTML。
- 原 `run` 改名 `regress`（示例包 vs 冻结 expected 的**回归工具**）；`run` 子命令已删除
  （干净克隆里 `cli run` 退出码 2，见 `raw-round2/11-cli-old-run.txt`）。
- `compare --before/--after` 也接受目录（不只在 `examples/` 下找包名）。
- 实测：examples 外的新包 `/tmp/newpkg` ⇒ `validate` 给出 PASS，`expected_used=false`；
  注入过期时间的新包 ⇒ FAIL 且 `findings_by_class.FAIL ≥ 1`（结论来自内核判定，不是 expected 比对）。

## 3. 第二轮回回归结果（干净克隆 + 全新 venv，Python 3.13.14）

| 套件 | 结果 | 原始输出 |
|---|---|---|
| `tools/make_examples.py` | rc=0，六包生成与仓库一致（`git status` 无改动） | `01` |
| `tools/stage0_gate.py`（六包） | `ALL_OK=true`，PASS/FAIL/PASS/INDETERMINATE/FAIL/FAIL | `02` |
| `tools/recheck_probes.py` | **30/30**（新增 `S1_validate_entry_new_bundle`、`S1_compare_closure_evidence`；CLI 冒烟改测 validate/regress） | `03` |
| `tools/compare_probes.py`（新） | **18/18**（五个外部反例 + 七组尺子变化 + 披露类 + 正例对照 + validate），输出全部通过 `schemas/stage1_compare.schema.json` | `04`、`04b` |
| `selfcheck_guards` / `check_schema_consistency` / `verify_env` | `GUARDS_OK=true` / `SCHEMA_CONSISTENT=true` / `ENV_VERIFY_OK=true` | `05`、`06`、`07` |
| CLI `validate` / `regress` / `compare` | rc=0 / rc=0（`ALL_OK=true`） / rc=2（`LEDGER_INDETERMINATE`） | `08`、`09`、`10` |
| 外部复核的五个反例（用外部脚本原样复跑） | 见 §2 表格，**无一再判为已完成** | `12`、`12b` |
| 冻结快照比对 | 判定层（规则/条款/总体/findings）**零差异**；几何层仍是第一轮已登记的 7 处有依据差异 | `14` |

`defective → corrected`（正例对照）保持既有结论不变：
`closed=8`、`not_comparable=1`（`SD-0005` 本身是重复 ID，身份无法建立）⇒ `LEDGER_INDETERMINATE`，
**不宣称整改完成**。

## 4. 未解决（如实登记，不写成已通过）

| ID | 级别 | 问题 | 状态 |
|---|---|---|---|
| S1-01 | P2 | Docker 冒烟未做（本机无 docker，WSL 被安全策略阻止） | 维持未决；替代证据＝本轮"干净克隆 + 全新 venv"复现 |
| S1-02 | P2 | 外部方原 Stage 0 探针仍用已删除的二参 `aggregate` | 仓库侧不保留第二判定路径；迁移待外部方 |
| S1-07 | P3 | 锁文件未出 3.11 专用版本 | **部分关闭**：README 与 `requirements.txt`/`lock` 已写明实测范围（3.13.14 可装、3.11.9 装不上 numpy==2.5.4），并强调"代码兼容 ≠ 锁文件可复现" |
| S1-08 | P3 | 删除实体缺少"批准删除"政策通道 | 新增；政策落地前一律 `removed_pending_review` |
| S1-09 | P3 | 规则重新批准（reviewer/approved_at 变化）会阻断关闭 | 新增；按外部复核 §六把批准来源纳入指纹的**保守**口径，待业务确认是否降为"仅披露" |
| S1-06 | P3 | geopandas 仅做运行验证，未进入判定链路 | 维持未决 |
| — | — | ~~完整输入格式 / 逐规则参数约束~~ / 任意复杂包的实测 | **逐规则参数约束已在第三轮接入正式执行入口**（S1-R2-01，见 `ROUND3.md`）；完整输入格式与任意复杂包实测仍未做，不视为完成整个 Stage 1 |

## 5. 独立性说明

本轮与实现在同一会话内完成，**独立性弱于外部复核**。为压低自证偏差：
① 仓库外干净克隆并检出固定 commit；② 全新虚拟环境（非实现时的 `.venv`）；
③ 五个外部反例直接用外部脚本原样复跑（不改写预期）；④ 预期值写在跑之前。
**建议仍由外部方复审**，不得把本轮当成"外部验收已通过"。
