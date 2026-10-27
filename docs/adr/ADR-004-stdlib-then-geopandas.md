# ADR-004 Stage 0 用零依赖 stdlib 内核，Stage 1 换权威实现

- 状态：已采纳（Stage 0 已实施）
- 背景：当前环境未安装 geopandas / shapely / pyproj / pydantic / fastapi（见 tools/smoke_deps.py）。
- 决策：Stage 0 的**语义验证内核**只用 Python 标准库；几何、距离、点在多边形各自做最小正确实现。
  Stage 1 一律替换为权威库，并针对示例包做"替换前后结论一致性"对比。
- 理由：Stage 0 要验证的是**语义是否正确**，不是性能；先排除"依赖装不上导致永远无法验证"的风险。
- 后果：引入了已知近似（Haversine、射线法、边界容差），记录于 limitations.md 并列入 OPEN_ISSUES。
- 复审条件：Stage 1 开工时必做基准对比；未完成对比不得删除本 ADR。
