"""报告渲染：把 run 产出的 report.json 渲染成 HTML（零第三方依赖）。

只做**呈现**，不做二次判定：所有结论都来自内核的 report.json，
HTML 里不新增任何"看起来更友好"的推断（例如把 INDETERMINATE 说成"基本通过"）。
文本一律 HTML 转义（Stage 0 遗留项 S0-09 在此闭合）。
"""
from __future__ import annotations

import html
import json
from pathlib import Path

VERDICT_COLOR = {
    "PASS": ("#0a7d3c", "#e8f5ec"),
    "FAIL": ("#c62828", "#fdecec"),
    "INDETERMINATE": ("#8a6d00", "#fff8e1"),
}


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _badge(verdict) -> str:
    fg, bg = VERDICT_COLOR.get(str(verdict), ("#333333", "#f0f0f0"))
    return '<span class="badge" style="color:%s;background:%s">%s</span>' % (
        fg, bg, _esc(verdict))


def render_html(report: dict) -> str:
    # report.json 的字段名是 aggregate_verdict / aggregate_reason（内核 write_outputs 产出）
    verdict = report.get("aggregate_verdict") or report.get("aggregate")
    reason = report.get("aggregate_reason") or ""
    cov = report.get("clause_coverage") or []
    results = report.get("check_results") or report.get("results") or []
    findings = report.get("findings") or []

    rows_clause = "\n".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
        % (_esc(c.get("requirement_id")), _esc(c.get("coverage_state")),
           _badge(c.get("verdict")), _esc(c.get("execution_status")),
           _esc(c.get("reason_code")),
           _esc(",".join(c.get("failure_reason_codes") or c.get("advisory_reason_codes") or [])))
        for c in cov)
    rows_rule = "\n".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
        % (_esc(r.get("rule_id")), _esc(",".join(r.get("requirement_ids") or [])),
           _esc((r['scope']['field']+'='+r['scope']['equals']) if r.get('scope') else '全批次'),
           _badge(r.get("verdict")), _esc(r.get("execution_status")),
           _esc(r.get("reason_code")),
           _esc((r.get("summary_counts") or {}).get("records_failed")))
        for r in results)
    rows_finding = "\n".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
        % (_esc(f.get("finding_id")), _esc(f.get("rule_id")),
           _esc((f.get("record_locator") or {}).get("record_id")),
           _esc(f.get("field")), _esc(f.get("reason_code")),
           _esc(f.get("observed_value")))
        for f in findings[:500])
    more = "" if len(findings) <= 500 else "<p>仅展示前 500 条，完整数据见 report.json。</p>"

    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>GeoAcceptance 验收报告 %(bundle)s</title>
<style>
 body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:24px;color:#222}
 h1{font-size:20px} h2{font-size:16px;margin-top:24px}
 table{border-collapse:collapse;width:100%%;font-size:13px}
 th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}
 th{background:#f5f5f5}
 .badge{padding:1px 6px;border-radius:3px;font-weight:600;font-size:12px}
 .meta{color:#555;font-size:13px}
</style></head><body>
<h1>GeoAcceptance 验收报告：%(bundle)s</h1>
<p class="meta">总体结论：%(badge)s　%(reason)s</p>
<p class="meta">schema_version=%(sv)s　tool=%(tool)s　生成时间=%(ts)s</p>
<h2>条款覆盖（clause_coverage，权威口径）</h2>
<table><tr><th>条款</th><th>覆盖状态</th><th>结论</th><th>执行状态</th><th>原因码</th><th>原因码数组</th></tr>
%(rows_clause)s</table>
<h2>规则结果（check_results）</h2>
<table><tr><th>规则</th><th>条款</th><th>适用范围</th><th>结论</th><th>执行状态</th><th>原因码</th><th>失败记录数</th></tr>
%(rows_rule)s</table>
<h2>缺陷清单（findings）</h2>
<table><tr><th>ID</th><th>规则</th><th>记录标识</th><th>字段</th><th>原因码</th><th>观测值</th></tr>
%(rows_finding)s</table>
%(more)s
<p class="meta">本报告只呈现内核结论，不做二次判定；INDETERMINATE 表示"证据不足，未放行"。</p>
</body></html>
""" % {"bundle": _esc(report.get("bundle") or ""), "badge": _badge(verdict),
       "reason": _esc(reason), "sv": _esc(report.get("schema_version")),
       "tool": _esc(report.get("tool_version") or report.get("tool")),
       "ts": _esc(report.get("generated_at") or report.get("timestamp")),
       "rows_clause": rows_clause, "rows_rule": rows_rule,
       "rows_finding": rows_finding, "more": more}


def write_html(report_json: Path, out_path: Path) -> Path:
    report = json.loads(Path(report_json).read_text(encoding="utf-8"))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(report), encoding="utf-8")
    return out_path
