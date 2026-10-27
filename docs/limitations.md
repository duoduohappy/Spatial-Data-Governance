# 已知限制（Stage 0）

## 1. 实现层面的近似（Stage 1 必须消除）

| 项 | 现状 | 影响 | 后续 |
|---|---|---|---|
| ~~距离计算~~ | ~~Haversine 球面近似，地球半径 6371008.8 m~~ | ~~与测地线结果有米级以下差异~~ | **Stage 1 已替换**：`pyproj.Geod(ellps="WGS84")` 测地距离；与旧值相对差 0.003%~0.56%，六包结论不变（见 `acceptance/stage-1/GEOMETRY_REPLACE.md`） |
| ~~点在多边形~~ | ~~射线法 + 边界容差 1e-12（自研）~~ | ~~不支持孔、不支持多部件复杂边界判定~~ | **Stage 1 已替换**：Shapely `contains`（exclusive）/ `covers`（inclusive），精确谓词、不再用绝对容差；不支持的几何形状仍落 `NOT_IMPLEMENTED` |
| ~~边界包含策略~~ | ~~仅支持轴向/线段上的数值判定~~ | ~~浮点误差下边界点可能两侧抖动~~ | **Stage 1 已替换**：`边界 = covers(p) ∧ ¬contains(p)`；注意 `boundary.touches(p)` 对线段**内部**的点返回 False，不能用作边界谓词 |
| ~~YAML 解析~~ | ~~自研极简解析器~~ | ~~不支持锚点、多行字符串、深层嵌套~~ | **Stage 1 已替换**：PyYAML `safe_load` + 序列键空值归一；替换前对 12 个 YAML 逐文件对拍全部一致 |
| 数据读取 | csv 标准库 | 大文件性能、编码容错弱 | Stage 1 换 pandas / GeoPandas |

## 2. 范围上的限制（本阶段刻意不做）

- 不支持 PDF / OCR / Word 解析；交付说明只接受 UTF-8 Markdown。
- 不支持栅格、BIM、IoT 时序、路网拓扑、三维渲染。
- 不自动纠偏、删改、合并数据；不生成并执行任意代码或 SQL。
- 不做标准全文知识库、不出具正式证书；不是企业多租户系统，无 SSO、无 K8s、无数据库 CDC、无企业血缘。
- 不自建通用模型网关（ADR-009）。

## 2.5 参数来源护栏的能力边界（GA-05，Stage 0）

`parameter_sources` + `tools/stage0_gate.py` 的 `verify_parameter_sources()` **只在字面上把关**：

**能验证**

- 来源文档的 sha256 与声明一致（`DOCUMENT_HASH_MISMATCH`）；
- `source_line_start..source_line_end` 覆盖范围内的文本与 `source_quote` 逐字一致；
- 参数值在批准引用中按 **token 边界**出现（`PARAMETER_SOURCE_NOT_FOUND`）；
  token 边界 = 词法切分后全等比较，**禁止** `str(value) in quote` 这类子串包含
  （`"3"` 不得命中 `"30"`，`"30"` 不得命中 `"30.0"`，`"EPSG:4326"` 不得命中 `"EPSG:43260"`）；
- 参数↔条款↔规则的绑定关系自洽；
- 来源记录本身的字段完整性（`interpretation` / `reviewer` / `approved_at` 不得为空）。

**不能验证（不得声称已实现）**

- **人工是否真的读过并认可** —— 只能记录 `reviewer` 字符串；
- **`interpretation` 的解释是否正确** —— 自由文本，机器无法判定；
  当参数取值与引用中的字面量不是同一个字符串（例如 `boundary_policy: inclusive`
  对应原文「落在边界线上的点视为落在范围内」），原型以
  `PARAMETER_VALUE_MAPPED_BY_INTERPRETATION` 风险信号登记，机器只校验字面存在；
- 同一文档**其他位置**是否存在冲突表述；
- 文档版本历史与批准版本的关系（无版本库）；
- 参数变更是否真的走了重新批准流程（Stage 0 无 `AuditEvent` 落地）。

结论表述：**参数来源护栏在 Stage 0 只实现到「字面可追溯」，未实现「语义正确可证」。**
任何对外材料不得把这条护栏描述成"阈值一定是对的"。

**人工解释映射的可枚举清单**：凡参数取值与引用字面量不是同一个字符串的映射，都会在
`report.json` 的 `risk_signals` 里以 `PARAMETER_VALUE_MAPPED_BY_INTERPRETATION` 逐条列出
（`rule_id` + `parameter` + `requirement_id` + `value_literal`），不藏在实现里。
当前 6 个示例包**共 6 条**该信号，去重后是**同一处映射**：
`R08.boundary_policy = inclusive` ← 条款 B3「落在边界线上的点视为落在范围内」。
即：**存在 1 类（6 处实例）参数由人工解释映射，机器只保证字面存在**，
不保证该解释符合条款原意；数量必须随示例包/规则增加而同步更新本段。

## 2.6 边界政策与几何支持范围（Stage 0，GA-08）

- 仅支持**单个简单 Polygon 外环**；带孔、多部件（MultiPolygon）、非闭合环一律
  `INDETERMINATE / NOT_IMPLEMENTED`（reason `GEOMETRY_SHAPE_UNSUPPORTED`），不自动闭合、不忽略多余的环。
- 边界判定用 **1e-12 绝对容差**，未做坐标量级自适应；投影坐标的大数值场景可能抖动。
- 只实现 `inclusive` / `exclusive` 两种边界政策；**未知政策或未声明政策会拒绝执行**
  （`BOUNDARY_POLICY_UNKNOWN` / `BOUNDARY_POLICY_UNSPECIFIED`），不退回 inclusive。
- 不支持任何缓冲（`buffer*` 参数 ⇒ `BOUNDARY_BUFFER_NOT_IMPLEMENTED`）。
- Stage 1 换 Shapely 后必须冻结本轮全部边界用例并重跑对比，未做结论一致性对比前不得声称等价。

## 2.7 时间格式范围（这个项目自己的子集）

实现接受的是 **RFC3339 风格子集**：必须带 `T` 分隔符、必须带显式时区（`Z` 或 `±HH:MM`）。
这是**本项目采用的格式子集**，不是 ISO8601 标准的全部；不得表述为"ISO8601 标准要求带时区"。

## 2.8 CRS 判定的能力边界（契约 §4 的 C3 / C4）

- **C3 坐标解释可用性**：声明单位下的坐标量级只产 `risk_signals` 里的 `CRS_MAGNITUDE_RISK`（WARN），
  **不写入任何 finding，不计入 verdict，不阻断下游**。理由：EPSG:3857 在原点附近的坐标值很小，
  与经纬度量级重合完全合法；用"看起来像经纬度"去判 FAIL 属于猜测。
- **C4 真实性恒不判定**：系统**没有真值来源**，因此永远不能回答"这批数据的真实坐标系是什么"。
  R07 PASS 只表示"声明与原文要求一致"，**不代表坐标真的在那个坐标系里**，也不代表没有 GCJ-02 / BD-09 偏移。
- **不做别名推断**：`EPSG:4326` / `EPSG:4490` / `WGS84` 一律按规范化后的字面严格比对，
  `EPSG:4490` 与 `EPSG:4326` 视为**不同**（即便同为 degree）。人工若认为二者等价，
  必须走条款解释与批准流程改原文，不得在实现里加别名表。

## 2.9 风险信号不得参与判定 —— 保证方式（契约 A3）

"风险信号不参与 verdict"这条红线是**机器化**保证的，不靠自觉：

1. **唯一入口**：只有 `Kernel.add_risk_signal(code, severity, message, evidence)` 能追加信号；
   它返回 `None`、签名里没有 `verdict` / `reason_code` 参数 —— 从 API 上就拿不到可用于判定的返回值。
2. **只写窗口**：`Kernel.run()` 执行期间 `self.risk_signals` 被替换成 `WriteOnlyRiskLog`，
   任何读取（`len()` / 迭代 / 下标 / `in` / 真值测试）都抛 `ContractViolation`。
   即"读信号去定结论"在实现层写不出来，写了就一定炸，不会静默生效。
3. **收口断言**：`run()` 结束后断言每个信号的 `code` 已登记，且信号对象不含
   `verdict` / `execution_status` / `reason_code` 字段。
4. **Schema 侧**：`schemas/risk_signal.schema.json` 约束 `code` 只能取注册表成员，
   且 `additionalProperties: false`（携带判定字段即校验失败）。

**仍不能保证的**：信号本身**提示得对不对**（例如"量级可疑"是否真的可疑）无法由机器判断，
因此信号永远只作人工核对的线索，不得作为放行依据。

## 3. 证据力度的限制

- **Stage 0 没有模型参与**，因此尚不能证明任何"模型辅助"带来的收益。任何对外材料不得暗示已验证 AI 效果。
- 示例数据全部为合成数据（见 `data/LICENSES.md`），不代表真实脏数据的分布；
  示例包跑通只证明语义实现正确，不证明泛化能力。
- 尚未执行任何人工工作流对照；没有人工耗时基线，也无第三方复核，不能给出"节省 X% 工时"这类数字。
- 参与方只有作者一人，且当前无 git 提交历史可用于追溯（见 OPEN_ISSUES）。
- 坐标小数位数不代表位置精度；没有真值或测量依据时，不对位置精度是否达标做出判定。
## 4. 对外表述的红线

不写"全球首创""零幻觉""100% 准确""已商业上线""城市级并发"或未经验证的提效比例；
人工个人项目单列，不包装成公司商业案例。
