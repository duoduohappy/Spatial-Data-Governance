"""compare / 入口校验反例回归（Stage 1 第二、三轮）。

**不复用**仓库自带探针的判定口径，全部用例现场造包：
- 五个外部反例（第一轮 EXT）：数据集失败未修、缺证据、规则未批准、删除实体、唯一实体多 finding；
- 七组"尺子变化"（EXT-04）：同版本改参数（结构性 trim / 判定阈值）、改数据字典、改项目范围、
  改基准时间、规则删除、依赖失效、批准来源变化；
- 实体清单差异五组（第二轮 S1-R2-02）：干净实体删除、故障实体删除、仅新增、无变化、行序打乱；
- 逐规则入口参数反例（第二轮 S1-R2-01）：十类规则各一个非法参数用例 + 未知 rule_type +
  缺 parameters + 有效输入正向对照，经**正式 validate 入口**断言受控拒绝且保留应检查条款数；
- 披露类：新增实体、新增规则必须可见；
- 正例对照：clean→clean、defective→corrected（保持既有结论不变）。

每条用例的预期是"不得判为已关闭"或"必须披露/拒绝"，**不迁就当前输出**。
结果落 `work/stage1-compare/compare-probe-results.json`，并用
`schemas/stage1_compare.schema.json` / `stage1_validate.schema.json` 校验每一份输出。

用法：
    python tools/compare_probes.py                 # 默认跑全部
    python tools/compare_probes.py --keep          # 保留造出来的样例包
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import sys
from pathlib import Path

# 终端编码：中文输出在 GBK 终端/重定向下会抛 UnicodeEncodeError（证据链断在中途）。
for _s in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
    if _s is not None and hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="strict")
import argparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import yaml  # noqa: E402
from geoacceptance import compare as cmp  # noqa: E402
from geoacceptance import validate as vld  # noqa: E402

EX = ROOT / "examples"
OUT = ROOT / "work" / "stage1-compare"
CASES = OUT / "cases"

CLOSED = "closed"


# ---------------------------------------------------------------- 造包工具
def _mk(name, src="clean"):
    p = CASES / name
    if p.exists():
        shutil.rmtree(p)
    shutil.copytree(EX / src, p)
    return p


def _rows(p: Path):
    with io.open(p, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def _write_rows(p: Path, rows):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)


def _yload(p: Path):
    return yaml.safe_load(io.open(p, encoding="utf-8").read())


def _ydump(p: Path, obj):
    io.open(p, "w", encoding="utf-8").write(
        yaml.safe_dump(obj, allow_unicode=True, sort_keys=False))


def _stale(p: Path, row=1, when="2026-08-01T00:00:00Z"):
    rows = _rows(p / "poi.csv")
    rows[row][-1] = when
    _write_rows(p / "poi.csv", rows)


def _blank_name(p: Path, row=1):
    rows = _rows(p / "poi.csv")
    rows[row][1] = "   "
    _write_rows(p / "poi.csv", rows)


def _bad_category(p: Path, row=1):
    rows = _rows(p / "poi.csv")
    rows[row][2] = "invalid_category"
    _write_rows(p / "poi.csv", rows)


def _outside(p: Path, row=1, lon="116.3300", lat="39.9100"):
    rows = _rows(p / "poi.csv")
    rows[row][3], rows[row][4] = lon, lat
    _write_rows(p / "poi.csv", rows)


def _repair(p: Path, row=1):
    """还原为 clean 的第一条数据（category/name/coords/source_time）。"""
    src = _rows(EX / "clean" / "poi.csv")
    rows = _rows(p / "poi.csv")
    good = src[1]
    rows[row] = [rows[row][0]] + good[1:]
    _write_rows(p / "poi.csv", rows)


def _rule(p: Path, rid):
    doc = _yload(p / "approved-rules.yaml")
    for r in doc["rules"]:
        if r.get("rule_id") == rid:
            return doc, r
    raise KeyError(rid)


def _save_rules(p: Path, doc):
    _ydump(p / "approved-rules.yaml", doc)


def _drop_row(p: Path, row=1):
    rows = _rows(p / "poi.csv")
    del rows[row]
    _write_rows(p / "poi.csv", rows)


def _add_row(p: Path, rid="SD-9001"):
    rows = _rows(p / "poi.csv")
    rows.append([rid, "新增设施", "学校", "116.3100", "39.9100", "2026-09-21T10:00:00Z"])
    _write_rows(p / "poi.csv", rows)


def _scale_area(p: Path, factor=4.0):
    g = json.loads(io.open(p / "area.geojson", encoding="utf-8").read())
    ring = g["coordinates"][0]
    cx = sum(x for x, _y in ring) / len(ring)
    cy = sum(y for _x, y in ring) / len(ring)
    g["coordinates"][0] = [[cx + (x - cx) * factor, cy + (y - cy) * factor] for x, y in ring]
    io.open(p / "area.geojson", "w", encoding="utf-8").write(json.dumps(g, ensure_ascii=False))


def _extend_enum(p: Path, field="category", value="invalid_category"):
    rows = _rows(p / "dictionary.csv")
    head = rows[0]
    fi = head.index("field_name")
    ei = head.index("enum_values")
    for r in rows[1:]:
        if r[fi] == field:
            cur = r[ei].strip()
            inner = cur[1:-1] if cur.startswith("[") else ""
            items = [x.strip() for x in inner.split(",") if x.strip()]
            if value not in [x.strip('"') for x in items]:
                items.append('"%s"' % value)
            r[ei] = "[" + ",".join(items) + "]"
    _write_rows(p / "dictionary.csv", rows)


def _add_rule_nonempty(p: Path, rid="R11", field="name"):
    doc = _yload(p / "approved-rules.yaml")
    doc["rules"].append({
        "rule_id": rid,
        "requirement_ids": ["A2"],
        "rule_type": "non_empty",
        "status": "APPROVED",
        "version": 1,
        "reviewer": "stage1-compare-probe",
        "approved_at": "2026-10-26",
        "required_for_release": True,   # A2 是必检条款；挂 false 会被判 CLAUSE_POLICY_DOWNGRADED_BY_RULE
        "parameters": {"fields": [field], "trim": True,
                       "allowed_missing_rate": 0.0, "missing_rate_policy": "STRICT"},
        "parameter_sources": [],
        "preconditions": ["R01"],
        "notes": "",
    })
    _save_rules(p, doc)


# ---------------------------------------------------------------- 用例
def build_cases():
    """返回 [(id, title, before, after, expect)]。expect 的判定见 check()。"""
    out = []

    # ---- 正例对照
    out.append(("C00-identical", "正例对照：clean → clean（无失败项）",
                EX / "clean", EX / "clean",
                {"overall_in": ["LEDGER_CLOSED_ACCEPTED"], "ledger_in": ["CLOSED"]}))
    out.append(("C01-canonical", "正例对照：defective → corrected（8 关闭 + SD-0005 重复不可比）",
                EX / "defective", EX / "corrected",
                {"overall_in": ["LEDGER_INDETERMINATE"],
                 "counts_eq": {"closed": 8, "not_comparable": 1}}))

    # ---- 外部复核五个反例
    out.append(("EXT01-1", "数据集级失败未修：blocked → blocked（CRS 声明错误没改）",
                EX / "blocked", EX / "blocked",
                {"no_closed": True, "ledger_in": ["OPEN"],
                 "status_of": {"R07": "still_open"},
                 "identity_kinds": ["dataset"]}))
    out.append(("EXT01-2", "整改后缺证据：clean → ambiguous（阈值与精度依据不足）",
                EX / "clean", EX / "ambiguous",
                {"no_closed": True, "overall_not_in": ["LEDGER_CLOSED_ACCEPTED"],
                 "after_acceptance_in": ["INDETERMINATE"],
                 "scope_nonempty": ["unknown_after"]}))
    b = _mk("ext01_rule_unapproved_before")
    _stale(b)
    a = _mk("ext01_rule_unapproved_after")
    _stale(a)
    doc, r09 = _rule(a, "R09")
    r09["status"] = "DRAFT"
    _save_rules(a, doc)
    out.append(("EXT01-3", "规则未批准：同数据但 R09 改 DRAFT（检查资格不具备）", b, a,
                {"no_closed": True, "status_of": {"R09": "unresolved_unknown"},
                 "ledger_in": ["INDETERMINATE"]}))

    b = _mk("ext02_deleted_before")
    _stale(b)
    a = _mk("ext02_deleted_after")
    _stale(a)
    _drop_row(a)
    out.append(("EXT02-1", "删除缺陷实体：整改后直接删掉这条记录（故障实体删除）", b, a,
                {"no_closed": True, "status_of_record": {"SD-0001": "removed_pending_review"},
                 "counts_eq": {"removed_pending_review": 1},
                 "scope_eq": {"entities_removed_after": ["SD-0001"]},
                 "ledger_in": ["INDETERMINATE"]}))

    b = _mk("ext03_multi_before")
    _bad_category(b)
    _stale(b)
    a = _mk("ext03_multi_after")
    _bad_category(a)
    _stale(a)
    _repair(a)
    out.append(("EXT03-1", "唯一实体多条 finding：不构成实体重复（两条都真实修复）", b, a,
                {"identity_dup_before": [], "identity_dup_after": [],
                 "status_of": {"R04": CLOSED, "R09": CLOSED},
                 "counts_eq": {"closed": 2},
                 "overall_in": ["LEDGER_CLOSED_ACCEPTED"]}))

    # ---- 尺子变化（EXT-04）
    b = _mk("ext04_trim_before")
    _blank_name(b)
    a = _mk("ext04_trim_after")
    _blank_name(a)
    doc, r02 = _rule(a, "R02")
    r02["parameters"]["trim"] = False      # version 仍是 1：同版本改参数
    _save_rules(a, doc)
    out.append(("EXT04-1", "同版本改参数：R02 trim=true→false（放宽尺子制造“修复”）", b, a,
                {"no_closed": True, "status_of": {"R02": "not_comparable"},
                 "ruler_fp_changed_include": ["R02"]}))

    b = _mk("ext04_threshold_before")
    _stale(b)
    a = _mk("ext04_threshold_after")
    _stale(a)
    doc, r09 = _rule(a, "R09")
    r09["parameters"]["max_age_days"] = 365   # 判定阈值变了，来源没跟着改
    _save_rules(a, doc)
    out.append(("EXT04-2", "改判定阈值：R09 max_age_days 30→365（来源对不上 ⇒ 配置拒绝）", b, a,
                {"no_closed": True, "status_of": {"R09": "not_comparable"},
                 "ruler_fp_changed_include": ["R09"],
                 "after_rejections_nonempty": True}))

    b = _mk("ext04_dict_before")
    _bad_category(b)
    a = _mk("ext04_dict_after")
    _bad_category(a)
    _extend_enum(a)
    out.append(("EXT04-3", "改数据字典：把非法类别加进枚举（字典变了就不是同一把尺子）", b, a,
                {"no_closed": True, "status_of": {"R04": "not_comparable"},
                 "artifacts_changed_include": ["dictionary.csv"]}))

    b = _mk("ext04_area_before")
    _outside(b)
    a = _mk("ext04_area_after")
    _outside(a)
    _scale_area(a)
    out.append(("EXT04-4", "改项目范围：把 area.geojson 放大 4 倍让越界点“变合法”", b, a,
                {"no_closed": True, "status_of": {"R08": "not_comparable"},
                 "artifacts_changed_include": ["area.geojson"]}))

    b = _mk("ext04_reftime_before")
    _stale(b)
    a = _mk("ext04_reftime_after")
    _stale(a)
    doc, r09 = _rule(a, "R09")
    r09["parameters"]["reference_time"] = "2026-08-15T00:00:00Z"
    for s in r09.get("parameter_sources") or []:
        if s.get("parameter") == "reference_time":
            s["value"] = "2026-08-15T00:00:00Z"
    _save_rules(a, doc)
    out.append(("EXT04-5", "改基准时间：R09 reference_time 前移（来源同步改 ⇒ 拒绝执行）", b, a,
                {"no_closed": True, "status_of": {"R09": "not_comparable"},
                 "ruler_fp_changed_include": ["R09"]}))

    b = _mk("ext04_rule_removed_before")
    _stale(b)
    a = _mk("ext04_rule_removed_after")
    _stale(a)
    doc, _r09 = _rule(a, "R09")
    doc["rules"] = [r for r in doc["rules"] if r.get("rule_id") != "R09"]
    _save_rules(a, doc)
    out.append(("EXT04-6", "规则删除：整改后批次没有 R09（尺子被撤走）", b, a,
                {"no_closed": True, "status_of": {"R09": "not_comparable"},
                 "ruler_removed_include": ["R09"]}))

    b = _mk("ext04_dep_before")
    _bad_category(b)
    a = _mk("ext04_dep_after")
    _bad_category(a)
    _repair(a)
    doc, r03 = _rule(a, "R03")
    r03["status"] = "DRAFT"   # 上游失效 ⇒ 下游 BLOCKED
    _save_rules(a, doc)
    out.append(("EXT04-7", "依赖失效：上游 R03 改 DRAFT ⇒ 下游未完整执行", b, a,
                {"no_closed": True, "status_of": {"R04": "unresolved_unknown"},
                 "ledger_in": ["INDETERMINATE"]}))

    b = _mk("ext04_reapproval_before")
    _stale(b)
    a = _mk("ext04_reapproval_after")
    _stale(a)
    _repair(a)
    doc, r09 = _rule(a, "R09")
    r09["reviewer"] = "stage1-复核人B"
    r09["approved_at"] = "2026-10-27"
    _save_rules(a, doc)
    out.append(("EXT04-8", "批准来源变化：数据修好了但 R09 被重新批准", b, a,
                {"no_closed": True, "status_of": {"R09": "not_comparable"},
                 "ruler_fp_changed_include": ["R09"]}))

    # ---- 披露类
    b = _mk("disc_add_entity_before")
    a = _mk("disc_add_entity_after")
    _add_row(a)
    out.append(("EXT02-2", "新增实体必须披露（不比较没出现过失败的实体是不够的）", b, a,
                {"scope_nonempty": ["entities_added_after"],
                 "overall_in": ["LEDGER_CLOSED_ACCEPTED"]}))

    b = _mk("disc_add_rule_before")
    _stale(b)
    a = _mk("disc_add_rule_after")
    _stale(a)
    _repair(a)
    _add_rule_nonempty(a)
    out.append(("EXT04-9", "新增规则必须披露（R11 只存在于整改后批次）", b, a,
                {"ruler_added_include": ["R11"], "status_of": {"R09": CLOSED},
                 "overall_in": ["LEDGER_CLOSED_ACCEPTED"]}))

    # ---- 实体清单差异五组（S1-R2-02：干净实体删除同样阻断）
    # 故障实体删除 = EXT02-1；仅新增 = EXT02-2；无变化 = C00-identical。这里补另外两组。
    b = _mk("r202_clean_delete_before")
    a = _mk("r202_clean_delete_after")
    _drop_row(a)          # 删掉的是**原本干净**的 SD-0001（没有制造任何缺陷）
    out.append(("R202-1", "干净实体删除：无缺陷记录消失也必须待审核，不得整体放行", b, a,
                {"no_closed": True,
                 "overall_not_in": ["LEDGER_CLOSED_ACCEPTED"],
                 "status_of_record": {"SD-0001": "removed_pending_review"},
                 "counts_eq": {"removed_pending_review": 1},
                 "scope_eq": {"entities_removed_after": ["SD-0001"]},
                 "ledger_in": ["INDETERMINATE"]}))

    b = _mk("r202_shuffle_before")
    a = _mk("r202_shuffle_after")
    rows = _rows(a / "poi.csv")
    _write_rows(a / "poi.csv", [rows[0]] + list(reversed(rows[1:])))
    out.append(("R202-2", "行序打乱：身份按 record_id 而非行号，结论不得变化", b, a,
                {"overall_in": ["LEDGER_CLOSED_ACCEPTED"], "ledger_in": ["CLOSED"],
                 "scope_eq": {"entities_removed_after": [], "entities_added_after": []},
                 "identity_dup_after": []}))
    return out


# ---------------------------------------------------------------- 逐规则参数反例（S1-R2-01）
def build_param_cases():
    """返回 [(id, title, bundle, expect)]。expect 经 check_validate() 判定。

    十类规则各一个非法参数用例 + 未知 rule_type + 缺 parameters + 有效输入正向对照。
    全部走**正式 validate 入口**（validate_bundle）：受控拒绝 ⇒ executed=false、
    INDETERMINATE、`INPUT_SCHEMA_INVALID` 且 target 定位到具体规则；
    拒绝后结构化报告必须保留"应检查的条款数量"（counts.clauses_required / clauses_pending）。
    """
    out = []

    def mkparam(cid, rid, mutate):
        p = _mk("param_%s" % cid.lower())
        doc, r = _rule(p, rid)
        mutate(r)
        _save_rules(p, doc)
        return p

    def add(cid, title, rid, mutate):
        out.append((cid, title, mkparam(cid, rid, mutate), rid))

    add("PARAM-01", "required_field_present：空必需数组（fields=[]）", "R01",
        lambda r: r["parameters"].__setitem__("fields", []))
    add("PARAM-02", "non_empty：错误类型（trim='yes' 字符串）", "R02",
        lambda r: r["parameters"].__setitem__("trim", "yes"))
    add("PARAM-03", "type_parse：fields 不是数组", "R03",
        lambda r: r["parameters"].__setitem__("fields", "record_id"))
    add("PARAM-04", "enum_value：缺必填参数（allow_alias）", "R04",
        lambda r: r["parameters"].pop("allow_alias"))
    add("PARAM-05", "id_unique：field 不是字符串", "R05",
        lambda r: r["parameters"].__setitem__("field", 123))
    add("PARAM-06", "coord_range：lon_range 少于 2 个数", "R06",
        lambda r: r["parameters"].__setitem__("lon_range", [-180]))
    add("PARAM-07", "crs_declaration：expected_crs 含非法字符", "R07",
        lambda r: r["parameters"].__setitem__("expected_crs", "EPSG:4326 地理坐标系"))
    add("PARAM-08", "within_project_area：boundary_policy 非法枚举", "R08",
        lambda r: r["parameters"].__setitem__("boundary_policy", "somewhere"))
    add("PARAM-09", "freshness：max_age_days 为负", "R09",
        lambda r: r["parameters"].__setitem__("max_age_days", -1))
    add("PARAM-10", "duplicate_candidate：未知参数键（extra）", "R10",
        lambda r: r["parameters"].__setitem__("extra_key", 1))
    add("PARAM-11", "未知 rule_type：magic_check", "R05",
        lambda r: r.__setitem__("rule_type", "magic_check"))
    add("PARAM-12", "缺 parameters：不得按默认值继续执行", "R01",
        lambda r: r.pop("parameters"))

    # 有效输入正向对照：未篡改的 clean 必须照常执行并给出 PASS
    out.append(("PARAM-00", "有效输入正向对照：clean 照常执行（不误杀）",
                _mk("param_valid_control"), None))
    return out


def check_validate(vres, expect):
    """校验 validate_bundle 的输出；返回 [] 表示通过。"""
    bad = []
    rid = expect.get("target_rule")
    if rid is None:  # 正向对照
        if not vres["executed"]:
            bad.append("有效输入被误杀：executed=false（rejections=%s）"
                       % vres["config_rejections"])
        if vres["aggregate_verdict"] != "PASS":
            bad.append("有效输入结论=%s，期望 PASS" % vres["aggregate_verdict"])
        return bad
    if vres["executed"]:
        bad.append("非法参数未受控拒绝：executed=true")
    if vres["aggregate_verdict"] != "INDETERMINATE":
        bad.append("结论=%s，期望 INDETERMINATE（拒绝执行）" % vres["aggregate_verdict"])
    codes = [r["code"] for r in vres["config_rejections"]]
    if "INPUT_SCHEMA_INVALID" not in codes:
        bad.append("未登记 INPUT_SCHEMA_INVALID（rejections=%s）" % vres["config_rejections"][:3])
    targets = [r["target"] for r in vres["config_rejections"]]
    if rid not in targets:
        bad.append("拒绝项未定位到规则 %s（targets=%s）" % (rid, targets[:5]))
    if vres["counts"]["clauses_required"] <= 0:
        bad.append("拒绝执行时 counts.clauses_required=%s：必须保留应检查的条款数量"
                   % vres["counts"]["clauses_required"])
    if not vres.get("clauses_pending"):
        bad.append("拒绝执行时 clauses_pending 为空：不得把拒绝执行说成项目没有条款")
    return bad


# ---------------------------------------------------------------- 断言
def check(res, expect):
    """返回 [] 表示通过，否则返回失败原因列表。"""
    bad = []
    items = res["items"]
    if expect.get("no_closed") and any(i["status"] == CLOSED for i in items):
        bad.append("出现 closed：%s" % [i["key"] for i in items if i["status"] == CLOSED])
    if "overall_in" in expect and res["overall"] not in expect["overall_in"]:
        bad.append("overall=%s 不在 %s" % (res["overall"], expect["overall_in"]))
    if "overall_not_in" in expect and res["overall"] in expect["overall_not_in"]:
        bad.append("overall=%s 落入禁止集合 %s" % (res["overall"], expect["overall_not_in"]))
    if "ledger_in" in expect and res["ledger"] not in expect["ledger_in"]:
        bad.append("ledger=%s 不在 %s" % (res["ledger"], expect["ledger_in"]))
    if "after_acceptance_in" in expect and res["after_acceptance"] not in expect["after_acceptance_in"]:
        bad.append("after_acceptance=%s 不在 %s"
                   % (res["after_acceptance"], expect["after_acceptance_in"]))
    for rid, want in (expect.get("status_of") or {}).items():
        got = sorted({i["status"] for i in items if i["rule_id"] == rid})
        if got != [want]:
            bad.append("规则 %s 的条目状态=%s，期望 [%s]" % (rid, got, want))
    for rid, want in (expect.get("status_of_record") or {}).items():
        got = sorted({i["status"] for i in items if i.get("record_id") == rid})
        if got != [want]:
            bad.append("实体 %s 的条目状态=%s，期望 [%s]" % (rid, got, want))
    for k, v in (expect.get("counts_eq") or {}).items():
        if res["counts"].get(k) != v:
            bad.append("counts[%s]=%s，期望 %s" % (k, res["counts"].get(k), v))
    for side in ("before", "after"):
        key = "identity_dup_%s" % side
        if key in expect and res["identity"][side]["duplicated"] != expect[key]:
            bad.append("identity.%s.duplicated=%s，期望 %s"
                       % (side, res["identity"][side]["duplicated"], expect[key]))
    if "identity_kinds" in expect:
        kinds = sorted({i["identity_kind"] for i in items})
        for k in expect["identity_kinds"]:
            if k not in kinds:
                bad.append("台账条目缺少 identity_kind=%s（实际 %s）" % (k, kinds))
    for rid in (expect.get("ruler_fp_changed_include") or []):
        if rid not in res["ruler"]["rule_fingerprint_changed"]:
            bad.append("规则 %s 未被识别为语义指纹变化（实际 %s）"
                       % (rid, sorted(res["ruler"]["rule_fingerprint_changed"])))
    for rid in (expect.get("ruler_removed_include") or []):
        if rid not in res["ruler"]["rules_removed_after"]:
            bad.append("规则 %s 未被记录为整改后缺失（实际 %s）"
                       % (rid, res["ruler"]["rules_removed_after"]))
    for rid in (expect.get("ruler_added_include") or []):
        if rid not in res["ruler"]["rules_added_after"]:
            bad.append("规则 %s 未被披露为整改后新增（实际 %s）"
                       % (rid, res["ruler"]["rules_added_after"]))
    for art in (expect.get("artifacts_changed_include") or []):
        if art not in res["ruler"]["artifacts_changed"]:
            bad.append("批次制品 %s 未被识别为变化（实际 %s）"
                       % (art, res["ruler"]["artifacts_changed"]))
    for k, v in (expect.get("scope_eq") or {}).items():
        if res["scope"].get(k) != v:
            bad.append("scope.%s=%s，期望 %s" % (k, res["scope"].get(k), v))
    for k in (expect.get("scope_nonempty") or []):
        if not res["scope"].get(k):
            bad.append("scope.%s 为空，必须可见" % k)
    if expect.get("after_rejections_nonempty") and not res["after"]["config_rejections"]:
        bad.append("整改后批次应存在配置拒绝，实际为空")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留造出来的样例包")
    args = ap.parse_args()

    if CASES.exists():
        shutil.rmtree(CASES)
    CASES.mkdir(parents=True, exist_ok=True)

    # Schema 校验器（仓库自带的标准库子集实现）
    from check_schema_consistency import make_validator
    v = make_validator()
    cmp_schema = v.load_schema("stage1_compare.schema.json")
    val_schema = v.load_schema("stage1_validate.schema.json")

    results = []
    for cid, title, b, a, exp in build_cases():
        res = cmp.compare_batches(Path(b), Path(a))
        errs = check(res, exp)
        schema_errs = v.validate(res, cmp_schema, cid)
        if schema_errs:
            errs.append("Schema 校验失败：%s" % schema_errs[:3])
        results.append({
            "case": cid, "title": title, "ok": not errs,
            "before": str(b), "after": str(a),
            "expected": exp,
            "actual": {"overall": res["overall"], "ledger": res["ledger"],
                       "after_acceptance": res["after_acceptance"],
                       "counts": res["counts"],
                       "identity": {"before": res["identity"]["before"],
                                    "after": res["identity"]["after"]},
                       "ruler": res["ruler"],
                       "scope": {k: res["scope"][k] for k in
                                 ("entities_removed_after", "entities_added_after",
                                  "advisory_after", "unknown_after", "ledger_size")},
                       "items": [{"key": i["key"], "rule_id": i["rule_id"],
                                  "status": i["status"], "before_codes": i["before_codes"],
                                  "after_codes": i["after_codes"],
                                  "after_unknown_codes": i["after_unknown_codes"],
                                  "reasons": i["reasons"]} for i in res["items"]]},
            "errors": errs,
        })
        print("[%s] %-12s %s" % ("PASS" if not errs else "FAIL", cid, title))
        print("      overall=%s ledger=%s after=%s counts=%s"
              % (res["overall"], res["ledger"], res["after_acceptance"], res["counts"]))
        for e in errs:
            print("      - %s" % e)

    # ---- 逐规则入口参数反例（S1-R2-01）：走正式 validate 入口
    for cid, title, bundle, rid in build_param_cases():
        vres = vld.validate_bundle(Path(bundle))
        errs = check_validate(vres, {"target_rule": rid})
        schema_errs = v.validate(vres, val_schema, cid)
        if schema_errs:
            errs.append("Schema 校验失败：%s" % schema_errs[:3])
        results.append({
            "case": cid, "title": title, "ok": not errs,
            "before": str(bundle), "after": "",
            "expected": {"executed": rid is None,
                         "verdict": "PASS" if rid is None else "INDETERMINATE",
                         "target_rule": rid},
            "actual": {"executed": vres["executed"],
                       "aggregate_verdict": vres["aggregate_verdict"],
                       "config_rejections": vres["config_rejections"][:5],
                       "counts": vres["counts"],
                       "clauses_pending": vres.get("clauses_pending")},
            "errors": errs,
        })
        print("[%s] %-12s %s" % ("PASS" if not errs else "FAIL", cid, title))
        print("      executed=%s verdict=%s clauses_required=%s rejections=%s"
              % (vres["executed"], vres["aggregate_verdict"],
                 vres["counts"]["clauses_required"],
                 [(r["code"], r["target"]) for r in vres["config_rejections"][:2]]))
        for e in errs:
            print("      - %s" % e)

    # 正式入口 validate：无 expected 也能检查新包，并通过 Schema
    vb = _mk("validate_probe_bundle")
    _stale(vb)
    vres = vld.validate_bundle(vb)
    verrs = v.validate(vres, val_schema, "validate_probe")
    vok = (vres["aggregate_verdict"] == "FAIL" and vres["expected_used"] is False
           and vres["findings_by_class"].get("FAIL", 0) >= 1 and not verrs)
    results.append({
        "case": "VALIDATE-1", "title": "正式入口 validate：新包无 expected 也能给出结论",
        "ok": vok, "before": str(vb), "after": "",
        "expected": {"aggregate_verdict": "FAIL", "expected_used": False},
        "actual": {"aggregate_verdict": vres["aggregate_verdict"],
                   "expected_used": vres["expected_used"],
                   "findings_by_class": vres["findings_by_class"],
                   "counts": vres["counts"],
                   "schema_errors": verrs},
        "errors": ([] if vok else ["validate 输出不符合预期：%s" % results]) ,
    })
    print("[%s] %-12s %s" % ("PASS" if vok else "FAIL", "VALIDATE-1",
                             "正式入口 validate：新包无 expected 也能给出结论"))
    print("      verdict=%s expected_used=%s findings=%s schema_err=%s"
          % (vres["aggregate_verdict"], vres["expected_used"],
             vres["findings_by_class"], verrs[:2]))

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "compare-probe-results.json"
    ok_n = sum(1 for r in results if r["ok"])
    out.write_text(json.dumps({"schema_version": "stage1-compare-probes-1",
                               "python": sys.version.split()[0],
                               "cases": len(results), "passed": ok_n,
                               "all_ok": ok_n == len(results),
                               "results": results},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.keep:
        shutil.rmtree(CASES, ignore_errors=True)
    print("")
    print("COMPARE_PROBES_OK=%s（%d/%d）" % ("true" if ok_n == len(results) else "false",
                                            ok_n, len(results)))
    print("结构化结果：%s" % out)
    return 0 if ok_n == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
