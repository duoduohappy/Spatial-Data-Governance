# 目标依赖冒烟：**阶段缺口，未做**

- 日期：2026-10-26　记录人：严过关（QA）
- 状态：**本轮 Stage 0 未做目标空间依赖的安装验证与运行验证，未做 Docker 冒烟。**
  本文件是**缺口记录**，不是完成报告。不得以"本机 stdlib 跑通"代替。

## 1. 为什么没做

1. Stage 0 的硬约束是**零第三方依赖**：全部实现只用 Python 3 标准库，因此本轮不存在
   "目标依赖"这一层要验证的东西——`tools/smoke_deps.py` 对本环境的结论是「Stage 0 依赖满足情况：满足」，
   这句话只说明**零依赖这一条成立**，不说明 Stage 1 的目标依赖可用。
2. 独立验收方明确点名了这一项（"目前运行的是语义原型，Stage 0 没有完成原计划的目标空间依赖
   安装/运行验证与 Docker 冒烟；需要在同一目标环境完成**或明确记录阶段缺口**"）。
   本轮选择**如实记录缺口**，不补做、不粉饰。

## 2. 目标依赖清单（`python tools/smoke_deps.py` 输出，只报告不安装）

原始输出见 `deps-smoke.txt`，摘要：

```
python=3.13.14 platform=Windows-11-10.0.26200-SP0

模块           状态     用途
------------------------------------------------------------------------------
yaml         OK     Stage 0+：配置文件读写（发行包名 PyYAML；当前 Stage 0 未使用，自研极简解析器代替）  (版本 6.0.3)
pydantic     MISSING Stage 1+：数据对象与 Schema 校验
jsonschema   MISSING Stage 1+：Schema 一致性校验
fastapi      MISSING Stage 1+：HTTP API
geopandas    MISSING Stage 1+：空间数据读写
shapely      MISSING Stage 1+：几何谓词与拓扑
pyproj       MISSING Stage 1+：坐标系变换与测地距离
pandas       MISSING Stage 1+：字段级剖析
pytest       MISSING Stage 1+：单元与集成测试

Stage 0 门槛要求：零第三方依赖即可完成端到端实例。本环境的 Stage 0 依赖满足情况：满足
```

## 3. 未安装的原因

- **不是权限或网络阻断**，而是本轮刻意不装：Stage 0 的验收判据之一就是零第三方依赖，
  装了反而破坏了本轮要证明的东西。
- 待 Stage 1 开工时按独立验收方的建议处理：用**项目 `.venv`** 安装并锁定版本，
  **不修改全局环境**；有实际网络/目录权限阻断再具体说明。

## 4. Docker 冒烟

**未做。** 本轮没有构建任何镜像，没有编写 Dockerfile，也没有在容器里跑过一次端到端。

## 5. 因此尚未执行的事

- 标准库实现（自研射线法 / Haversine / 极简 YAML 解析）与目标库（shapely / pyproj / PyYAML）
  的**替换对比尚未执行**。
- Stage 1 替换完成后，必须**冻结本轮六个包 + 本轮全部边界用例**并在目标库上重跑，
  逐条对比结论；未做对比之前不得删除 ADR-004，也不得声称"替换后语义一致"（沿用 OPEN_ISSUES S0-03）。
