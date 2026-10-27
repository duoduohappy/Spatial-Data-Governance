# 架构（Stage 0）

## 1. 分层与职责

```
交付说明 / 数据字典 / 数据 / 范围 / CRS
                 │
        ┌────────▼─────────┐
        │ Ingestion        │  只读快照 + SHA-256，不改原始值
        └────────┬─────────┘
        ┌────────▼─────────┐
        │ Requirement      │  Stage 2 起由模型提议，逐字引用 + 冻结行号
        │ Extraction       │  Stage 0：人工编写并锁定
        └────────┬─────────┘
        ┌────────▼─────────┐
        │ Rule Approval    │  提议 → 澄清 → 人工批准 → 版本化
        └────────┬─────────┘
        ┌────────▼──────────────────────────┐
        │ Deterministic Execution Kernel    │  十类规则，按前置拓扑排序执行
        │ GDAL/Shapely/PostGIS（Stage 1）   │  失败 ⇒ BLOCKED，不伪执行
        └────────┬──────────────────────────┘
        ┌────────▼─────────┐   ┌──────────────────┐
        │ Aggregation      │   │ Model Gateway    │  Stage 2：路由/降级/成本
        │ 三态 + 必检聚合  │   │ 预算旋钮 θ（ADR-006）│
        └────────┬─────────┘   └──────────────────┘
        ┌────────▼─────────┐
        │ Reporting        │  JSON（事实来源）+ Markdown/HTML（渲染）
        │ 地图证据视图     │  可降级增强层（ADR-005）
        └────────┬─────────┘
        ┌────────▼─────────┐
        │ Recheck 复验     │  resolved / persisting / new / not_comparable
        └──────────────────┘
```

## 2. Stage 0 的边界：**零第三方依赖内核**（该边界随 Stage 0 一起冻结；Stage 1 起按 ADR-004 已替换为 shapely / pyproj / PyYAML / pydantic，见 `acceptance/stage-1/GEOMETRY_REPLACE.md`）

本阶段的执行内核只使用 Python 标准库，原因与环境事实：

- 当前环境未安装 geopandas / shapely / pyproj / pydantic / fastapi（见 `tools/smoke_deps.py` 输出）。
- Stage 0 的门槛是“一个完整实例从原文走到预期结果”，不是性能；先用 stdlib 把语义跑通，
  再在 Stage 1 换成权威实现并做基准对比，避免“依赖装不上导致语义永远无法验证”。
- 已知近似点见 `docs/limitations.md`，Stage 1 必须回来消掉。

## 3. 目录结构

```
backend/{api,domain,ingestion,rules,workflow,llm,reporting,storage}   Stage 1 起建立
frontend/src                                                         Stage 3 起建立
cli、schemas、examples/{clean,defective,corrected,ambiguous,blocked}
eval/{datasets,annotations,configs,scripts,results}
tests/{unit,integration,adversarial}
docs/{architecture,rule-semantics,three-state-verdict,threat-model,evaluation,limitations,adr}
acceptance/stage-0 ... stage-5
tools/{make_examples.py,stage0_gate.py,smoke_deps.py,selfcheck_guards.py}
```

## 4. 运行时模式：manual / replay / live

| 模式 | 定义 | Stage 0 是否存在 |
|---|---|---|
| manual | 规则由人工编写并批准，无任何模型调用 | 是（唯一模式） |
| replay | 使用录制的模型输出重放，**成本低但不能声称真实链路通过** | 否，Stage 2 引入并强制标注 |
| live | 真实调用模型，带 token / 费用 / 重试记录 | 否，Stage 2 引入 |

## 5. 关键不变量

1. 原始输入只读；所有产物写在 `work/` 下。
2. 规则、参数、输入哈希写进 manifest，任何结论可追回到输入。
3. 地图/前端是可选层，判定链路不依赖它；底图不可用时表格与审查仍然可用。
4. 默认 localhost；公网部署需要另补认证、隔离、配额（Stage 3 之前不做）。
