# Stage 0 运行结果（原始输出）

环境：Windows-11-10.0.26200-SP0，Python 3.13.14，工作区 `geoacceptance`。
所有命令在 `rm -rf work` 之后重新执行，避免残留产物造成通过假象。

## 1. 生成示例数据

命令：`python tools/make_examples.py`　退出码：**0**

```
bundles written: clean, defective, corrected, ambiguous, blocked
example_root: C:\Users\TempAdmin\WorkBuddy\2026-10-26-13-17-35\geoacceptance\examples
```

## 2. 端到端门禁

命令：`python tools/stage0_gate.py`　退出码：**0**

```
[PASS] clean      aggregate=PASS          findings=1   -> C:\...\geoacceptance\work\stage0\clean
[PASS] defective  aggregate=FAIL          findings=11  -> C:\...\geoacceptance\work\stage0\defective
[PASS] corrected  aggregate=PASS          findings=1   -> C:\...\geoacceptance\work\stage0\corrected
[PASS] ambiguous  aggregate=INDETERMINATE findings=1   -> C:\...\geoacceptance\work\stage0\ambiguous
[PASS] blocked    aggregate=FAIL          findings=1   -> C:\...\geoacceptance\work\stage0\blocked

ALL_OK=true
```

说明：`[PASS]` 指的是**实际结果与人工预先写好的期望一致**，不是"数据合格"。
`defective` / `blocked` 两个包的验收结论本身就是 FAIL，这正是期望结果。

### defective 包的逐规则实际输出

| 规则 | 条款 | 结论 | 运行状态 | 缺陷数 | 已检记录 | 阻断记录 |
|---|---|---|---|---|---|---|
| R01 | A1 | PASS | COMPLETED | 0 | 15 | 0 |
| R02 | A2 | FAIL | PARTIAL | 2 | 13 | 2 |
| R03 | A3 | FAIL | PARTIAL | 2 | 11 | 4 |
| R04 | A4 | FAIL | PARTIAL | 1 | 11 | 4 |
| R05 | A5 | FAIL | COMPLETED | 2 | 15 | 0 |
| R07 | B2 | PASS | COMPLETED | 0 | 15 | 0 |
| R09 | C1 | FAIL | PARTIAL | 1 | 11 | 4 |
| R06 | B1 | FAIL | PARTIAL | 1 | 11 | 4 |
| R08 | B3 | FAIL | PARTIAL | 1 | 11 | 4 |
| R10 | C2 | INDETERMINATE | PARTIAL | 1 | 11 | 4 |

注意规则执行顺序为拓扑序（R09 先于 R06/R08），不是文件里的书写顺序。

### blocked 包的逐规则实际输出（依赖阻断）

| 规则 | 条款 | 结论 | 运行状态 | 缺陷数 | 已检记录 | 阻断记录 |
|---|---|---|---|---|---|---|
| R01 | A1 | PASS | COMPLETED | 0 | 12 | 0 |
| R02 | A2 | PASS | COMPLETED | 0 | 12 | 0 |
| R03 | A3 | PASS | COMPLETED | 0 | 12 | 0 |
| R04 | A4 | PASS | COMPLETED | 0 | 12 | 0 |
| R05 | A5 | PASS | COMPLETED | 0 | 12 | 0 |
| R07 | B2 | FAIL | PARTIAL | 1 | 0 | 12 |
| R09 | C1 | PASS | COMPLETED | 0 | 12 | 0 |
| R06 | B1 | UNKNOWN | BLOCKED | 0 | 0 | 12 |
| R08 | B3 | UNKNOWN | BLOCKED | 0 | 0 | 12 |
| R10 | C2 | UNKNOWN | BLOCKED | 0 | 0 | 12 |

唯一缺陷：`F0001 R07 CRS_DECLARATION_CONFLICT`（数据集级，declared_crs=EPSG:3857）。
系统未自动纠偏为 EPSG:4326，未猜测真实坐标系。

> **【作废标注｜2026-10-26 Stage 0 重验补记，严过关（QA）】**
> 原因码 `CRS_DECLARATION_CONFLICT` 是**量级驱动时代**的产物，已随 GA-03 一并删除，
> 不再登记于 `tools/stage0_gate.py` 的 `FAIL_REASON_CODES`（该文件注释中亦已注明"不再登记"）。
> 当前正确原因码为 **`CRS_DECLARATION_MISMATCH`**，判定依据也从「声明单位与坐标量级冲突」
> 改为「原文 B2 要求 EPSG:4326 与提交声明 EPSG:3857 的**可证明声明冲突**」（契约 §4.2 / §4.5）。
> 缺陷条数与总体结论不变（仍 1 条、仍 FAIL）。
> 同理，上表中 R06/R08/R10 的 `UNKNOWN` 是旧词汇，按契约 §1.1 已废止，现为 `INDETERMINATE`
> （`execution_status` 仍为 `BLOCKED`）。
> **本文件其余内容保留为历史记录，不做改写**；本轮独立审查发现的 P1 与撤回说明见同目录 `RETRACTED.md`，
> 重验材料见 `../stage-0-recheck/`。

## 3. 护栏负面自检

命令：`python tools/selfcheck_guards.py`　退出码：**0**

```
[PASS] A 伪造引用必须被拦截：拦截信息：A1 引用内容与第 7 行不一致
  期望: A1. 必填字段必须存在（改写后的伪引用）。
  实际: A1. 每条记录必须包含全部必填字段
[PASS] B 无来源阈值必须被拦截：拦截信息：R09 参数 max_age_days=365 在 C1 的原文引用中找不到来源
[PASS] C Stage 0 产物不得标为 live：检查 manifest 5 个，非 manual 的 0 个
[PASS] D 空数据不得判定通过：实际=INDETERMINATE（零记录或零必检规则不得判定为通过）

GUARDS_OK=true
```

## 4. 依赖冒烟

命令：`python tools/smoke_deps.py`　退出码：**0**（本脚本只报告，不安装）

```
python=3.13.14 platform=Windows-11-10.0.26200-SP0
yaml         OK      版本 6.0.3
pydantic     MISSING
jsonschema   MISSING
fastapi      MISSING
geopandas    MISSING
shapely      MISSING
pyproj       MISSING
pandas       MISSING
pytest       MISSING
Stage 0 门槛要求：零第三方依赖即可完成端到端实例。本环境的 Stage 0 依赖满足情况：满足
```

## 5. 失败与异常记录

| 时间 | 现象 | 处理 |
|---|---|---|
| 生成阶段 | 字典 CSV 未按 CSV 转义，枚举字段被逗号截断，导致 R04 全表误报 | 生成器改用 `csv.writer` |
| 首次门禁 | `2026-09-22 09:30` 被 Python 3.11+ 的宽松 `fromisoformat` 接受 | 改为严格的 ISO8601 正则（必须 T 分隔、带时区） |
| 首次门禁 | 规则按书写顺序执行，被依赖的规则还没跑，依赖阻断失效 | 引入拓扑排序 |
| 首次门禁 | 判定失败的记录仍参与下游检查（"伪执行"） | 把失败行纳入 effective_blocked |
| 报告渲染 | 数据集级缺陷没有行号导致格式化报错 | 区分 record_locator 与 dataset_locator |

以上均已修复并重跑，当前状态为修复后状态。

## 6. 尚未做的事（不得解读为已通过）

- 没有执行任何评测，没有任何指标数字。
- 没有实现 CLI、`compare`、Web、异步任务。
- 没有运行 24 项必测挑战集，仅覆盖了其中第 1、2、3、10 项对应的语义。
- 没有引入任何模型调用，因此不存在"模型链路已验证"的说法。
