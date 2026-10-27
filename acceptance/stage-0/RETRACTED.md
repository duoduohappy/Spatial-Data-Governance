# 撤回声明：原 Stage 0 验收包的「P1 = 0」结论作废

- 日期：2026-10-26
- 提出：严过关（QA，Stage 0 重验 T05）
- 依据：独立验收方 2026-10-26 的《GeoAcceptance Stage 0 独立验收报告》（结论：**不通过**）
  + 其可运行探针 `stage0_independent_probes.py` 与探针结果 `stage0-independent-results.json`
- 状态：**本文件只撤回结论，不改写历史**。同目录 `HANDOFF.md` / `OPEN_ISSUES.md` / `TEST_RESULTS.md`
  全部保留为历史记录；重验材料见 `../stage-0-recheck/`。

---

## 1. 被撤回的结论

`acceptance/stage-0/OPEN_ISSUES.md` 第 5 行原文：

> 当前：**P0 = 0，P1 = 0**。以下为 P2/P3，均计划在指定 Stage 修复。

**该结论作废。** 理由不是"我们后来觉得不严谨"，而是**独立方用可运行反例实测证明了它是错的**：
门禁五个包全部与 expected 相符、四项护栏自检全部通过、输入哈希全部一致 —— 这些自检查**全部为真**，
但它们只证明了"所提供的样例可以被复现"，**没有一项**证明判定语义是对的。
把"样例跑通"当成"语义正确"，是本轮被撤回的那个结论的根因。

P0 结论（P0 = 0）**仍然成立**：本轮未发现泄露/未授权写/任意代码执行/伪造结果类问题。

---

## 2. 独立审查发现的 5 个 P1 与 5 个 P2

### 2.1 P1（验收阻断项，共 5 个）

| 编号 | 名称 | 反例（修复前实测） | 修复后实测 | 修复方式 |
|---|---|---|---|---|
| **GA-01** | 必检条款覆盖不完整仍可通过 | clean 删除 R09（C1 仍必检且 SUPPORTED），总体 **PASS** | **INDETERMINATE**，C1 `coverage_state=UNMAPPED` / `CLAUSE_NOT_COVERED_BY_RULE` | 聚合改为以必检条款全集 U 为输入（`build_clause_coverage()` + 新版 `aggregate()`），未映射/未批准/无实现/被拒/缺结果五态各自落 INDETERMINATE |
| **GA-02** | 规则可自行降低条款必检级别 | defective 把 R09 `required_for_release` 改 false + 注入过期记录，总体 **PASS** | **INDETERMINATE**，`config_rejections` 含 `CLAUSE_POLICY_DOWNGRADED_BY_RULE` | `resolve_required_for_release()` 按条款派生 `derived = OR(required_for_release)`，规则声明与派生态冲突即**拒绝执行**该规则 |
| **GA-03** | CRS 未与原文要求比对，且量级猜测被当作事实 | ① 声明改 EPSG:4490（单位仍 degree）→ R07 **PASS**（漏报）；② 移除 `declared_crs` → 总体 **FAIL**（应为 INDETERMINATE） | ① R07 **FAIL** / `CRS_DECLARATION_MISMATCH`；② 总体 **INDETERMINATE**，R06/R08/R10 `INDETERMINATE/BLOCKED` | CRS 拆成 C1 声明一致性 / C2 完备性 / C3 解释可用性 / C4 真实性四类；只有 C1 能判 FAIL；量级只写 `risk_signals.CRS_MAGNITUDE_RISK`；blocked 包真值改为「原文 B2 要求 EPSG:4326 vs 提交 EPSG:3857」的**可证明声明冲突** |
| **GA-04** | 未知依赖被忽略，未批准上游也未阻断 | clean 的 R01 加 `NONEXISTENT_RULE` 依赖，总体 **PASS** | **INDETERMINATE**，`config_rejections` 含 `UNKNOWN_PRECONDITION` | `validate_configuration()` 执行前校验未知依赖/重复 ID/有环/自依赖/重复 precondition，命中即整包拒绝；`ordered_rules()` 删除"过滤不认识的依赖"写法；新增依赖状态传播矩阵（§5.2） |
| **GA-05** | 阈值与文档哈希护栏可被绕过 | ① `max_age_days` 30→3，来源核验**返回空**（"3" 是 "30" 的子串）；② 条款 `document_sha256` 改全 0，核验**返回空** | ① 返回 `PARAMETER_VALUE_MISMATCH` + `PARAMETER_SOURCE_NOT_FOUND`；② 返回 `DOCUMENT_HASH_MISMATCH` | 引入结构化 `ParameterSource`（来源条款/文档哈希/冻结行号/逐字引用/token 级字面量/单位/解释/批准人）；禁用 `str in quote` 子串匹配，改用 token 边界匹配；`verify_document_hashes()` 独立校验哈希 |

### 2.2 P2（契约 / 统计 / 范围问题，共 5 个）

| 编号 | 名称 | 修复方式 |
|---|---|---|
| **GA-06** | `UNKNOWN` 与三态契约冲突（`check_result.schema.json` 只允许 PASS/FAIL/INDETERMINATE） | 全库废止 `UNKNOWN` → `INDETERMINATE`；"没跑成"的信息搬到 `execution_status`；新增 `NOT_IMPLEMENTED / REJECTED / FAILED` 三个状态；组合合法性矩阵写进 `LEGAL_COMBOS` 并运行时断言（删掉「FAIL + NOT_EXECUTED 合法」格，PASS 只允许 COMPLETED） |
| **GA-07** | 已执行失败与候选被算作"未执行"（clean R10 实测 evaluated=11 / blocked=1） | `summary_counts` 改为七字段互斥口径（evaluated / failed / indeterminate / skipped_upstream / uninterpretable + 派生 blocked）；候选不是失败也不阻断；I1–I6 六条不变式写进 `assert_contract()` 运行时断言 |
| **GA-08** | 边界政策与实现不一致（R08 硬编码 `inclusive=True`；`point_in_ring` 在 exclusive 下左/下边 True、右/上边 False） | 重写为"先判边界、再射线法"，两种政策下四边对称；R08 读取 `boundary_policy`；未声明/未知政策/缓冲/带孔/多部件一律 `REJECTED` 或 `NOT_IMPLEMENTED`，禁止静默按另一政策执行 |
| **GA-09** | Schema 草案缺十类参数约束；无依赖的 `preconditions` 被序列化为 `null` 而 Schema 要求 array | 新增 `schemas/parameter_source.schema.json`；按 rule_type 补十类 `parameters` 约束；新增 `tools/check_schema_consistency.py`（标准库子集校验器，显式列出不参与校验的关键字，不静默跳过）；空序列一律 `[]` |
| **GA-10** | ADR-006 重新引入模型网关与预算置信度升级，偏离首版范围 | ADR-006 降级为"未来实验"，移出 Stage 2 必做范围；保留预算上限与成本记录；新增"模型自报置信度不得作为批准依据"约束；新增 ADR-010 记录本轮决策与备选方案（架构师产出，见 `docs/adr/`） |

### 2.3 验收方「自检证据的限制」六条的处理

| # | 验收方意见 | 处理 |
|---|---|---|
| 1 | 护栏 C 项只是检查现有 manifest 的 mode，不是注入负面测试 | C 项改名「产物 mode 一致性检查」；新增 C2 **真注入负面**（真实写入 `mode=live` manifest 后跑同一检查被拦 + 反向确认改回 manual 不报错）；新增 E/F/G 三项 |
| 2 | 主门禁只比结论与缺陷数，"命中错行但数量相同"会通过 | `compare_expected()` 升级为记录级；`per_rule` 升级为对象；新增 `expected/findings.json`、`expected/clause_coverage.json` 两层逐条比对。本轮**独立验证**：四类篡改（错行/多一条/少一条/字段篡改）全部被抓，无变异时零差异 |
| 3 | 生成器会同时重写数据与期望，"重生成全绿"不算真值证明 | 新增 `examples/TRUTH_REVIEW.md`（人工推导过程 + 差异登记表）；每个 expected 增加 `truth_review` 字段；`make_examples.py` 同步真值字典，重跑后 `git diff` 逐条可回溯 |
| 4 | R02 缺失率语义不清 | 新增显式 `missing_rate_policy: "STRICT"`；Stage 0 只允许 STRICT，`allowed_missing_rate > 0` 或政策非 STRICT → `MISSING_RATE_POLICY_NOT_APPROVED` |
| 5 | 把开放式 ISO8601 收紧成"必须带 T 且强制时区"，应写明这是本项目子集 | 六个包 `requirements.yaml` 的 A3 条款补 `interpretation` 字段，写明"本项目采用 ISO8601 的 RFC3339 子集…这是本项目采用的格式子集，不是 ISO8601 标准的全部" |
| 6 | 目标空间依赖安装/运行验证与 Docker 冒烟未完成 | **如实记为阶段缺口**（见 `../stage-0-recheck/DEPS_SMOKE.md`），未声称已完成 |

---

## 3. 撤回之后，原验收包里哪些结论还成立

| 原结论 | 现状态 |
|---|---|
| P0 = 0 | **仍成立** |
| P1 = 0 | **作废**（实为 5 个） |
| 五项端到端样例与 expected 相符 | 成立，但**只是样例可复现**，不构成语义正确的证据 |
| INPUT_MANIFEST 哈希一致 | 成立（本轮重算后仍一致，60 个文件） |
| 标注 manual，没有冒充 live / 没有模型调用 | 成立，且本轮新增了"注入 live 必须被拦"的真负面护栏 |
| "尚未做的事"一节（未做评测 / 未实现 CLI / 未跑 24 项挑战集 / 无模型链路） | 成立 |

---

## 4. 修复提交 SHA

见 `../stage-0-recheck/HANDOFF.md` 第 4 节（含 d057c0a 之后的全部修复提交）。

## 5. 历史记录的处置

- `HANDOFF.md` / `OPEN_ISSUES.md`：保留原文，不做改写（其"P1 = 0"与本文件冲突时，**以本文件为准**）。
- `TEST_RESULTS.md`：保留原文，仅在第 64 行的旧原因码 `CRS_DECLARATION_CONFLICT` 处补了一段
  **作废标注**（2026-10-26 补记），说明该码已随 GA-03 删除、当前正确码为 `CRS_DECLARATION_MISMATCH`，
  以及表中 `UNKNOWN` 的历史含义。除该标注外未改动任何历史内容。
