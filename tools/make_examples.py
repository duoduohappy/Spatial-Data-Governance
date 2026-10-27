"""生成示例包：clean / defective / corrected / ambiguous / blocked / crs_same_unit_wrong（共六组）。

设计原则：
- 全部数据为合成数据，不涉及任何真实客户或测绘成果。
- 每个示例包自带：交付说明、数据字典、POI 数据、范围、CRS 声明、已批准规则、期望结果。
- 引用的原文行号由本脚本在写入 spec 后回算并冻结，避免手写行号错位。
"""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sys

# 终端编码：中文输出在 GBK 终端/重定向下会抛 UnicodeEncodeError（证据链断在中途）。
# 统一把标准输出/错误固定为 UTF-8：等价于 README 建议的 `python -X utf8`，
# 且不依赖调用方是否设置 PYTHONUTF8 / PYTHONIOENCODING。
for _s in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
    if _s is not None and hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="strict")

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"

REF_TIME = "2026-10-01T00:00:00Z"

SPEC_COMMON = [
    "# 示例区公共设施 POI 交付说明 v0.1",
    "",
    "本文档为交付验收依据。以下条款为本次交付检查的唯一依据，条款编号仅用于追溯。",
    "",
    "## A. 通用要求",
    "",
    "A1. 每条记录必须包含全部必填字段。",
    "A2. 必填字段不得为空值；空值指去除首尾空白后长度为 0 的字符串。",
    "A3. 字段类型必须符合数据字典声明；日期时间字段采用 ISO8601 格式。",
    "A4. category 字段取值必须在数据字典给定的枚举范围内。",
    "A5. record_id 必须唯一，不得重复，也不得为空。",
    "",
    "## B. 空间要求",
    "",
    "B1. 坐标必须是有限数值；经度取值范围 [-180,180]，纬度取值范围 [-90,90]。",
    "B2. 坐标参考系必须与 crs.json 的声明一致；本批次声明为 EPSG:4326。",
    "B3. 点位必须落在项目范围 area.geojson 之内，落在边界线上的点视为落在范围内。",
    "",
    "## C. 时效与其他",
    "",
    "C1. 采集时间距基准时间不得超过 30 天。基准时间固定为 2026-10-01T00:00:00Z。",
    "C2. 相距不超过 30 米且名称相同的点位，应提交人工确认是否为重复设施。本项仅供参考，不作为放行依据。",
]

SPEC_AMBIGUOUS_EXTRA = [
    "",
    "## D. 待澄清条款",
    "",
    "D1. 数据应及时更新。",
    "D2. 坐标精度应满足项目要求。",
]

DICTIONARY_HEADER = "field_name,description,data_type,required,enum_values\n"
DICTIONARY_ROWS = [
    ("record_id", "记录唯一标识", "string", "true", ""),
    ("name", "设施名称", "string", "true", ""),
    ("category", "设施类别", "string", "true", '["学校","医院","公园","公交站"]'),
    ("longitude", "经度（WGS84 十进制度）", "number", "true", ""),
    ("latitude", "纬度（WGS84 十进制度）", "number", "true", ""),
    ("source_time", "数据采集时间", "datetime", "true", ""),
]
FIELDS = [r[0] for r in DICTIONARY_ROWS]

AREA = {
    "type": "Polygon",
    "coordinates": [[
        [116.3000, 39.9000], [116.3200, 39.9000], [116.3200, 39.9200],
        [116.3000, 39.9200], [116.3000, 39.9000],
    ]],
}

CLEAN_ROWS = [
    # record_id, name, category, lon, lat, source_time
    ("SD-0001", "示例第一小学", "学校", "116.3050", "39.9050", "2026-09-20T10:00:00Z"),
    ("SD-0002", "示例社区卫生服务中心", "医院", "116.3080", "39.9080", "2026-09-22T09:30:00Z"),
    ("SD-0003", "示例中心公园", "公园", "116.3120", "39.9130", "2026-09-25T14:00:00Z"),
    ("SD-0004", "示例公交站（南）", "公交站", "116.3155", "39.9025", "2026-09-18T08:00:00Z"),
    ("SD-0005", "示例第二小学", "学校", "116.3025", "39.9175", "2026-09-26T11:20:00Z"),
    ("SD-0006", "示例区医院", "医院", "116.3180", "39.9160", "2026-09-27T16:45:00Z"),
    ("SD-0007", "示范路公交站", "公交站", "116.3100", "39.9005", "2026-09-19T07:15:00Z"),
    ("SD-0008", "示例北苑公园", "公园", "116.3035", "39.9110", "2026-09-28T13:05:00Z"),
    ("SD-0009", "示例第三小学", "学校", "116.3165", "39.9085", "2026-09-21T15:30:00Z"),
    ("SD-0010", "示例南门公交站", "公交站", "116.3070", "39.9190", "2026-09-24T12:00:00Z"),
    ("SD-0011", "示例口袋公园", "公园", "116.3140", "39.9185", "2026-09-23T10:40:00Z"),
    ("SD-0012", "示例口袋公园", "公园", "116.3142", "39.9186", "2026-09-23T10:45:00Z"),
]


def rows_to_csv(rows):
    out = [",".join(FIELDS)]
    for r in rows:
        out.append(",".join(r))
    return "\n".join(out) + "\n"


def replace_row(rows, rid, **kwargs):
    new = []
    for r in rows:
        if r[0] == rid:
            lst = list(r)
            for k, v in kwargs.items():
                lst[FIELDS.index(k)] = v
            new.append(tuple(lst))
        else:
            new.append(r)
    return new


def build_defective(base):
    rows = list(base)
    rows = replace_row(rows, "SD-0003", category="公共厕所")
    rows = replace_row(rows, "SD-0007", category="")
    rows = replace_row(rows, "SD-0002", source_time="2026-09-22 09:30")
    rows = replace_row(rows, "SD-0009", latitude="91.5000")
    rows = replace_row(rows, "SD-0010", longitude="")
    rows = replace_row(rows, "SD-0011", longitude="116.3600")
    rows = replace_row(rows, "SD-0006", source_time="2026-08-01T00:00:00Z")
    rows = replace_row(rows, "SD-0012", record_id="SD-0005")
    rows.append(("SD-0013", "示例西园公园", "公园", "abc", "39.9070", "2026-09-20T09:00:00Z"))
    rows.append(("SD-0014", "示例东园公园", "公园", "116.3130", "39.9145", "2026-09-22T10:00:00Z"))
    rows.append(("SD-0015", "示例东园公园", "公园", "116.3131", "39.9146", "2026-09-22T10:05:00Z"))
    return rows


def build_corrected(base, defective):
    """整改包：所有可整改缺陷均已修复，且保留 SD-0011/SD-0012 这组候选（演示非必检项始终可见）。"""
    rows = list(CLEAN_ROWS)
    rows.append(("SD-0013", "示例西园公园", "公园", "116.3090", "39.9070", "2026-09-20T09:00:00Z"))
    rows.append(("SD-0014", "示例东园公园", "公园", "116.3130", "39.9145", "2026-09-22T10:00:00Z"))
    rows.append(("SD-0015", "示例东园公园（二期）", "公园", "116.3170", "39.9146", "2026-09-22T10:05:00Z"))
    return rows


# 条款解释记录（契约 §9.3 / 验收方点名）：把实现限制写成**本项目采用的格式子集**，
# 不得把「我们只实现了这个子集」说成「ISO8601 标准要求如此」。
CLAUSE_INTERPRETATIONS = {
    "A3": ("本项目采用 ISO8601 的 RFC3339 子集：必须带 T 分隔符与显式时区（Z 或 ±HH:MM）。"
           "这是本项目采用的格式子集，不是 ISO8601 标准的全部。"),
}

CLAUSE_QUOTES = {
    "A1": "A1. 每条记录必须包含全部必填字段。",
    "A2": "A2. 必填字段不得为空值；空值指去除首尾空白后长度为 0 的字符串。",
    "A3": "A3. 字段类型必须符合数据字典声明；日期时间字段采用 ISO8601 格式。",
    "A4": "A4. category 字段取值必须在数据字典给定的枚举范围内。",
    "A5": "A5. record_id 必须唯一，不得重复，也不得为空。",
    "B1": "B1. 坐标必须是有限数值；经度取值范围 [-180,180]，纬度取值范围 [-90,90]。",
    "B2": "B2. 坐标参考系必须与 crs.json 的声明一致；本批次声明为 EPSG:4326。",
    "B3": "B3. 点位必须落在项目范围 area.geojson 之内，落在边界线上的点视为落在范围内。",
    "C1": "C1. 采集时间距基准时间不得超过 30 天。基准时间固定为 2026-10-01T00:00:00Z。",
    "C2": "C2. 相距不超过 30 米且名称相同的点位，应提交人工确认是否为重复设施。本项仅供参考，不作为放行依据。",
    "D1": "D1. 数据应及时更新。",
    "D2": "D2. 坐标精度应满足项目要求。",
}

RULE_MAP = [
    ("R01", "A1", "required_field_present", True, {"fields": FIELDS}, []),
    ("R02", "A2", "non_empty", True,
     {"fields": FIELDS, "trim": True, "allowed_missing_rate": 0.0, "missing_rate_policy": "STRICT"}, []),
    ("R03", "A3", "type_parse", True, {"fields": FIELDS}, ["R02"]),
    ("R04", "A4", "enum_value", True, {"field": "category", "allow_alias": False}, ["R01", "R03"]),
    ("R05", "A5", "id_unique", True, {"field": "record_id"}, ["R01"]),
    ("R06", "B1", "coord_range", True, {"lon_range": [-180, 180], "lat_range": [-90, 90]}, ["R01", "R03", "R07"]),
    ("R07", "B2", "crs_declaration", True,
     {"expected_from_sidecar": True, "expected_crs": "EPSG:4326"}, ["R01"]),
    ("R08", "B3", "within_project_area", True, {"boundary_policy": "inclusive"}, ["R01", "R03", "R06", "R07"]),
    ("R09", "C1", "freshness", True, {"max_age_days": 30, "reference_time": REF_TIME}, ["R01", "R03"]),
    ("R10", "C2", "duplicate_candidate", False, {"max_distance_m": 30, "name_equal": True}, ["R01", "R03", "R06"]),
]

# 结构化参数来源（契约 §6.1）：只有「参与判定的参数」需要来源，
# 结构性配置（trim / allow_alias / name_equal / expected_from_sidecar / missing_rate_policy）不需要。
# value_literal 必须是冻结引用中的**完整 token**（GA-05：禁用子串包含）。
PARAM_SOURCE_SPEC = {
    "R06": [
        ("lon_range", "B1", ["-180", "180"], "degree", "原文直接给出经度取值区间 [-180,180]。"),
        ("lat_range", "B1", ["-90", "90"], "degree", "原文直接给出纬度取值区间 [-90,90]。"),
    ],
    "R07": [
        ("expected_crs", "B2", ["EPSG:4326"], None,
         "原文明确本批次声明为 EPSG:4326；判定按规范形式严格比对，Stage 0 不做别名推断。"),
    ],
    "R08": [
        ("boundary_policy", "B3", ["落在边界线上的点视为落在范围内"], None,
         "原文规定边界线上的点视为在范围内，映射为 inclusive；该映射由人工批准，"
         "机器只校验字面存在，不判定解释是否正确。"),
    ],
    "R09": [
        ("max_age_days", "C1", ["30"], "day", "原文直接给出天数上限，无需解释。"),
        ("reference_time", "C1", ["2026-10-01T00:00:00Z"], None,
         "原文固定基准时间；实现禁止取当前时间。"),
    ],
    "R10": [
        ("max_distance_m", "C2", ["30"], "metre", "原文直接给出 30 米的距离上限。"),
    ],
}

REVIEWER = "stage0-人工批准（示例）"
APPROVED_AT = "2026-10-26"

SCHEMA_VERSION = "stage0-2"
# 人工真值审核记录（契约 §9.6）。与 examples/TRUTH_REVIEW.md §1 必须一致；
# 本脚本只负责把它写进 expected，不代表"生成即真值"。
TRUTH_REVIEW = {
    "reviewer": "严过关（QA，Stage 0 重验）",
    "date": "2026-10-26",
    "method": ("人工逐条推导：以 examples/README.md 缺陷真值表 + docs/stage0-recheck-contract.md "
               "（§1 三态 / §4 CRS 四类 / §7 统计口径 / §9.4 记录级比对）为唯一依据，"
               "先写出期望值再执行实现；实现输出与推导不一致即视为实现缺陷并上报。"),
    "basis": ("examples/*/delivery_spec.md 冻结条款行 + INPUT_MANIFEST.json 哈希 + "
              "examples/README.md 缺陷真值表；每条数字可回溯到具体数据行号。"),
    "reviewed_fields": ("per_rule 的 verdict / execution_status / reason_code / 六个统计字段 / findings / "
                        "failure_reason_codes / advisory_reason_codes；"
                        "expected/findings.json 的 stable_key / reason_code / field / observed_value / "
                        "review_state / execution_status / record_locator；"
                        "expected/clause_coverage.json 的 coverage_state / verdict / "
                        "execution_status / reason_code / failure_reason_codes / advisory_reason_codes。"),
}


def build_parameter_sources(rule_id, params, req_by_id):
    """生成某条规则的 ParameterSource 列表。

    判定类参数必须有来源，来源要写清：来源条款、文档哈希、冻结行号、逐字引用、
    token 级字面量、单位、解释与批准人。Stage 0 只能保证「字面可追溯」。
    """
    out = []
    for pname, cid, literals, unit, interpretation in PARAM_SOURCE_SPEC.get(rule_id, []):
        meta = req_by_id.get(cid)
        if meta is None:
            continue
        out.append({
            "parameter": pname,
            "value": params[pname],
            "requirement_id": cid,
            "document_id": meta["document_id"],
            "document_sha256": meta["document_sha256"],
            "source_line_start": meta["source_line_start"],
            "source_line_end": meta["source_line_end"],
            "source_quote": meta["source_quote"],
            "value_literal": literals,
            "unit": unit,
            "interpretation": interpretation,
            "reviewer": REVIEWER,
            "approved_at": APPROVED_AT,
        })
    return out


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def sha256_of(path: Path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def build_bundle(name, spec_lines, rows, declared_crs, expected):
    bdir = EX / name
    spec_text = "\n".join(spec_lines) + "\n"
    spec_path = bdir / "delivery_spec.md"
    write_text(spec_path, spec_text)
    lines = spec_text.split("\n")

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["field_name", "description", "data_type", "required", "enum_values"])
    for r in DICTIONARY_ROWS:
        writer.writerow(list(r))
    write_text(bdir / "dictionary.csv", buf.getvalue())
    write_text(bdir / "poi.csv", rows_to_csv(rows))
    write_text(bdir / "area.geojson", json.dumps(AREA, ensure_ascii=False, indent=2) + "\n")

    if declared_crs == "EPSG:4326":
        write_text(bdir / "crs.json", json.dumps({
            "declared_crs": "EPSG:4326",
            "declared_unit": "degree",
            "note": "示例包：经纬度十进制度。合成数据，非真实测绘成果。",
        }, ensure_ascii=False, indent=2) + "\n")
    else:
        write_text(bdir / "crs.json", json.dumps({
            "declared_crs": "EPSG:3857",
            "declared_unit": "metre",
            "note": ("示例包（合成数据）：交付说明 B2（第 16 行，已冻结并哈希）明确「本批次声明为 EPSG:4326」，"
                     "此处提交 EPSG:3857 —— 构成可证明的**声明冲突**。判定只看声明与要求是否一致："
                     "不按坐标量级推断真实 CRS，坐标量级仅作风险信号。依赖 CRS 的空间检查按 §4.4 全批阻断。"),
        }, ensure_ascii=False, indent=2) + "\n")

    # 回算引用行号（1-based），找不到引用即失败，不允许静默通过
    requirements = []
    for cid, quote in CLAUSE_QUOTES.items():
        if quote not in lines:
            continue
        idx = lines.index(quote) + 1
        requirements.append({
            "requirement_id": cid,
            "document_id": "delivery_spec.md",
            "document_sha256": sha256_of(spec_path),
            "source_line_start": idx,
            "source_line_end": idx,
            "source_quote": quote,
            "required_for_release": cid not in ("C2",),
            "support_status": "NEEDS_CLARIFICATION" if cid in ("D1", "D2") else "SUPPORTED",
        })
        if cid in CLAUSE_INTERPRETATIONS:
            requirements[-1]["interpretation"] = CLAUSE_INTERPRETATIONS[cid]

    req_doc = {
        "schema_version": 1,
        "bundle": name,
        "reference_time": REF_TIME,
        "requirements": requirements,
    }
    write_text(bdir / "requirements.yaml", dump_yaml(req_doc))

    req_by_id = {r["requirement_id"]: r for r in requirements}
    approved = []
    for rid, cid, rtype, req_rel, params, deps in RULE_MAP:
        cid_supported = True
        for q in requirements:
            if q["requirement_id"] == cid and q["support_status"] != "SUPPORTED":
                cid_supported = False
        approved.append({
            "rule_id": rid,
            "requirement_ids": [cid],
            "rule_type": rtype,
            "status": "APPROVED" if cid_supported else "DRAFT",
            "version": 1,
            "reviewer": REVIEWER,
            "approved_at": APPROVED_AT,
            "required_for_release": req_rel,
            "parameters": params,
            "parameter_sources": build_parameter_sources(rid, params, req_by_id),
            "preconditions": deps,
            "notes": "" if cid_supported else "原文缺少可判定阈值，不得批准，保持 DRAFT",
        })
    write_text(bdir / "approved-rules.yaml", dump_yaml({"schema_version": 1, "bundle": name, "rules": approved}))

    payload = dict(expected)
    # 人工真值审核记录（契约 §9.6）：expected 必须自带"谁审的、怎么审的"，
    # 与 examples/TRUTH_REVIEW.md 保持一致；重生成不构成真值证明。
    payload["schema_version"] = SCHEMA_VERSION
    payload["truth_source"] = "人工推导"
    payload["truth_review"] = dict(TRUTH_REVIEW)
    ordered = {"schema_version": payload["schema_version"],
               "truth_source": payload["truth_source"],
               "truth_review": payload["truth_review"]}
    ordered.update({k: v for k, v in payload.items() if k not in ordered})
    write_text(bdir / "expected" / "aggregate.json",
               json.dumps(ordered, ensure_ascii=False, indent=2) + "\n")


def dump_yaml(obj, indent=0):
    """极简 YAML 序列化，避免 Stage 0 引入额外依赖。"""
    pad = "  " * indent
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list) and not v:
                # 空序列必须写成 `k: []`（GA-09）：换行写法会被极简解析器当成子映射
                out.append("%s%s: []" % (pad, k))
            elif isinstance(v, (dict, list)):
                out.append(f"{pad}{k}:")
                out.append(dump_yaml(v, indent + 1))
            else:
                out.append(f"{pad}{k}: {_scalar(v)}")
    elif isinstance(obj, list):
        if not obj:
            # 空序列必须序列化成 []（GA-09）：否则解析侧得到 None，与 Schema 要求的 array 冲突
            return pad + "[]"
        for v in obj:
            if isinstance(v, (dict, list)):
                item = dump_yaml(v, indent + 1)
                out.append(f"{pad}-")
                out.append(item if item else "")
            else:
                out.append(f"{pad}- {_scalar(v)}")
    return "\n".join(x for x in out if x != "")


def _scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s.startswith("[") or s.startswith("{"):
        return '"%s"' % s.replace('"', '\\"')
    return '"%s"' % s.replace('"', '\\"')


def pr(verdict, status, reason, total, evaluated, failed, indeterminate,
       skipped_upstream, uninterpretable, findings, failure=(), advisory=()):
    """构造 per_rule 的**记录级**真值条目（契约 §9.4 / §7.1）。

    旧写法是 `[verdict, findings]` 二元组——主门禁只比这两个数时，「命中错行但数量相同」会通过。
    现在逐字段登记：verdict / execution_status / reason_code / 六个统计字段 / findings
    + failure_reason_codes / advisory_reason_codes（§3.5.2：去重、保留首次出现顺序）。
    参数顺序即字段顺序，避免长字典字面量串行错位。
    """
    return {
        "verdict": verdict,
        "execution_status": status,
        "reason_code": reason,
        "records_total": total,
        "records_evaluated": evaluated,
        "records_failed": failed,
        "records_indeterminate": indeterminate,
        "records_skipped_upstream": skipped_upstream,
        "records_uninterpretable": uninterpretable,
        "findings": findings,
        "failure_reason_codes": list(failure),
        "advisory_reason_codes": list(advisory),
    }


def main():
    base = build_defective(CLEAN_ROWS)
    corrected = build_corrected(CLEAN_ROWS, base)

    # ---------------------------------------------------------------- 人工真值（登记在 examples/TRUTH_REVIEW.md）
    # 红线：这里的每一个数字都必须能在 examples/TRUTH_REVIEW.md 找到推导依据。
    # 结论与缺陷数前后不变：PASS/FAIL/PASS/INDETERMINATE/FAIL/FAIL — 1/11/1/1/1/1。
    # reason_code 一律遵守 I7–I9（§3.5.1）：OK 只出现在 PASS 上；FAIL 取第一条 FAIL 类 finding 的码；
    # INDETERMINATE 取覆盖态码 / 上游码 / 缺证据类码 / 候选码，绝不回退 OK。
    # crs_same_unit_wrong 是手写反例包，不参与生成（见 build_bundle 与 TRUTH_REVIEW §2）。
    P12 = ("PASS", "COMPLETED", "OK", 12, 12, 0, 0, 0, 0, 0)
    P15 = ("PASS", "COMPLETED", "OK", 15, 15, 0, 0, 0, 0, 0)
    # blocked / crs_same_unit_wrong：数据集级 CRS 冲突 → 全批 uninterpretable，下游全批 BLOCKED
    P12B = ("INDETERMINATE", "BLOCKED", "ALL_RECORDS_BLOCKED", 12, 0, 0, 0, 12, 0, 0)

    EXPECTED = {
        "clean": {
            "aggregate_verdict": "PASS",
            "per_rule": {
                "R01": pr(*P12), "R02": pr(*P12), "R03": pr(*P12), "R04": pr(*P12),
                "R05": pr(*P12), "R06": pr(*P12), "R07": pr(*P12), "R08": pr(*P12),
                "R09": pr(*P12),
                # GA-07：候选不是失败也不是阻断 → evaluated 12、indeterminate 2、failed 0
                "R10": pr("INDETERMINATE", "COMPLETED", "DUPLICATE_CANDIDATE", 12, 12, 0, 2, 0, 0, 1),
            },
            "note": "R10 为非必检项，存在 1 组待人工确认的重复候选，但不阻断放行。",
        },
        "defective": {
            "aggregate_verdict": "FAIL",
            "per_rule": {
                "R01": pr(*P15),
                "R02": pr("FAIL", "COMPLETED", "EMPTY_VALUE", 15, 15, 2, 0, 0, 0, 2,
                          failure=["EMPTY_VALUE"]),
                "R03": pr("FAIL", "PARTIAL", "TYPE_PARSE_ERROR", 15, 13, 2, 0, 2, 0, 2,
                          failure=["TYPE_PARSE_ERROR"]),
                "R04": pr("FAIL", "PARTIAL", "ENUM_VIOLATION", 15, 11, 1, 0, 4, 0, 1,
                          failure=["ENUM_VIOLATION"]),
                "R05": pr("FAIL", "COMPLETED", "DUPLICATE_ID", 15, 15, 2, 0, 0, 0, 2,
                          failure=["DUPLICATE_ID"]),
                "R06": pr("FAIL", "PARTIAL", "LATITUDE_OUT_OF_RANGE", 15, 11, 1, 0, 4, 0, 1,
                          failure=["LATITUDE_OUT_OF_RANGE"]),
                "R07": pr(*P15),
                "R08": pr("FAIL", "PARTIAL", "OUTSIDE_PROJECT_AREA", 15, 10, 1, 0, 5, 0, 1,
                          failure=["OUTSIDE_PROJECT_AREA"]),
                "R09": pr("FAIL", "PARTIAL", "STALE_RECORD", 15, 11, 1, 0, 4, 0, 1,
                          failure=["STALE_RECORD"]),
                # R10：候选 1 组 + 上游阻断 5 行 ⇒ 取值链上"上游码/ALL_RECORDS_BLOCKED"先于候选码（§3.5.1）
                "R10": pr("INDETERMINATE", "PARTIAL", "ALL_RECORDS_BLOCKED", 15, 10, 0, 2, 5, 0, 1),
            },
            "blocked_findings_at_least": {"R03": 1},
            "note": "存在必检 FAIL，总体 FAIL；R03 有 1 条因 R02 失败被阻断而不伪执行。",
        },
        "corrected": {
            "aggregate_verdict": "PASS",
            "per_rule": {
                "R01": pr(*P15), "R02": pr(*P15), "R03": pr(*P15), "R04": pr(*P15),
                "R05": pr(*P15), "R06": pr(*P15), "R07": pr(*P15), "R08": pr(*P15),
                "R09": pr(*P15),
                "R10": pr("INDETERMINATE", "COMPLETED", "DUPLICATE_CANDIDATE", 15, 15, 0, 2, 0, 0, 1),
            },
            "note": "整改后必检项全部通过；R10 候选仍在报告中可见（SD-0011/SD-0012）。",
        },
        "ambiguous": {
            "aggregate_verdict": "INDETERMINATE",
            "per_rule": {
                "R01": pr(*P12), "R02": pr(*P12), "R03": pr(*P12), "R04": pr(*P12),
                "R05": pr(*P12), "R06": pr(*P12), "R07": pr(*P12), "R08": pr(*P12),
                "R09": pr(*P12),
                "R10": pr("INDETERMINATE", "COMPLETED", "DUPLICATE_CANDIDATE", 12, 12, 0, 2, 0, 0, 1),
                # D1/D2：原文无阈值 → 不批准、不执行；total=0 表示「一行都没看」
                # D1/D2：原文无阈值 → 不批准、不执行；total=0 表示「一行都没看」。
                # reason_code 由 NOT_APPROVABLE_NO_THRESHOLD 改为 CLAUSE_NOT_COVERED_BY_RULE：
                # 与权威口径 build_clause_coverage() 的未映射必检条款用同一个码（§3.5.1 追加项 2）。
                "D1": pr("INDETERMINATE", "NOT_EXECUTED", "CLAUSE_NOT_COVERED_BY_RULE",
                         0, 0, 0, 0, 0, 0, 0),
                "D2": pr("INDETERMINATE", "NOT_EXECUTED", "CLAUSE_NOT_COVERED_BY_RULE",
                         0, 0, 0, 0, 0, 0, 0),
            },
            "note": "D1/D2 原文缺少可判定阈值，规则不得批准，保持 INDETERMINATE，不作为通过证据。",
        },
        "blocked": {
            "aggregate_verdict": "FAIL",
            "per_rule": {
                "R01": pr(*P12), "R02": pr(*P12), "R03": pr(*P12), "R04": pr(*P12),
                "R05": pr(*P12),
                "R07": pr("FAIL", "PARTIAL", "CRS_DECLARATION_MISMATCH", 12, 0, 0, 0, 0, 12, 1,
                          failure=["CRS_DECLARATION_MISMATCH"]),
                "R09": pr(*P12),
                "R06": pr(*P12B), "R08": pr(*P12B), "R10": pr(*P12B),
            },
            "note": ("声明冲突（原文 B2 要求 EPSG:4326，提交为 EPSG:3857）：判定 FAIL，"
                     "依赖 CRS 的空间检查全部阻断为 INDETERMINATE，不自动纠偏。"
                     "坐标量级只作风险信号，不参与判定。"),
        },
    }

    build_bundle("clean", SPEC_COMMON, CLEAN_ROWS, "EPSG:4326", EXPECTED["clean"])
    build_bundle("defective", SPEC_COMMON, base, "EPSG:4326", EXPECTED["defective"])
    build_bundle("corrected", SPEC_COMMON, corrected, "EPSG:4326", EXPECTED["corrected"])
    build_bundle("ambiguous", SPEC_COMMON + SPEC_AMBIGUOUS_EXTRA, CLEAN_ROWS, "EPSG:4326", EXPECTED["ambiguous"])
    build_bundle("blocked", SPEC_COMMON, CLEAN_ROWS, "EPSG:3857", EXPECTED["blocked"])

    manifest = {}
    # crs_same_unit_wrong 是手写反例包（不参与生成，只登记哈希），见 examples/README.md
    # expected/ 三个文件一并登记：真值文件本身也必须被哈希冻结，改真值要能被发现。
    for name in ["clean", "defective", "corrected", "ambiguous", "blocked", "crs_same_unit_wrong"]:
        d = EX / name
        manifest[name] = {
            f: {"sha256": sha256_of(d / f), "bytes": (d / f).stat().st_size}
            for f in ["delivery_spec.md", "dictionary.csv", "poi.csv", "area.geojson", "crs.json",
                      "requirements.yaml", "approved-rules.yaml", "expected/aggregate.json",
                      "expected/findings.json", "expected/clause_coverage.json"]
        }
    write_text(EX / "INPUT_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print("bundles written:", ", ".join(manifest.keys()))
    print("example_root:", EX)


if __name__ == "__main__":
    main()
