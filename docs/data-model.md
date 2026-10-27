# 数据对象与 Schemas（Stage 0）

Stage 0 只落地结构与字段语义；机器校验（JSON Schema / Pydantic）在 Stage 1 引入
`jsonschema` / `pydantic` 后启用。`schemas/` 下的 `.json` 文件为草案，字段含义以下表为准。

自然语言报告不是事实唯一来源：`report.md` 由 `report.json` 渲染而来，任何结论以 JSON 为准。

## 1. Requirement（交付条款）

| 字段 | 含义 |
|---|---|
| requirement_id | 条款编号，仅用于追溯，不表达优先级 |
| document_id | 来源文档文件名 |
| document_sha256 | 来源文档哈希；文档改了而引用未更新 ⇒ 校验失败 |
| source_line_start / source_line_end | 冻结行号（1-based） |
| source_quote | 原文逐字引用，必须与指定行完全一致 |
| required_for_release | 是否必检（决定总体聚合是否受阻） |
| support_status | SUPPORTED / NEEDS_CLARIFICATION / UNSUPPORTED |

约束：原子要求可共享同一引用，但必须独立追踪；不存在的引用会被拦截。

## 2. RuleDraft / ApprovedRule（检查规则）

| 字段 | 含义 |
|---|---|
| rule_id | 规则编号 |
| requirement_ids | 对应的条款编号列表 |
| rule_type | 十类规则之一 |
| parameters | 参数；其中判定阈值必须能在原文引用中找到来源 |
| preconditions | 前置规则；前置失败时本规则对该记录/数据集不执行（BLOCKED，非 PASS） |
| status | DRAFT → NEEDS_CLARIFICATION / READY_FOR_REVIEW → APPROVED / REJECTED |
| version / approved_at / reviewer | 版本与批准信息 |
| rule_hash | 规则内容哈希；改参数即产生新版本，旧批准失效 |

约束：缺必要参数或存在未解决歧义不得批准。

## 3. CheckResult（单次执行结果）

| 字段 | 含义 |
|---|---|
| run_id | 运行批次 |
| rule_id / version / hash | 规则身份 |
| requirement_ids | 覆盖的条款 |
| verdict | PASS / FAIL / INDETERMINATE（业务结论） |
| execution_status | COMPLETED / PARTIAL / BLOCKED / NOT_EXECUTED（运行状态） |
| reason_code | 结论原因码 |
| summary_counts | findings / records_evaluated / records_blocked |
| coverage | 覆盖范围说明 |
| tool_version / duration_ms | 执行环境留痕 |

## 4. Finding（缺陷/发现）

| 字段 | 含义 |
|---|---|
| finding_id | 本次运行内唯一 |
| stable_key | `规则\|原因码\|位置\|字段`，用于跨批次比较（整改前后不被重复计数） |
| record_locator | 文件 + 行号；数据集级缺陷不带行号，不触发记录级阻断 |
| observed_value / expected_constraint | 观测值与约束描述 |
| evidence | 结构化证据（距离、同源行、字典行号等） |
| review_state | 人工复核状态 |

约束：record_locator 不能只依赖业务 ID（否则缺/重 ID 的记录无法定位）；敏感原值不进入普通日志。

## 5. RunManifest（运行留痕）

输入 SHA-256、规则集合哈希、reference_time、软件/依赖版本、commit SHA、`mode`（live / replay / manual）、
模型配置、覆盖范围、输出 SHA-256。**不记录 Key，不记录不可用片段冒充成功。**

Stage 0 所有运行的 mode 恒为 `manual`：本阶段不存在任何模型调用，规则全部来自人工批准的 YAML。
后续若出现 live 运行，必须能给出调用记录、token、费用与失败重试日志。

## 6. AuditEvent（审核留痕）

actor、action、时间、旧/新版本、原因。记录批准、改参、复核等状态变化。
不声称普通日志具备防篡改认证能力——Stage 0 的日志是可被编辑的文件，不是审计系统。
