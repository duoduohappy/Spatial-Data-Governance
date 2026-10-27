# ADR 索引

| 编号 | 决策 | 状态 | 复审条件 |
|---|---|---|---|
| [ADR-001](ADR-001-deterministic-core.md) | 确定性内核与模型职责分离 | 已采纳 | 引入模型前复审 |
| [ADR-002](ADR-002-three-state-verdict.md) | 三态业务判定与运行状态分离 | 已采纳 | Stage 3 异步任务上线时复审 |
| [ADR-003](ADR-003-rule-approval-versioning.md) | 规则批准制 + 版本化 + 改参失效 | 已采纳 | Stage 2 前复审 |
| [ADR-004](ADR-004-stdlib-then-geopandas.md) | Stage 0 用零依赖 stdlib 内核，Stage 1 换权威实现 | 已采纳 | Stage 1 开工时复审 |
| [ADR-005](ADR-005-map-evidence-view.md) | 地图证据视图作为可降级增强层 | 已采纳 | Stage 3 实现前复审 |
| [ADR-006](ADR-006-budget-knob-routing.md) | 预算上限与成本记录保留；置信度升级路由与模型网关降级为未来实验 | **已降级（未来实验，不在 Stage 2 必做范围）** | 出现实测数据后复审，无实测不实现 |
| [ADR-007](ADR-007-agent-ablation.md) | 多 Agent 为实验组，以消融实验决定去留；默认单 Agent | 已采纳 | Stage 4 出对照结果后复审 |
| [ADR-008](ADR-008-quote-freeze-and-threshold-source.md) | 引用行号冻结 + 哈希校验 + 阈值必须有来源 | 已采纳 | Stage 2 模型提取上线时复审 |
| [ADR-009](ADR-009-scope-out.md) | 不自建通用网关、不上 K8s/SSO/多租户 | 已采纳 | 出现明确付费租户时复审 |
| [ADR-010](ADR-010-stage0-recheck-contract.md) | Stage 0 重验契约统一：判定授权公理、三态收敛、条款授权与覆盖、CRS 四类分离、结构化参数来源 | 已采纳（Stage 0 重验实施依据） | Stage 1 引入权威库/完整 Schema 校验时复审 |

## 本轮相对《项目执行与验收方案 v1.0》的三处补充

原方案第 2 节已排除三维渲染，第 6 节把多 Agent 归为实验组，并明确不自建通用网关。
本轮在此基础上补了三条（ADR-005 / 006 / 007），动机是：原方案的可信度设计已经足够强，
但缺失"技术决策"层面的证据链路；补这三条不改变可靠性约束，只增加可解释的决策记录。
除此之外均以原方案为准，原方案中的排除项一律保持排除。
