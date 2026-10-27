# ADR-010 Stage 0 重验契约统一（三态收敛、条款授权、CRS 四类分离、结构化参数来源）

- 状态：**已采纳**（Stage 0 重验实施依据；取代 `docs/three-state-verdict.md`、`docs/rule-semantics.md` 中与之冲突的部分）
- 日期：2026-10-26
- 触发：独立验收结论"不通过"，GA-01 ~ GA-05 为阻断项，GA-06 ~ GA-10 为契约/范围问题
- 相关：ADR-002（三态）、ADR-003（规则批准与版本化）、ADR-008（引用冻结与阈值来源）、ADR-009（不自建通用网关）、ADR-006（本轮降级）
- 完整契约：`docs/stage0-recheck-contract.md`；任务分解：`docs/stage0-recheck-tasks.md`

## 背景

独立验收用五个反例证明：当前实现会在"缺证据"的场景下给出 PASS 或错误 FAIL。五个反例的表现不同，根因是同一个 —— **判定权力的来源没有被约束**：

- 聚合看的是"有哪些规则结果"，而不是"有哪些必检条款"（GA-01）；
- 规则文件能改写条款的必检级别（GA-02）；
- 坐标量级这种"风险信号"被当成 CRS 冲突的"证据"（GA-03）；
- 上游不可执行被当成"无阻断"（GA-04）；
- 字符串子串包含被当成"阈值来自原文"的批准证据（GA-05）。

因此本 ADR 不是"打五个补丁"，而是引入一条可机械校验的公理，并让五处修复都从它推出。

## 决策

### D1 判定授权公理（契约 §0）

- `FAIL` 只能由「已批准的期望值证据」+「已实现且有明确语义的比较器」得出；
- 期望值无来源 / 观测值缺失 / 比较器未实现 / 政策未批准 / 上游不可执行 —— 任一成立即 `INDETERMINATE`；
- 量级、分布、经验、常识、模型自报置信度只能是 risk signal，永不构成 `FAIL` 或 `PASS`。

### D2 三态收敛（GA-06）

`verdict` 只有 `PASS / FAIL / INDETERMINATE`；`UNKNOWN` 废止。"没跑成"的信息全部搬到 `execution_status`，并新增 `NOT_IMPLEMENTED / REJECTED / FAILED` 三个状态。组合合法性矩阵写进代码常量并断言；**收紧**：删除旧矩阵中的「FAIL + NOT_EXECUTED 合法」，PASS 只允许搭配 `COMPLETED`。

### D3 条款授权（GA-02）

`required_for_release` 的权威在条款；规则的 `required_for_release` 是派生声明，必须等于 `OR(覆盖条款的 required_for_release)`。冲突即 `REJECTED`（拒绝执行），不放行也不强跑。

### D4 覆盖模型（GA-01）

聚合以必检条款全集为对象，逐条判定 `UNMAPPED / UNAPPROVED / NO_IMPLEMENTATION / CONFIG_REJECTED / MISSING_RESULT / COVERED`；多规则映射同一条款时不允许"任一通过即通过"。

### D5 CRS 四类分离（GA-03）

拆为「声明一致性（唯一可判 FAIL）」「元数据完备性」「坐标解释可用性（只出信号）」「真实性（不可证）」。匹配以批准的 `expected_crs` 为准，严格规范比、不做别名推断；量级只写 `risk_signals`。

### D6 依赖图（GA-04）

执行前校验存在性 / 无环 / 无重复 ID；**删除**"过滤掉不认识的依赖"的写法；上游 `BLOCKED / NOT_EXECUTED / NOT_IMPLEMENTED / REJECTED / FAILED` 一律向下游传播不可执行。

### D7 结构化参数来源（GA-05）

引入 `ParameterSource`（来源条款 + 文档哈希 + 冻结行号 + 逐字引用 + 字面量 + 单位 + 解释 + 审核人），校验采用 **token 边界匹配**与**文档哈希校验**，彻底删除字符串子串匹配。并明确写下 Stage 0 能力边界："只做到字面可追溯，未做到语义正确可证"。

### D8 统计口径（GA-07）

`records_total = evaluated + skipped_upstream + uninterpretable`（互斥），`failed / indeterminate` 是 `evaluated` 的重叠子集；`records_blocked` 作为派生兼容字段保留到 Stage 1。候选（`DUPLICATE_CANDIDATE`）计入 `indeterminate`，不计失败、不传播阻断。

### D9 边界政策（GA-08）

`inclusive / exclusive` 有明确语义；几何函数改为"先判边界、再射线法"以消除不对称；未知政策、缓冲、带孔/多部件几何一律 `REJECTED / NOT_IMPLEMENTED`，**禁止静默按另一政策执行**。

### D10 未实现即拒绝（贯穿）

本轮所有"Stage 0 不做"的能力（exclusive 之外的几何形状、缓冲、缺失率容忍政策、CRS 别名映射、模型置信度路由）必须以 `REJECTED / NOT_IMPLEMENTED` 显式拒绝，不得降级为默认值或另一政策。

## 备选方案与"为什么不这么做"

| 议题 | 备选方案 | 未采用的原因 |
|---|---|---|
| 规则降级条款必检级别 | **A**：以条款为准覆盖规则声明，继续执行并最终 FAIL | 会把"配置越权"伪装成"数据缺陷"。报告读者会以为是数据过期导致失败，实际是有人在规则文件里偷偷改了政策。越权必须显形，故采用**拒绝执行**（§2.3） |
| 未映射的必检条款 | **B**：保持现状，只在报告里加一条提示 | 提示不改变放行结论，等于保留"缺规则也放行"的 P1。必须进入聚合（§3.4） |
| CRS 冲突判定 | **C**：保留量级推断，但把结论从 FAIL 降为 INDETERMINATE | 仍然把 signal 当 evidence，只是改了标签；且 clean 改声明为 EPSG:4490 的漏报依然存在。必须改为声明比对（§4.2） |
| CRS 缺声明 | **D**：维持现状判 FAIL（"连声明都没有显然不合格"） | 无批准条款授权，违反 D1；且与"GeoJSON 默认解释"等约定冲突。改为 `INDETERMINATE` + 下游阻断（§4.4） |
| 未知依赖 | **E**：保留过滤，但记一条 warning | warning 默认被忽略，等于保留原行为。必须拒绝（§5.1） |
| 阈值来源 | **F**：保留子串匹配，但要求长度 ≥ 2 或加分隔符 | 治标；`"30"` 与 `"300"` 之类问题仍会复发。改为 token 边界匹配（§6.2） |
| 三态矩阵 | **G**：保留「FAIL + NOT_EXECUTED 合法」以兼容数据集级失败 | 数据集级失败在有 finding 且全批阻断时状态应为 `PARTIAL`，无需该例外格；留着它等于承认"未执行也能判失败"，与 D1 冲突 |
| 统计口径 | **H**：只加字段不改语义，`records_blocked` 含义不变 | 候选被算作"未执行"的错误（clean R10 evaluated=11）不会消失。必须重定义互斥口径（§7.1） |
| 反例承载方式 | **I**：全部新增为冻结示例包 | 成本高且 `make_examples.py` 会同时重写 expected，削弱独立性。本轮以**内存变异探针**（`tools/recheck_probes.py`）为主，仅对"量级无法区分的同单位错误 CRS"新增一个冻结包 |
| 参数来源完整性 | **J**：Stage 0 就要求落地 `AuditEvent` 证明"改参即失效" | 超出零依赖语义原型范围；以 `parameter_sources` 提供静态等价证据，审计留痕列入 OPEN_ISSUES（契约 Q5） |

## 后果

**正面**

- 五个 P1 反例从"可通过"变为"被拒绝或显式未知"，且路径可追溯到具体条款/规则/参数。
- 报告新增 `clause_coverage` 与 `config_rejections`，读者能直接看到"哪项没被覆盖、为什么"。
- 契约可机械校验：组合矩阵、I1–I6 不变式、依赖传播矩阵都能写成断言。

**代价**

- `expected/aggregate.json` 结构升级、六个包需要同步（集中在 T05，逐条登记理由）。
- `blocked` 包的真值依据改写，证据链需要重写。
- 配置校验变严，任何"抄来的规则文件"都会先被拒一批；这是有意为之。
- Stage 0 又新增一个示例包与一个探针脚本，交付面变大（写入 HANDOFF 偏差说明）。

## 不声称

- 本 ADR **不声称**护栏已完整实现：参数来源只做到"字面可追溯"，未做到"语义正确可证"（§6.3）。
- **不声称** CRS 真实性可被验证（C4 恒 `NOT_APPLICABLE`）。
- **不声称**目标环境依赖与 Docker 冒烟已完成 —— 作为阶段缺口记录。

## 增补一（2026-10-26）：§3.2 措辞勘误与 `coverage_state` 覆盖缺口

### 事实

QA 核对时发现契约 §3.2 原文写「ambiguous 包的 D1/D2 是 NEEDS_CLARIFICATION 且规则为 DRAFT，落到 `UNAPPROVED`」，
但实测 `clause_coverage` 为 `UNMAPPED / CLAUSE_NOT_COVERED_BY_RULE`。核实结果：`examples/ambiguous/approved-rules.yaml`
只有 R01–R10 十条规则、映射 A1–C2，**不存在任何 `requirement_ids` 含 D1/D2 的规则**（连 DRAFT 也没有）。
结论同为 `INDETERMINATE`，故不违反放行语义，但契约描述与示例数据不一致，二次验收方逐条对契约时会撞上。

### 决策

1. **改契约，不改数据**：§3.2 修正为「D1/D2 无任何规则声明覆盖 ⇒ `UNMAPPED`」，并把 `UNAPPROVED` 的适用条件明确为
   "包内确实存在映射该条款但 `status != APPROVED` 的规则"。
2. **声明覆盖缺口**：六态中只有 `UNMAPPED`（2 条）与 `COVERED`（54 条）在六个示例包中有正例；
   `UNAPPROVED`、`NO_IMPLEMENTATION`、`MISSING_RESULT`、`CONFIG_REJECTED` 四态**无示例包级正例**
   （`CONFIG_REJECTED` 仅被探针间接覆盖，且探针只断言 `config_rejections` 的码、未断言 `coverage_state`）。
   列入 Stage 1 待办，并在验收材料中写明，不得声称覆盖模型已被完整验证。
3. **附带一致性要求**：同一事实在 `clause_coverage` 与 `check_results` 兼容条目中不得给出不同 `reason_code`，
   `clause_coverage` 为权威口径（D1/D2 两处均为 `CLAUSE_NOT_COVERED_BY_RULE`）。

### 为什么不选择「给 ambiguous 补两条 DRAFT 规则」

- **那是改数据，不是改文档**。补 DRAFT 规则要动 `examples/ambiguous/approved-rules.yaml`、
  重算 `INPUT_MANIFEST.json`，并连带 `expected/aggregate.json`（D1/D2 的 `reason_code` 会从
  `CLAUSE_NOT_COVERED_BY_RULE` 变成 `RULE_NOT_APPROVED`）—— 而本轮红线是"expected 的每一处改动都必须登记理由"，
  为一次措辞勘误去动真值，成本与风险都不成比例。
- **`DRAFT` 规则存在与否是数据事实，不是契约立场**。契约要规定的是"给定数据形态 → 落到哪个状态"的映射，
  不是"示例包应该长什么样"。让契约去迁就数据，等于把契约降级成数据说明书。
- **覆盖缺口本来就该显式声明**。补一个正例只是把缺口掩盖掉；写进 Stage 1 待办并让验收材料载明，
  比临时凑一个正例更符合本 ADR「不声称未验证的能力」的立场。

### 为什么不选择「删掉 §3.2 里 ambiguous 这句举例」

举例是契约可读性的来源，删掉后 `UNMAPPED` 与 `UNAPPROVED` 的界限会更模糊。保留并改正，同时补覆盖缺口声明，信息量最大。

## 增补二（2026-10-26）：`reason_code` 语义明确化（I7–I9）

### 事实

`aggregate_clause()` 在 FAIL 时取的是**规则级执行状态码**，导致报告出现「FAIL：A2(OK)」这一自相矛盾表述。
根因：规则级 `reason_code` 原本承担"执行状态的原因"（`RULE_NOT_APPROVED` / `NO_IMPLEMENTATION` 等），
被直接搬到条款级后与业务结论冲突。

### 决策

确认工程师的修法**符合契约原意**（§3.5 示例 `"reason_code": "STALE_RECORD"` 本就是业务失败原因码）：
`FAIL` 取该条款下第一条 FAIL 类 finding 的 `reason_code`；`INDETERMINATE` 取缺证据/未覆盖原因码；`PASS` 保持 `OK`。
并补充三条不变式使之可机械校验：`I7 PASS⇒OK`、`I8 FAIL⇒非 OK`、`I9 INDETERMINATE⇒非 OK`，
降级链末端用 `CONTRACT_VIOLATION` 兜底，使「FAIL:OK」在结构上不可能出现。
**注意：该 bug 在规则级同样存在**（部分记录被阻断且无 finding 的规则会得到 `INDETERMINATE/PARTIAL/OK`，
clean 的 R10 候选场景即为此类），I7–I9 对规则级与条款级一并适用，不可只修条款级。

### 实现对齐（2026-10-26，工程师 commit 9af939b 后的三项裁定）

工程师实现后询问三个语义点，裁定如下，已写入契约 §3.5.2：

1. **"第一条 FAIL finding" 按发射顺序，不按行号重排** —— 确认。发射顺序 = 规则拓扑执行序 × 规则内行号升序；
   跨规则重排会打乱规则优先级（上游根因应排在下游症状之前）。并补确定性要求（并列以 `rule_id` 字典序 tie-break）。
2. **`failure_reason_codes` 去重** —— **修订**（实现为保留重复）。理由：数量信息已由 `summary_counts.findings`
   与 `records_failed` 承载；重复数组既不是集合也不是计数，会让 QA 的 expected 比对依赖注入顺序而变脆。
   若需按码计数，Stage 1 加 `reason_code_counts` 对象，不把数组写成多重集。
3. **INDETERMINATE 取值链** —— 部分确认：上游侧（规则级非 OK 时照取 `UPSTREAM_*`）符合契约；
   必补两处：①候选类码（`DUPLICATE_CANDIDATE`）须纳入，否则"仅候选"的必检条款会拿到 OK
   （当前只因 C2 非必检而未暴露，契约不依赖数据巧合）；②回退链末端是 `CONTRACT_VIOLATION`，**不是 OK**。

附带要求：两个新字段必须写进 `schemas/check_result.schema.json` 并纳入 `check_schema_consistency.py`，否则 GA-09 覆盖不到。

## 复审条件

- Stage 1 引入 `jsonschema` / `pydantic` 时：把 `tools/check_schema_consistency.py` 的"支持子集"替换为完整校验，并重跑本轮全部一致性用例。
- Stage 1 引入 `shapely` / `pyproj` 时：重跑边界政策与 CRS 全部用例，未做结论一致性对比前不得删除 ADR-004。
- Stage 2 引入模型时：复审"模型自报置信度不得作为批准依据"（与 ADR-006 降级后的约束一致）。
- 若 `parameter_sources` 在实际使用中导致大量合理规则无法批准，则复审 token 匹配规则与结构性配置清单的划分，但**不得回退到子串匹配**。
