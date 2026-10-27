# Stage 1：内核/CLI、报告与整改 compare

- 日期：2026-10-26　对应最终复验报告《Stage 1 的进入条件与顺序》第 6、8 条
- 冻结基线：Stage 0 提交 `31d43a8`（标签 `stage0-frozen`）

> **归档注（2026-10-26 第二轮）**：本文件与同目录的 `cli-compare.txt`、
> `compare-defective-corrected.json` 是**第一轮（`stage1-compare-1`）**的口径与产物：
> 当时 `closed` 的判据是"整改后没有 FAIL finding"，总体叫 `COMPLETE`，`run` 同时承担
> 正式检查与 expected 回归。外部复核（Codex）判定该口径**不成立**并给出五个反例，
> 第二轮已重写 compare 与 CLI 入口。**现行口径见 `../stage-1-verify/ROUND2.md`**，
> 本文件保留为历史记录，不再作为现状说明。

---

## 1. 模块划分（最小模块，**不复制判定逻辑**）

| 模块 | 职责 |
|---|---|
| `tools/stage0_gate.py` | **内核**：Kernel、十类规则、条款覆盖、聚合、契约断言（唯一判定口径） |
| `geoacceptance/cli.py` | CLI：`run` / `report` / `compare` / `env` |
| `geoacceptance/compare.py` | 整改复验 compare（跨批次身份 + 规则版本） |
| `geoacceptance/reporting.py` | HTML 报告渲染（只呈现，不做二次判定；文本全部 HTML 转义） |
| `geoacceptance/inputs.py` | 输入防护：路径穿越、文件大小上限、UTF-8 强制 |

刻意**不**把内核复制一份进包里：Stage 0 的教训是"两处判定口径"必然发散（见 S0-R8）。

## 2. CLI

```bash
./.venv/Scripts/python.exe -X utf8 -m geoacceptance.cli run --bundle clean --html
./.venv/Scripts/python.exe -X utf8 -m geoacceptance.cli run --html          # 六包 + HTML
./.venv/Scripts/python.exe -X utf8 -m geoacceptance.cli report \
    --from-json work/stage0/defective/report.json --out work/stage1/cli-report.html
./.venv/Scripts/python.exe -X utf8 -m geoacceptance.cli compare \
    --before defective --after corrected --out work/stage1/compare.json
./.venv/Scripts/python.exe -X utf8 -m geoacceptance.cli env
```

原始输出：`cli-run.txt`（六包 + 6 个 HTML）、`cli-compare.txt`、`sample-report-defective.html`。

退出码：`run` 0/1（沿用门禁语义）；`compare` **0 = COMPLETE，2 = 存在未完成或不可比较项**。

## 3. 整改 compare：身份不靠行号（第 8 条）

身份策略：`record_id`（poi.csv 首列），要求两批**都存在且唯一**；
**不用行号兜底** —— 插入或删除一行会让行号整体漂移，按行号匹配会把甲的问题记到乙头上。

| 情形 | 判定 |
|---|---|
| 标识缺失或批次内重复 | `not_comparable`（并写明原因） |
| 规则版本不同（`rule.version` 变化） | 该规则涉及条目 `not_comparable`（不是同一把尺子） |
| 规则只存在于整改后 | `not_comparable`（无基线可比） |
| 整改前有失败、整改后无 | `fixed` |
| 两边都有失败 | `still_open`（失败码集合缩小附 `reduced=True`） |
| 整改前无、整改后有 | `new_issue` |

总体：`COMPLETE` 仅当无 `still_open` / `new_issue` / `not_comparable`；
有未完成项 ⇒ `NOT_COMPLETE`；**有不可比较项 ⇒ `INDETERMINATE`（不得宣称整改完成）**。

### 实测（defective → corrected）

```
整改前总体=FAIL（findings=11）　整改后总体=PASS（findings=1）
身份策略：record_id（poi.csv 首列），要求两批均存在且唯一；不使用行号
汇总：fixed=8, not_comparable=1
结论：INDETERMINATE
  SD-0002 R03 fixed  TYPE_PARSE_ERROR → -
  ...（共 8 条 fixed）
  SD-0005 R05 not_comparable  DUPLICATE_ID → -  ← 记录稳定标识不可用（批次内重复），拒绝按行号匹配
```

`SD-0005` 之所以不可比，是因为 defective 包里的这条缺陷**本身就是重复 ID** ——
身份无法建立，如实标 `not_comparable`，而不是"挑一个行号继续比"。
因此这次 compare 的结论是 `INDETERMINATE`，**不宣称"整改已完成"**。

对照用例：`clean → clean` ⇒ `COMPLETE`、无差异；
把副本里 `R02.version` 改成 2 ⇒ 涉及 R02 的条目全部 `not_comparable`。

## 4. 报告（HTML）

- 由 `report.json` 渲染，**不新增任何推断**（例如不把 INDETERMINATE 说成"基本通过"）；
- 三态着色：PASS 绿 / FAIL 红 / INDETERMINATE 琥珀；
- 文本全部 `html.escape`（闭合 Stage 0 遗留项 S0-09）；
- 样例：`sample-report-defective.html`。

## 5. 输入防护

- 包路径必须位于根目录之内：`../..` 实测抛 `InputGuardError`（不静默放行）；
- 单文件超过 20 MiB 报错（不截断，避免"读了一半"被当成完整证据）；
- 非 UTF-8 明确报错（不用 `errors="ignore"` 掩盖）。

## 6. 本批回归结果

| 套件 | 结果 |
|---|---|
| `tools/recheck_probes.py` | `RECHECK_PROBES_OK=true`，**28/28**（新增 `S1_uncovered_coverage_branches`、`S1_input_schema_validation`、`S1_cli_smoke`、`S1_compare_identity`） |
| `tools/stage0_gate.py`（六包） | `ALL_OK=true`，退出 0 |
| `tools/selfcheck_guards.py` / `check_schema_consistency.py` | `GUARDS_OK=true` / `SCHEMA_CONSISTENT=true` |
| 冻结快照比对 | 六包全部规则/条款字段**零差异** |

## 7. 未解决 / 遗留

- CLI 只支持 `examples/` 下的包名（绝对路径包尚未开放，需先扩展输入防护的白名单机制）。
- compare 目前只比较 **FAIL 类** finding；候选（`DUPLICATE_CANDIDATE`）与缺证据类的跨批次变化未纳入台账（Stage 1 后续）。
- JSON 报告沿用 `report.json`；结构化 Schema 校验尚未覆盖 compare 产物。
- Docker 冒烟仍未做（见 `ENV.md` §5）；geopandas 仍只做运行验证。
