"""整改复验 compare：**关闭一个整改项必须有正面证据**（Stage 1 第二轮重写）。

对应外部复核（Codex）S1-EXT-01 ~ S1-EXT-04。四条硬约束，缺一即不得宣称"已整改"：

1. **关闭需要正面证据**（EXT-01）
   `closed` 的判据不是"整改后没有 FAIL finding"，而是**同一把尺子在整改后完整执行并通过**：
   规则仍存在、仍 APPROVED、未被配置校验拒绝、有结果、`execution_status == COMPLETED`、
   规则结论 PASS、所映射条款覆盖状态 `COVERED` 且结论 PASS。
   任一条不满足 ⇒ `unresolved_unknown`（未知不得当成已关闭 / 也不得当成"没有失败"）。
2. **实体身份来自全量输入记录**（EXT-02 / EXT-03）
   身份索引用 `poi.csv` 的**全部行**建立（唯一 / 重复 / 无标识），不是只统计出现过失败的 finding ——
   同一实体多条 finding 不构成"实体重复"。
   **删除实体一律待审核（S1-R2-02）**：`removed_pending_review` 条目在**全量 before/after
   实体清单差集**上统一生成（每实体一条，多条规则的失败码合并，避免重复计数）——
   "原本干净的实体被删掉"与"带缺陷的实体被删掉"同样阻断，不得以"原本没问题"自动授权放行。
   当前**没有批准删除通道**：缺失交付实体 ⇒ `LEDGER_INDETERMINATE`。
   新增实体单独披露（`entities_added_after`），不参与关闭判定。
3. **数据集级问题不会因无 record_id 而消失**（EXT-01）
   数据集级 finding 用「规则身份 + 证据域（file）」作为身份，例如 `dataset:crs.json|R07`。
4. **尺子必须同一把**（EXT-04）
   不只比较人工递增的 `version`：比较**规则语义指纹**（rule_type / 参数 / 参数来源 /
   依赖 / 条款映射 / 批准状态）与**批次制品指纹**（数据字典 / 项目范围 / 规范原文 / 基准时间）。
   指纹不同 ⇒ `not_comparable`；规则被撤走 ⇒ `not_comparable`；新增规则单独披露。

总体口径（**不再叫"整改完成"**）：
- `ledger`        ：整改前失败台账的处理情况 —— `CLOSED` / `OPEN` / `INDETERMINATE`
- `after_acceptance`：整改后批次**自身**的验收结论（PASS / FAIL / INDETERMINATE）
- `overall`       ：两者组合 ——
  `LEDGER_CLOSED_ACCEPTED`（台账关闭且整改后批次自身通过）/
  `LEDGER_CLOSED_NOT_ACCEPTED`（台账关闭但整改后批次自身未通过）/
  `LEDGER_OPEN` / `LEDGER_INDETERMINATE`

只有 `LEDGER_CLOSED_ACCEPTED` 才是"全部验收通过"；`LEDGER_CLOSED_NOT_ACCEPTED`
只表示"所选失败台账已处理"，**不等于**这批交付可以放行。
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
import stage0_gate as gate  # noqa: E402
from geoacceptance import inputs  # noqa: E402

SCHEMA_VERSION = "stage1-compare-3"

# 参与规则语义指纹的字段：**排除** bundle / notes（不影响判定）
RULE_FINGERPRINT_FIELDS = ("rule_id", "rule_type", "status", "version", "required_for_release",
                           "requirement_ids", "parameters", "parameter_sources",
                           "preconditions", "reviewer", "approved_at")
# 参与批次制品指纹的项：这些变了，同一条规则量出来的结果也不是一回事。
# crs.json 与 poi.csv 是**被测数据**（CRS 声明本身就是检查对象），不进尺子指纹。
ARTIFACT_FILES = ("dictionary.csv", "area.geojson", "delivery_spec.md")
BUNDLE_TEXT_FILES = ("delivery_spec.md", "dictionary.csv", "poi.csv", "area.geojson",
                     "crs.json", "requirements.yaml", "approved-rules.yaml")

# 台账状态
CLOSED = "closed"                            # 有正面证据：同一检查整改后完整执行并通过
STILL_OPEN = "still_open"                    # 两侧都有 FAIL
NEW_ISSUE = "new_issue"                      # 整改后新出现 FAIL
UNRESOLVED_UNKNOWN = "unresolved_unknown"    # 无 FAIL 但也没有"已通过"的证据；或整改后仍未知
REMOVED_PENDING_REVIEW = "removed_pending_review"  # 整改后实体消失（未获批准删除）
NOT_COMPARABLE = "not_comparable"            # 身份或尺子不可比

BLOCKING_OPEN = (STILL_OPEN, NEW_ISSUE)
BLOCKING_UNKNOWN = (UNRESOLVED_UNKNOWN, REMOVED_PENDING_REVIEW, NOT_COMPARABLE)


# ---------------------------------------------------------------- 输入防护
def guard_bundle(bundle: Path, max_bytes: int = inputs.DEFAULT_MAX_BYTES):
    """与 CLI 一致的输入防护：存在性 + 单文件上限 + UTF-8（超限/非 UTF-8 一律报错）。

    两批都过这道闸，避免"读了一半的批次"被当成完整证据参与整改判定。
    """
    bundle = Path(bundle)
    if not bundle.is_dir():
        raise inputs.InputGuardError("批次目录不存在：%s" % bundle)
    for name in BUNDLE_TEXT_FILES:
        p = bundle / name
        if not p.exists():
            raise inputs.InputGuardError("批次缺少输入文件 %s：%s" % (name, bundle))
        inputs.read_text_capped(p, max_bytes)


# ---------------------------------------------------------------- 身份（EXT-02 / EXT-03）
def _entity_index(kernel):
    """从**全量输入记录**建立身份索引（不是只统计出现过失败的 finding）。"""
    counts = Counter()
    unidentified = 0
    for _lineno, row in kernel.rows:
        rid = (row[0].strip() if row else "")
        if not rid:
            unidentified += 1
        else:
            counts[rid] += 1
    return {
        "records": len(kernel.rows),
        "distinct": len(counts),
        "counts": counts,
        "unidentified": unidentified,
        "duplicated": sorted(k for k, v in counts.items() if v > 1),
        "unique": {k for k, v in counts.items() if v == 1},
    }


# ---------------------------------------------------------------- 尺子（EXT-04）
def _sha256_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rule_fingerprint(rule) -> str:
    import json
    payload = {k: rule.get(k) for k in RULE_FINGERPRINT_FIELDS}
    return _sha256_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str))


def _rule_fingerprint_diff(rule_b, rule_a):
    """返回逐字段差异（给人看），不只看 hash 是否不同；长值截断，避免刷屏。"""
    def short(v):
        s = repr(v)
        return s if len(s) <= 120 else s[:117] + "..."
    diff = []
    for k in RULE_FINGERPRINT_FIELDS:
        if k == "rule_id":
            continue
        vb, va = rule_b.get(k), rule_a.get(k)
        if vb != va:
            diff.append("%s: %s → %s" % (k, short(vb), short(va)))
    return diff


def _artifact_fingerprints(kernel):
    import json
    out = {}
    for name in ARTIFACT_FILES:
        p = kernel.dir / name
        out[name] = gate.sha256_file(p) if p.exists() else None
    reqs = []
    for r in kernel.req_doc.get("requirements") or []:
        reqs.append({k: r.get(k) for k in ("requirement_id", "required_for_release",
                                           "support_status", "source_line_start",
                                           "source_line_end", "source_quote",
                                           "document_id", "document_sha256")
                     if k in r})
    out["requirements"] = _sha256_text(json.dumps(reqs, sort_keys=True, ensure_ascii=False,
                                                  default=str))
    out["reference_time"] = str(kernel.ref_time)
    return out


# ---------------------------------------------------------------- 台账归组
def _key_of(finding, index):
    """跨批次稳定的台账键。

    - 记录级：`record:<rid>`（rid 非空；**是否唯一**在身份判定阶段按批次索引确认，
      重复 ⇒ 该条目 `not_comparable`，但仍然保留 rid 便于人工定位）
    - 无标识记录：`unidentified:<rule_id>`（首列为空，无法跨批次对应）
    - 数据集级：`dataset:<file>`（规则身份 + 证据域，不因无 record_id 消失）
    """
    loc = finding.get("record_locator") or {}
    rid = (loc.get("record_id") or "").strip()
    rule_id = str(finding.get("rule_id"))
    if "line" in loc:  # 记录级
        if rid:
            return ("record", rid, rule_id)
        return ("unidentified", "", rule_id)
    return ("dataset", str(loc.get("file") or "-"), rule_id)


def _ledger(findings, index):
    """{key: {"kind","ident","rule_id","fail":set,"cand":set,"indet":set}}"""
    out = {}
    for f in findings or []:
        code = f.get("reason_code")
        cls = gate.classify_reason_code(code)
        key = _key_of(f, index)
        slot = out.setdefault(key, {"kind": key[0], "ident": key[1], "rule_id": key[2],
                                    "fail": set(), "cand": set(), "indet": set()})
        if cls == "FAIL":
            slot["fail"].add(code)
        elif cls == "CANDIDATE":
            slot["cand"].add(code)
        elif cls == "INDETERMINATE":
            slot["indet"].add(code)
    return out


# ---------------------------------------------------------------- 关闭证据（EXT-01）
def _closure_evidence(ctx, rule_id):
    """整改后"同一检查已完整执行并通过"的正面证据；返回 (ok, reasons, evidence)。"""
    reasons = []
    ev = {}
    rules = ctx["rules_by_id"]
    if rule_id not in rules:
        return False, ["整改后批次不存在该规则：尺子被撤走，无法证明同一检查已通过"], ev
    rule = rules[rule_id]
    ev["rule_status"] = rule.get("status")
    ev["rule_version"] = rule.get("version")
    if rule.get("status") != "APPROVED":
        reasons.append("整改后该规则状态为 %r（非 APPROVED）：不具备判定资格"
                       % rule.get("status"))
    if rule_id in ctx["rejected_rule_ids"]:
        codes = sorted({str(r.get("code")) for r in ctx["rejections"]
                        if str(r.get("rule_id") or r.get("target")) == rule_id})
        reasons.append("整改后该规则被配置校验拒绝（%s）：检查未获准执行"
                       % (",".join(codes) or "REJECTED"))
    res = ctx["results_by_rule"].get(rule_id)
    if res is None:
        reasons.append("整改后该规则没有结果（缺结果）：不得以'无失败'推定已修复")
    else:
        ev["rule_verdict"] = res.get("verdict")
        ev["rule_execution_status"] = res.get("execution_status")
        if res.get("execution_status") != "COMPLETED":
            reasons.append("整改后该规则未完整执行：execution_status=%r"
                           % res.get("execution_status"))
        if res.get("verdict") == "FAIL":
            reasons.append("整改后该规则结论仍为 FAIL")
        elif res.get("verdict") != "PASS":
            reasons.append("整改后该规则结论为 %r（非 PASS）：证据不足，不得关闭"
                           % res.get("verdict"))
    clauses = {}
    for cid in (rule.get("requirement_ids") or []):
        cid = str(cid)
        c = ctx["coverage_by_clause"].get(cid)
        if c is None:
            reasons.append("整改后条款 %s 不在必检覆盖内：无法证明该检查已覆盖" % cid)
            continue
        clauses[cid] = {"coverage_state": c.get("coverage_state"),
                        "verdict": c.get("verdict"),
                        "execution_status": c.get("execution_status")}
        if c.get("coverage_state") != "COVERED":
            reasons.append("整改后条款 %s 覆盖状态为 %r（未完整覆盖）"
                           % (cid, c.get("coverage_state")))
        if c.get("verdict") != "PASS":
            reasons.append("整改后条款 %s 结论为 %r" % (cid, c.get("verdict")))
    if clauses:
        ev["clauses"] = clauses
    return (not reasons), reasons, ev


# ---------------------------------------------------------------- 主流程
def _run_batch(bundle: Path, max_bytes: int):
    guard_bundle(bundle, max_bytes)
    k = gate.Kernel(bundle)
    rejections = k.collect_config_rejections()
    problems = k.verify_quotes() + k.verify_parameter_sources()
    # 与门禁 main() 同一条纪律：配置校验/前置校验未过 ⇒ **拒绝执行**，
    # 不得拿"跑出来的结果"去凑整改证据（EXT-01：缺证据一律不关闭）。
    if rejections or problems:
        results, findings, coverage = [], [], []
        agg, reason = "INDETERMINATE", "配置/前置校验未通过，拒绝执行（%d 项拒绝 / %d 项问题）" % (
            len(rejections), len(problems))
        exec_error = None
    else:
        try:
            results, findings = k.run()
            coverage = k.build_clause_coverage(results)
            agg, reason = gate.aggregate(coverage, rejections, len(k.rows))
            exec_error = None
        except Exception as exc:  # noqa: BLE001 —— 执行期异常不得变成"看起来正常"的批次
            results, findings, coverage = [], [], []
            agg, reason = "INDETERMINATE", "执行期异常，拒绝判定：%s: %s" % (type(exc).__name__, exc)
            exec_error = "%s: %s" % (type(exc).__name__, exc)
    ctx = {
        "kernel": k,
        "dir": bundle,
        "results": results,
        "findings": findings,
        "coverage": coverage,
        "aggregate": agg,
        "aggregate_reason": reason,
        "rejections": rejections,
        "problems": problems,
        "results_by_rule": {str(r.get("rule_id")): r for r in results},
        "coverage_by_clause": {str(c.get("requirement_id")): c for c in coverage},
        "rules_by_id": {str(r.get("rule_id")): r for r in k.rule_doc["rules"]},
        "rule_fp": {str(r.get("rule_id")): _rule_fingerprint(r) for r in k.rule_doc["rules"]},
        "artifacts": _artifact_fingerprints(k),
        "rejected_rule_ids": set(k.rejected_rule_ids()),
        "index": _entity_index(k),
        "exec_error": exec_error,
    }
    by_class = Counter()
    for f in findings:
        by_class[gate.classify_reason_code(f.get("reason_code"))] += 1
    ctx["findings_by_class"] = dict(by_class)
    return ctx


def _batch_summary(ctx):
    return {
        "bundle": str(ctx["dir"]),
        "aggregate": ctx["aggregate"],
        "aggregate_reason": ctx["aggregate_reason"],
        "findings": len(ctx["findings"]),
        "findings_by_class": ctx["findings_by_class"],
        "records": ctx["index"]["records"],
        "config_rejections": [{"code": r.get("code"), "target": r.get("target"),
                               "detail": str(r.get("detail"))[:200]}
                              for r in ctx["rejections"]],
        "preflight_problems": [str(p)[:200] for p in ctx["problems"]],
        "exec_error": ctx["exec_error"],
    }


def compare_batches(before_dir: Path, after_dir: Path,
                    max_bytes: int = inputs.DEFAULT_MAX_BYTES):
    """跑两个批次并逐条比较，返回结果字典（可直接 JSON 序列化）。"""
    b = _run_batch(Path(before_dir), max_bytes)
    a = _run_batch(Path(after_dir), max_bytes)

    # ---- 尺子可比性（EXT-04）
    rules_removed = sorted(set(b["rules_by_id"]) - set(a["rules_by_id"]))
    rules_added = sorted(set(a["rules_by_id"]) - set(b["rules_by_id"]))
    fp_changed = {}
    for rid in sorted(set(b["rules_by_id"]) & set(a["rules_by_id"])):
        if b["rule_fp"][rid] != a["rule_fp"][rid]:
            fp_changed[rid] = _rule_fingerprint_diff(b["rules_by_id"][rid],
                                                     a["rules_by_id"][rid])
    artifacts_changed = sorted(k for k in set(b["artifacts"]) | set(a["artifacts"])
                               if b["artifacts"].get(k) != a["artifacts"].get(k))
    version_changed = sorted(rid for rid in set(b["rules_by_id"]) & set(a["rules_by_id"])
                             if b["rules_by_id"][rid].get("version")
                             != a["rules_by_id"][rid].get("version"))

    # ---- 台账归组
    lb = _ledger(b["findings"], b["index"])
    la = _ledger(a["findings"], a["index"])

    before_ids = set(b["index"]["counts"])
    after_ids = set(a["index"]["counts"])
    entities_removed = sorted(before_ids - after_ids)
    entities_added = sorted(after_ids - before_ids)

    items = []
    # S1-R2-02：被删实体的失败码先按实体合并（多条规则 → 一条待审核条目，不重复计实体）
    removed_set = set(entities_removed)
    removed_before_codes = defaultdict(set)
    for key, eb in lb.items():
        if key[0] == "record" and key[1] in removed_set:
            removed_before_codes[key[1]] |= eb["fail"] | eb["indet"]
    for key in sorted(set(lb) | set(la)):
        kind, ident, rule_id = key
        if kind == "record" and ident in removed_set:
            # 实体已消失：统一在全量差集上生成单条 removed_pending_review（见循环后的块），
            # 不再按规则逐条生成，避免同一实体被多条规则重复计入。
            continue
        eb = lb.get(key, {"fail": set(), "cand": set(), "indet": set()})
        ea = la.get(key, {"fail": set(), "cand": set(), "indet": set()})
        before_fail, after_fail = eb["fail"], ea["fail"]
        after_indet = ea["indet"]
        if not (before_fail or after_fail or after_indet):
            continue  # 两侧都没有失败/未知：不进台账（候选另行披露）
        reasons = []
        status = None
        # ① 身份可用性（按记录判定，不用行号兜底）
        if kind == "unidentified":
            reasons.append("记录缺少稳定标识（首列为空或该批次内重复），拒绝按行号匹配")
        elif kind == "record":
            if ident in b["index"]["duplicated"] or ident in a["index"]["duplicated"]:
                reasons.append("记录标识 %s 在批次内重复，身份不可用（拒绝按行号匹配）" % ident)
        # ② 尺子可比性（先判"资格"，再判"尺子内容"：资格不具备不是"尺子不同"，
        #    而是"整改后根本没有这把尺子的合格执行"，两者都不能关闭但原因必须分清）
        qual_reason = None
        if rule_id in rules_removed:
            reasons.append("整改后批次不存在该规则：尺子被撤走，无法证明同一检查已通过")
        else:
            st = a["rules_by_id"].get(rule_id, {}).get("status")
            if st != "APPROVED":
                qual_reason = ("整改后该规则状态为 %r（非 APPROVED）：检查资格不具备，"
                               "不得按'无失败'推定已修复" % st)
            if rule_id in fp_changed:
                reasons.append("规则语义指纹不同（%s）：不是同一把尺子"
                               % "; ".join(fp_changed[rule_id]))
            elif artifacts_changed:
                reasons.append("批次制品指纹不同（%s）：判定所依赖的字典/范围/规范/基准时间变了"
                               % ",".join(artifacts_changed))
            elif rule_id in rules_added:
                reasons.append("该规则只存在于整改后批次，无基线可比")

        if qual_reason:
            reasons.insert(0, qual_reason)
            status = status or UNRESOLVED_UNKNOWN
        elif reasons:
            status = status or NOT_COMPARABLE
        elif after_fail and before_fail:
            status = STILL_OPEN
        elif after_fail and not before_fail:
            status = NEW_ISSUE
            if rule_id in rules_added:
                reasons.append("整改后新增规则发现的问题（无基线，需人工确认）")
        elif after_indet:
            status = UNRESOLVED_UNKNOWN
            reasons.append("整改后仍为缺证据/未知（%s）：不得按'无失败'推定已修复"
                           % ",".join(sorted(after_indet)))
        elif before_fail:
            ok, rs, ev = _closure_evidence(a, rule_id)
            if ok:
                status = CLOSED
            else:
                status = UNRESOLVED_UNKNOWN
                reasons.extend(rs)
        else:  # pragma: no cover —— 上面 continue 已排除
            continue

        items.append({
            "key": "%s:%s|%s" % (kind, ident or "-", rule_id),
            "identity_kind": kind,
            "record_id": ident if kind == "record" else None,
            "evidence_domain": ident if kind == "dataset" else None,
            "rule_id": rule_id,
            "status": status,
            "before_codes": sorted(before_fail),
            "after_codes": sorted(after_fail),
            "after_unknown_codes": sorted(after_indet),
            "reduced": bool(before_fail and after_fail and after_fail < before_fail),
            "closure_evidence": (a["results_by_rule"].get(rule_id) and {
                "rule_status": a["rules_by_id"].get(rule_id, {}).get("status"),
                "rule_verdict": a["results_by_rule"][rule_id].get("verdict"),
                "rule_execution_status": a["results_by_rule"][rule_id].get("execution_status"),
            }) or None,
            "reasons": reasons,
        })

    # ---- S1-R2-02：在全量实体清单差集上统一生成 removed_pending_review
    # 无论该实体在整改前是否有失败 finding（"原本干净"还是"原本有缺陷"），
    # 缺失交付实体都显式待审核；当前没有批准删除通道 ⇒ 计入 BLOCKING_UNKNOWN，阻断整体放行。
    for rid in entities_removed:
        codes = sorted(removed_before_codes.get(rid, ()))
        reasons = ["整改后批次缺失实体（%s）：当前没有批准删除通道，一律待审核——"
                   "无论该实体整改前是否有失败项，都不得据此自动放行" % rid]
        if codes:
            reasons.append("该实体在整改前的失败/未知项（%s）也未随之解决" % ",".join(codes))
        items.append({
            "key": "record:%s|-" % rid,
            "identity_kind": "record",
            "record_id": rid,
            "evidence_domain": None,
            "rule_id": "-",
            "status": REMOVED_PENDING_REVIEW,
            "before_codes": codes,
            "after_codes": [],
            "after_unknown_codes": [],
            "reduced": False,
            "closure_evidence": None,
            "reasons": reasons,
        })

    def _unknown(ctx):
        """该批次里"缺证据 / 不适用 / 不完整"的条款：必须可见，不得因为台账里没它就被当成通过。"""
        return [{"requirement_id": c.get("requirement_id"),
                 "coverage_state": c.get("coverage_state"),
                 "verdict": c.get("verdict"),
                 "execution_status": c.get("execution_status"),
                 "reason_code": c.get("reason_code")}
                for c in ctx["coverage"] if c.get("verdict") != "PASS"]

    # `ledger` 只描述**台账条目**；整改后批次自身是否通过由 `after_acceptance` / `overall` 承载
    # （LEDGER_CLOSED_NOT_ACCEPTED 表示"台账条目已处理但这批仍不得放行"）。
    unknown_after = _unknown(a)
    counts = Counter(i["status"] for i in items)
    if any(i["status"] in BLOCKING_UNKNOWN for i in items):
        ledger = "INDETERMINATE"
    elif any(i["status"] in BLOCKING_OPEN for i in items):
        ledger = "OPEN"
    else:
        ledger = "CLOSED"
    if ledger == "CLOSED" and a["aggregate"] == "PASS":
        overall = "LEDGER_CLOSED_ACCEPTED"
    elif ledger == "CLOSED":
        overall = "LEDGER_CLOSED_NOT_ACCEPTED"
    elif ledger == "OPEN":
        overall = "LEDGER_OPEN"
    else:
        overall = "LEDGER_INDETERMINATE"

    advisory = [{"key": "%s:%s|%s" % (k[0], k[1] or "-", k[2]),
                 "rule_id": k[2], "codes": sorted(v["cand"])}
                for k, v in sorted(la.items()) if v["cand"]]

    notes = []
    if entities_removed:
        notes.append("整改后缺失 %d 个实体：当前无批准删除通道，一律 removed_pending_review 阻断"
                     "（S1-R2-02）；若要允许某类删除，必须先显式定义政策与可追溯的批准记录"
                     % len(entities_removed))
    if not items:
        notes.append("台账为空：整改前无 FAIL 项，整改后也无失败/未知项；"
                     "这不等于'全部检查都跑过'，仅表示所选失败台账无可比条目")
    if b["problems"] or a["problems"]:
        notes.append("存在前置校验问题（引用/参数来源），详见各批次 preflight_problems")
    if unknown_after:
        notes.append("整改后批次有 %d 个条款未取得 PASS（缺证据/不适用/不完整）："
                     "台账条目即使全部关闭，这批交付也不得放行（见 after_acceptance 与 overall），"
                     "详见 scope.unknown_after" % len(unknown_after))

    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": gate.TOOL_VERSION,
        "python": sys.version.split()[0],
        "before": _batch_summary(b),
        "after": _batch_summary(a),
        "identity": {
            "strategy": "record_id（poi.csv 首列）在两批均存在且唯一；不使用行号",
            "index_source": "全量输入记录（不是只统计出现过失败的 finding）",
            "dataset_identity": "数据集级问题用「规则身份 + 证据域 file」追踪，不因无 record_id 消失",
            "before": {"records": b["index"]["records"], "distinct": b["index"]["distinct"],
                       "unidentified": b["index"]["unidentified"],
                       "duplicated": b["index"]["duplicated"]},
            "after": {"records": a["index"]["records"], "distinct": a["index"]["distinct"],
                      "unidentified": a["index"]["unidentified"],
                      "duplicated": a["index"]["duplicated"]},
            "ok": not (b["index"]["duplicated"] or a["index"]["duplicated"]
                       or b["index"]["unidentified"] or a["index"]["unidentified"]),
        },
        "ruler": {
            "rule_fingerprint_fields": list(RULE_FINGERPRINT_FIELDS),
            "artifact_fingerprint_fields": list(ARTIFACT_FILES) + ["requirements",
                                                                   "reference_time"],
            "rules_removed_after": rules_removed,
            "rules_added_after": rules_added,
            "rule_fingerprint_changed": fp_changed,
            "artifacts_changed": artifacts_changed,
            "rule_versions_changed": version_changed,
            "same_ruler": not (rules_removed or fp_changed or artifacts_changed),
        },
        "scope": {
            "entities_removed_after": entities_removed,
            "entities_added_after": entities_added,
            "advisory_after": advisory,
            "unknown_before": _unknown(b),
            "unknown_after": unknown_after,
            "ledger_size": len(items),
            "closure_rule": ("closed 需要整改后同一规则仍 APPROVED、未被配置拒绝、有结果、"
                             "execution_status=COMPLETED、规则与所映射条款结论均为 PASS；"
                             "实体缺失一律 removed_pending_review（全量实体清单差集，无批准删除通道）"),
        },
        "counts": dict(counts),
        "ledger": ledger,
        "after_acceptance": a["aggregate"],
        "overall": overall,
        "notes": notes,
        "items": items,
    }


def render_text(result) -> str:
    """人类可读输出（与 JSON 同源，不另算一遍）。"""
    L = []
    L.append("整改复验 compare：%s → %s" % (result["before"]["bundle"], result["after"]["bundle"]))
    L.append("  整改前：%s（findings=%d %s）　整改后：%s（findings=%d %s）"
             % (result["before"]["aggregate"], result["before"]["findings"],
                result["before"]["findings_by_class"],
                result["after"]["aggregate"], result["after"]["findings"],
                result["after"]["findings_by_class"]))
    L.append("  身份：整改前 %d 条/%d 个标识（重复=%s 无标识=%d）；整改后 %d 条/%d 个（重复=%s 无标识=%d）"
             % (result["identity"]["before"]["records"], result["identity"]["before"]["distinct"],
                result["identity"]["before"]["duplicated"] or "无",
                result["identity"]["before"]["unidentified"],
                result["identity"]["after"]["records"], result["identity"]["after"]["distinct"],
                result["identity"]["after"]["duplicated"] or "无",
                result["identity"]["after"]["unidentified"]))
    r = result["ruler"]
    if r["same_ruler"]:
        L.append("  尺子：一致（规则语义指纹 + 批次制品指纹）")
    else:
        if r["rules_removed_after"]:
            L.append("  尺子：整改后缺失规则 %s" % ",".join(r["rules_removed_after"]))
        if r["rules_added_after"]:
            L.append("  尺子：整改后新增规则 %s" % ",".join(r["rules_added_after"]))
        for rid, d in r.get("rule_fingerprint_changed", {}).items():
            L.append("  尺子：%s 语义指纹变化 → %s" % (rid, "; ".join(d)))
        if r["artifacts_changed"]:
            L.append("  尺子：批次制品变化 %s" % ",".join(r["artifacts_changed"]))
    sc = result["scope"]
    if sc["entities_removed_after"]:
        L.append("  实体：整改后缺失 %s（%d 个）"
                 % (",".join(sc["entities_removed_after"]), len(sc["entities_removed_after"])))
    if sc["entities_added_after"]:
        L.append("  实体：整改后新增 %s（%d 个）"
                 % (",".join(sc["entities_added_after"]), len(sc["entities_added_after"])))
    if sc["advisory_after"]:
        L.append("  候选（不参与关闭，仅供参考）：%s"
                 % "; ".join("%s=%s" % (x["key"], ",".join(x["codes"]))
                             for x in sc["advisory_after"]))
    if sc["unknown_after"]:
        L.append("  整改后未取得 PASS 的条款（缺证据/不适用/不完整，不等于通过）：%s"
                 % "; ".join("%s=%s/%s" % (x["requirement_id"], x["coverage_state"],
                                           x["verdict"]) for x in sc["unknown_after"]))
    L.append("  台账：%s　条目 %d　汇总 %s"
             % (result["ledger"], sc["ledger_size"],
                ", ".join("%s=%d" % kv for kv in sorted(result["counts"].items())) or "无条目"))
    L.append("  整改后批次自身验收结论：%s" % result["after_acceptance"])
    L.append("  结论：%s" % result["overall"])
    for n in result["notes"]:
        L.append("  注：%s" % n)
    L.append("")
    L.append("  %-24s %-8s %-22s %s" % ("台账键", "规则", "status", "before → after"))
    for i in result["items"]:
        L.append("  %-24s %-8s %-22s %s%s"
                 % (i["key"], i["rule_id"], i["status"],
                    "%s → %s%s" % (",".join(i["before_codes"]) or "-",
                                   ",".join(i["after_codes"]) or "-",
                                   ("（未知：" + ",".join(i["after_unknown_codes"]) + "）")
                                   if i["after_unknown_codes"] else ""),
                    ("  ← " + ";".join(i["reasons"])) if i["reasons"] else ""))
    return "\n".join(L)
