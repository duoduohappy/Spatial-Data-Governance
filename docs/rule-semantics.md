# 十类检查规则的语义（Stage 0）

通用约束：

- 每种规则必须定义：参数 Schema、前置条件、通过 / 失败 / 未知的判定语义、边界与正反例。
- **模型提议、人工批准、确定性工具判定。** 模型（Stage 2 起存在）不得更改最终 verdict。
- **依赖（preconditions）失败时不伪执行**：前置检查失败的原始记录在本规则中标记为 BLOCKED，
  既不记为 PASS 也不记为 FAIL。
- 不得因为“文档没写”而填入行业默认阈值；没写就保持未批准 / 未知。

下文“.valueOf”一列中的取值均为示例。

## R01 必需字段存在

| 项 | 内容 |
|---|---|
| 参数 | `fields: [字段名列表]` |
| 前置条件 | 无 |
| PASS | 数据表包含全部字段，且每行字段数与表头一致 |
| FAIL | `FIELD_COLUMN_MISSING`（整列缺失，数据集级，不挂记录行）/ `FIELD_COUNT_MISMATCH`（行字段数不符） |
| 未知 | 不适用于本规则 |
| 边界 | 字段存在但整列为空由 R02 负责；本规则只管“在不在” |

## R02 非空

| 项 | 内容 |
|---|---|
| 参数 | `fields`、`trim`、`allowed_missing_rate`、`missing_rate_policy`（契约 §9.2） |
| 前置条件 | R01 |
| PASS | 指定字段去除首尾空白后长度不为 0 |
| FAIL | `EMPTY_VALUE`（计入 `records_failed`） |
| 未知 | Stage 0 **只允许** `missing_rate_policy: "STRICT"`（缺失率必须为 0 才 PASS）。`allowed_missing_rate > 0` 或政策非 STRICT ⇒ `config_rejections: MISSING_RATE_POLICY_NOT_APPROVED`，整包拒绝执行。**禁止**靠字段名混用语义，也禁止把字段缺失静默记成"未执行" |
| 边界 | `"   "` 视为空；字符串 `"0"` 不为空 |

## R03 类型 / 解析

| 项 | 内容 |
|---|---|
| 参数 | `fields`（取自数据字典的 `data_type`） |
| 前置条件 | R02 |
| PASS | string / integer / number / ISO8601 datetime 均可被解析；原值保留，不静默纠正 |
| FAIL | `TYPE_PARSE_ERROR`、`NON_FINITE_NUMBER`（NaN / Infinity）、`UNSUPPORTED_DATA_TYPE`（字典里声明了未知类型） |
| 未知 | 同一记录中任一字段为空 ⇒ 该记录整体 BLOCKED，不给出部分有效的假象 |
| 边界 | 布尔值不算数字；`"2026-09-22 09:30"`（空格分隔、无时区）**不**算合法时间。本非空时间格式是**本项目采用的 RFC3339 风格子集**（必须带 `T` 分隔、必须带显式时区 `Z` 或 `±HH:MM`），**不是 ISO8601 标准的全部**；不得以"ISO8601 要求"为由声称标准本身有此要求（契约 §9.3） |

## R04 枚举分类

| 项 | 内容 |
|---|---|
| 参数 | `field`、`allow_alias: false` |
| 前置条件 | R01、R03 |
| PASS | 取值落在已批准字典的枚举内 |
| FAIL | `ENUM_VIOLATION`（证据含字典行号） |
| 未知 | 字段为空 ⇒ BLOCKED；存在未批准的别名映射请求 ⇒ NEEDS_CLARIFICATION，不允许先改值再判通过 |
| 边界 | 大小写差异不放过；枚举字典本身为空 ⇒ 本规则 FAIL 并提示字典缺陷 |

## R05 ID 唯一

| 项 | 内容 |
|---|---|
| 参数 | `field`（record_id） |
| 前置条件 | R01 |
| PASS | 全部 ID 非空且唯一 |
| FAIL | `DUPLICATE_ID`（每条重复记录各出一条 finding，附 duplicates 行号）/ `EMPTY_ID` |
| 未知 | 业务 ID 缺失时依靠行号定位，仍可出具 finding |
| 边界 | 不允许通过去重后的样本数来计算通过率 |

## R06 坐标几何

| 项 | 内容 |
|---|---|
| 参数 | `lon_range`、`lat_range` |
| 前置条件 | R01、R03、R07 |
| PASS | 有限数值且落在范围内 |
| FAIL | `LONGITUDE_OUT_OF_RANGE` / `LATITUDE_OUT_OF_RANGE` |
| 未知 | CRS 未确定或声明冲突 ⇒ 整批不执行；坐标均落在合法范围**不能**证明经纬度顺序或位置正确 |
| 边界 | NaN / Infinity 视为解析失败（R03）；疑似经纬反转只有在两者都合法时才标为**无法证明**，不断言正确 |

## R07 CRS 声明一致性（契约 §4：四类分离）

R07 把原来混在一起的四件事分开判定，**只有第一类能判 FAIL**：

| 类 | 判什么 | 结论 | 证据要求 |
|---|---|---|---|
| C1 声明一致性 | 提交的 `declared_crs` 与原文要求的 CRS 是否一致 | 唯一可判 FAIL：`CRS_DECLARATION_MISMATCH` | `expected_crs`、`declared_crs`、`requirement_id`、`document_id`、`document_sha256`、`source_line_start`、`source_quote`；严格规范化后比对（去空白、转小写），**不做别名推断** |
| C2 元数据完备性 | 是否有 CRS 声明 | 缺声明 ⇒ `CRS_MISSING_DECLARATION`，规则级 **INDETERMINATE**，并按 §4.4 阻断下游空间规则 | finding 记在数据集级记录（`crs.json`），不挂行号 |
| C3 坐标解释可用性 | 声明单位下的坐标量级是否"看起来像经纬度" | **只产 risk signal**（`CRS_MAGNITUDE_RISK`），永不参与 verdict、不产 finding | 见下条边界说明 |
| C4 真实性 | 数据真实的坐标系究竟是什么 | **恒不判定**（本系统无真值），写入 `docs/limitations.md` | 无 |

| 项 | 内容 |
|---|---|
| 参数 | `expected_from_sidecar: true`（以 crs.json 为准）、`expected_crs`（须有已批准 ParameterSource） |
| 前置条件 | R01 |
| PASS | 声明存在，且与原文要求的 CRS 严格一致 |
| FAIL | `CRS_DECLARATION_MISMATCH`（数据集级）——仅由 C1 产生 |
| 未知 | `CRS_MISSING_DECLARATION`（缺声明）/ `CRS_EXPECTED_NOT_APPROVED`（要求的 CRS 无已批准来源）：整批空间检查阻断，规则级 INDETERMINATE |
| 边界 | 单位相同**不能**救回错误的 CRS：EPSG:4490（degree）≠ EPSG:4326（degree），见反例包 `examples/crs_same_unit_wrong`；**系统不自动猜测或纠偏** WGS84 / GCJ-02 / BD-09；坐标量级（"声明为米单位但坐标落在经纬度量级"）在 EPSG:3857 下原点附近完全合法，因此只作风险信号，不写进 finding evidence |

## R08 项目范围

| 项 | 内容 |
|---|---|
| 参数 | `boundary_policy: inclusive/exclusive`（必须来自配置）、`expected_*`；缓冲类参数（`buffer*`）Stage 0 不支持 |
| 前置条件 | R01、R03、R06、R07 |
| PASS | 点位落在范围内；政策决定边界线上的点算不算通过（见下表） |
| FAIL | `OUTSIDE_PROJECT_AREA` |

**边界政策语义**（契约 §8.1，Stage 0 已按此实现）：

| 政策 | 内部 | 边界线上 | 外部 |
|---|---|---|---|
| `inclusive` | PASS | PASS | FAIL |
| `exclusive` | PASS | FAIL | FAIL |

实现要点（GA-08）：先判边界、再判内部。旧实现先走射线法导致 exclusive 下单位正方形
左/下边误判为在范围内，右/上边为外部（不对称）。

**Stage 1 起改为 Shapely 精确谓词**（口径不变，实现替换）：
- `exclusive` ⇔ `Polygon.contains(p)`（严格内部，不含边界）；
- `inclusive` ⇔ `Polygon.covers(p)`（内部 ∪ 边界）；
- 边界判定 ⇔ `covers(p) ∧ ¬contains(p)`。
  不能用 `boundary.touches(p)`：Shapely 的 `touches` 要求公共点只落在两者边界上，
  对**线段内部**的点返回 False（实测四边中点/顶点全部为 False）。
- Stage 0 的 1e-12 绝对容差已取消：它会把距边 1e-12 度（≈1e-7 m）内的点都算作边界，
  **包括真正落在多边形外的点**（属错误放行倾向）。

| 未知 / 拒绝 | 处置 |
|---|---|
| 坐标无法解析或 CRS 未定 | BLOCKED（记 `records_skipped_upstream`） |
| `boundary_policy` 缺失 | `config_rejections: BOUNDARY_POLICY_UNSPECIFIED`，规则 `INDETERMINATE / REJECTED` |
| 值不在 {inclusive, exclusive} | `BOUNDARY_POLICY_UNKNOWN` + `REJECTED` |
| 出现任何 `buffer*` 参数 | `BOUNDARY_BUFFER_NOT_IMPLEMENTED` + `REJECTED`（禁止静默忽略缓冲） |
| 带孔 / MultiPolygon / 非闭合环 | 规则 `INDETERMINATE / NOT_IMPLEMENTED`，reason `GEOMETRY_SHAPE_UNSUPPORTED` |
| 边界/几何实现 | **Stage 1 已换 Shapely**（`contains` / `covers`），并已按冻结基线重跑对比：六包全部规则/条款字段无变化，仅 1e-13 级边界扰动点与距离值的判定按精确谓词修正（依据见 `acceptance/stage-1/GEOMETRY_REPLACE.md`）。仍只支持单个简单 Polygon 外环，带孔/MultiPolygon 依旧 `NOT_IMPLEMENTED` |

## R09 时效

| 项 | 内容 |
|---|---|
| 参数 | `reference_time`（固定值，禁止使用“当前时间”）、`max_age_days` |
| 前置条件 | R01、R03 |
| PASS | 时间与基准时间之差 ≤ 阈值，且不晚于基准时间 |
| FAIL | `STALE_RECORD`（附 age_days）/ `FUTURE_TIMESTAMP` |
| 未知 | 无时区信息且未被人工确认 ⇒ `TIMEZONE_UNDECLARED` 并按未定处理；时间不可解析 ⇒ BLOCKED |
| 边界 | 原文未给出天数不得默认 30 天；跨日重跑使用固定 reference_time，核心结论必须一致 |

## R10 重复候选（不断言重复）

| 项 | 内容 |
|---|---|
| 参数 | `max_distance_m`、`name_equal` |
| 前置条件 | R01、R03、R06 |
| PASS | 不存在符合策略的候选 |
| FAIL | 不适用——本规则不产生 FAIL；候选不是失败（契约 §7.2） |
| 未知 | 存在候选 ⇒ 规则级 `INDETERMINATE`，等待人工确认；**近邻不等于同一实体** |
| 统计 | 候选涉及行进 `records_indeterminate`，**不进** `records_failed`、**不向下游传播阻断**；finding 以"组"计（1 条可覆盖 2 行） |
| 边界 | 证据必须给出实测距离与对侧行号；两个邻近院区是典型的"候选但非重复"反例 |

## 原因码与风险信号的登记纪律（新增码必读）

**红线：新增 `reason_code` 必须显式声明归属三类之一，未声明在登记期即报错。**

| 类别 | 常量 | 语义 | 对规则级结论的影响 |
|---|---|---|---|
| FAIL 类 | `FAIL_REASON_CODES` | 作为 finding 出现即判定失败（默认类） | 结论 FAIL |
| 候选类 | `CANDIDATE_REASON_CODES` | 只是待人工确认的候选，**不是失败** | 进 `records_indeterminate`，不阻断下游（§7.2） |
| 缺证据类 | `INDETERMINATE_REASON_CODES` | 拿不出证据，不是失败 | 结论 INDETERMINATE，按 §4.4 阻断下游 |

保证方式（三层，缺一不可）：

1. `REASON_CODES` 是三类之**并**，不再单独维护字面量 —— 因此不存在"登记了但没分类"的码；
2. 模块导入期执行 `check_registries()`：三类不互斥、并集不等于全表、风险信号码混入原因码表，
   一律 `RegistryError`（**启动即失败**，不是运行到某条规则才 quietly 退回 FAIL）；
3. `Kernel.finding()` 再校验一次：未登记 / 未分类 / 属于规则级专用码（`RESULT_ONLY_REASON_CODES`）
   的码一律 `ContractViolation`。

另外：规则级状态类的码（`OK`、`ALL_RECORDS_BLOCKED`、`UPSTREAM_*` 等）只允许出现在
`CheckResult.reason_code`，**不得写进 finding**；`schemas/finding.schema.json` 的枚举必须等于
`FINDING_REASON_CODES`，由 `tools/check_schema_consistency.py` 的登记表一致性检查兜底。

**`reason_code` 与 verdict 必须相容（契约 §3.5.1，I7–I9）**：`OK` 只在 PASS 时合法；
FAIL 取第一条 FAIL 类 finding 的码；INDETERMINATE 按「覆盖态码 → 缺证据类码 → 上游码 /
`ALL_RECORDS_BLOCKED` → 候选类码」取值链取码，任何分支取不到码一律 `CONTRACT_VIOLATION` 兜底，
**禁止退回 OK**。规则级（`assert_contract`）与条款级（`build_clause_coverage`）共用同一组运行时断言；
`failure_reason_codes` / `advisory_reason_codes` 去重、保留首次出现顺序，Schema 已登记并受奇偶校验。

**风险信号（A3）**：`RISK_SIGNAL_CODES` 是唯一注册表（当前 3 个：
`PARAMETER_VALUE_MAPPED_BY_INTERPRETATION`、`IMPLICIT_REQUIRED_FOR_RELEASE`、`CRS_MAGNITUDE_RISK`），
Schema 侧由 `schemas/risk_signal.schema.json` 约束，且信号对象**不得携带** `verdict` /
`execution_status` / `reason_code` 字段。详见下一节「风险信号不得参与判定的保证方式」。

## Stage 0 已验证 vs 待补

- 已实现并在 `tools/stage0_gate.py` 中端到端跑通：R01–R10 全部主干语义；
  其中 R02 的缺失率政策、R08 的边界政策、R10 的候选口径已按重验契约重做。
- 距离用 Haversine（地球半径 6371008.8 m，球面近似），Stage 1 起改为 pyproj 测地线并对比差异。
- `allowed_missing_rate > 0`、别名映射、非零缓冲等业务策略留到 Stage 1，本阶段一律取严格值，
  避免"默认值"污染判定；配置项出现非 STRICT 政策或缓冲参数时**拒绝执行**，而不是退回默认值。
- R07 的 CRS 判定已按契约 §4 重做为**四类分离**（C1 声明一致性唯一可判 FAIL；C2 缺声明落 INDETERMINATE
  并阻断下游；C3 坐标量级只产 risk signal；C4 真实性恒不判定）。**"由坐标量级驱动 FAIL"的历史实现已删除**，
  量级不再进入任何 finding 的 evidence，只出现在 `risk_signals`。
  回归护栏：`examples/blocked` 的真值改为可证明的**声明冲突**（B2 冻结行要求 EPSG:4326，提交 EPSG:3857），
  `examples/crs_same_unit_wrong` 用 EPSG:4490（同为 degree）钉死"按单位放行"的回退实现。
