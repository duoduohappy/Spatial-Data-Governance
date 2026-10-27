# ADR-002 三态业务判定与运行状态分离

- 状态：已采纳（Stage 0 已实施）
- 背景：质检工具最常见的失效是把"没跑到"当成"没问题"。二态（通过/不通过）无法表达
  "证据不足"和"执行失败"。
- 决策：业务结论取值 PASS / FAIL / INDETERMINATE；运行状态取值
  QUEUED / RUNNING / COMPLETED / PARTIAL / BLOCKED / FAILED / CANCELLED。两者同时在报告中呈现。
- 理由：输入损坏或执行失败既不能算通过，也不能自动算业务不合格——那是两件不同的事。
- 后果：聚合逻辑必须区分必检与非必检；未知项即使不影响"必须 FAIL"，也必须保留可见。
- 复审条件：Stage 3 引入异步任务时，补齐 QUEUED/RUNNING/FAILED/CANCELLED 四个状态。
