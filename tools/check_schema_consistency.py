"""Schema 一致性校验（GA-09）：用 Python 标准库实现的 JSON Schema 子集校验器。

零第三方依赖要求（契约 §10.2）：Stage 0 不得引入 jsonschema，因此这里自己实现一个**明确声明的子集**。

本脚本的两条硬性纪律：
1. 支持范围之外的关键字必须**显式列出**（`UNSUPPORTED_KEYWORD`），并以非 0 退出；
   严禁静默跳过当作通过 —— 静默跳过会让"Schema 校验是绿的"变成假的。
2. 不参与校验的注解类关键字也要列出（`DECLARED_NON_VALIDATING`），
   明确区分"知道它但不校验"与"根本不认识它"。

用法：
    python tools/check_schema_consistency.py            # 全部检查
    python tools/check_schema_consistency.py --list     # 只打印关键字子集清单
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys

# 终端编码：中文输出在 GBK 终端/重定向下会抛 UnicodeEncodeError（证据链断在中途）。
# 统一把标准输出/错误固定为 UTF-8：等价于 README 建议的 `python -X utf8`，
# 且不依赖调用方是否设置 PYTHONUTF8 / PYTHONIOENCODING。
for _s in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
    if _s is not None and hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="strict")
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"
EX = ROOT / "examples"
WORK = ROOT / "work" / "stage0"

# ---------------------------------------------------------------- 关键字子集声明
# 参与校验的关键字：本脚本对它们的语义实现见 validate() 与各 _check_* 函数。
SUPPORTED_KEYWORDS = frozenset({
    "$ref",          # 仅支持同文件 "#/definitions/x" 与 schemas 目录内的相对文件路径
    "allOf", "anyOf", "oneOf", "not",
    "type", "enum", "const",
    "properties", "additionalProperties",   # 后者支持布尔与子 schema 两种形式
    "items", "minItems", "maxItems", "uniqueItems",
    "required", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern",
})

# 已知但不参与校验的关键字：不改变实例的合法性判定。显式登记，避免与"不认识"混淆。
DECLARED_NON_VALIDATING = frozenset({
    "$schema", "title", "description", "default", "examples", "deprecated",
    "definitions",       # 容器：内部 $ref 可引用，本身不约束实例
    "additionalItems",   # 元组型 items 的配套关键字，本项目不用；登记为已知但不实现
})

TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _equal(a, b):
    """实例与期望值是否相等；布尔与数字严格区分（JSON 中 true 不等于 1）。"""
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def walk_keywords(node, seen):
    """递归收集 schema 中出现的全部关键字（properties 下的字段名不算关键字）。"""
    if not isinstance(node, dict):
        return
    for key, val in node.items():
        seen.add(key)
        if key in ("properties", "definitions") and isinstance(val, dict):
            for sub in val.values():
                walk_keywords(sub, seen)
        elif key in ("items", "not", "additionalProperties") and isinstance(val, (dict, list)):
            for sub in (val if isinstance(val, list) else [val]):
                walk_keywords(sub, seen)
        elif key in ("allOf", "anyOf", "oneOf") and isinstance(val, list):
            for sub in val:
                walk_keywords(sub, seen)


# ---------------------------------------------------------------- 校验器
class SchemaValidator(object):
    """极小 JSON Schema 子集校验器；不支持的关键字由 walk_keywords() 单独拦，
    这里只负责已声明子集内的判定。"""

    def __init__(self, schema_dir):
        self.schema_dir = schema_dir
        self.cache = {}

    def load_schema(self, name):
        key = str(name)
        if key not in self.cache:
            with io.open(self.schema_dir / name, encoding="utf-8") as f:
                self.cache[key] = json.load(f)
        return self.cache[key]

    def resolve_ref(self, ref, current_name):
        """解析 $ref：支持 "#/definitions/x"（当前文件）与 "xxx.schema.json"（schemas 目录）。"""
        if "#" in ref:
            file_part, _, frag = ref.partition("#")
            target = file_part or current_name
            node = self.load_schema(target)
            for token in frag.strip("/").split("/"):
                if not token:
                    continue
                if not isinstance(node, dict) or token not in node:
                    raise ValueError("无法解析 $ref：%s（文件 %s）" % (ref, target))
                node = node[token]
            return node, target
        return self.load_schema(ref), ref

    def validate(self, instance, schema, path):
        """返回错误列表；空列表表示该实例通过。"""
        errors = []
        if isinstance(schema, bool):
            if not schema:
                errors.append("%s：被 false schema 拒绝" % path)
            return errors

        ref = schema.get("$ref")
        if ref is not None:
            try:
                resolved, target = self.resolve_ref(ref, self._current)
            except (ValueError, IOError, OSError) as exc:
                return ["%s：$ref 解析失败：%s" % (path, exc)]
            prev = self._current
            self._current = target
            errors.extend(self.validate(instance, resolved, path))
            self._current = prev
            return errors

        errors.extend(self._type(instance, schema, path))
        if "const" in schema and not _equal(instance, schema["const"]):
            errors.append("%s：必须等于 %r" % (path, schema["const"]))
        if "enum" in schema and not any(_equal(instance, cand) for cand in schema["enum"]):
            errors.append("%s：取值 %r 不在允许枚举 %r 内" % (path, instance, schema["enum"]))

        if isinstance(instance, dict):
            errors.extend(self._object(instance, schema, path))
        if isinstance(instance, list):
            errors.extend(self._array(instance, schema, path))
        if isinstance(instance, str):
            errors.extend(self._string(instance, schema, path))
        if isinstance(instance, (int, float)) and not isinstance(instance, bool):
            errors.extend(self._number(instance, schema, path))

        for i, sub in enumerate(schema.get("allOf") or []):
            errors.extend(self.validate(instance, sub, "%s/allOf[%d]" % (path, i)))
        if "not" in schema:
            if not self.validate(instance, schema["not"], path):
                errors.append("%s：命中了 not 禁止的形状" % path)
        any_of = schema.get("anyOf")
        if any_of is not None:
            if not any(not self.validate(instance, s, path) for s in any_of):
                errors.append("%s：不满足 anyOf 的任一分支" % path)
        one_of = schema.get("oneOf")
        if one_of is not None:
            hits = [s for s in one_of if not self.validate(instance, s, path)]
            if len(hits) != 1:
                errors.append("%s：命中 oneOf 分支数=%d，要求恰好 1" % (path, len(hits)))
        return errors

    def set_current(self, name):
        """记录当前正在使用的 schema 文件名，供 $ref 相对路径解析使用。"""
        self._current = name

    # --- 逐关键字判定
    def _type(self, instance, schema, path):
        want = schema.get("type")
        if want is None:
            return []
        options = want if isinstance(want, list) else [want]
        for opt in options:
            check = TYPE_CHECKS.get(opt)
            if check is not None and check(instance):
                return []
        return ["%s：类型应为 %r，实际为 %s" % (path, want, type(instance).__name__)]

    def _object(self, instance, schema, path):
        errors = []
        for key in schema.get("required") or []:
            if key not in instance:
                errors.append("%s：缺少必填字段 %s" % (path, key))
        props = schema.get("properties") or {}
        for key, sub in props.items():
            if key in instance:
                errors.extend(self.validate(instance[key], sub, "%s.%s" % (path, key)))
        extra = schema.get("additionalProperties")
        if extra is not None:
            for key in instance:
                if key in props:
                    continue
                if extra is True:
                    continue
                if extra is False:
                    errors.append("%s：出现未声明的字段 %s" % (path, key))
                else:
                    errors.extend(self.validate(instance[key], extra, "%s.%s" % (path, key)))
        return errors

    def _array(self, instance, schema, path):
        errors = []
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append("%s：至少需要 %d 项，实际 %d" % (path, schema["minItems"], len(instance)))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append("%s：最多允许 %d 项，实际 %d" % (path, schema["maxItems"], len(instance)))
        if schema.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in instance}) != len(instance):
            errors.append("%s：uniqueItems 要求各项互不相同" % path)
        items = schema.get("items")
        if isinstance(items, (dict, bool)):
            for i, item in enumerate(instance):
                errors.extend(self.validate(item, items, "%s[%d]" % (path, i)))
        return errors

    def _string(self, instance, schema, path):
        errors = []
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append("%s：长度需 >= %d，实际 %d" % (path, schema["minLength"], len(instance)))
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append("%s：长度需 <= %d，实际 %d" % (path, schema["maxLength"], len(instance)))
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, instance) is None:
            errors.append("%s：取值 %r 不匹配模式 %s" % (path, instance, pattern))
        return errors

    def _number(self, instance, schema, path):
        errors = []
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append("%s：需 >= %s，实际 %s" % (path, schema["minimum"], instance))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append("%s：需 <= %s，实际 %s" % (path, schema["maximum"], instance))
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append("%s：需 > %s，实际 %s" % (path, schema["exclusiveMinimum"], instance))
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            errors.append("%s：需 < %s，实际 %s" % (path, schema["exclusiveMaximum"], instance))
        return errors


def make_validator():
    v = SchemaValidator(SCHEMAS)
    v.set_current("")
    return v


# ---------------------------------------------------------------- 检查 1：关键字子集
def check_keyword_support():
    """扫描 schemas/*.json：任何未声明支持的关键字都显式列出并报错。"""
    problems = []
    used = set()
    for p in sorted(SCHEMAS.glob("*.json")):
        with io.open(p, encoding="utf-8") as f:
            doc = json.load(f)
        seen = set()
        walk_keywords(doc, seen)
        used |= seen
        bad = sorted(seen - SUPPORTED_KEYWORDS - DECLARED_NON_VALIDATING)
        if bad:
            problems.append("[UNSUPPORTED_KEYWORD] %s：%s —— 本校验器未实现这些关键字的语义，"
                            "必须补齐实现或从 Schema 中移除，不得静默跳过"
                            % (p.name, ", ".join(bad)))
    nonval = sorted(used & DECLARED_NON_VALIDATING)
    supported = sorted(used & SUPPORTED_KEYWORDS)
    print("支持（参与校验）的关键字 [%d]：%s" % (len(supported), ", ".join(supported)))
    print("已知但不参与校验的关键字 [%d]：%s" % (len(nonval), ", ".join(nonval)))
    print("子集外关键字：%s" % ("（无）" if not problems else "见下方 [UNSUPPORTED_KEYWORD]"))
    return problems


# ---------------------------------------------------------------- 检查 2：十类规则的参数约束
def _rule_fixture(rule_type, params):
    base = {
        "rule_id": "RX",
        "requirement_ids": ["A1"],
        "rule_type": rule_type,
        "status": "APPROVED",
        "version": 1,
        "parameters": params,
        "preconditions": [],
    }
    return base


# (规则类型, 合法参数, 必须缺键时报错的字段名)
RULE_FIXTURES = [
    ("required_field_present", {"fields": ["record_id"]}, "fields"),
    ("non_empty", {"fields": ["record_id"], "missing_rate_policy": "STRICT"}, "fields"),
    ("type_parse", {"fields": ["record_id"]}, "fields"),
    ("enum_value", {"field": "category", "allow_alias": False}, "field"),
    ("id_unique", {"field": "record_id"}, "field"),
    ("coord_range", {"lon_range": [-180, 180], "lat_range": [-90, 90]}, "lon_range"),
    ("crs_declaration", {"expected_crs": "EPSG:4326", "expected_from_sidecar": True}, "expected_crs"),
    ("within_project_area", {"boundary_policy": "inclusive"}, "boundary_policy"),
    ("freshness", {"reference_time": "2026-10-01T00:00:00Z", "max_age_days": 30}, "max_age_days"),
    ("duplicate_candidate", {"max_distance_m": 30, "name_equal": True}, "max_distance_m"),
]


def check_rule_parameter_constraints(v):
    """十类规则：缺参数必须被拦下；参数齐全的合法样例不得被误拦（GA-09）。"""
    problems = []
    for rule_type, params, missing_key in RULE_FIXTURES:
        ok = _rule_fixture(rule_type, params)
        errs = v.validate(ok, v.load_schema("rule.schema.json"), "rule")
        if errs:
            problems.append("[SCHEMA_FALSE_POSITIVE] %s 的合法样例被误拦：%s"
                            % (rule_type, errs[0]))
            continue
        bad = _rule_fixture(rule_type, {k: val for k, val in params.items() if k != missing_key})
        errs = v.validate(bad, v.load_schema("rule.schema.json"), "rule")
        if not errs:
            problems.append("[SCHEMA_GAP] %s 缺少 %s 却未被拦下" % (rule_type, missing_key))
    print("十类规则参数约束负例：%d 条，全部按预期被拦下 = %s"
          % (len(RULE_FIXTURES), not problems))
    return problems


# ---------------------------------------------------------------- 检查 3：示例包文档
def check_bundle_documents(v):
    problems = []
    bundles = sorted(p.parent.name for p in EX.glob("*/requirements.yaml"))
    for name in bundles:
        bdir = EX / name
        req_path, rule_path = bdir / "requirements.yaml", bdir / "approved-rules.yaml"
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            import stage0_gate as gate
            req_doc = gate.load_yaml(req_path)
            rule_doc = gate.load_yaml(rule_path)
        except Exception as exc:  # noqa: BLE001 —— 自检脚本需要把任何解析失败变成可见问题
            problems.append("[PARSE_ERROR] %s：%s" % (name, exc))
            continue

        v.set_current("requirement.schema.json")
        for i, item in enumerate(req_doc.get("requirements") or []):
            for err in v.validate(item, v.load_schema("requirement.schema.json"),
                                  "%s/requirements[%d]" % (name, i)):
                problems.append("[REQ_SCHEMA] %s" % err)

        v.set_current("rule.schema.json")
        for i, item in enumerate(rule_doc.get("rules") or []):
            for err in v.validate(item, v.load_schema("rule.schema.json"),
                                  "%s/rules[%d]" % (name, i)):
                problems.append("[RULE_SCHEMA] %s" % err)
            # preconditions 为 null 是 GA-09 点名的序列化缺陷，单独给出可读提示
            if item.get("preconditions") is None:
                problems.append("[NULL_PRECONDITIONS] %s/rules[%s]：无依赖必须写 []，不得为 null"
                                % (name, item.get("rule_id", i)))
            for j, src in enumerate(item.get("parameter_sources") or []):
                v.set_current("parameter_source.schema.json")
                for err in v.validate(src, v.load_schema("parameter_source.schema.json"),
                                      "%s/rules[%s].parameter_sources[%d]" % (name, item.get("rule_id", i), j)):
                    problems.append("[PARAM_SOURCE_SCHEMA] %s" % err)
    print("示例包文档校验：%d 个包" % len(bundles))
    return problems


# ---------------------------------------------------------------- 检查 4：登记表与 Schema 枚举的一致性
def check_registry_parity():
    """代码登记表与 Schema 枚举必须一一对应。

    只改一边（代码加了码、Schema 没加，或反之）都会被这里拦下 ——
    否则"Schema 校验是绿的"会变成假的。
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import stage0_gate as gate
    problems = []

    risk_schema = json.loads((SCHEMAS / "risk_signal.schema.json").read_text(encoding="utf-8"))
    want_risk = set(risk_schema["properties"]["code"]["enum"])
    got_risk = set(gate.RISK_SIGNAL_CODES)
    if want_risk != got_risk:
        problems.append("[REGISTRY_PARITY] risk_signal.schema.json 的 code 枚举与 RISK_SIGNAL_CODES "
                        "不一致：仅 Schema 有=%s；仅代码有=%s"
                        % (sorted(want_risk - got_risk), sorted(got_risk - want_risk)))

    finding_schema = json.loads((SCHEMAS / "finding.schema.json").read_text(encoding="utf-8"))
    want_reason = set(finding_schema["properties"]["reason_code"]["enum"])
    got_reason = set(gate.FINDING_REASON_CODES)
    if want_reason != got_reason:
        problems.append("[REGISTRY_PARITY] finding.schema.json 的 reason_code 枚举与 "
                        "FINDING_REASON_CODES 不一致：仅 Schema 有=%s；仅代码有=%s"
                        % (sorted(want_reason - got_reason), sorted(got_reason - want_reason)))

    unclassified = sorted(c for c in got_reason if gate.classify_reason_code(c) is None)
    if unclassified:
        problems.append("[REGISTRY_PARITY] 原因码未归入 FAIL/CANDIDATE/INDETERMINATE 三类之一：%s"
                        % unclassified)

    # 契约 §3.5.2 (4)：failure_reason_codes / advisory_reason_codes 的枚举必须与分类表一致
    cr_schema = json.loads((SCHEMAS / "check_result.schema.json").read_text(encoding="utf-8"))
    want_fail_codes = set(cr_schema["properties"]["failure_reason_codes"]["items"]["enum"])
    got_fail_codes = set(gate.FAIL_REASON_CODES) & set(gate.FINDING_REASON_CODES)
    if want_fail_codes != got_fail_codes:
        problems.append("[REGISTRY_PARITY] check_result.schema.json 的 failure_reason_codes 枚举与 "
                        "FAIL 类 ∩ FINDING_REASON_CODES 不一致：仅 Schema 有=%s；仅代码有=%s"
                        % (sorted(want_fail_codes - got_fail_codes),
                           sorted(got_fail_codes - want_fail_codes)))
    want_adv_codes = set(cr_schema["properties"]["advisory_reason_codes"]["items"]["enum"])
    got_adv_codes = set(gate.INDETERMINATE_REASON_CODES)
    if want_adv_codes != got_adv_codes:
        problems.append("[REGISTRY_PARITY] check_result.schema.json 的 advisory_reason_codes 枚举与 "
                        "INDETERMINATE_REASON_CODES 不一致：仅 Schema 有=%s；仅代码有=%s"
                        % (sorted(want_adv_codes - got_adv_codes),
                           sorted(got_adv_codes - want_adv_codes)))

    print("登记表一致性：原因码 %d（FAIL %d / CANDIDATE %d / INDETERMINATE %d；其中 finding 可用 %d、"
          "规则级专用 %d）、风险信号码 %d"
          % (len(gate.REASON_CODES), len(gate.FAIL_REASON_CODES),
             len(gate.CANDIDATE_REASON_CODES), len(gate.INDETERMINATE_REASON_CODES),
             len(got_reason), len(gate.RESULT_ONLY_REASON_CODES), len(got_risk)))
    return problems


# ---------------------------------------------------------------- 检查 5：已产出产物
def check_artifacts(v):
    problems = []
    if not WORK.exists():
        print("产物校验：work/stage0 不存在，跳过")
        return problems
    n = 0
    for report_path in sorted(WORK.glob("*/report.json")):
        n += 1
        report = json.loads(io.open(report_path, encoding="utf-8").read())
        v.set_current("check_result.schema.json")
        for i, item in enumerate(report.get("check_results") or []):
            for err in v.validate(item, v.load_schema("check_result.schema.json"),
                                  "%s/check_results[%d]" % (report_path.parent.name, i)):
                problems.append("[CHECK_RESULT_SCHEMA] %s" % err)
        v.set_current("finding.schema.json")
        for i, item in enumerate(report.get("findings") or []):
            for err in v.validate(item, v.load_schema("finding.schema.json"),
                                  "%s/findings[%d]" % (report_path.parent.name, i)):
                problems.append("[FINDING_SCHEMA] %s" % err)
    m = 0
    for manifest_path in sorted(WORK.glob("*/run_manifest.json")):
        m += 1
        v.set_current("run_manifest.schema.json")
        for err in v.validate(json.loads(io.open(manifest_path, encoding="utf-8").read()),
                              v.load_schema("run_manifest.schema.json"), manifest_path.parent.name):
            problems.append("[MANIFEST_SCHEMA] %s" % err)
    print("产物校验：report.json %d 个、run_manifest.json %d 个" % (n, m))
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="只打印支持的关键字子集清单")
    args = ap.parse_args()

    print("=" * 72)
    print("Schema 一致性校验（标准库子集实现，Stage 0 不引入 jsonschema）")
    print("=" * 72)
    print("支持（参与校验）的关键字全集 [%d]：%s"
          % (len(SUPPORTED_KEYWORDS), ", ".join(sorted(SUPPORTED_KEYWORDS))))
    print("已知但不参与校验 [%d]：%s"
          % (len(DECLARED_NON_VALIDATING), ", ".join(sorted(DECLARED_NON_VALIDATING))))
    print("")
    if args.list:
        return 0

    v = make_validator()
    problems = []
    problems += check_keyword_support()
    print("")
    problems += check_rule_parameter_constraints(v)
    print("")
    problems += check_bundle_documents(v)
    print("")
    problems += check_registry_parity()
    print("")
    problems += check_artifacts(v)

    print("")
    if problems:
        print("[FAIL] 发现 %d 处不一致：" % len(problems))
        for p in problems[:60]:
            print("   -", p)
        if len(problems) > 60:
            print("   ... 其余 %d 处省略" % (len(problems) - 60))
        print("SCHEMA_CONSISTENT=false")
        return 1
    print("[PASS] 全部一致性检查通过（子集范围内无不支持关键字被静默跳过）")
    print("SCHEMA_CONSISTENT=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
