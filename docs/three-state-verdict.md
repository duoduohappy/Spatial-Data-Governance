# 三态判定与总体聚合（Stage 0）

## 1. 两个维度必须分开

| 维度 | 取值 | 含义 |
|---|---|---|
| 业务结论 verdict | PASS / FAIL / INDETERMINATE | 这份数据相对条款"能不能放行" |
| 运行状态 execution_status | COMPLETED / PARTIAL / BLOCKED / NOT_EXECUTED / NOT_IMPLEMENTED / REJECTED / FAILED（QUEUED / RUNNING / CANCELLED 留给 Stage 3） | 这次检查"跑没跑完" |

**输入损坏或执行失败不能算通过，也不能自动算业务不合格。** 报告必须同时呈现两者。
**`UNKNOWN` 已废止**（GA-06）：原本塞在 verdict 里的"没跑成"信息全部搬到 `execution_status`。

| status | 含义 |
|---|---|
| COMPLETED | 覆盖范围内的全部对象均已执行判定 |
| PARTIAL | 部分对象已执行，其余因上游阻断/缺证据未执行 |
| BLOCKED | 零对象被执行（上游不可执行、依赖阻断、数据集级失败导致全批阻断） |
| NOT_EXECUTED | 规则/条款未批准，登记但不执行 |
| NOT_IMPLEMENTED | 规则已批准但能力未在 Stage 0 实现（如带孔几何、未知几何类型） |
| REJECTED | 配置校验未通过，拒绝执行（不放行也不强跑） |
| FAILED | 执行期抛出未捕获异常，或不变式断言被违反（兜底） |

## 2. 组合矩阵（**已按重验契约收紧**，实现=常量 `LEGAL_COMBOS`，运行时断言）

| verdict \ status | COMPLETED | PARTIAL | BLOCKED | NOT_EXECUTED | NOT_IMPLEMENTED | REJECTED | FAILED |
|---|---|---|---|---|---|---|---|
| PASS | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| FAIL | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| INDETERMINATE | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

相对本文件旧版的两处收紧：

1. **删除**「FAIL + NOT_EXECUTED 合法」。未执行就没有比对，按 A1 不能判 FAIL。
   数据集级失败（如 CRS 声明冲突）在有 finding 且全批被阻断时，状态取 `PARTIAL`，不是 `NOT_EXECUTED`。
2. **PASS 只允许搭配 `COMPLETED`**。只要有对象未执行，就不能说 PASS。

非法组合出现即抛 `ContractViolation`，并由 `run()` 兜底登记为 `INDETERMINATE / FAILED`，
**不会**被"修正"成一个看起来合理的值。

## 2.5 统计口径（GA-07）

`summary_counts` 七字段 + 派生字段：

| 字段 | 定义 |
|---|---|
| `records_total` | 本包数据行总数 |
| `records_evaluated` | 本规则**实际给出结论**（PASS/FAIL/INDETERMINATE 之一）的行数 |
| `records_failed` | 给出 FAIL 的行数（⊂ evaluated，**重叠子集**） |
| `records_indeterminate` | 给出待定/候选的行数（⊂ evaluated，**重叠子集**） |
| `records_skipped_upstream` | 因上游依赖不可执行而未评估的行数（与 evaluated **互斥**） |
| `records_uninterpretable` | 本规则自身因缺证据而拿不出任何结论的行数（与 evaluated **互斥**） |
| `records_blocked` | **派生字段** = skipped_upstream + uninterpretable（Stage 1 移除） |
| `findings` | finding 条目数（候选以"组"计，1 条 finding 可覆盖 2 行） |

运行时断言：

```
I1: total == evaluated + skipped_upstream + uninterpretable
I2: failed + indeterminate <= evaluated
I3: blocked == skipped_upstream + uninterpretable
I4: failed > 0                 ⇒ verdict == FAIL
I5: 0 < evaluated < total      ⇒ status ∈ {PARTIAL, BLOCKED}
I6: verdict == PASS            ⇒ skipped == 0 且 uninterpretable == 0 且 failed == 0
```

**候选（`DUPLICATE_CANDIDATE`）不是失败也不是阻断**：涉及行进 `records_indeterminate`，
不进 `records_failed`，不向下游传播阻断。clean 包 R10 修复后为
`total=12, evaluated=12, failed=0, indeterminate=2, findings=1`。

## 3. 记录级规则如何落到 rule 级结论

每行先归入**互斥**的三类之一：`evaluated` / `skipped_upstream` / `uninterpretable`（I1）；
`failed` 与 `indeterminate` 是 `evaluated` 的**重叠子集**：

```
upstream        = 前置规则不可执行的行
own_blocked     = 本规则内部标为阻断的行（已排除 upstream）
failed_lines    = 本规则判 FAIL 的行
candidate_lines = DUPLICATE_CANDIDATE 的行及其 peer 行
no_verdict      = own_blocked - failed_lines - candidate_lines   # 拿不出任何结论 ⇒ 缺证据
evaluated       = 全部行 - upstream - no_verdict

if evaluated == 0 且无任何 finding:
    verdict = INDETERMINATE, status = BLOCKED, reason = ALL_RECORDS_BLOCKED
elif 存在失败类 finding:                       # 含数据集级 finding
    verdict = FAIL,          status = PARTIAL（有 skipped/uninterpretable）否则 COMPLETED
elif 只有候选 finding:
    verdict = INDETERMINATE, status = PARTIAL（有 skipped/uninterpretable）否则 COMPLETED
elif 有 skipped/uninterpretable 但没有 finding:
    verdict = INDETERMINATE, status = PARTIAL
else:
    verdict = PASS,          status = COMPLETED
```

下游阻断的行集合 = `upstream ∪ no_verdict ∪ failed_lines`（**不含候选行**）。

关键点：**前置失败的原始记录不参与后续检查**。经典反例是“坐标已判定越界的记录继续去做是否在范围内”，
那样会得到“多处越界”的错误结论，也属于伪执行。

## 4. 总体聚合（**改为条款级覆盖聚合**，GA-01）

聚合的唯一输入是**必检条款全集 U 的覆盖结果**，不再是"有哪些规则结果"：

```
U = { 条款 | required_for_release == true }

for req in U:
    mapped = 覆盖该条款的全部规则
    mapped 为空                 → UNMAPPED          → INDETERMINATE / NOT_EXECUTED / CLAUSE_NOT_COVERED_BY_RULE
    任一 mapped 规则被配置拒绝  → CONFIG_REJECTED   → INDETERMINATE / REJECTED / UPSTREAM_CONFIG_REJECTED
    mapped 全部未批准           → UNAPPROVED        → INDETERMINATE / NOT_EXECUTED / RULE_NOT_APPROVED
    mapped 全部无实现           → NO_IMPLEMENTATION → INDETERMINATE / NOT_IMPLEMENTED / NO_IMPLEMENTATION
    mapped 有实现但无结果       → MISSING_RESULT    → INDETERMINATE / NOT_EXECUTED / RESULT_MISSING_FOR_CLAUSE
    否则                        → COVERED           → 取该条款下全部规则结果做条款级聚合（§3.3）

条款级聚合：任一 FAIL → FAIL；无 FAIL 但有非 PASS → INDETERMINATE；全部 PASS → PASS；兜底 INDETERMINATE。

if config_rejections 非空:                   INDETERMINATE（拒绝执行，不得算合格）
elif U 为空或记录数为 0:                      INDETERMINATE（“零记录/零必检条款”不得通过）
elif 任一 req ∈ U 的 verdict == FAIL:         FAIL
elif 任一 req ∈ U 的 verdict != PASS:         INDETERMINATE
else:                                         PASS
```

要点：**多规则映射同一条款时不允许"任一通过即通过"**，只要有一条未 PASS，该条款即为 INDETERMINATE。
规则级结果只作为条款级聚合的输入，不再直接参与总体聚合。
`required_for_release` 的权威值在条款上，规则侧声明必须等于 `OR(覆盖条款)`，冲突即拒绝执行（GA-02）。

- FAIL 时同时展示未知与未执行项，不允许只报失败、隐藏不知道的部分。
- 非必检项永远可见（示例中的 R10 重复候选），但不决定放行。
- 部分执行或抽样执行不得用于出具“整体 PASS”。
- 通过仅针对**本轮已批准的规则与覆盖范围**，不证明数据整体真实、准确或全面合格。

## 5. Stage 0 已验证的四种结果

| 示例包 | 总体结论 | 触发原因 |
|---|---|---|
| clean | PASS | 全部必检项执行完毕且无失败 |
| defective | FAIL | R02/R03/R04/R05/R06/R08/R09 存在必检失败 |
| corrected | PASS | 整改后必检项全部执行完毕且无失败（R10 候选仍可见） |
| ambiguous | INDETERMINATE | 原文缺阈值，条款不可批准，必检项保持未知 |
| blocked | FAIL | CRS 声明冲突（数据集级失败），且下游空间检查全部阻断为未知 |

## 6. 禁止事项（写死在实现里）

- 回放（replay）或手工规则（manual）不得标为 live；Stage 0 的 manifest 恒为 `manual`。
- 不得用占位接口、假日志、模拟指标冒充真实结果。
- 不得因为“看起来差不多”而给附带勾选的样例判 PASS；结果必须能追溯到逐条 finding 证据。
