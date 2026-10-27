# 示例包 expected 真值审核记录（Stage 0 重验）

- 版本：v1.0（2026-10-26）
- 编制：严过关（QA，Stage 0 重验，任务 T05）
- 契约依据：`docs/stage0-recheck-contract.md`（**唯一契约来源，本文件不得与其冲突**）
- 覆盖范围：`examples/{clean, defective, corrected, ambiguous, blocked, crs_same_unit_wrong}/expected/`

---

## 0. 先说清楚这份文件是干什么的

上一轮独立验收给了两条硬意见，本文件是这两条的直接落地：

1. 「主门禁只比结论与缺陷数，命中错行但数量相同可能通过」——> 门禁已升级为**记录级比对**（契约 §9.4），
   `expected/aggregate.json` 的 `per_rule` 必须由 `[verdict, findings]` 升级为完整对象，否则新比对器会把
   绝大多数字段判为「未登记」而失去比对意义。
2. 「示例生成器会同时重写数据和期望，不能把『重生成后全过』当独立真值证明」——> 本文件逐条记录
   **人是怎么推出这个 expected 的**，以及**本轮相对原始版本改了哪几条、凭什么改**。

### 红线（本轮自我约束，违反即返工）

- **不得为了让门禁变绿而修改任何判定语义。** 判定实现的改动只有一条（见 §3.7），且不是本文件负责的 expected 改动。
- **expected 的每一处改动都必须在本文件 §3 的登记表里有对应条目**，写明：文件路径 / 字段名 / 旧值 / 新值 / 理由编号。
  **表外任何改动视为违规。**
- **任何一条改动都不得放松结论**：`PASS / FAIL / PASS / INDETERMINATE / FAIL / FAIL` 六个总体结论与
  `1 / 11 / 1 / 1 / 1 / 1` 六个缺陷数在本轮前后完全不变（见 §5）。
- `python tools/make_examples.py` 只用于**重建输入包**，不得用于**回填 expected**。本文件的登记表
  是 expected 改动的唯一授权来源；重生成后的 `git diff` 必须逐条可回溯到 §3（核对结果见 §6）。

---

## 1. 审核信息与审核方式

| 项 | 内容 |
|---|---|
| 审核人 | 严过关（QA，Stage 0 重验） |
| 审核日期 | 2026-10-26 |
| 审核方式 | **先写期望，再跑实现**。逐条按 `examples/README.md` 缺陷真值表 + `docs/stage0-recheck-contract.md` 人工推导；实现输出与推导**不一致即视为实现缺陷并上报**，不反向改期望去迁就实现。 |
| 推导依据 | 各包 `delivery_spec.md` 的冻结条款行（行号 + `source_quote` + `document_sha256`）、`INPUT_MANIFEST.json` 哈希、`examples/README.md` 缺陷真值表 |
| 可回溯性 | 每条数字都能落到具体数据行号（如 defective 的 11 条缺陷逐条对应 `poi.csv` 第 3/4/6/7/8/10/11/12/13/14/15 行） |
| 审核字段 | `per_rule` 的 `verdict / execution_status / reason_code / 六个统计字段 / findings / failure_reason_codes / advisory_reason_codes`；`expected/findings.json` 的 `stable_key / reason_code / field / observed_value / review_state / execution_status / record_locator.{file,line,record_id}`；`expected/clause_coverage.json` 的 `requirement_id / coverage_state / verdict / execution_status / reason_code / failure_reason_codes / advisory_reason_codes` |

**独立推导的交叉验证（不经过 `stage0_gate.py`）**：本轮用一次性脚本直接从 `poi.csv` 重算了一遍
空值 / 重复 ID / 枚举越界 / 数值不可解析 / 经纬度越界 / 时间格式 / 超时阈值，得到的事实集合与
`work/stage0/*/findings.json` 逐条一致（defective 11 条、clean 1 条、corrected 1 条、ambiguous 1 条、
blocked 1 条、crs_same_unit_wrong 1 条）。这一步只是**核对**，不是真值来源——真值来源是上面的条款与真值表。

---

## 2. 逐包人工推导（结论与缺陷数：本轮前后不变）

| 包 | 总体结论 | 缺陷数 | 推导要点 |
|---|---|---|---|
| `clean` | PASS | 1 | 12 行，A1–A5/B1/B2/B3/C1 全部有完整 PASS 证据；C2 非必检，R10 产出 1 组重复候选（SD-0011/SD-0012，实测距离 20.36 m ≤ 30 m 且同名），按契约 §7.2 候选**不是失败**，计 `records_indeterminate=2`，不阻断放行。 |
| `defective` | FAIL | 11 | 15 行。R02 空值 2（第 8 行 category、第 11 行 longitude）→ R03 类型 2（第 3 行时间无 T、第 14 行 longitude=abc，第 8/11 行被 R02 阻断不伪执行）→ R04 枚举 1（第 4 行 公共厕所）→ R05 重复 ID 2（第 6/13 行 SD-0005）→ R06 纬度越界 1（第 10 行 91.5）→ R08 出界 1（第 12 行 116.36）→ R09 超期 1（第 7 行 61 天 > 30 天）→ R10 候选 1（第 15/16 行 14.01 m）。2+2+1+2+1+1+1+1 = 11。 |
| `corrected` | PASS | 1 | 15 行，defective 的可整改缺陷全部修完；保留 SD-0011/SD-0012 这组候选（R10 非必检，可见但不阻断）。 |
| `ambiguous` | INDETERMINATE | 1 | 12 行，A1–C1 与 clean 一致；D1/D2 原文「数据应及时更新」「坐标精度应满足项目要求」**没有可判定阈值**，`support_status=NEEDS_CLARIFICATION`，规则保持 DRAFT 不得批准（契约 §3.2 的 `UNAPPROVED`/未映射分支），结论为不可放行。 |
| `blocked` | FAIL | 1 | 12 行。真值依据是**可证明的声明冲突**：`delivery_spec.md` 第 16 行 B2 原文「本批次声明为 EPSG:4326」（该行 `source_quote` 已冻结且哈希校验通过）vs `crs.json` 提交 `EPSG:3857`。按契约 §4.2 判 `FAIL / CRS_DECLARATION_MISMATCH`；依赖 CRS 的 R06/R08/R10 按 §4.4 全批阻断。坐标量级**只作风险信号**（`CRS_MAGNITUDE_RISK`，`degree_like_records=12`），不参与判定。 |
| `crs_same_unit_wrong` | FAIL | 1 | 12 行，手写反例包。声明单位与要求**同为 degree**，但 CRS 声明为 `EPSG:4490` ≠ 要求的 `EPSG:4326`。用于钉死「只看单位不看 CRS」或「按量级猜 CRS」这类回退实现（契约 §4.5）。expected 为人工先写、再跑实现。 |

---

## 3. expected 改动登记表（**表外无改动**）

共 **6 类**、落到 6 个包。逐条登记如下。

### 3.1 第 1 类｜`blocked` 的 R06/R08/R10：`UNKNOWN` → `INDETERMINATE`（理由编号 GA-06）

| 文件 | 字段 | 旧值 | 新值 | 理由 |
|---|---|---|---|---|
| `examples/blocked/expected/aggregate.json` | `per_rule.R06.verdict` | `UNKNOWN` | `INDETERMINATE` | 契约 §1.1 废止 `UNKNOWN`；`UNKNOWN` 不在 `schemas/check_result.schema.json` 枚举内，属 P1 契约违规（GA-06）。`execution_status` 仍为 `BLOCKED`、`reason_code=ALL_RECORDS_BLOCKED`，「没跑成」的信息搬到了状态字段，没有丢失。 |
| 同上 | `per_rule.R08.verdict` | `UNKNOWN` | `INDETERMINATE` | 同上 |
| 同上 | `per_rule.R10.verdict` | `UNKNOWN` | `INDETERMINATE` | 同上 |

**是否放松结论：否。** `UNKNOWN` 与 `INDETERMINATE` 都表示不可放行；改动只是词汇迁移（契约 §1.4 迁移对照第 1 行）。
`total=12 / evaluated=0 / skipped_upstream=12` 三个统计口径本轮前后一致。

### 3.2 第 2 类｜`blocked` 的真值依据措辞：量级冲突 → 声明冲突（理由编号 GA-03）

| 文件 | 字段 | 旧值 | 新值 | 理由 |
|---|---|---|---|---|
| `examples/blocked/expected/aggregate.json` | `note` | `「CRS 声明与坐标量级冲突：判定 FAIL，依赖 CRS 的空间检查全部阻断为 UNKNOWN，不自动纠偏。」` | `「声明冲突（原文 B2 要求 EPSG:4326，提交为 EPSG:3857）：判定 FAIL，依赖 CRS 的空间检查全部阻断为 INDETERMINATE，不自动纠偏。坐标量级只作风险信号，不参与判定。」` | GA-03：原依据（用坐标量级猜测 CRS 声明错误）被独立验收方判定为**知识性错误**——EPSG:3857 下原点附近的小值坐标同样合法，量级不能证明声明错误。契约 §4.5 要求换成可证明的声明冲突。`examples/blocked/crs.json` 的 `note` 已由 T04 同步改写；本条是 expected 侧的措辞同步。 |

**是否放松结论：否。** 结论仍为 `FAIL`，R06/R08/R10 仍阻断；改的只是「凭什么说它 FAIL」。

### 3.3 第 3 类｜`ambiguous` 的 D1/D2：`UNKNOWN` → `INDETERMINATE`（理由编号 GA-06）

| 文件 | 字段 | 旧值 | 新值 | 理由 |
|---|---|---|---|---|
| `examples/ambiguous/expected/aggregate.json` | `per_rule.D1.verdict` | `UNKNOWN` | `INDETERMINATE` | 同 3.1（GA-06）。`execution_status=NOT_EXECUTED`、`reason_code=NOT_APPROVABLE_NO_THRESHOLD`、`total=0`（一行都没看，与「看了但没判成」区分，见 `zero_counts()` 注释）。 |
| 同上 | `per_rule.D2.verdict` | `UNKNOWN` | `INDETERMINATE` | 同上 |
| 同上 | `note` | `「…规则不得批准，保持未知，不作为通过证据。」` | `「…规则不得批准，保持 INDETERMINATE，不作为通过证据。」` | 同 3.1 的词汇迁移，避免 `note` 与 `verdict` 字段用词不一致造成误解。 |

**是否放松结论：否。** 仍为不可放行。

### 3.4 第 4 类｜`per_rule` 升级为记录级对象 + 新增两个 expected 文件（验收方「自检证据的限制」第 2 条）

| 文件 | 字段 | 旧值 | 新值 | 理由 |
|---|---|---|---|---|
| 全部 6 包 `expected/aggregate.json` | `per_rule.<RID>` | `[verdict, findings]` 二元组数组 | 对象：`{verdict, execution_status, reason_code, records_total, records_evaluated, records_failed, records_indeterminate, records_skipped_upstream, records_uninterpretable, findings}` | 契约 §9.4：主门禁只比结论与缺陷数时，「命中错行但数量相同」会通过。升级为记录级后逐字段比对（6 个统计字段 + `reason_code` + `execution_status`）。**比对变严，不是放松。** |
| 全部 6 包 | `expected/findings.json` | 无此文件 | 新增：逐条登记 `stable_key / reason_code / field / observed_value / review_state / execution_status / record_locator.{file,line,record_id}` | 验收方「自检证据的限制」第 2 条：只比数量不足以证明命中的是**正确的那一条**。逐条比对 finding 的属性与定位。 |
| 全部 6 包 | `expected/clause_coverage.json` | 无此文件 | 新增：逐条登记 `requirement_id / coverage_state / verdict / execution_status / reason_code` | 契约 §3.5：总体聚合以**必检条款全集 U 的覆盖结果**为唯一输入，因此覆盖记录必须与规则结果一样被冻结核对。 |

**是否放松结论：否。** 比对项从 2 项增加到 20+ 项，且新增 finding 级与条款级两层比对，只会更严。

### 3.5 第 5 类｜每个 expected 增加 `truth_review` 字段（验收方「自检证据的限制」第 3 条）

| 文件 | 字段 | 旧值 | 新值 | 理由 |
|---|---|---|---|---|
| 全部 6 包 `expected/aggregate.json`、`expected/findings.json`、`expected/clause_coverage.json` | `schema_version` / `truth_source` / `truth_review` | 无 | `schema_version="stage0-2"`、`truth_source="人工推导"`、`truth_review={reviewer, date, method, basis, reviewed_fields}` | 契约 §9.6：保留**人工真值审核记录**（谁审的、什么时候、怎么审的、依据什么）。字段内容与本文件 §1 一致。 |

### 3.6 第 6 类｜`clean` 的 R10 统计口径修正（理由编号 GA-07）

| 文件 | 字段 | 旧值 | 新值 | 理由 |
|---|---|---|---|---|
| `examples/clean/expected/aggregate.json` | `per_rule.R10.records_evaluated` | `11`（旧口径：把候选行当「未执行」扣掉了） | `12` | GA-07：候选不是失败、也不是阻断（契约 §7.2）。全批 12 行都做了距离计算，就应该算 12 行已评估。 |
| 同上 | `per_rule.R10.records_indeterminate` | 无此字段 | `2`（SD-0011、SD-0012） | 契约 §7.1：候选涉及行进 `records_indeterminate`。 |
| 同上 | `per_rule.R10.records_failed` | 无此字段 | `0` | 候选**不是失败**，`records_failed` 必须为 0。 |
| 同上 | `per_rule.R10.records_skipped_upstream` | 无此字段（旧口径隐含 `records_blocked=1`） | `0` | 契约 §5.3：候选不向下游传播阻断，因此没有行被跳过。 |
| 同上 | `per_rule.R10.records_uninterpretable` | 无此字段 | `0` | 该规则对全部 12 行都拿出了结论（候选也是结论）。 |
| 同上 | `per_rule.R10.findings` | `1` | `1`（不变） | 1 组候选 = 1 条 finding，覆盖 2 行。 |

**是否放松结论：否。** R10 规则级仍为 `INDETERMINATE`（不可放行），总体仍为 `PASS`（R10 覆盖的 C2 为非必检条款）。
改的是「已评估/待定/跳过」这三类互斥口径的归属，符合契约 §7.1 的 I1–I3。

### 3.7 附：本轮唯一一条判定实现改动（**不属于 expected 改动**，登记在此以示可追溯）

| 文件 | 改动 | 裁决人 | 理由 |
|---|---|---|---|
| `tools/stage0_gate.py` | `TIMEZONE_UNDECLARED` 从 `FAIL_REASON_CODES` 移到 `INDETERMINATE_REASON_CODES` | 主理人（2026-10-26） | `docs/rule-semantics.md` R09 行写「无时区信息 ⇒ `TIMEZONE_UNDECLARED` 并**按未定处理**」，与契约 §0 公理 A2（缺观测 ⇒ INDETERMINATE）一致；实现此前先补 `tzinfo=utc` 继续算再产 finding，实际按 FAIL 处理，与文档冲突。 |

该改动对六个包**零影响**（见 §6 的核对与 §7 的 grep 证据）：本项目采用 RFC3339 子集，`parse_value()`
的 `ISO8601` 正则要求显式时区，不带时区的时间戳先被判 `TYPE_PARSE_ERROR`，`TIMEZONE_UNDECLARED`
分支在现有样例中不可达。

---

## 4. 明确**没有**改的东西（防止下一个人误以为放宽了）

| 项 | 状态 |
|---|---|
| 六个包的 `aggregate_verdict` | 未改：PASS / FAIL / PASS / INDETERMINATE / FAIL / FAIL |
| 六个包的 `findings` 条数 | 未改：1 / 11 / 1 / 1 / 1 / 1 |
| `per_rule.<RID>.verdict` 中除 §3.1/§3.3 那 5 条之外的全部取值 | 未改 |
| 六个包的 `per_rule.<RID>.reason_code` / 条款级 `reason_code`（§3.9 的 24 条） | **只换值，不换结论**：`verdict` / `execution_status` / 六个统计字段 / `findings` 一条未动；新值受 I7–I9 约束，比旧值更严（见 §3.9 开头三条判断依据） |
| 六个包的 `failure_reason_codes` / `advisory_reason_codes`（§3.10） | 纯新增证据字段，不参与判定语义；原字段一条未改 |
| `defective` 的 `blocked_findings_at_least: {R03: 1}` | 未改（本轮不新增此类登记项） |
| 六个包的输入数据（`poi.csv` / `crs.json` / `delivery_spec.md` / `requirements.yaml` / `approved-rules.yaml` / `dictionary.csv` / `area.geojson`） | 未改（除 §3.8 的 A3 `interpretation` 补字段，见下） |
| `examples/crs_same_unit_wrong` 的 expected 结论 | 未改（本轮只做 `per_rule` 结构升级 + `truth_review`，结论与缺陷数原样） |

### 3.8 补登记：A3 条款的 `interpretation` 字段（非 expected 改动，但影响输入包哈希）

| 文件 | 字段 | 旧值 | 新值 | 理由 |
|---|---|---|---|---|
| 6 个包 `requirements.yaml` 的 A3 条款 | `interpretation` | 无 | `「本项目采用 ISO8601 的 RFC3339 子集：必须带 T 分隔符与显式时区（Z 或 ±HH:MM）。这是本项目采用的格式子集，不是 ISO8601 标准的全部。」` | 契约 §9.3（验收方点名）：把开放式「ISO8601」收紧成只接受 T 且强制时区，必须在要求里写明**这是本项目子集**，不得把实现限制说成整个标准。`schemas/requirement.schema.json` 已有该字段。 |
| `tools/make_examples.py` | `CLAUSE_INTERPRETATIONS` 常量 + `requirements` 生成逻辑 | 无 | 为 A3 注入上述 `interpretation` | 生成脚本与包内容必须一致，否则重生成会静默改回。 |
| `examples/INPUT_MANIFEST.json` | `requirements.yaml` 哈希 + 新增 `expected/findings.json`、`expected/clause_coverage.json` 两个条目 | — | 重算 | 由 `make_examples.py` 生成，不手改。新增两个 expected 条目是为了让**真值文件本身也被哈希冻结**（防止改真值不被发现）。 |

### 3.9 第 7 类｜`reason_code` 全链路取值修正（**24 条**，理由：契约 §3.5.1 + 不变式 I7–I9）

**背景**：§8 记录的那处"FAIL 条款的 `reason_code` 是 `OK`"已由工程师修复（提交 `9af939b` → `f433286` → `1fd2b21`），
并扩大为**规则级 + 条款级全链路**断言。修复后原来的 expected 登记值失效，本条逐条登记新真值。

**新取值规则（契约 §3.5.1，不变式 I7–I9）**：

- I7：`PASS` ⇒ `reason_code == "OK"`（`OK` **只**能出现在 PASS 上）；
- I8：`FAIL` ⇒ 第一条 **FAIL 类** finding 的码（不得是 `OK`、也不得是候选/缺证据类码）；
- I9：`INDETERMINATE` ⇒ 覆盖态码 / 上游码 / `ALL_RECORDS_BLOCKED` / 缺证据类码 / 候选类码，
  **绝不回退 `OK`**；
- 取值链优先级（`INDETERMINATE`）：缺证据类码 → 上游码 / `ALL_RECORDS_BLOCKED` → 候选类码 → `CONTRACT_VIOLATION` 兜底。

**是否放松结论：否，全部 24 条都不是。** 判断依据有三条，逐条核对过：

1. 全部是**字段级替换**：`verdict` / `execution_status` / 六个统计字段 / `findings` 一条都没动；
2. 总体结论与缺陷数前后完全不变（见 §5，仍是 `PASS/FAIL/PASS/INDETERMINATE/FAIL/FAIL`、`1/11/1/1/1/1`）；
3. 新值比旧值**更严**：旧值 `OK` 会让"失败"和"通过"在 `reason_code` 上无法区分（这正是 S0-R1 的问题），
   新值强制每个 FAIL/INDETERMINATE 都带可追溯原因码。

**独立核实方式（未采信工程师清单）**：先跑 `python tools/stage0_gate.py`，再从
`work/stage0/<bundle>/expected_diff.json` 逐包枚举 `[FIELD]` 差异，与工程师给出的 24 条清单比对——
**恰好 24 条，逐条一致**（clean 1 / defective 15 / corrected 1 / ambiguous 3 / blocked 2 / crs_same_unit_wrong 2）。

#### 3.9.1 规则级 `per_rule.<RID>.reason_code`（15 条）

| # | 文件 | 字段 | 旧值 | 新值 | 推导依据 | 放松结论？ |
|---|---|---|---|---|---|---|
| 1 | `examples/clean/expected/aggregate.json` | `per_rule.R10.reason_code` | `OK` | `DUPLICATE_CANDIDATE` | I9：R10 是 INDETERMINATE，只有候选类 finding ⇒ 取候选类码（取值链最末档）。`OK` 在 INDETERMINATE 上非法（I9） | 否 |
| 2 | `examples/defective/expected/aggregate.json` | `per_rule.R02.reason_code` | `OK` | `EMPTY_VALUE` | I8：第一条 FAIL 类 finding = 第 8 行 category 空值 ⇒ `EMPTY_VALUE` | 否 |
| 3 | 同上 | `per_rule.R03.reason_code` | `OK` | `TYPE_PARSE_ERROR` | I8：第 3 行时间无 T、第 14 行 longitude=abc ⇒ 首条为 `TYPE_PARSE_ERROR` | 否 |
| 4 | 同上 | `per_rule.R04.reason_code` | `OK` | `ENUM_VIOLATION` | I8：第 4 行 category=公共厕所 越界 ⇒ `ENUM_VIOLATION` | 否 |
| 5 | 同上 | `per_rule.R05.reason_code` | `OK` | `DUPLICATE_ID` | I8：第 6/13 行 SD-0005 重复 ⇒ 首条 `DUPLICATE_ID` | 否 |
| 6 | 同上 | `per_rule.R06.reason_code` | `OK` | `LATITUDE_OUT_OF_RANGE` | I8：第 10 行 latitude=91.5 ⇒ `LATITUDE_OUT_OF_RANGE` | 否 |
| 7 | 同上 | `per_rule.R08.reason_code` | `OK` | `OUTSIDE_PROJECT_AREA` | I8：第 12 行 longitude=116.36 出界 ⇒ `OUTSIDE_PROJECT_AREA` | 否 |
| 8 | 同上 | `per_rule.R09.reason_code` | `OK` | `STALE_RECORD` | I8：第 7 行 61 天 > 30 天 ⇒ `STALE_RECORD` | 否 |
| 9 | 同上 | `per_rule.R10.reason_code` | `OK` | `ALL_RECORDS_BLOCKED` | I9 取值链：R10 同时有候选（2 行）与上游阻断（5 行），**上游码/ALL_RECORDS_BLOCKED 先于候选码** ⇒ `ALL_RECORDS_BLOCKED`（不是 `DUPLICATE_CANDIDATE`） | 否 |
| 10 | `examples/corrected/expected/aggregate.json` | `per_rule.R10.reason_code` | `OK` | `DUPLICATE_CANDIDATE` | I9：整改后只剩 SD-0011/SD-0012 一组候选，无阻断 ⇒ 候选类码 | 否 |
| 11 | `examples/ambiguous/expected/aggregate.json` | `per_rule.R10.reason_code` | `OK` | `DUPLICATE_CANDIDATE` | I9：同 #1 | 否 |
| 12 | `examples/ambiguous/expected/aggregate.json` | `per_rule.D1.reason_code` | `NOT_APPROVABLE_NO_THRESHOLD` | `CLAUSE_NOT_COVERED_BY_RULE` | §3.5.1 追加项 2：兼容条目必须与**权威口径** `build_clause_coverage()` 用同一个码。D1/D2 在权威口径里是"未映射的必检条款"，统一用 `CLAUSE_NOT_COVERED_BY_RULE`。旧码是规则自有码，与条款级分叉 | 否（同为规则级专用码，只是统一口径） |
| 13 | 同上 | `per_rule.D2.reason_code` | `NOT_APPROVABLE_NO_THRESHOLD` | `CLAUSE_NOT_COVERED_BY_RULE` | 同 #12（D2 与 D1 同因同果） | 否 |
| 14 | `examples/blocked/expected/aggregate.json` | `per_rule.R07.reason_code` | `OK` | `CRS_DECLARATION_MISMATCH` | I8：规则级唯一 FAIL finding 的码（声明冲突 EPSG:3857 ≠ 要求 EPSG:4326） | 否 |
| 15 | `examples/crs_same_unit_wrong/expected/aggregate.json` | `per_rule.R07.reason_code` | `OK` | `CRS_DECLARATION_MISMATCH` | I8：同 #14（声明 `EPSG:4490` ≠ 要求 `EPSG:4326`） | 否 |

#### 3.9.2 条款级 `expected/clause_coverage.json[].reason_code`（9 条）

| # | 文件 | `requirement_id` | 旧值 | 新值 | 推导依据 | 放松结论？ |
|---|---|---|---|---|---|---|
| 16 | `defective` | `A2` | `OK` | `EMPTY_VALUE` | I8：条款级取第一条 FAIL 类 finding 的码（映射规则 R02） | 否 |
| 17 | `defective` | `A3` | `OK` | `TYPE_PARSE_ERROR` | I8（R03） | 否 |
| 18 | `defective` | `A4` | `OK` | `ENUM_VIOLATION` | I8（R04） | 否 |
| 19 | `defective` | `A5` | `OK` | `DUPLICATE_ID` | I8（R05） | 否 |
| 20 | `defective` | `B1` | `OK` | `LATITUDE_OUT_OF_RANGE` | I8（R06） | 否 |
| 21 | `defective` | `B3` | `OK` | `OUTSIDE_PROJECT_AREA` | I8（R08） | 否 |
| 22 | `defective` | `C1` | `OK` | `STALE_RECORD` | I8（R09） | 否 |
| 23 | `blocked` | `B2` | `OK` | `CRS_DECLARATION_MISMATCH` | I8：声明冲突（B2 原文 EPSG:4326 vs 提交 EPSG:3857）⇒ 唯一 FAIL finding 的码 | 否 |
| 24 | `crs_same_unit_wrong` | `B2` | `OK` | `CRS_DECLARATION_MISMATCH` | I8：声明 `EPSG:4490` ≠ 要求 `EPSG:4326`（单位同为 degree，量级不作证据） | 否 |

> **合计口径**：规则级 15 条（#1–#15）+ 条款级 9 条（#16–#24）= **24 条**。
> 按包分：clean 1 / defective 15（规则级 8 + 条款级 7）/ corrected 1 / ambiguous 3 / blocked 2 /
> crs_same_unit_wrong 2 —— 与 `COMMANDS.md` C11 的语义级比对输出逐条一致。
>
> **一处容易误读的地方（如实记录）**：`ambiguous` 的**条款级** D1/D2 在本轮**没有变化**——
> 工程师 `f433286` 已把 `clause_coverage` 侧对齐为 `CLAUSE_NOT_COVERED_BY_RULE`，本轮同步的
> 只是**规则级**（`per_rule.D1/D2`）那两条。这正是判据 12 想要的状态：两处口径一致。

### 3.10 第 8 类｜新增两个字段 `failure_reason_codes` / `advisory_reason_codes`（18 处非空登记）

**理由**：契约 §3.5.1 要求"第一条 FAIL 类 finding 的码"，而"第一条"的定义（§3.5.2）是
**排放顺序**（拓扑规则序 × 行号升序），不是行号重排。要能验证这一点，expected 必须登记**完整码序列**，
而不只是首码。§3.5.2 同时要求这两个数组**去重、保留首次出现顺序**（不是多重集——几处失败由统计字段承载）。

**是否放松结论：否。** 这两个字段是**新增**的证据字段，不参与任何判定语义；原字段一条未改。
它们只会让比对更严：多出一组此前完全没被比对的字段。

| # | 文件 | 字段 | 旧值 | 新值 | 推导依据 | 放松结论？ |
|---|---|---|---|---|---|---|
| 25 | `defective/expected/aggregate.json` | `per_rule.R02.failure_reason_codes` | 无 | `["EMPTY_VALUE"]` | 该规则 FAIL finding 的码序列（去重后仅 1 个：2 条空值同为 `EMPTY_VALUE`） | 否 |
| 26 | 同上 | `per_rule.R03.failure_reason_codes` | 无 | `["TYPE_PARSE_ERROR"]` | 同上（2 条同为 `TYPE_PARSE_ERROR`） | 否 |
| 27 | 同上 | `per_rule.R04.failure_reason_codes` | 无 | `["ENUM_VIOLATION"]` | 1 条 | 否 |
| 28 | 同上 | `per_rule.R05.failure_reason_codes` | 无 | `["DUPLICATE_ID"]` | 2 条同码 | 否 |
| 29 | 同上 | `per_rule.R06.failure_reason_codes` | 无 | `["LATITUDE_OUT_OF_RANGE"]` | 1 条 | 否 |
| 30 | 同上 | `per_rule.R08.failure_reason_codes` | 无 | `["OUTSIDE_PROJECT_AREA"]` | 1 条 | 否 |
| 31 | 同上 | `per_rule.R09.failure_reason_codes` | 无 | `["STALE_RECORD"]` | 1 条 | 否 |
| 32 | `defective/expected/clause_coverage.json` | `A2.failure_reason_codes` | 无 | `["EMPTY_VALUE"]` | 条款级同步携带（映射规则 R02） | 否 |
| 33 | 同上 | `A3.failure_reason_codes` | 无 | `["TYPE_PARSE_ERROR"]` | R03 | 否 |
| 34 | 同上 | `A4.failure_reason_codes` | 无 | `["ENUM_VIOLATION"]` | R04 | 否 |
| 35 | 同上 | `A5.failure_reason_codes` | 无 | `["DUPLICATE_ID"]` | R05 | 否 |
| 36 | 同上 | `B1.failure_reason_codes` | 无 | `["LATITUDE_OUT_OF_RANGE"]` | R06 | 否 |
| 37 | 同上 | `B3.failure_reason_codes` | 无 | `["OUTSIDE_PROJECT_AREA"]` | R08 | 否 |
| 38 | 同上 | `C1.failure_reason_codes` | 无 | `["STALE_RECORD"]` | R09 | 否 |
| 39 | `blocked/expected/aggregate.json` | `per_rule.R07.failure_reason_codes` | 无 | `["CRS_DECLARATION_MISMATCH"]` | 1 条声明冲突 | 否 |
| 40 | `blocked/expected/clause_coverage.json` | `B2.failure_reason_codes` | 无 | `["CRS_DECLARATION_MISMATCH"]` | R07 | 否 |
| 41 | `crs_same_unit_wrong/expected/aggregate.json` | `per_rule.R07.failure_reason_codes` | 无 | `["CRS_DECLARATION_MISMATCH"]` | 同 #39 | 否 |
| 42 | `crs_same_unit_wrong/expected/clause_coverage.json` | `B2.failure_reason_codes` | 无 | `["CRS_DECLARATION_MISMATCH"]` | 同 #40 | 否 |

| 43 | 6 个包 `expected/aggregate.json` | `truth_review.reviewed_fields` | 旧文案未含两个新字段 | 追加 `failure_reason_codes / advisory_reason_codes` | 与 §1「审核字段」保持一致：`truth_review` 声明"审了哪些字段"，新增字段必须写进去，否则声明与内容不符 | 否（纯描述性元数据） |

**其余全部条目（含 6 个包的所有 PASS 规则/条款）登记为空数组 `[]`——这是如实登记，不是"没登记"。**
六包合计：非空 `failure_reason_codes` **18 处**；`failure_reason_codes` / `advisory_reason_codes`
两个键在 118 个条目上首次出现（其中 advisory 全部为空数组）。

**`advisory_reason_codes` 六包全部为空数组 `[]`，这是本次核实发现的一处覆盖缺口，如实记录**：
六个示例包中**没有任何一条"缺证据类"finding**（`CRS_MISSING_DECLARATION` / `TIMEZONE_UNDECLARED`），
六个包里所有规则级 INDETERMINATE 都由「上游阻断 / 全批阻断 / 候选 / 未映射」产生，
走的是 §3.5.1 取值链的**上游码与候选类码**分支，不走缺证据类分支。
因此：

- §3.5.1 取值链中"缺证据类码"这一档**在示例包中没有正例**；
- `advisory_reason_codes` 的"去重 + 首次出现顺序"（§3.5.2）也**没有多元素正例**。

已作为 `acceptance/stage-0-recheck/OPEN_ISSUES.md` 的 **S0-R6** 登记（与"coverage_state 六态中四态无正例"同类）。
本轮**不**为了让文件好看而编造一个假包：新增示例包属于输入变更，超出 T05 的授权范围。

---

## 5. 结论与缺陷数前后对照（红线自检）

| 包 | 结论（前 → 后） | 缺陷数（前 → 后） |
|---|---|---|
| clean | PASS → PASS | 1 → 1 |
| defective | FAIL → FAIL | 11 → 11 |
| corrected | PASS → PASS | 1 → 1 |
| ambiguous | INDETERMINATE → INDETERMINATE | 1 → 1 |
| blocked | FAIL → FAIL | 1 → 1 |
| crs_same_unit_wrong | FAIL → FAIL | 1 → 1 |

---

## 6. 重生成核对（防止「重跑一遍全绿」冒充真值证明）

命令：

```
python tools/make_examples.py
git diff --stat examples/
git diff --numstat examples/*/expected/
python tools/stage0_gate.py
```

判据与实测结果（本轮完成后填写，见 §7）：

- ✅ 重生成只应改动 §3.8 登记的 `requirements.yaml`（A3 `interpretation`）与 `INPUT_MANIFEST.json`；
- ✅ `git diff examples/*/expected/` 的每一处差异都能回溯到 §3.1–§3.6；
- ✅ `expected/` 中没有出现 §3 之外的字段或结论变化；
- ✅ 重生成后门禁六包仍全绿，且结论/缺陷数不变。

**注意**：`make_examples.py` 重生成不构成真值证明（契约 §9.6）。重生成在本轮只用于两件事：
(1) 保证生成脚本里的 expected 真值字典与 `expected/` 落盘内容一致（否则下次重生成会静默改回旧值）；
(2) 重算 `INPUT_MANIFEST.json`。

---

## 7. 实测记录（本轮执行后的真实结果）

| 检查 | 命令 | 结果 |
|---|---|---|
| 六包门禁 | `python tools/stage0_gate.py` | `ALL_OK=true`，退出码 0；六包 `[PASS]`（clean/defective/corrected/ambiguous/blocked/crs_same_unit_wrong） |
| 护栏自检 | `python tools/selfcheck_guards.py` | `GUARDS_OK=true`，退出码 0；7 项分组（A/B/C+C2/D/E/F/G） |
| Schema 一致性 | `python tools/check_schema_consistency.py` | `SCHEMA_CONSISTENT=true`，退出码 0；原因码登记表 35 条（FAIL 31 / CANDIDATE 1 / INDETERMINATE 3） |
| 回归套件 + 对拍 | `python tools/recheck_probes.py --probes-script <原独立探针>` | `RECHECK_PROBES_OK=true`，**19/19**；对拍 7 项全部不再产出 PASS |
| expected 差异语义级枚举 | `git show HEAD:<expected>` 与工作区逐字段比对（见 `COMMANDS.md` C11） | `reason_code` **24 条**、非空 `failure_reason_codes` **18 处**、`advisory_reason_codes` 非空 **0 处**、其他差异 6 条（`truth_review.reviewed_fields` 文案，§3.10 #43）；`expected/findings.json` 六包零差异 |
| 重生成幂等 | `python tools/make_examples.py` 连跑两次，逐文件 sha256 比对 | 相对基线变化文件 **0 个**、第二次相对第一次变化文件 **0 个**（见 `COMMANDS.md` C10） |
| 判据 11/15 全库扫描 | 扫 `work/stage0/*/report.json` 的 check_results + clause_coverage | 「verdict != PASS 且 reason_code == OK」**0 条**；I7/I8/I9 分类违反 **0 条** |
| 判据 14 全库扫描 | 扫 `work/stage0/*/report.json`，比对数组与 findings 码集合 | 重复 **0 处**、与 findings 码集合不一致 **0 处**；非空 advisory **0 处**（S0-R6） |
| 判据 12 D1/D2 双口径 | 扫 `work/stage0/ambiguous/report.json` | 规则级与条款级均为 `CLAUSE_NOT_COVERED_BY_RULE`，一致 |
| 无 `UNKNOWN` 残留 | `grep -rn "UNKNOWN" examples/*/expected/` | 空 |
| 无不带时区时间戳 | `grep -rEn "T[0-9]{2}:[0-9]{2}(:[0-9]{2})?(,\|$)" examples/*/poi.csv` | 空（见 §3.7） |
| 零第三方依赖 | `grep -rE "import (geopandas\|shapely\|pyproj\|pydantic\|jsonschema\|pandas\|pytest)"` | 空 |
| 结论/缺陷数不变 | 见 §5 | 不变 |

---

## 8. 一处需要下一个人知道的现状（第一轮）

`examples/*/expected/clause_coverage.json` 里，FAIL 条款的 `reason_code` 曾登记为 **`OK`**。

原因：`aggregate_clause()` 取的是**规则级** `reason_code`（其语义是"为什么是这个执行状态"，
成功即 `OK`），而不是失败原因（失败原因在 finding 上）。契约 §3.5 的示例写的是
`"reason_code": "STALE_RECORD"`，因此这是一处**实现与契约示例不一致**。

第一轮**按现状登记**（如实反映当时实现，不为了让文件好看而写一个实现给不出的值），
并已升级为开放问题 `acceptance/stage-0-recheck/OPEN_ISSUES.md` 的 **S0-R1**。

### 8.1 最终回归轮：该问题已修复，expected 已同步（S0-R1 关闭）

工程师在 `9af939b`（条款级）→ `f433286`（规则级 + 兼容条目 + Schema 登记）→ `1fd2b21`（兼容路径兜底）
→ `dedc2f9`（兼容路径接入断言 + FAIL 取值链源头去掉 OK 兜底）→ `8048245`（I7–I9 违反处置统一为
fail-closed）→ `e2e9124`（`aggregate` 兼容分支捕获契约违规返回 INDETERMINATE 而非抛栈）
完成修复，并把约束扩大为**规则级 + 条款级全链路**的 I7–I9 断言（`assert_reason_compat()`）。

本轮已按新真值同步 expected，**逐条登记在 §3.9（24 条 reason_code）与 §3.10（18 处新字段）**。
因此**本节 §8 描述的"登记为 OK"状态已作废**，以 §3.9/§3.10 为准。

同步后的实测：门禁 `ALL_OK=true`、退出码 0，六包结论与缺陷数
`PASS/FAIL/PASS/INDETERMINATE/FAIL/FAIL`、`1/11/1/1/1/1`（与 §5 一致，未放松）。

