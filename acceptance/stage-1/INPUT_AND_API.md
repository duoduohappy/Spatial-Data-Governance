# Stage 1：执行入口输入校验 + 判定接口收敛

- 日期：2026-10-26　对应最终复验报告《Stage 1 的进入条件与顺序》第 5 条
- 冻结基线：Stage 0 提交 `31d43a8`（标签 `stage0-frozen`）

---

## 1. 执行入口的结构化输入校验（Pydantic，strict）

新增 `tools/input_models.py`，由 `Kernel.collect_config_rejections()` 在**实际执行入口**调用
（`reject_input_schema()`），失败即登记 `INPUT_SCHEMA_INVALID` 并整包拒绝执行（契约 §2.4 / §9.1）。

- **strict=True**：不接受 `"yes" → True`、`"1" → 1` 这类隐式类型收敛（lax 模式实测会把 `"yes"` 收敛成 `True`，
  见 `env-verify.txt`）—— 隐式类型是错误放行的温床。
- 已知字段从严，未知字段 `extra="allow"`（Schema 演进不误杀）。
- 覆盖：`Requirement`（ID/哈希 64 位十六进制/行号 ≥1/`support_status` 三值枚举）、
  `Rule`（`requirement_ids` 非空/`status`/`rule_type`）、`ParameterSource`（同条款来源结构）。

### 回归用例（`S1_input_schema_validation`，25 项探针之一）

| 输入 | 预期 | 实测 |
|---|---|---|
| 六个真实包 | **不得**出现 `INPUT_SCHEMA_INVALID`（不误杀） | 通过（误杀 0） |
| `required_for_release: "yes"`（类型收敛） | 登记 `INPUT_SCHEMA_INVALID`，总体 != PASS | `INPUT_SCHEMA_INVALID`，`INDETERMINATE` |
| `support_status: "SUPPORTED_X"`（枚举越界） | 同上（另有两种既有拒绝码同时命中） | `INPUT_SCHEMA_INVALID` + `CLAUSE_SUPPORT_STATUS_UNKNOWN` + `APPROVED_RULE_FOR_UNSUPPORTED_CLAUSE`，`INDETERMINATE` |
| `document_sha256: "abc"`（哈希格式） | 同上 | `INPUT_SCHEMA_INVALID`，`INDETERMINATE` |
| `source_line_start: 0`（行号越界） | 同上 | `INPUT_SCHEMA_INVALID`，`INDETERMINATE` |

---

## 2. 判定接口收敛：删除 `aggregate` 二参数兼容路径

| 项 | 处理 |
|---|---|
| `aggregate(results, n_rows)` 二参数签名 | **已删除**；以旧签名调用即 `TypeError`，消息里给出迁移写法 |
| `_coverage_from_results()` 兼容辅助 | **已删除** |
| 唯一正式接口 | `coverage = kernel.build_clause_coverage(results)` → `aggregate(coverage, kernel.collect_config_rejections(), len(kernel.rows))` |

不再保留"两处判定口径"：Stage 0 的 S0-R8（兼容路径与权威路径的 FAIL 条款列举顺序不一致）
随兼容路径一并消失。

### 迁移影响（**对外显式说明，不隐藏**）

独立验收方的原探针 `stage0_independent_probes.py` 仍以二参数调用（第 9、47 行），
现在会抛 `TypeError`。本仓库采取的做法：

- **不**为了让它跑通而在内核保留第二条判定路径（那正是验收方要求收敛的东西）；
- 对拍环节如实报 `[SKIP] 原探针使用已删除的二参接口` 并打印迁移写法，不计为通过也不计为失败；
- 本仓库 25 项探针已全部迁到唯一正式接口，其中**包含原那五个 P1 用例**
  （GA01/GA03×2/GA04/GA02），对拍的证据价值由它们承载。

迁移写法（原探针两处）：

```python
# 旧：a, reason = g.aggregate(r, len(k.rows))
cov = k.build_clause_coverage(r)
a, reason = g.aggregate(cov, k.collect_config_rejections(), len(k.rows))
```

---

## 3. 顺带修掉的契约漏洞（在迁移过程中暴露）

**条款级聚合会把「规则级 PASS + 非 OK 原因码」洗白成 PASS/OK。**
故障注入 `R02 → A2: PASS + EMPTY_VALUE`（I7 违反）时，`aggregate_clause()` 走
「全部 PASS ⇒ PASS/OK」分支，把违规输入改写成一条看起来正常的条款结论。

修复：`aggregate_clause()` 入口只拦 **I7**（`PASS` 且 `reason_code != "OK"`）⇒
`INDETERMINATE / FAILED / CONTRACT_VIOLATION`。
不拦 I8/I9：`FAIL + OK`、`INDETERMINATE + OK` 由契约 §3.5.1 的**取值链补齐原因**
（分别落到 `CONTRACT_VIOLATION` / `DUPLICATE_CANDIDATE` / 缺证据类码），属于修复而非放行；
而 PASS 一旦带非 OK 码，补任何值都等于放行，只能失败关闭。

回归：`NEW_single_official_interface` 覆盖 I7/I8/I9 三类违反 + 仅候选 + 无码可取 + 正常 PASS。

---

## 4. 本批回归结果

| 套件 | 结果 |
|---|---|
| `tools/stage0_gate.py`（六包） | `ALL_OK=true`，退出 0 |
| `tools/recheck_probes.py` | `RECHECK_PROBES_OK=true`，**25/25**（新增 `S1_input_schema_validation`） |
| `tools/selfcheck_guards.py` | `GUARDS_OK=true` |
| `tools/check_schema_consistency.py` | `SCHEMA_CONSISTENT=true` |
| 冻结快照比对 | 六包全部规则/条款字段**零差异**（仍只有几何层 7 处有依据的差异） |
