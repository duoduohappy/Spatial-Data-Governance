"""正式检查入口 `validate`：**任意交付包目录，不需要 expected 真值**。

与回归工具的职责分离（外部复核 §七）：

| 入口 | 用途 | 是否需要 expected |
|---|---|---|
| `validate` | 正式检查一个交付包（examples 内的示例包、或任何给出的目录） | **不需要**（无 expected 也能给出三态结论） |
| `regress`  | 把 examples 六个**示例包**的实际结果与**冻结 expected** 逐字段比对 | 需要（回归工具，不是正式入口） |

`validate` 的纪律与内核一致：
- 配置/前置校验未过 ⇒ **拒绝执行**（`executed=false`，结论 INDETERMINATE），不拿"跑出来的数"凑结论；
- 结论只来自 `build_clause_coverage` → `aggregate` 这条唯一正式路径；
- 输入防护（存在性 / 单文件上限 / UTF-8）与 CLI 一致，超限或非 UTF-8 一律报错，不静默截断；
- findings 按 FAIL / CANDIDATE / INDETERMINATE 三类分别计数并列出，**候选与未知不被混进"失败数"**。
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
import stage0_gate as gate  # noqa: E402
from geoacceptance import inputs  # noqa: E402
from geoacceptance.compare import BUNDLE_TEXT_FILES, guard_bundle  # noqa: E402

SCHEMA_VERSION = "stage1-validate-2"


def validate_bundle(bundle: Path, max_bytes: int = inputs.DEFAULT_MAX_BYTES) -> dict:
    """跑一个交付包并给出结论；**不读取也不比对任何 expected**。"""
    bundle = Path(bundle)
    guard_bundle(bundle, max_bytes)
    k = gate.Kernel(bundle)
    rejections = k.collect_config_rejections()
    problems = k.verify_quotes() + k.verify_parameter_sources()

    # 拒绝执行 ≠ "项目没有条款"（S1-R2-01 最小修复要求）：
    # 应检查的条款清单始终来自 requirements.yaml，即使整包被拒也要在报告里保留数量与清单。
    clauses_pending = [str(r.get("requirement_id"))
                       for r in (k.req_doc.get("requirements") or [])]

    inputs_meta = {}
    for name in BUNDLE_TEXT_FILES:
        p = bundle / name
        inputs_meta[name] = {"sha256": gate.sha256_file(p), "bytes": p.stat().st_size}

    if rejections or problems:
        # 与门禁 main() 同一条纪律：拒绝执行，不给"看起来正常"的结论
        results, findings, coverage = [], [], []
        agg, reason = "INDETERMINATE", ("配置/前置校验未通过，拒绝执行（%d 项拒绝 / %d 项问题）；"
                                        "仍有 %d 个条款应检查（clauses_pending），未执行不得当成通过"
                                        % (len(rejections), len(problems), len(clauses_pending)))
        executed, exec_error = False, None
    else:
        try:
            results, findings = k.run()
            coverage = k.build_clause_coverage(results)
            agg, reason = gate.aggregate(coverage, rejections, len(k.rows))
            executed, exec_error = True, None
        except Exception as exc:  # noqa: BLE001 —— 执行期异常不得变成"看起来正常"的结论
            results, findings, coverage = [], [], []
            agg, reason = "INDETERMINATE", ("执行期异常，拒绝判定：%s: %s"
                                            % (type(exc).__name__, exc))
            executed, exec_error = False, "%s: %s" % (type(exc).__name__, exc)

    by_class = Counter()
    for f in findings:
        by_class[gate.classify_reason_code(f.get("reason_code"))] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": gate.TOOL_VERSION,
        "python": sys.version.split()[0],
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "bundle": str(bundle),
        "mode": "validate",
        "mode_note": "正式检查入口：不需要 expected 真值，结论只来自内核唯一判定路径。",
        "expected_used": False,
        "inputs": inputs_meta,
        "executed": executed,
        "exec_error": exec_error,
        # 拒绝执行时保留"应检查的条款"（S1-R2-01）：不得把拒绝执行说成项目没有条款
        "clauses_pending": clauses_pending if not executed else [],
        "config_rejections": [{"code": r.get("code"), "target": r.get("target"),
                               "detail": str(r.get("detail"))} for r in rejections],
        "preflight_problems": [str(p) for p in problems],
        "aggregate_verdict": agg,
        "aggregate_reason": reason,
        "clause_coverage": coverage,
        "check_results": results,
        "findings": findings,
        "findings_by_class": dict(by_class),
        "counts": {
            "records": len(k.rows),
            # 拒绝执行时也要报告"应检查的条款数量"（来自 requirements.yaml，不是 coverage）
            "clauses_required": len(coverage) if executed else len(clauses_pending),
            "clauses_covered": sum(1 for c in coverage if c.get("coverage_state") == "COVERED"),
            "rules": len(results),
            "findings": len(findings),
        },
    }


def render_text(result: dict) -> str:
    """人类可读输出（与 JSON 同源，不另算一遍）。"""
    L = []
    L.append("正式检查 validate：%s" % result["bundle"])
    L.append("  结论：%s　%s" % (result["aggregate_verdict"], result["aggregate_reason"]))
    L.append("  记录 %d 条　必检条款 %d（已覆盖 %d）　规则结果 %d　findings %d %s"
             % (result["counts"]["records"], result["counts"]["clauses_required"],
                result["counts"]["clauses_covered"], result["counts"]["rules"],
                result["counts"]["findings"], result["findings_by_class"]))
    L.append("  expected 真值：%s（本入口不需要 expected）"
             % ("已使用" if result["expected_used"] else "未使用"))
    if not result["executed"]:
        L.append("  未执行：仍有 %d 个条款应检查（%s），配置修复并重跑前不得当成通过"
                 % (result["counts"]["clauses_required"],
                    ",".join(result.get("clauses_pending") or []) or "-"))
    if result["config_rejections"]:
        L.append("  配置拒绝 %d 项：%s"
                 % (len(result["config_rejections"]),
                    ", ".join("%s/%s" % (r["code"], r["target"])
                              for r in result["config_rejections"][:10])))
    if result["preflight_problems"]:
        L.append("  前置校验问题 %d 项：%s"
                 % (len(result["preflight_problems"]),
                    result["preflight_problems"][0][:160]))
    if result["exec_error"]:
        L.append("  执行期异常：%s" % result["exec_error"])
    L.append("")
    L.append("  %-6s %-16s %-14s %-14s %s" % ("条款", "覆盖状态", "结论", "执行状态", "原因码"))
    for c in result["clause_coverage"]:
        L.append("  %-6s %-16s %-14s %-14s %s"
                 % (c.get("requirement_id"), c.get("coverage_state"), c.get("verdict"),
                    c.get("execution_status"), c.get("reason_code")))
    if result["findings"]:
        L.append("")
        L.append("  缺陷清单（前 20 条）：")
        for f in result["findings"][:20]:
            loc = f.get("record_locator") or {}
            L.append("    %-5s %-6s %-22s %-22s %s"
                     % (f.get("finding_id"), f.get("rule_id"),
                        loc.get("record_id") or ("dataset:" + str(loc.get("file"))),
                        f.get("reason_code"), f.get("observed_value")))
    return "\n".join(L)
