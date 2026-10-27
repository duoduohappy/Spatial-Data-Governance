# 示例包说明（含缺陷真值）

所有数据均为**合成数据**：坐标落在虚构的"示例区"矩形范围内（116.3000–116.3200 E，39.9000–39.9200 N），
设施名称为杜撰，与任何真实设施、真实测绘成果无关。许可与溯源见 `../../data/LICENSES.md`。

生成方式：`python tools/make_examples.py`（确定性，可重复；引用行号由脚本回算后冻结）。
`crs_same_unit_wrong` 是唯一的**手写**反例包，脚本不生成它，只登记哈希。
输入哈希清单：`INPUT_MANIFEST.json`。

## 通用文件

| 文件 | 用途 |
|---|---|
| delivery_spec.md | 中文交付说明，条款引用的唯一来源 |
| dictionary.csv | 数据字典（字段名/描述/类型/是否必填/枚举） |
| poi.csv | POI 点数据（record_id, name, category, longitude, latitude, source_time） |
| area.geojson | 项目范围 Polygon |
| crs.json | CRS 声明（含单位） |
| requirements.yaml | 条款对象（含冻结行号与逐字引用） |
| approved-rules.yaml | 已批准规则（或保持 DRAFT） |
| expected/aggregate.json | 期望的总体结论与逐规则**记录级**结论（人工事先写定的基准） |
| expected/findings.json | 期望的逐条 finding（stable_key / reason_code / field / observed_value / review_state / execution_status / record_locator） |
| expected/clause_coverage.json | 期望的逐条必检条款覆盖记录（契约 §3.5） |
| `../../examples/TRUTH_REVIEW.md` | **人工真值审核记录**：每条 expected 的推导过程、本轮差异清单与理由（契约 §9.6） |

## 各包的意图与真值

### clean（12 条记录）— 期望 PASS

全部必检项通过；SD-0011 与 SD-0012 相距约 20 米且同名，作为 R10 的重复候选存在，
但因为 C2 条款明确"仅供参考、不作为放行依据"，该规则 `required_for_release=false`，不影响总体结论。
这一组演示：**非必检项永远可见，但不决定放行。**

### defective（15 条记录）— 期望 FAIL

| 记录 | 注入缺陷 | 期望触发 |
|---|---|---|
| SD-0002 | source_time 写成 `2026-09-22 09:30`（空格分隔、无时区） | R03 TYPE_PARSE_ERROR |
| SD-0003 | category 取值 `公共厕所`（不在枚举内） | R04 ENUM_VIOLATION |
| SD-0005 / SD-0012 | record_id 重复 | R05 DUPLICATE_ID（两条 finding） |
| SD-0006 | source_time = 2026-08-01（超出 30 天） | R09 STALE_RECORD |
| SD-0007 | category 为空字符串 | R02 EMPTY_VALUE |
| SD-0009 | latitude = 91.5000（越界） | R06 LATITUDE_OUT_OF_RANGE |
| SD-0010 | longitude 为空字符串 | R02 EMPTY_VALUE；其 R03 因依赖失败被 BLOCKED |
| SD-0011 | longitude = 116.3600（范围外） | R08 OUTSIDE_PROJECT_AREA |
| SD-0013 | longitude = `abc`（不可解析） | R03 TYPE_PARSE_ERROR |
| SD-0014 / SD-0015 | 相距约 13 米且同名 | R10 DUPLICATE_CANDIDATE（候选，不断言重复） |

### corrected（15 条记录）— 期望 PASS

defective 的整改版本：全部可整改缺陷已修复；保留 SD-0011/SD-0012 这组候选以演示"始终可见"。
SD-0015 更名并移开，R10 候选数量减少但不为零——用于后续 Stage 实现复验对比时的 resolved/persisting 分类。

### ambiguous（12 条记录 + D 组条款）— 期望 INDETERMINATE

数据本身干净，但交付说明多了两条无法判定的条款：

- D1「数据应及时更新」——没有给出天数，**不得默认 30 天**；
- D2「坐标精度应满足项目要求」——没有给出精度真值或测量依据，**不得**。

两条均为必检但不可批准，因此规则保持 DRAFT，执行结果登记为 NOT_EXECUTED / INDETERMINATE，
总体结论 INDETERMINATE。这一组演示：**缺证据就是缺证据，不能被"通过"消化掉。**

### blocked（12 条记录，crs.json 声明 EPSG:3857）— 期望 FAIL

真值是**可证明的声明冲突**，不是"坐标量级可疑"：
交付说明 B2（第 16 行，行号已冻结、文档已哈希）明确「本批次声明为 EPSG:4326」，
而本包 crs.json 提交的是 EPSG:3857。系统按契约 §4 的 **C1 声明一致性**判定 R07 FAIL（数据集级），
finding 的 evidence 给出 `expected_crs` / `declared_crs` / `requirement_id` / `source_quote`；
**不按坐标量级推断真实 CRS**（量级只作 `risk_signals` 里的 `CRS_MAGNITUDE_RISK`，不构成判定依据）。
依赖 CRS 的 R06（坐标范围）、R08（项目范围）、R10（重复候选）按 §4.4 全部阻断为 INDETERMINATE，
其余不依赖坐标系的检查正常执行。这一组演示**依赖阻断**与"绝不自动改坐标系"这条边界。

### crs_same_unit_wrong（12 条记录，crs.json 声明 EPSG:4490）— 期望 FAIL

**手写反例包**（不参与 `make_examples.py` 生成，只在 `INPUT_MANIFEST.json` 登记哈希）。
数据内容与 clean 完全相同，唯一差别是 crs.json 声明 `EPSG:4490`（单位同为 `degree`）。
用来钉死一类回退实现：**单位相同不等于 CRS 正确**。判定只看声明与要求是否严格一致，
不做别名推断（EPSG:4490 ≠ EPSG:4326），因此 R07 必须 FAIL，R06/R08/R10 阻断为 INDETERMINATE，
总体 FAIL。若某个实现让本包 PASS，说明它退化成了"只看单位"或"按量级猜 CRS"。

## 期望结果的可靠性说明

`expected/` 下的文件是**人工按上表逐条推导**后再跑实现的结果（先写期望，再写实现），
不是运行实现后回填的产物；若两者不一致，优先怀疑实现。
`crs_same_unit_wrong` 的期望同样是**先手写**再跑实现，属于重验任务新增的反例包（见上文说明）。

**重生成不等于真值证明**：`python tools/make_examples.py` 会同时重写输入数据与期望文件，
因此"重生成后全绿"不构成独立证据。重生成只允许用于**重建输入包**，
期望的每一次改动都必须先在 `TRUTH_REVIEW.md` 逐条登记理由，再落到文件。

本轮（Stage 0 重验 T05）期望文件的改动共 6 类，逐条登记在 `TRUTH_REVIEW.md` §3：
`UNKNOWN → INDETERMINATE`（GA-06）、blocked 真值依据改为可证明的声明冲突（GA-03）、
`per_rule` 升级为记录级对象与新增 findings/clause_coverage 两个期望文件（验收方"自检证据的限制"第 2 条）、
新增 `truth_review` 人工审核字段（第 3 条）、clean 的 R10 统计口径修正（GA-07）。
**六个包的总体结论与缺陷数本轮前后完全不变**：PASS / FAIL / PASS / INDETERMINATE / FAIL / FAIL，
1 / 11 / 1 / 1 / 1 / 1。当前 `python tools/stage0_gate.py` 对六个包全部输出 `[PASS]`，退出码 0。
任何对 examples 的修改都需要同步更新 `INPUT_MANIFEST.json`、本文件与 `TRUTH_REVIEW.md`。
