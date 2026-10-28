"""Stage 0 门禁：一个完整实例从原文走到预期结果。

约束（对应方案文档第 3、5、8 节 + 重验契约 docs/stage0-recheck-contract.md）：
- 零第三方依赖：只用 Python 标准库，确保任何环境都能跑；Stage 1 再替换为 GeoPandas/Shapely 实现。
- 引用必须核验：条款的 source_quote 与实际行内容逐字比对，对不上即失败。
- 阈值必须有来源：参与判定的参数必须有 structured ParameterSource，且用 token 边界匹配核验。
- 依赖失败不伪执行：前置检查失败的整条记录标记为 BLOCKED，不给出假装通过的结论。
- 运行状态与业务结论分离；mode 固定为 manual（本阶段无模型调用，不得标 live）。

【能力边界（契约 §6.3，禁止删改，也不得声称已超越）】
参数来源护栏在 Stage 0 只做到「**字面可追溯**」，未做到「**语义正确可证**」：
- 能验证：文档哈希一致、引用行内容逐字一致、参数值在批准引用中的字面出现（token 级）、
  参数↔条款↔规则的绑定自洽、来源记录字段完整。
- 不能验证：「人工是否真的读过并认可」（只记录 reviewer）、interpretation 的解释是否正确、
  同一文档别处是否存在冲突表述、文档版本历史、参数变更是否真的走了重新批准流程。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import sys

# 终端编码：中文输出在 GBK 终端/重定向下会抛 UnicodeEncodeError（证据链断在中途）。
# 统一把标准输出/错误固定为 UTF-8：等价于 README 建议的 `python -X utf8`，
# 且不依赖调用方是否设置 PYTHONUTF8 / PYTHONIOENCODING。
for _s in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
    if _s is not None and hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="strict")
from pathlib import Path

if __package__:
    from .rule_scopes import validate_scopes,population
else:
    from rule_scopes import validate_scopes,population

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"
WORK = ROOT / "work" / "stage0"

SCHEMA_VERSION = "stage0-2"
TOOL_VERSION = "geoacceptance/0.6.0-rc1 (shapely/pyproj/PyYAML/pydantic; scoped freshness)"

# ---------------------------------------------------------------- 契约词汇表（契约 §1）
VERDICTS = ("PASS", "FAIL", "INDETERMINATE")

# Stage 0 会产出的运行状态
STAGE0_STATUSES = ("COMPLETED", "PARTIAL", "BLOCKED", "NOT_EXECUTED",
                   "NOT_IMPLEMENTED", "REJECTED", "FAILED")
# 全量词汇：QUEUED / RUNNING / CANCELLED 留给 Stage 3 异步任务，Stage 0 不产出
EXECUTION_STATUSES = STAGE0_STATUSES + ("QUEUED", "RUNNING", "CANCELLED")

# 组合合法性矩阵（契约 §1.3）。要点：PASS 只允许 COMPLETED；删除「FAIL + NOT_EXECUTED」合法格。
LEGAL_COMBOS = frozenset({
    ("PASS", "COMPLETED"),
    ("FAIL", "COMPLETED"),
    ("FAIL", "PARTIAL"),
    ("INDETERMINATE", "COMPLETED"),
    ("INDETERMINATE", "PARTIAL"),
    ("INDETERMINATE", "BLOCKED"),
    ("INDETERMINATE", "NOT_EXECUTED"),
    ("INDETERMINATE", "NOT_IMPLEMENTED"),
    ("INDETERMINATE", "REJECTED"),
    ("INDETERMINATE", "FAILED"),
})

# 条款覆盖状态机（契约 §3.2 / GA-01）
COVERAGE_STATES = ("UNMAPPED", "UNAPPROVED", "NO_IMPLEMENTATION", "CONFIG_REJECTED",
                   "MISSING_RESULT", "COVERED")
# 上游状态 → 下游不可执行的原因码（契约 §5.2 状态传播矩阵）
UPSTREAM_REASON = {
    "BLOCKED": "UPSTREAM_BLOCKED",
    "NOT_EXECUTED": "UPSTREAM_NOT_APPROVED",
    "NOT_IMPLEMENTED": "UPSTREAM_NOT_IMPLEMENTED",
    "REJECTED": "UPSTREAM_CONFIG_REJECTED",
    "FAILED": "UPSTREAM_FAILED",
}
# 允许下游正常执行的上游状态（契约 §5.2 不变式）
UPSTREAM_OK_STATUSES = ("COMPLETED", "PARTIAL")

# ---------------------------------------------------------------- 原因码三分类（强制归类）
# 契约红线：新增 reason_code 必须**显式声明**归属下列三类之一，未声明在登记期（模块导入）即报错。
# 三类的语义直接决定规则级结论的推导方式：
#   - FAIL 类：作为 finding 出现即把规则级结论推向 FAIL（默认类，也是绝大多数码的归属）；
#   - 候选类：只进 records_indeterminate，**不是失败**，也不向下游传播阻断（契约 §7.2）；
#   - 缺证据类：产生 finding 但结论是 INDETERMINATE，并按 §4.4 阻断下游（缺证据 ≠ 失败）。
# 三类必须**互斥**，且 REASON_CODES 恰为三者之并 —— 因此不可能出现"登记了但没分类"的码。
FAIL_REASON_CODES = frozenset({
    # 执行/配置类（多为规则级状态的原因码，不产生 finding；归本类表示"不属于另两类"）
    "OK", "RULE_NOT_APPROVED", "NO_IMPLEMENTATION", "ALL_RECORDS_BLOCKED",
    "NOT_APPROVABLE_NO_THRESHOLD", "CONFIG_REJECTED", "EXECUTION_EXCEPTION",
    "GEOMETRY_SHAPE_UNSUPPORTED", "CONTRACT_VIOLATION",
    # 条款级（GA-01）
    "CLAUSE_NOT_COVERED_BY_RULE", "RESULT_MISSING_FOR_CLAUSE",
    "UPSTREAM_CONFIG_REJECTED",
    # 依赖传播（GA-04）
    "UPSTREAM_BLOCKED", "UPSTREAM_NOT_APPROVED", "UPSTREAM_NOT_IMPLEMENTED",
    "UPSTREAM_FAILED",
    # 缺陷类（与 schemas/finding.schema.json 的枚举保持一致）
    "FIELD_COLUMN_MISSING", "FIELD_COUNT_MISMATCH", "EMPTY_VALUE", "EMPTY_ID",
    "TYPE_PARSE_ERROR", "NON_FINITE_NUMBER", "UNSUPPORTED_DATA_TYPE", "ENUM_VIOLATION",
    "DUPLICATE_ID", "LONGITUDE_OUT_OF_RANGE", "LATITUDE_OUT_OF_RANGE",
    # 注：量级驱动的 CRS_DECLARATION_CONFLICT（旧实现）已随 GA-03 一并删除，
    # 不再登记；CRS 只有 CRS_DECLARATION_MISMATCH 一条能判 FAIL。
    "CRS_DECLARATION_MISMATCH", "OUTSIDE_PROJECT_AREA",
    "STALE_RECORD", "FUTURE_TIMESTAMP",
})

# 候选类原因码：计入 records_indeterminate，不计失败、不传播阻断（契约 §7.2）
CANDIDATE_REASON_CODES = frozenset({"DUPLICATE_CANDIDATE"})
# 「缺证据」类原因码（CRS 的 C2/C1 前置；R09 时区未声明）：产生 finding 但**不是 FAIL**，
# 结论为 INDETERMINATE 且阻断下游（契约 §4.1 / §4.4）
# TIMEZONE_UNDECLARED：docs/rule-semantics.md R09 明确要求「按未定处理」，
# 与契约 §0 公理 A2（缺观测 ⇒ INDETERMINATE）一致；实现此前把它归入 FAIL 类属文档与实现不一致，
# 由主理人裁决归位到本类（2026-10-26）。
INDETERMINATE_REASON_CODES = frozenset({
    "CRS_MISSING_DECLARATION", "CRS_EXPECTED_NOT_APPROVED", "TIMEZONE_UNDECLARED",
})
# 原因码分类表：(类别名, 集合)。顺序即判定优先级无关的展示顺序。
REASON_CODE_CLASSES = (
    ("FAIL", FAIL_REASON_CODES),
    ("CANDIDATE", CANDIDATE_REASON_CODES),
    ("INDETERMINATE", INDETERMINATE_REASON_CODES),
)
# 全部允许的原因码 = 三类之并（不再单独维护字面量，避免出现"登记但未分类"的码）
REASON_CODES = FAIL_REASON_CODES | CANDIDATE_REASON_CODES | INDETERMINATE_REASON_CODES
# 只出现在 CheckResult.reason_code（规则级状态）、**不会**出现在 finding 里的码
RESULT_ONLY_REASON_CODES = frozenset({
    "OK", "RULE_NOT_APPROVED", "NO_IMPLEMENTATION", "ALL_RECORDS_BLOCKED",
    "NOT_APPROVABLE_NO_THRESHOLD", "CONFIG_REJECTED", "EXECUTION_EXCEPTION",
    "GEOMETRY_SHAPE_UNSUPPORTED", "CONTRACT_VIOLATION",
    "CLAUSE_NOT_COVERED_BY_RULE", "RESULT_MISSING_FOR_CLAUSE",
    "UPSTREAM_CONFIG_REJECTED", "UPSTREAM_BLOCKED", "UPSTREAM_NOT_APPROVED",
    "UPSTREAM_NOT_IMPLEMENTED", "UPSTREAM_FAILED",
})
# 允许出现在 finding 里的原因码 = 全表减去规则级专用码；
# 必须与 schemas/finding.schema.json 的 reason_code 枚举**完全一致**（check_schema_consistency 校验）
FINDING_REASON_CODES = frozenset(REASON_CODES - RESULT_ONLY_REASON_CODES)
# 风险信号中心注册表（契约 A3）：只有登记的码才能发出，且**永不参与 verdict**
RISK_SIGNAL_CODES = frozenset({
    "PARAMETER_VALUE_MAPPED_BY_INTERPRETATION",  # 参数靠人工解释映射到原文
    "IMPLICIT_REQUIRED_FOR_RELEASE",             # 规则未声明 required_for_release，按派生态执行
    "CRS_MAGNITUDE_RISK",                        # 坐标量级与声明单位不符（只提示，不判定）
})
RISK_SIGNAL_SEVERITIES = ("INFO", "WARN")

# ---------------------------------------------------------------- 参数溯源模型（契约 §6）
# 参与判定的参数：必须有且仅有一条 ParameterSource
SOURCE_REQUIRED_PARAMS = frozenset({
    "max_age_days", "max_distance_m", "lon_range", "lat_range", "expected_crs",
    "reference_time", "allowed_missing_rate", "boundary_policy",
})
# 结构性配置：不需要来源，但必须在 schemas/rule.schema.json 中列出允许取值
STRUCTURAL_PARAMS = frozenset({
    "fields", "field", "trim", "allow_alias", "name_equal",
    "expected_from_sidecar", "missing_rate_policy",
})
# 参数语义允许的单位；unit 非空时必须落在允许集合内（契约 §6.2 第 8 条）
PARAM_UNITS = {
    "max_age_days": ("day",),
    "max_distance_m": ("metre",),
    "lon_range": ("degree",),
    "lat_range": ("degree",),
}
# 结构性配置/列表类 YAML 键：空值时一律归一为 []，不得为 None（契约 T01 / GA-09）
SEQUENCE_KEYS = frozenset({
    "requirement_ids", "preconditions", "fields", "dependencies", "ambiguities",
    "parameter_sources", "value_literal", "lon_range", "lat_range", "third_party_dependencies",
})
# 来源自身校验不过的硬错误（这些情况下来源不能充当证据）
SOURCE_HARD_FAILURES = frozenset({
    "DOCUMENT_NOT_FOUND", "DOCUMENT_HASH_MISMATCH", "SOURCE_RANGE_OUT_OF_BOUNDS",
    "PARAMETER_QUOTE_MISMATCH", "PARAMETER_SOURCE_NOT_FOUND",
})
# 边界政策（契约 §8）：Stage 0 只实现 inclusive / exclusive 两种
BOUNDARY_POLICIES = ("inclusive", "exclusive")
# 缺失率政策（契约 §9.2）：Stage 0 只允许 STRICT
MISSING_RATE_POLICIES = ("STRICT",)

# 条款支持状态（契约 §2.4，RC-02）：枚举必须在**执行入口**校验，不能只靠单独跑 Schema 脚本。
# 只有 SUPPORTED 的条款才允许挂 APPROVED 规则并参与放行判定；其余状态
# （NEEDS_CLARIFICATION / UNSUPPORTED / 字段缺失 / 未知取值）一律按"条款尚未可判定"处理，
# 且**不允许**"旧状态 + 已批准规则 + 执行结果"三者并存 —— 重新确认支持必须显式改状态。
CLAUSE_SUPPORT_STATUSES = ("SUPPORTED", "NEEDS_CLARIFICATION", "UNSUPPORTED")
CLAUSE_EXECUTABLE_SUPPORT_STATUSES = ("SUPPORTED",)


# ---------------------------------------------------------------- token 精确匹配（GA-05 核心修复）
# 把引用文本切成 token 再做**全等比较**；严禁 str in quote 形式的子串包含。
# 顺序敏感：时间戳先于数值，避免 "2026-10-01T00:00:00Z" 被切成碎片。
TOKEN_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?"   # RFC3339 时间戳
    r"|[A-Za-z_][A-Za-z0-9_]*:[A-Za-z0-9_.:+/-]*"                                  # 带冒号标识：EPSG:4326
    r"|[-+]?\d+(?:\.\d+)?"                                                         # 数值（含符号）
    r"|[A-Za-z_][A-Za-z0-9_.+/-]*"                                                 # 普通标识符
    r"|[\u4e00-\u9fff]+"                                                           # CJK 连续串（标点之间的整段）
)


def tokenize(text):
    """把文本切成 token 序列；空白与标点、CJK 之外的边界符号均为分隔符。"""
    return TOKEN_RE.findall(text or "")


def literal_list(value_literal):
    """value_literal 允许单个字符串或字符串列表，统一成列表返回。"""
    if value_literal is None:
        return []
    if isinstance(value_literal, (list, tuple)):
        return [str(x) for x in value_literal]
    return [str(value_literal)]


def literal_in_quote(literal, quote):
    """token 边界匹配：字面量必须在引用中作为 token 出现（契约 §6.2 第 6 条）。

    "3" 不得命中 "30"（等价于契约给出的后置 lookahead 规则）；
    "-180" 与 "180" 互不冒充；"30" 不得命中 "30.0"；"EPSG:4326" 不得命中 "EPSG:43260"。
    """
    want = tokenize(str(literal))
    if not want:
        return False
    got = tokenize(quote)
    if len(want) == 1:
        return want[0] in got
    for i in range(len(got) - len(want) + 1):
        if got[i:i + len(want)] == want:
            return True
    return False


def normalize_crs(value):
    """CRS 规范比：去首尾空白 + 统一大小写。

    契约 §4.2 明确**不做**等价推断：WGS84 ↔ EPSG:4326、EPSG:4490 ↔ EPSG:4326 一律视为不同，
    Stage 0 也不配置 crs_alias_table。
    """
    return str(value or "").strip().lower()


def scalar_literal(value):
    """单个值的字面形式：整型浮点按整数写，其余按 str()；布尔与空值返回 None。"""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def value_literals(value):
    """参数值的字面形式列表；列表/元组按元素展开，布尔与空值返回 []。"""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            lit = scalar_literal(item)
            if lit is not None:
                out.append(lit)
        return out
    lit = scalar_literal(value)
    return [] if lit is None else [lit]


class ContractViolation(Exception):
    """契约不变式被违反（三态词汇 / 组合矩阵 / I1–I6）。出现即视为 P1 实现缺陷，不得静默修正。"""


class NotImplementedByStage(Exception):
    """Stage 0 未实现的能力（几何形状 / 政策）：必须落成 NOT_IMPLEMENTED，禁止降级为另一种方式。"""

    def __init__(self, reason_code, message):
        super(NotImplementedByStage, self).__init__(message)
        self.reason_code = reason_code


class RegistryError(RuntimeError):
    """登记表本身不一致（原因码未分类 / 风险信号码未登记）。**启动即报错**，不留到运行时。"""


def classify_reason_code(code):
    """返回原因码所属类别名；未归入任何一类时返回 None（调用方必须据此报错）。"""
    for name, codes in REASON_CODE_CLASSES:
        if code in codes:
            return name
    return None


def check_registries():
    """登记表自检：原因码三分类互斥完备、风险信号码不得混入原因码表。

    放在模块导入期执行（`check_registries()` 在文件末尾调用），因此"新增码忘了分类"
    是**启动即失败**，而不是运行到某条规则才 quietly 退回 FAIL。
    """
    problems = []

    # 1. 三类必须两两互斥
    names = [n for n, _ in REASON_CODE_CLASSES]
    for i in range(len(REASON_CODE_CLASSES)):
        for j in range(i + 1, len(REASON_CODE_CLASSES)):
            both = REASON_CODE_CLASSES[i][1] & REASON_CODE_CLASSES[j][1]
            if both:
                problems.append("原因码 %s 同时归入 %s 与 %s 两类（必须互斥）：%s"
                                % (sorted(both), names[i], names[j], sorted(both)))

    # 2. 并集必须等于 REASON_CODES：不允许出现"登记了但没分类"的码
    union = set()
    for _n, codes in REASON_CODE_CLASSES:
        union |= set(codes)
    if union != set(REASON_CODES):
        problems.append("REASON_CODES(%d) 与三类并集(%d) 不一致，存在未分类或重复分类的码：差集=%s"
                        % (len(REASON_CODES), len(union), sorted(set(REASON_CODES) ^ union)))

    # 3. 风险信号码不得混进原因码表（A3：信号永不参与判定）
    overlap = set(RISK_SIGNAL_CODES) & set(REASON_CODES)
    if overlap:
        problems.append("风险信号码不得出现在 REASON_CODES 中（契约 A3）：%s" % sorted(overlap))

    # 4. finding 可用码 = 全表 − 规则级专用码，两者必须恰好划分 REASON_CODES
    both = set(FINDING_REASON_CODES) & set(RESULT_ONLY_REASON_CODES)
    if both:
        problems.append("原因码同时出现在 finding 与规则级专用表（必须互斥）：%s" % sorted(both))
    if set(FINDING_REASON_CODES) | set(RESULT_ONLY_REASON_CODES) != set(REASON_CODES):
        problems.append("FINDING_REASON_CODES ∪ RESULT_ONLY_REASON_CODES != REASON_CODES；"
                        "差集=%s" % sorted(set(FINDING_REASON_CODES)
                                           ^ (set(REASON_CODES) - set(RESULT_ONLY_REASON_CODES))))

    if problems:
        raise RegistryError("登记表自检失败（%d 项）：\n  - %s"
                            % (len(problems), "\n  - ".join(problems)))
    return True


class WriteOnlyRiskLog(object):
    """判定推导期间的**只写**风险信号日志（契约 A3 的机器化保证）。

    run() 执行窗口内把 Kernel.risk_signals 换成此对象：允许 append，任何**读取**
    （len / 迭代 / 下标 / in / 真值测试）一律抛 ContractViolation。
    于是"读风险信号去定结论"在实现层写不出来 —— 写了就一定炸，不会静默生效。
    """

    __slots__ = ("_backing",)

    def __init__(self, backing):
        self._backing = backing

    def append(self, signal):
        self._backing.append(signal)

    def _denied(self, *args, **kwargs):
        raise ContractViolation(
            "风险信号在判定推导期间被读取：契约 A3 禁止 risk_signals 参与 verdict；"
            "只允许 add_risk_signal() 追加，不允许读取、统计或用于任何分支判断")

    __getitem__ = _denied
    __setitem__ = _denied
    __iter__ = _denied
    __len__ = _denied
    __contains__ = _denied
    __bool__ = _denied
    index = _denied
    count = _denied
    copy = _denied
    extend = _denied


def _unique_ordered(codes):
    """去重并保留首次出现顺序（契约 §3.5.2：原因码数组不是多重集，几处失败由统计字段承载）。"""
    out = []
    for c in codes:
        if c not in out:
            out.append(c)
    return out


def assert_reason_compat(verdict, reason):
    """I7–I9 运行时断言（契约 §3.5.1）：OK 只在 PASS 时合法；FAIL/INDETERMINATE 必须带可追溯原因码。

    规则级（assert_contract）与条款级（build_clause_coverage）共用；违反即 ContractViolation，
    由调用方按"失败关闭"登记 FAILED，绝不静默改值。
    """
    if verdict == "PASS" and reason != "OK":
        raise ContractViolation("I7 违反：PASS 的 reason_code 必须是 OK，实际=%r" % reason)
    if verdict == "FAIL":
        if reason == "OK":
            raise ContractViolation("I8 违反：FAIL 不得携带 OK（§3.5.1：须为第一条 FAIL 类 finding 的码）")
        if classify_reason_code(reason) != "FAIL":
            raise ContractViolation("I8 违反：FAIL 的 reason_code 必须是 FAIL 类码，实际=%r（%s 类）"
                                    % (reason, classify_reason_code(reason)))
    if verdict == "INDETERMINATE":
        if reason == "OK":
            raise ContractViolation("I9 违反：INDETERMINATE 不得携带 OK"
                                    "（§3.5.1：须为覆盖态/缺证据/上游/候选类码之一）")
        cls = classify_reason_code(reason)
        if cls == "FAIL" and reason not in RESULT_ONLY_REASON_CODES:
            raise ContractViolation("I9 违反：INDETERMINATE 的 reason_code 不得是可判失败的码，实际=%r"
                                    % reason)


def _truthy_number(value):
    """是否为一个非零数值；allowed_missing_rate 只有 > 0 时才需要批准来源。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value > 0


def _same_value(a, b):
    """两个参数值是否等价。数字允许 int/float 混写，其余要求严格相等。"""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same_value(x, y) for x, y in zip(a, b))
    return a == b


def _numericish(value):
    """值是否为数值（或数值列表）。数值必须与其字面量严格等价；非数值允许"证据短语"式来源。"""
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, (list, tuple)):
        return any(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value)
    return False


# ---------------------------------------------------------------- YAML 读取（Stage 1：PyYAML）
# Stage 0 的自研极简解析器（不支持锚点/多行/深层嵌套）已删除，改用 PyYAML 的 safe_load。
# 替换前的对拍证据：examples 下 12 个 YAML 逐文件与旧解析器输出**完全一致**
# （见 tools/verify_env.py 第 5 节与 acceptance/stage-1/env-verify.txt）。
try:
    import yaml as _yaml
except ImportError as _exc:  # pragma: no cover
    raise SystemExit(
        "缺少 PyYAML：Stage 1 起配置读取依赖 PyYAML。请在项目虚拟环境内执行：\n"
        "  python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements.txt\n"
        "（原始错误：%s）" % _exc)


def _normalize_sequences(node):
    """空值归一（GA-09）：已知序列类键必须得到 []，不得为 None（`preconditions: ` 这类写法）。

    这不是"解析"，只是把 YAML 的 None 收敛成空列表，避免下游 `or []` 到处兜底。
    """
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            out[k] = [] if (k in SEQUENCE_KEYS and v is None) else _normalize_sequences(v)
        return out
    if isinstance(node, list):
        return [_normalize_sequences(v) for v in node]
    return node


def load_yaml(path: Path):
    """PyYAML 解析（safe_load，禁止任意对象构造）。返回 dict / list / 标量。"""
    text = Path(path).read_text(encoding="utf-8")
    data = _yaml.safe_load(text)
    return _normalize_sequences(data) if data is not None else {}


# ---------------------------------------------------------------- 输入读取
def sha256_file(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_spec_lines(p: Path):
    return Path(p).read_text(encoding="utf-8").split("\n")


def read_csv_rows(p: Path):
    text = Path(p).read_text(encoding="utf-8")
    reader = csv.reader(io.StringIO(text))
    rows = []
    header = None
    for lineno, row in enumerate(reader, start=1):
        if header is None:
            header = row
            continue
        rows.append((lineno, row))
    return header, rows


def read_dictionary(p: Path):
    header, rows = read_csv_rows(p)
    d = {}
    for lineno, row in rows:
        rec = dict(zip(header, row))
        enum_raw = (rec.get("enum_values") or "").strip()
        enums = []
        if enum_raw.startswith("["):
            enums = [x.strip().strip('"') for x in enum_raw[1:-1].split(",") if x.strip()]
        d[rec["field_name"]] = {
            "description": rec.get("description", ""),
            "data_type": rec.get("data_type", ""),
            "required": str(rec.get("required", "")).lower() == "true",
            "enum_values": enums,
            "source_line": lineno,
        }
    return d


# ---------------------------------------------------------------- 几何（Stage 1：Shapely + pyproj）
# Stage 0 用自研射线法 + 1e-12 绝对容差 + haversine 球近似；
# Stage 1 起改为专业库，**判定口径必须与契约 §8.1 一致**，差异依据见
# acceptance/stage-1/GEOMETRY_REPLACE.md 与 `tools/compare_snapshots.py` 的逐项比对。
try:
    from shapely.geometry import Point as _ShapelyPoint, Polygon as _ShapelyPolygon
except ImportError as _exc:  # pragma: no cover —— 依赖缺失必须在启动时显式失败
    raise SystemExit(
        "缺少 Shapely：Stage 1 起几何判定依赖专业库。请在项目虚拟环境内执行：\n"
        "  python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements.txt\n"
        "（原始错误：%s）" % _exc)

try:
    from pyproj import Geod as _Geod
except ImportError as _exc:  # pragma: no cover
    raise SystemExit(
        "缺少 pyproj：Stage 1 起距离计算依赖 WGS84 测地线。请在项目虚拟环境内执行：\n"
        "  python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements.txt\n"
        "（原始错误：%s）" % _exc)

# WGS84 椭球测地距离（替代 R=6371008.8 的球近似）
_GEOD = _Geod(ellps="WGS84")
# 保留旧常量名仅作文档用途：Shapely 用**精确谓词**，不再按绝对容差判定边界
BOUNDARY_TOL = 1e-12


def geodesic_m(lon1, lat1, lon2, lat2):
    """WGS84 椭球测地距离（米），替代 Stage 0 的 haversine 球近似。

    依据：pyproj 的 Geod.inv 用 Karney 算法求解椭球大地线；
    球近似（R=6371008.8）在 100 km 量级上有 1e-3 ~ 1e-2 的相对偏差。
    """
    try:
        _az12, _az21, dist = _GEOD.inv(float(lon1), float(lat1), float(lon2), float(lat2))
    except ValueError:
        # 重合点/无效坐标：pyproj 抛 ValueError；按"拿不到结论"处理，返回 0 交给规则级判定
        return 0.0
    return abs(float(dist))


def _ring_polygon(ring):
    """环 → Shapely Polygon（自动闭合，兼容已闭合/未闭合两种输入）。"""
    return _ShapelyPolygon([(float(x), float(y)) for x, y in ring])


def point_in_ring(lon, lat, ring):
    """严格内部（不含边界）：Shapely `Polygon.contains`。"""
    poly = _ring_polygon(ring)
    if not poly.is_valid:
        # 无效几何（自交/退化）：不得猜一个答案，按"不可判定"处理由调用方登记
        raise ValueError("项目范围多边形无效（is_valid=False），无法给出边界判定")
    return bool(poly.contains(_ShapelyPoint(float(lon), float(lat))))


def point_on_ring_boundary(lon, lat, ring, tol=BOUNDARY_TOL):
    """点是否落在边界上：Shapely `boundary.touches`（精确谓词，不再用绝对容差）。

    实现口径：**边界 = 闭包内 ∧ 内部外**（`covers(p) and not contains(p)`）。
    不直接用 `boundary.touches(p)`：Shapely 的 `touches` 要求"公共点只落在两者边界上"，
    落在**线段内部**的点会被判 False（实测四边中点/顶点全部为 False），与契约 §8.1 不符。

    `tol` 参数保留仅为兼容旧调用签名，**不参与判定**（旧实现会把距边 1e-12 度内的
    点都算作边界，包含真正落在多边形外的点 —— 这是本轮替换要修掉的语义偏差）。
    """
    poly = _ring_polygon(ring)
    if not poly.is_valid:
        raise ValueError("项目范围多边形无效（is_valid=False），无法给出边界判定")
    p = _ShapelyPoint(float(lon), float(lat))
    return bool(poly.covers(p) and not poly.contains(p))


def point_in_ring_or_boundary(lon, lat, ring, inclusive=True):
    """按边界政策判定（契约 §8.1）：inclusive ⇔ `covers`，exclusive ⇔ `contains`。

    Shapely 语义：contains = 严格内部（不含边界）；covers = 内部 ∪ 边界。
    四点对称，不依赖射线法的方向偏好（GA-08 的不对称问题在专业库里不存在）。
    """
    poly = _ring_polygon(ring)
    if not poly.is_valid:
        raise ValueError("项目范围多边形无效（is_valid=False），无法给出边界判定")
    p = _ShapelyPoint(float(lon), float(lat))
    return bool(poly.covers(p) if inclusive else poly.contains(p))


# ---------------------------------------------------------------- 类型解析
ISO8601 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$")


def parse_value(v: str, data_type: str):
    if data_type == "number":
        try:
            f = float(v)
        except ValueError:
            return None, "TYPE_PARSE_ERROR"
        if math.isnan(f) or math.isinf(f):
            return None, "NON_FINITE_NUMBER"
        return f, None
    if data_type == "integer":
        try:
            return int(v), None
        except ValueError:
            return None, "TYPE_PARSE_ERROR"
    if data_type == "datetime":
        s = v.strip()
        # 严格要求带 T 分隔符与时区的 ISO8601；不接受 "2026-09-22 09:30" 这类宽松写法
        if not ISO8601.match(s):
            return None, "TYPE_PARSE_ERROR"
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return dt.datetime.fromisoformat(s), None
        except ValueError:
            return None, "TYPE_PARSE_ERROR"
    if data_type == "string":
        return v, None
    return None, "UNSUPPORTED_DATA_TYPE"


# ---------------------------------------------------------------- 内核
class Kernel:
    def __init__(self, bundle: Path):
        self.dir = bundle
        self.errors = []
        self.spec_lines = read_spec_lines(bundle / "delivery_spec.md")
        self.req_doc = load_yaml(bundle / "requirements.yaml")
        self.rule_doc = load_yaml(bundle / "approved-rules.yaml")
        self.dict = read_dictionary(bundle / "dictionary.csv")
        self.header, self.rows = read_csv_rows(bundle / "poi.csv")
        self.area = json.loads((bundle / "area.geojson").read_text(encoding="utf-8"))
        self.crs = json.loads((bundle / "crs.json").read_text(encoding="utf-8"))
        self.ref_time = self.req_doc.get("reference_time")
        self.finding_seq = 0
        self.blocked_map = {}  # rule_id -> 被阻断的记录行号集合
        self.risk_signals = []  # 风险信号（A3）：不参与 verdict，也不产生阻断性 finding
        self.config_rejections = []  # [{"code","target","detail"}]，非空即拒绝执行（契约 §9.1）
        self._rejections_collected = False
        self._ps_rejections = []
        self.status_by_rule = {}  # rule_id -> execution_status，供依赖状态传播使用（契约 §5.2）

    # ---- 校验：引用冻结与文档哈希（契约 §6.2 第 1–3 条）
    def verify_quote_texts(self):
        """条款引用逐字一致：source_line_start..source_line_end 覆盖范围内拼出的文本必须等于 source_quote。"""
        problems = []
        for req in self.req_doc["requirements"]:
            start = req["source_line_start"]
            end = req.get("source_line_end") or start
            if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
                problems.append("%s 引用的行号范围非法: %s-%s" % (req.get("requirement_id"), start, end))
                continue
            if end > len(self.spec_lines):
                problems.append("%s 引用行号越界: %s" % (req["requirement_id"], end))
                continue
            actual = "\n".join(self.spec_lines[start - 1:end])
            if actual != req["source_quote"]:
                span = str(start) if start == end else "%d-%d" % (start, end)
                problems.append(
                    "%s 引用内容与第 %s 行不一致\n  期望: %s\n  实际: %s"
                    % (req["requirement_id"], span, req["source_quote"], actual))
        return problems

    def verify_document_hashes(self):
        """来源文档哈希必须等于 sha256(包内实际文件)（修 GA-05 的"哈希改成全 0 仍通过"）。"""
        problems = []
        cache = {}
        for req in self.req_doc["requirements"]:
            doc = req.get("document_id")
            path = (self.dir / str(doc)) if doc else None
            if not doc or path is None or not path.exists():
                problems.append("[DOCUMENT_NOT_FOUND] %s 的来源文档 %s 不存在"
                                % (req.get("requirement_id"), doc))
                continue
            if doc not in cache:
                cache[doc] = sha256_file(path)
            declared = str(req.get("document_sha256") or "")
            if declared != cache[doc]:
                problems.append(
                    "[DOCUMENT_HASH_MISMATCH] %s 声明的文档哈希与实际不一致\n  声明: %s\n  实际: %s（%s）"
                    % (req.get("requirement_id"), declared, cache[doc], doc))
        return problems

    def verify_quotes(self):
        """引用逐字一致 + 来源文档哈希。哈希部分也可单独调用 verify_document_hashes()。"""
        return self.verify_quote_texts() + self.verify_document_hashes()

    # ---- 校验：结构化参数来源（契约 §6.2）
    def verify_parameter_sources(self):
        """逐条校验 ParameterSource，返回可读问题列表；结构化版本见 parameter_source_rejections()。"""
        return ["[%s] %s：%s" % (code, target, detail)
                for code, target, detail in self.parameter_source_rejections()]

    def verify_threshold_sources(self):
        """旧接口，仅为兼容外部探针与既有调用点保留；语义等价于 verify_parameter_sources()。

        保留原因：QA 的独立探针 stage0_independent_probes.py 直接调用本名字。
        Stage 1 起删除，调用方一律改用 verify_parameter_sources()。
        """
        return self.verify_parameter_sources()

    def parameter_source_rejections(self):
        """返回 [(code, target, detail)]：任一非空即表示该包的参数链不可信，必须拒绝执行。"""
        if not self._rejections_collected:
            self.collect_config_rejections()
        return self._ps_rejections

    def _parameter_source_scan(self):
        """实际扫描实现；由 collect_config_rejections() 调用，保证每轮只跑一次。"""
        out = []
        req_by_id = {r["requirement_id"]: r for r in self.req_doc["requirements"]}
        for rule in self.rule_doc["rules"]:
            rid = rule.get("rule_id")
            params = rule.get("parameters") or {}
            by_param = {}
            for idx, src in enumerate(rule.get("parameter_sources") or []):
                name = src.get("parameter") if isinstance(src, dict) else None
                if not name:
                    out.append(("PARAMETER_SOURCE_MALFORMED", str(rid),
                                "第 %d 条来源记录缺少 parameter 字段" % idx))
                    continue
                if name in by_param:
                    out.append(("DUPLICATE_PARAMETER_SOURCE", str(rid),
                                "参数 %s 存在多条来源记录（契约要求有且仅有一条）" % name))
                if name not in params:
                    out.append(("PARAMETER_SOURCE_UNKNOWN_PARAMETER", str(rid),
                                "来源记录指向的参数 %s 不在 parameters 中" % name))
                by_param[name] = src
            for pname in sorted(params):
                if pname in STRUCTURAL_PARAMS:
                    continue
                if pname not in SOURCE_REQUIRED_PARAMS:
                    out.append(("PARAMETER_SOURCE_UNCLASSIFIED", str(rid),
                                "参数 %s 既不在「必须溯源」清单也不在「结构性配置」清单中；"
                                "必须显式归类，禁止当作无关参数放过" % pname))
                    continue
                # allowed_missing_rate 为 0 时不参与判定，无需来源；未批准规则不登记拒绝
                if pname == "allowed_missing_rate" and not _truthy_number(params.get(pname)):
                    continue
                if rule.get("status") != "APPROVED":
                    continue
                src = by_param.get(pname)
                if src is None:
                    out.append(("THRESHOLD_WITHOUT_SOURCE", str(rid),
                                "判定参数 %s 没有 ParameterSource，不得参与判定" % pname))
                    continue
                out.extend(self._check_parameter_source(rule, pname, params.get(pname), src, req_by_id))
        return out

    def _check_parameter_source(self, rule, pname, pvalue, src, req_by_id):
        """单条 ParameterSource 的 8 项校验（契约 §6.2）。失败即登记，绝不以默认值放行。"""
        out = []
        rid = str(rule.get("rule_id"))
        quote = str(src.get("source_quote") or "")

        # 2. 文档存在性 → 1. 文档哈希 → 3. 引用逐字一致（完整范围覆盖）
        doc = src.get("document_id")
        path = (self.dir / str(doc)) if doc else None
        if not doc or path is None or not path.exists():
            out.append(("DOCUMENT_NOT_FOUND", rid,
                        "参数 %s 的来源文档 %s 不存在" % (pname, doc)))
        else:
            actual_hash = sha256_file(path)
            declared_hash = str(src.get("document_sha256") or "")
            if declared_hash != actual_hash:
                out.append(("DOCUMENT_HASH_MISMATCH", rid,
                            "参数 %s 声明的文档哈希与实际不一致\n    声明: %s\n    实际: %s（%s）"
                            % (pname, declared_hash, actual_hash, doc)))
            start, end = src.get("source_line_start"), src.get("source_line_end")
            lines = read_spec_lines(path)
            if not isinstance(start, int) or not isinstance(end, int) \
                    or start < 1 or end < start or end > len(lines):
                out.append(("SOURCE_RANGE_OUT_OF_BOUNDS", rid,
                            "参数 %s 的引用行号范围非法或越界: %s-%s" % (pname, start, end)))
            elif "\n".join(lines[start - 1:end]) != quote:
                out.append(("PARAMETER_QUOTE_MISMATCH", rid,
                            "参数 %s 的来源引用与第 %s 行内容不一致" % (pname, start)))

        # 4. 参数↔条款绑定
        srid = src.get("requirement_id")
        if srid not in req_by_id:
            out.append(("PARAMETER_SOURCE_UNKNOWN_REQUIREMENT", rid,
                        "参数 %s 的来源条款 %s 不存在" % (pname, srid)))
        elif srid not in (rule.get("requirement_ids") or []):
            out.append(("PARAMETER_SOURCE_REQUIREMENT_UNBOUND", rid,
                        "参数 %s 的来源条款 %s 不在本规则的 requirement_ids 中" % (pname, srid)))

        # 5. 值一致（两种：规则实际值 vs 来源记录值；来源记录值 vs 声明的字面量）
        src_value = src.get("value")
        if not _same_value(pvalue, src_value):
            out.append(("PARAMETER_VALUE_MISMATCH", rid,
                        "参数 %s 的实际值 %r 与其批准来源记录的值 %r 不一致"
                        % (pname, pvalue, src_value)))
        declared_literals = literal_list(src.get("value_literal"))
        expected_literals = value_literals(src_value)
        if declared_literals != expected_literals:
            if _numericish(src_value):
                # 数值：{"30"} 必须等于 value 的字面形式（契约 §6.2 第 5 条）
                out.append(("PARAMETER_VALUE_LITERAL_MISMATCH", rid,
                            "参数 %s 的来源记录中 value=%r 与 value_literal=%r 不对应"
                            % (pname, src_value, declared_literals)))
            else:
                # 非数值（policy 名 / CRS 代码）无法从中文原文中取到自身字面量，
                # 允许以「证据短语」作字面来源，但必须显式记 "人工解释"，且只按风险信号登记。
                # 这正是 §6.3 的能力边界：机器只校验字面存在，不校验解释是否正确。
                self.add_risk_signal(
                    "PARAMETER_VALUE_MAPPED_BY_INTERPRETATION", "INFO",
                    "参数 %s 的取值 %r 与引用中的字面量 %r 不相同，依赖人工批准的解释做映射"
                    % (pname, src_value, declared_literals),
                    {"rule_id": rid, "parameter": pname,
                     "requirement_id": srid, "value_literal": declared_literals})

        # 5c. 直接溯源：数值型参数的实际值本身也必须在批准引用中按 token 出现
        if _numericish(pvalue):
            for lit in value_literals(pvalue):
                if not literal_in_quote(lit, quote):
                    out.append(("PARAMETER_SOURCE_NOT_FOUND", rid,
                                "参数 %s 取值 %s 在 %s 的批准引用中找不到来源"
                                "（token 边界匹配，禁止子串包含）" % (pname, lit, srid)))

        # 6. token 精确匹配（禁止子串包含）
        for lit in declared_literals:
            if not lit:
                out.append(("PARAMETER_SOURCE_INCOMPLETE", rid,
                            "参数 %s 的 value_literal 为空" % pname))
                continue
            if not literal_in_quote(lit, quote):
                out.append(("PARAMETER_SOURCE_NOT_FOUND", rid,
                            "参数 %s 的字面量 \"%s\" 在批准引用中找不到来源"
                            "（token 边界匹配，禁止子串包含）" % (pname, lit)))

        # 7. 解释记录完整性
        for field in ("interpretation", "reviewer", "approved_at"):
            if not str(src.get(field) or "").strip():
                out.append(("PARAMETER_SOURCE_INCOMPLETE", rid,
                            "参数 %s 的来源记录缺 %s" % (pname, field)))

        # 8. 单位相容性
        unit = src.get("unit")
        allowed_units = PARAM_UNITS.get(pname)
        if unit not in (None, "") and allowed_units is not None and unit not in allowed_units:
            out.append(("PARAMETER_UNIT_INCOMPATIBLE", rid,
                        "参数 %s 的单位 %s 与语义不符，允许值：%s"
                        % (pname, unit, "/".join(allowed_units))))
        return out

    # ---- 执行前配置校验（契约 §9.1：非空即拒绝执行）
    def reject_input_schema(self):
        """契约 §2.4（Stage 1）：**执行入口**用 Pydantic(strict) 校验输入结构。

        不再只靠单独跑 Schema 脚本：这里是唯一"实际要执行"的地方，
        类型/取值不合规一律登记 `INPUT_SCHEMA_INVALID`，整包拒绝执行。
        """
        out = []
        try:
            if __package__:
                from .input_models import validate_inputs
            else:
                from input_models import validate_inputs
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("缺少 input_models/pydantic：请安装 requirements.txt（%s）" % exc)
        for target, detail in validate_inputs(self.req_doc, self.rule_doc):
            out.append({"code": "INPUT_SCHEMA_INVALID", "target": target, "detail": detail})
        return out

    def collect_config_rejections(self):
        """汇总全部拒绝项（幂等）。输入结构 + 引用完整性 + 授权派生 + 依赖图 + 政策未实现 + 参数来源。"""
        if self._rejections_collected:
            return self.config_rejections
        out = []
        out.extend(self.reject_input_schema())
        out.extend(validate_scopes(self.rule_doc['rules'], self.req_doc['requirements'], self.header, self.dict))
        out.extend(self.reject_missing_rate_policy())
        out.extend(self.reject_boundary_policy())
        ps = self._parameter_source_scan()
        self._ps_rejections = ps
        out.extend([{"code": c, "target": t, "detail": d} for c, t, d in ps])
        out.extend(self.reject_reference_integrity())
        out.extend(self.reject_authority_conflicts())
        out.extend(self.reject_dependency_graph())
        self.config_rejections = out
        self._rejections_collected = True
        return self.config_rejections

    # ---- 引用完整性（契约 §2.4）
    def reject_reference_integrity(self):
        out = []
        seen_rule, seen_req = {}, {}
        req_ids = {r["requirement_id"] for r in self.req_doc["requirements"]}
        for req in self.req_doc["requirements"]:
            rid = req.get("requirement_id")
            if rid in seen_req:
                out.append({"code": "DUPLICATE_REQUIREMENT_ID", "target": str(rid),
                            "detail": "条款 ID 重复，无法确定覆盖关系"})
            seen_req[rid] = True
            # RC-02：support_status 的枚举校验属于**执行入口**责任。缺失或未知取值
            # 与 UNSUPPORTED 同害（都无法证明该条款可判定），不得静默当作可判定。
            status = req.get("support_status")
            if status not in CLAUSE_SUPPORT_STATUSES:
                out.append({"code": "CLAUSE_SUPPORT_STATUS_UNKNOWN", "target": str(rid),
                            "detail": "support_status=%r 不在 %s 内（缺失/未知取值一律按未支持处理，"
                                      "不得默认可判定）" % (status, "/".join(CLAUSE_SUPPORT_STATUSES))})
        for rule in self.rule_doc["rules"]:
            rid = str(rule.get("rule_id"))
            if rid in seen_rule:
                out.append({"code": "DUPLICATE_RULE_ID", "target": rid,
                            "detail": "规则 ID 重复，依赖图无法确定唯一的执行者"})
            seen_rule[rid] = True
            refs = rule.get("requirement_ids") or []
            if not refs:
                out.append({"code": "RULE_WITHOUT_REQUIREMENT", "target": rid,
                            "detail": "规则没有覆盖任何条款，不得参与放行判定"})
            for cid in refs:
                if cid not in req_ids:
                    out.append({"code": "RULE_REFERENCES_UNKNOWN_REQUIREMENT", "target": rid,
                                "detail": "引用的条款 %s 不存在（孤立规则）" % cid})
            # RC-02：只要规则是 APPROVED，它覆盖的条款就必须是 SUPPORTED。
            # 原实现只查 NEEDS_CLARIFICATION 且只在规则声明必检时查，
            # 于是 UNSUPPORTED / 状态缺失 / 未知取值 都能与"已批准 + 已执行"并存并整体放行。
            # 是否与必检无关：非必检规则一旦产出结果，同样会进入覆盖口径影响结论。
            if rule.get("status") == "APPROVED":
                for cid in refs:
                    req = self.requirement_by_id(cid)
                    if req is None:
                        continue  # 孤立规则已在上面登记，不重复报
                    if req.get("support_status") not in CLAUSE_EXECUTABLE_SUPPORT_STATUSES:
                        out.append({"code": "APPROVED_RULE_FOR_UNSUPPORTED_CLAUSE", "target": rid,
                                    "detail": "条款 %s 的 support_status=%r 不是 SUPPORTED，"
                                              "其规则不得是 APPROVED；若已重新确认支持，"
                                              "必须显式更新条款状态与批准记录，"
                                              "不允许旧状态与执行结果并存"
                                              % (cid, req.get("support_status"))})
        return out

    def requirement_by_id(self, requirement_id):
        for req in self.req_doc["requirements"]:
            if req.get("requirement_id") == requirement_id:
                return req
        return None

    # ---- 授权派生（契约 §2.2 / §2.3，GA-02）
    def derived_required_for_release(self, rule):
        """derived = OR over 覆盖条款的 required_for_release；权威值在条款上。"""
        return any(bool(self.requirement_by_id(cid) and
                        self.requirement_by_id(cid).get("required_for_release"))
                   for cid in (rule.get("requirement_ids") or []))

    def reject_authority_conflicts(self):
        """规则单方面改写条款的必检级别 = 越权，一律拒绝执行（不得强跑后判 FAIL）。"""
        out = []
        for rule in self.rule_doc["rules"]:
            rid = str(rule.get("rule_id"))
            declared = rule.get("required_for_release")
            if declared is None:
                # 未提供声明：按 derived 处理，但必须留痕（契约 §2.3）
                self.add_risk_signal(
                    "IMPLICIT_REQUIRED_FOR_RELEASE", "INFO",
                    "规则 %s 未声明 required_for_release，本轮按条款派生态执行" % rid,
                    {"rule_id": rid})
                continue
            derived = self.derived_required_for_release(rule)
            if derived and not declared:
                out.append({"code": "CLAUSE_POLICY_DOWNGRADED_BY_RULE", "target": rid,
                            "detail": "覆盖条款为必检（derived=true），规则声明 false —— 越权降级，拒绝执行"})
            elif not derived and declared:
                out.append({"code": "CLAUSE_POLICY_UPGRADED_BY_RULE", "target": rid,
                            "detail": "覆盖条款非必检（derived=false），规则声明 true —— 越权升级，拒绝执行"})
        return out

    # ---- 依赖图（契约 §5.1，GA-04）
    def reject_dependency_graph(self):
        """未知依赖 / 有环 / 自依赖 / 重复前置 —— 一律拒绝，禁止"过滤掉不认识的依赖"。"""
        out = []
        ids = [str(r.get("rule_id")) for r in self.rule_doc["rules"]]
        id_set = set(ids)
        for rule in self.rule_doc["rules"]:
            rid = str(rule.get("rule_id"))
            pre = rule.get("preconditions") or []
            seen = set()
            for dep in pre:
                dep_str = str(dep)
                if dep_str not in id_set:
                    out.append({"code": "UNKNOWN_PRECONDITION", "target": rid,
                                "detail": "前置依赖 %s 不在规则集合内；证据链不完整，禁止当作无依赖" % dep_str})
                if dep_str in seen:
                    out.append({"code": "DUPLICATE_PRECONDITION", "target": rid,
                                "detail": "前置依赖 %s 重复声明" % dep_str})
                seen.add(dep_str)
        for rid in self._cycle_members():
            out.append({"code": "CYCLIC_DEPENDENCY", "target": rid,
                        "detail": "依赖图存在环，无法拓扑排序，整包拒绝执行"})
        return out

    def _cycle_members(self):
        """返回**真正处于环中**的规则 ID（含自依赖）；环的下游不算环成员。"""
        graph = {str(r.get("rule_id")): [str(d) for d in (r.get("preconditions") or [])]
                 for r in self.rule_doc["rules"]}
        color, stack, members = {}, [], set()

        def dfs(node):
            color[node] = 1
            stack.append(node)
            for dep in graph.get(node, []):
                if dep not in graph:
                    continue
                if color.get(dep, 0) == 1:          # 回边：dep..node 这一段都在环上
                    members.update(stack[stack.index(dep):])
                elif color.get(dep, 0) == 0:
                    dfs(dep)
            stack.pop()
            color[node] = 2

        for node in graph:
            if color.get(node, 0) == 0:
                dfs(node)
        return sorted(members)

    def rejected_rule_ids(self):
        """被配置校验拒绝执行的规则 ID 集合；这些规则不得给出任何业务结论。"""
        return {str(r["target"]) for r in self.collect_config_rejections() if r.get("target")}

    def reject_missing_rate_policy(self):
        """契约 §9.2：Stage 0 只允许 STRICT（含容差的政策未实现，必须拒绝）。"""
        out = []
        for rule in self.rule_doc["rules"]:
            if rule.get("rule_type") != "non_empty":
                continue
            rid = str(rule.get("rule_id"))
            params = rule.get("parameters") or {}
            policy = params.get("missing_rate_policy")
            if policy in (None, ""):
                out.append({"code": "MISSING_RATE_POLICY_NOT_APPROVED", "target": rid,
                            "detail": "未声明 missing_rate_policy；Stage 0 必须显式写 STRICT"})
            elif policy not in MISSING_RATE_POLICIES:
                out.append({"code": "MISSING_RATE_POLICY_NOT_APPROVED", "target": rid,
                            "detail": "missing_rate_policy=%s 未实现（Stage 0 仅支持 STRICT）" % policy})
            rate = params.get("allowed_missing_rate")
            if _truthy_number(rate):
                out.append({"code": "MISSING_RATE_POLICY_NOT_APPROVED", "target": rid,
                            "detail": "allowed_missing_rate=%s > 0，需要批准的阈值来源；Stage 0 不实现" % rate})
        return out

    def reject_boundary_policy(self):
        """契约 §8.2：未知政策 / 未声明政策 / 带缓冲的几何一律拒绝，禁止静默按另一政策执行。"""
        out = []
        for rule in self.rule_doc["rules"]:
            if rule.get("rule_type") != "within_project_area":
                continue
            rid = str(rule.get("rule_id"))
            params = rule.get("parameters") or {}
            policy = params.get("boundary_policy")
            if policy in (None, ""):
                out.append({"code": "BOUNDARY_POLICY_UNSPECIFIED", "target": rid,
                            "detail": "未声明 boundary_policy；不得默认按 inclusive 执行"})
            elif policy not in BOUNDARY_POLICIES:
                out.append({"code": "BOUNDARY_POLICY_UNKNOWN", "target": rid,
                            "detail": "boundary_policy=%s 不是已批准政策（允许：%s）"
                                      % (policy, "/".join(BOUNDARY_POLICIES))})
            for key in sorted(params):
                if key.startswith("buffer"):
                    out.append({"code": "BOUNDARY_BUFFER_NOT_IMPLEMENTED", "target": rid,
                                "detail": "检测到缓冲类参数 %s；Stage 0 不支持缓冲，禁止静默忽略" % key})
        return out

    # ---- 记录结构
    def record_locator(self, lineno, row):
        rid = row[0].strip() if row else ""
        return {"file": "poi.csv", "line": lineno, "record_id": rid or None}

    @staticmethod
    def dataset_locator(file):
        """数据集级缺陷：不挂在任何单条记录上，因此不会触发记录级依赖阻断。"""
        return {"file": file, "record_id": None}

    def field_value(self, row, field):
        if field not in self.header:
            return None
        return row[self.header.index(field)]

    def add_risk_signal(self, code, severity, message, evidence=None):
        """登记风险信号的**唯一**入口（契约 A3）。

        三重保证，缺一不可：
        1. **注册表**：code 必须在 RISK_SIGNAL_CODES 内，未登记即 ContractViolation；
        2. **返回 None**：调用方拿不到任何可用于判定结论的返回值；签名里也没有
           verdict / reason_code 参数，从 API 上杜绝"用信号定结论"的写法；
        3. **只写窗口**：run() 期间 self.risk_signals 被替换成 WriteOnlyRiskLog，
           任何读取都会抛错（见 WriteOnlyRiskLog 的说明）。
        """
        if code not in RISK_SIGNAL_CODES:
            raise ContractViolation(
                "风险信号码 %r 未登记；新增码必须同步 RISK_SIGNAL_CODES 与 "
                "schemas/risk_signal.schema.json（当前已登记：%s）"
                % (code, sorted(RISK_SIGNAL_CODES)))
        if severity not in RISK_SIGNAL_SEVERITIES:
            raise ContractViolation("风险信号 severity %r 不在 %s 内"
                                    % (severity, list(RISK_SIGNAL_SEVERITIES)))
        self.risk_signals.append({
            "code": code,
            "severity": severity,
            "message": message,
            "evidence": evidence or {},
        })
        return None

    def finding(self, rule_id, record, field, observed, expected, reason, evidence=None):
        # 原因码必须已登记**且已分类**：未分类的码在这里也会被拦下（第二道网）
        if reason not in REASON_CODES:
            raise ContractViolation(
                "原因码 %r 未登记；新增码必须同步 REASON_CODES 三分类与 finding.schema.json" % reason)
        if classify_reason_code(reason) is None:
            raise ContractViolation(
                "原因码 %r 未归入 FAIL / CANDIDATE / INDETERMINATE 三类之一；"
                "新增码必须显式声明归属（契约红线）" % reason)
        if reason not in FINDING_REASON_CODES:
            raise ContractViolation(
                "原因码 %r 是规则级专用码（RESULT_ONLY），不得写进 finding；"
                "只允许出现在 CheckResult.reason_code" % reason)
        self.finding_seq += 1
        return {
            "finding_id": f"F{self.finding_seq:04d}",
            "stable_key": f"{rule_id}|{reason}|{record.get('line', 'dataset')}|{field or '-'}",
            "record_locator": record,
            "record_id": record.get("record_id"),
            "rule_id": rule_id,
            "field": field,
            "observed_value": observed,
            "expected_constraint": expected,
            "reason_code": reason,
            "evidence": evidence or {},
            "review_state": "OPEN",
        }

    # ---- 条款覆盖模型（契约 §3，GA-01）
    def required_clause_ids(self):
        """必检条款全集 U（契约 §3.1）。聚合以此为全集，而不是"看已有规则结果"。"""
        return [r["requirement_id"] for r in self.req_doc["requirements"]
                if r.get("required_for_release")]

    def mapped_rules(self, requirement_id):
        return [r for r in self.rule_doc["rules"]
                if requirement_id in (r.get("requirement_ids") or [])]

    def has_implementation(self, rule):
        return getattr(self, "rule_" + str(rule.get("rule_type")), None) is not None

    def build_clause_coverage(self, results):
        """逐条判定 U 中每个条款的覆盖状态，输出 clause_coverage（契约 §3.2 / §3.5）。

        RC-01：判定"覆盖是否完整"的**唯一证据**是「应有结果规则集合 == 实得结果规则集合」，
        不是"这个条款至少有一条结果"。部分缺失、重复、冲突一律失败关闭：
          - 重复/冲突：同一规则 ID 出现多条结果 ⇒ 结果集不可信（禁止后一条覆盖前一条）；
          - 缺结果且无已知 FAIL ⇒ 条款未知（INDETERMINATE），不得放行；
          - 缺结果且已有 FAIL ⇒ 保留已知失败（FAIL），同时**显式列出**缺失规则，不隐藏。
        """
        rejected = self.rejected_rule_ids()
        coverage = []
        for cid in self.required_clause_ids():
            req = self.requirement_by_id(cid)
            mapped = self.mapped_rules(cid)
            mapped_ids = [str(r.get("rule_id")) for r in mapped]
            # 契约 §3.5.2(1)：条款内按**拓扑执行序**取结果（不是配置文档顺序），
            # 保证「第一条 FAIL finding」的语义在跨规则时也成立（上游原因更根本）
            mapped_set = set(mapped_ids)
            clause_results = [r for r in results if str(r.get("rule_id")) in mapped_set]
            # 结果身份归组：按 rule_id 收集（保留执行序），用于识别重复/冲突
            by_rule, present = {}, []
            for r in clause_results:
                rid = str(r.get("rule_id"))
                by_rule.setdefault(rid, []).append(r)
                if len(by_rule[rid]) == 1:
                    present.append(r)
            conflicting = sorted(rid for rid, v in by_rule.items() if len(v) > 1)
            # 应执行的规则：未被配置拒绝 + 已批准 + 有实现（其余已在下面的分支里先行判掉）
            expected_ids = [str(r.get("rule_id")) for r in mapped
                            if str(r.get("rule_id")) not in rejected
                            and r.get("status") == "APPROVED"
                            and self.has_implementation(r)]
            missing = [rid for rid in expected_ids if rid not in by_rule]
            entry = {
                "requirement_id": cid,
                "required_for_release": bool(req.get("required_for_release")),
                "support_status": req.get("support_status"),
                "mapped_rule_ids": mapped_ids,
            }
            if not mapped:
                state = "UNMAPPED"
                verdict, status, reason = "INDETERMINATE", "NOT_EXECUTED", "CLAUSE_NOT_COVERED_BY_RULE"
            elif req.get("support_status") not in CLAUSE_EXECUTABLE_SUPPORT_STATUSES:
                # RC-02 兜底网：条款状态与"已批准且已执行"矛盾 ⇒ 不得放行。
                # 正常情况下 reject_reference_integrity() 已把这些规则拦下（CONFIG_REJECTED），
                # 这里是为了防止"绕过配置校验直接调覆盖率接口"时静默 PASS。
                state = "CONFIG_REJECTED"
                verdict, status, reason = "INDETERMINATE", "REJECTED", "UPSTREAM_CONFIG_REJECTED"
            elif any(i in rejected for i in mapped_ids):
                state = "CONFIG_REJECTED"
                verdict, status, reason = "INDETERMINATE", "REJECTED", "UPSTREAM_CONFIG_REJECTED"
            elif all(r.get("status") != "APPROVED" for r in mapped):
                state = "UNAPPROVED"
                verdict, status, reason = "INDETERMINATE", "NOT_EXECUTED", "RULE_NOT_APPROVED"
            elif all(not self.has_implementation(r) for r in mapped):
                state = "NO_IMPLEMENTATION"
                verdict, status, reason = "INDETERMINATE", "NOT_IMPLEMENTED", "NO_IMPLEMENTATION"
            elif conflicting:
                # 同一规则多条结果：无法判定哪一条是权威 ⇒ 结果集整体不可信
                state = "MISSING_RESULT"
                verdict, status, reason = "INDETERMINATE", "FAILED", "CONTRACT_VIOLATION"
                entry["conflicting_rule_ids"] = conflicting
                entry["missing_rule_ids"] = missing
                entry["detail"] = ("规则 %s 各有 %s 条结果（重复/冲突），结果集不可信；"
                                   "禁止以后一条覆盖前一条"
                                   % (",".join(conflicting),
                                      "/".join(str(len(by_rule[r])) for r in conflicting)))
            elif missing:
                state = "MISSING_RESULT"
                entry["missing_rule_ids"] = missing
                if any(r.get("verdict") == "FAIL" for r in present):
                    # 已有已知失败：保留 FAIL（不因部分结果缺失而降级为"未知"），
                    # 但缺失规则必须**显式列出**，不得隐藏
                    verdict, status, reason = self.aggregate_clause(cid, present)
                    # 结果集不完整 ⇒ 执行状态不得宣称 COMPLETED
                    status = "PARTIAL"
                    all_codes = []
                    for r in present:
                        if r.get("verdict") == "FAIL":
                            all_codes.extend(r.get("failure_reason_codes") or [])
                    if all_codes:
                        entry["failure_reason_codes"] = _unique_ordered(all_codes)
                else:
                    verdict, status, reason = "INDETERMINATE", "NOT_EXECUTED", "RESULT_MISSING_FOR_CLAUSE"
            elif not clause_results:
                state = "MISSING_RESULT"
                verdict, status, reason = "INDETERMINATE", "NOT_EXECUTED", "RESULT_MISSING_FOR_CLAUSE"
            else:
                state = "COVERED"
                verdict, status, reason = self.aggregate_clause(cid, present)
                if verdict == "FAIL":
                    # S0-R1：条款多条失败时，reason_code 取第一条，全部失败原因在这里列出
                    all_codes = []
                    for r in present:
                        if r.get("verdict") == "FAIL":
                            all_codes.extend(r.get("failure_reason_codes") or [])
                    if all_codes:
                        entry["failure_reason_codes"] = _unique_ordered(all_codes)
                elif verdict == "INDETERMINATE":
                    adv = []
                    for r in present:
                        adv.extend(r.get("advisory_reason_codes") or [])
                    if adv:
                        entry["advisory_reason_codes"] = _unique_ordered(adv)
            # I7–I9 对条款级同样适用（契约 §3.5.1 / §1）；违反按"失败关闭"登记，不静默改值
            try:
                assert_reason_compat(verdict, reason)
            except ContractViolation as exc:
                verdict, status, reason = "INDETERMINATE", "FAILED", "CONTRACT_VIOLATION"
                entry["detail"] = str(exc)
            entry.update({"coverage_state": state, "verdict": verdict,
                          "execution_status": status, "reason_code": reason})
            coverage.append(entry)
        return coverage

    @staticmethod
    def aggregate_clause(requirement_id, clause_results):
        """条款级聚合（契约 §3.3）：任一 FAIL → FAIL；无 FAIL 但有非 PASS → INDETERMINATE；
        全部 PASS 才 PASS；兜底 INDETERMINATE（禁止默认 PASS，不允许"任一通过即通过"）。

        **输入侧同样失败关闭（Stage 1）**：传入的规则结果若自身违反 **I7**（`PASS + 非 OK 码`），
        不得被条款级「全部 PASS ⇒ PASS/OK」静默改写成一条看起来正常的 PASS —— 那是把契约违规洗白。
        此处一律落 `INDETERMINATE / FAILED / CONTRACT_VIOLATION`。

        只拦 I7：`FAIL + OK`、`INDETERMINATE + OK` 由契约 §3.5.1 的**取值链修复**
        （分别落到 CONTRACT_VIOLATION / 候选类码 / 缺证据类码），属于"补齐原因"而非放宽；
        而 PASS 一旦带了非 OK 码，修复任何值都等于放行，只能失败关闭。
        """
        for r in clause_results:
            if r.get("verdict") == "PASS" and r.get("reason_code") != "OK":
                return "INDETERMINATE", "FAILED", "CONTRACT_VIOLATION"
        if any(r.get("verdict") == "FAIL" for r in clause_results):
            first = next(r for r in clause_results if r.get("verdict") == "FAIL")
            status = first.get("execution_status") or "PARTIAL"
            if status not in ("COMPLETED", "PARTIAL"):   # FAIL 只允许这两种状态（契约 §1.3）
                status = "PARTIAL"
            # S0-R1：条款级 reason_code 必须指向**失败原因**——该条款覆盖规则下
            # 第一条 FAIL finding 的 reason_code（契约 §3.5 的示例是 STALE_RECORD）。
            # 规则级 reason_code 在 FAIL 时是 OK（状态码），不能拿它当失败原因，
            # 否则总体理由会写成「FAIL：A2(OK)」这种自相矛盾的行。
            codes = []
            for r in clause_results:
                if r.get("verdict") == "FAIL":
                    codes.extend(r.get("failure_reason_codes") or [])
            # 退化链（§3.5.1）：规则级 reason_code（须属 FAIL 类且非 OK）→ CONTRACT_VIOLATION 兜底，
            # 在源头闭合；断言回归成"不该发生"，不再靠下游 assert_reason_compat 兜底
            fallback = first.get("reason_code")
            if codes:
                reason = codes[0]
            elif fallback and fallback != "OK" and classify_reason_code(fallback) == "FAIL":
                reason = fallback
            else:
                reason = "CONTRACT_VIOLATION"
            return "FAIL", status, reason
        non_pass = [r for r in clause_results if r.get("verdict") != "PASS"]
        if non_pass:
            first = non_pass[0]
            reason = first.get("reason_code") or "OK"
            if reason == "OK":
                # 规则级本不该出现 INDETERMINATE+OK（I9）；一旦出现，按 §3.5.1 取值链补齐：
                # 缺证据类 finding 码 → 候选类码 → CONTRACT_VIOLATION 兜底。
                # **禁止取不到就退回 OK**——那等于给 I9 开后门。
                if first.get("advisory_reason_codes"):
                    reason = first["advisory_reason_codes"][0]
                elif (first.get("summary_counts") or {}).get("records_indeterminate"):
                    reason = "DUPLICATE_CANDIDATE"
                else:
                    reason = "CONTRACT_VIOLATION"
            return "INDETERMINATE", first.get("execution_status") or "NOT_EXECUTED", reason
        if clause_results:
            return "PASS", clause_results[0].get("execution_status") or "COMPLETED", "OK"
        return "INDETERMINATE", "NOT_EXECUTED", "RESULT_MISSING_FOR_CLAUSE"

    # ---- 统计口径（契约 §7）
    def upstream_status_problem(self, rule):
        """按契约 §5.2 传播矩阵判定：上游不可执行时返回下游应报告的 reason_code，否则 None。"""
        for dep in (rule.get("preconditions") or []):
            status = self.status_by_rule.get(str(dep))
            if status is not None and status not in UPSTREAM_OK_STATUSES:
                return UPSTREAM_REASON.get(status, "UPSTREAM_BLOCKED")
        return None

    def classify_records(self, rule, findings, blocked):
        """把每一行归入互斥的 evaluated / skipped_upstream / uninterpretable（I1）。

        failed 与 indeterminate 是 evaluated 的**重叠子集**，不是互斥项。
        候选（DUPLICATE_CANDIDATE）计入 indeterminate，不计失败，也不传播阻断（§7.2）。
        缺证据类（INDETERMINATE_REASON_CODES）finding 的行同样**不是失败**（S0-R2）：
        与 CANDIDATE 对称地归到 uninterpretable —— 否则这些行一边进了 records_failed、
        一边规则级结论是 INDETERMINATE，I4（有失败必然是 FAIL）必然抛 CONTRACT_VIOLATION。
        一行同时有 FAIL 类 finding 时仍算失败（FAIL 优先，不因缺证据而降级）。
        """
        all_lines = sorted(population(rule, self.header, self.rows, self.dict)[0])
        upstream = {l for l in self.blocked_lines(rule) if l in set(all_lines)}
        own_blocked = {l for l in (blocked or set()) if l in set(all_lines)} - upstream

        failed, candidates, advisory = set(), set(), set()
        for fi in findings or []:
            line = (fi.get("record_locator") or {}).get("line")
            if line is None:
                continue  # 数据集级 finding 不挂行号
            if fi.get("reason_code") in CANDIDATE_REASON_CODES:
                candidates.add(line)
                peer = (fi.get("evidence") or {}).get("peer_line")
                if peer is not None:
                    candidates.add(peer)
            elif fi.get("reason_code") in INDETERMINATE_REASON_CODES:
                advisory.add(line)
            else:
                failed.add(line)

        # 有结论的行（含判 FAIL 的行）都算"本规则完成判定"，属于 evaluated；
        # 只有本规则**拿不出任何结论**的行（被自身阻断且没有任何 finding，
        # 或只有缺证据类 finding——那条 finding 自己说的就是"我没法判定"）
        # 才是缺证据的 uninterpretable。
        # 这样 records_failed ⊆ records_evaluated 天然成立，也符合 §7.1 对 evaluated 的定义
        # （"给出 PASS/FAIL/INDETERMINATE 之一"）。
        no_verdict = (own_blocked | (advisory - failed)) - failed - candidates
        evaluated = {l for l in all_lines if l not in upstream and l not in no_verdict}

        c = {
            "records_total": len(all_lines),
            "records_evaluated": len(evaluated),
            "records_failed": len(failed & evaluated),
            "records_indeterminate": len(candidates & evaluated),
            "records_skipped_upstream": len(upstream),
            "records_uninterpretable": len(no_verdict),
            "records_blocked": len(upstream) + len(no_verdict),  # 派生字段，Stage 1 移除
            "findings": len(findings or []),
        }
        return c, evaluated, failed, candidates

    def _executed_counts(self, rule, findings, blocked):
        """规则执行成功后取得 (计数, 已评估行集合, 失败行集合)。"""
        c, evaluated, failed, _candidates = self.classify_records(rule, findings, blocked)
        return c, evaluated, failed

    # ---- 运行
    def run(self):
        """执行全部规则。判定推导期间 risk_signals 处于**只写**状态（契约 A3 的机器化保证）。

        RC-04：每次 run() 都是一次**独立运行** —— 运行局部状态（finding 序号、运行期风险信号）
        在开头复位。因此同一实例连续跑两次，results / findings / risk_signals 完全一致；
        输入侧（配置文档、配置校验结果、配置期风险信号）不复位，它们不是运行产物。
        """
        self._begin_run()
        real_signals = self.risk_signals
        self.risk_signals = WriteOnlyRiskLog(real_signals)
        try:
            return self._run_rules()
        finally:
            self.risk_signals = real_signals
            self._assert_risk_signals_inert()

    def _begin_run(self):
        """复位**运行局部**状态（RC-04）。

        finding_seq：不复位会让第二次 run() 的 finding_id 从上一轮的末尾继续编号，
        同一输入两次运行得到两份"内容相同但 ID 不同"的 findings（独立验收 RC-04）。
        运行期风险信号：同理会重复累积，必须裁回配置期长度。
        配置期信号只登记一次 —— collect_config_rejections() 幂等，重跑不会二次登记。
        """
        self.collect_config_rejections()
        base = getattr(self, "_config_signal_count", None)
        if base is None:
            self._config_signal_count = len(self.risk_signals)
        else:
            del self.risk_signals[base:]
        self.finding_seq = 0
        self.status_by_rule = {}
        self.blocked_map = {}

    def _assert_risk_signals_inert(self):
        """收口断言：风险信号只能是"提示"，不得携带任何可用于判定的字段。"""
        for sig in self.risk_signals:
            if sig.get("code") not in RISK_SIGNAL_CODES:
                raise ContractViolation("风险信号码 %r 未登记（契约 A3 要求中心注册表）"
                                        % sig.get("code"))
            for banned in ("verdict", "execution_status", "reason_code"):
                if banned in sig:
                    raise ContractViolation(
                        "风险信号不得携带 %s 字段：信号永不参与判定（契约 A3），实际=%r"
                        % (banned, sig))
        return True

    def _run_rules(self):
        self.blocked_map = {}
        self.status_by_rule = {}
        all_lines = {lineno for lineno, _ in self.rows}
        rejected = self.rejected_rule_ids()
        results, findings = [], []

        def push(result):
            """登记结果并记住状态，供下游依赖传播使用。"""
            results.append(result)
            key = result.get("rule_id")
            if key is not None:
                self.status_by_rule[str(key)] = result.get("execution_status")

        for rule in self.ordered_rules():
            rid = rule.get("rule_id")
            # 契约 §5.2：上游不可执行 ⇒ 本规则不得执行，更不得 PASS
            upstream_problem = self.upstream_status_problem(rule)
            # 被配置校验拒绝的规则：不执行、不给任何业务结论（契约 §2.3 / §8.2 / §9.1）
            if str(rid) in rejected:
                push(make_result(rule, "INDETERMINATE", "REJECTED", "CONFIG_REJECTED",
                                 zero_counts()))
                self.blocked_map[rid] = set(all_lines)
                continue
            if rule.get("status") != "APPROVED":
                push(make_result(rule, "INDETERMINATE", "NOT_EXECUTED",
                                 "RULE_NOT_APPROVED", zero_counts()))
                self.blocked_map[rid] = set(all_lines)
                continue
            handler = getattr(self, "rule_" + rule["rule_type"], None)
            if handler is None:
                push(make_result(rule, "INDETERMINATE", "NOT_IMPLEMENTED",
                                 "NO_IMPLEMENTATION", zero_counts()))
                self.blocked_map[rid] = set(all_lines)
                continue
            if upstream_problem is not None:
                # 上游不可执行：本规则整体不可执行（数据集级），不得给出任何业务结论
                push(make_result(rule, "INDETERMINATE", "BLOCKED", upstream_problem, zero_counts()))
                self.blocked_map[rid] = set(all_lines)
                continue
            try:
                f, blocked = handler(rule, None)
            except NotImplementedByStage as exc:
                # Stage 0 未实现的几何/政策：必须落成 NOT_IMPLEMENTED，禁止按另一种方式静默执行
                push(make_result(rule, "INDETERMINATE", "NOT_IMPLEMENTED",
                                 exc.reason_code, zero_counts()))
                self.blocked_map[rid] = set(all_lines)
                continue
            except Exception as exc:  # noqa: BLE001 —— 兜底：不得把异常吞掉后给出 PASS
                failed_result = make_result(rule, "INDETERMINATE", "FAILED",
                                            "EXECUTION_EXCEPTION", zero_counts())
                failed_result["detail"] = "%s: %s" % (type(exc).__name__, exc)
                push(failed_result)
                self.blocked_map[rid] = set(all_lines)
                continue

            counts, _evaluated, failed = self._executed_counts(rule, f, blocked)
            candidate_lines = set()
            for fi in f:
                line = (fi.get("record_locator") or {}).get("line")
                if line is not None and fi.get("reason_code") in CANDIDATE_REASON_CODES:
                    candidate_lines.add(line)
            failure_findings = [fi for fi in f
                                if fi.get("reason_code") not in CANDIDATE_REASON_CODES
                                and fi.get("reason_code") not in INDETERMINATE_REASON_CODES]
            advisory_findings = [fi for fi in f
                                 if fi.get("reason_code") in INDETERMINATE_REASON_CODES]

            # 下游阻断 = 上游阻断行 ∪ 本规则不可解释行 ∪ 本规则判失败的行；**候选不阻断**（§7.2）
            self.blocked_map[rid] = self.blocked_lines(rule) | {
                l for l in (blocked or set()) if l in all_lines} | {
                l for l in failed if l in all_lines and l not in candidate_lines}

            # reason_code 取值规则（契约 §3.5.1，I7–I9：OK 只在 PASS 时合法）：
            #   FAIL ⇒ 第一条 FAIL 类 finding 的码；INDETERMINATE ⇒ 缺证据类 finding 码
            #   > 上游码 / ALL_RECORDS_BLOCKED > 候选类码；任何分支都取不到码 ⇒ CONTRACT_VIOLATION，
            #   禁止"取不到就退回 OK"。
            if not f and counts["records_evaluated"] == 0:
                verdict, status, reason = "INDETERMINATE", "BLOCKED", "ALL_RECORDS_BLOCKED"
            elif failure_findings:
                verdict, reason = "FAIL", failure_findings[0]["reason_code"]
                status = "PARTIAL" if (counts["records_skipped_upstream"]
                                       or counts["records_uninterpretable"]) else "COMPLETED"
            elif advisory_findings:
                # "缺证据"类 finding：规则级 INDETERMINATE，不是失败但也不放行
                verdict, reason = "INDETERMINATE", advisory_findings[0]["reason_code"]
                status = "PARTIAL" if (counts["records_skipped_upstream"]
                                       or counts["records_uninterpretable"]) else "COMPLETED"
            elif counts["records_skipped_upstream"] or counts["records_uninterpretable"]:
                verdict, status, reason = "INDETERMINATE", "PARTIAL", "ALL_RECORDS_BLOCKED"
            elif counts["records_indeterminate"] > 0:
                # 只有候选：候选类码在取值链最末（§3.5.1）
                verdict, status, reason = "INDETERMINATE", "COMPLETED", "DUPLICATE_CANDIDATE"
            else:
                verdict, status, reason = "PASS", "COMPLETED", "OK"

            try:
                result = make_result(rule, verdict, status, reason, counts)
                if rule.get('scope'):
                    eligible, unknown, excluded = population(rule, self.header, self.rows, self.dict)
                    result['scope_selection'] = {'eligible_records':len(eligible), 'unknown_selector_records':len(unknown), 'excluded_records':len(excluded)}
                if failure_findings:
                    # S0-R1：保留 FAIL finding 的原因码序列（**去重、保留首次出现顺序**，契约 §3.5.2），
                    # 供条款级聚合取「第一条 FAIL finding 的 reason_code」作条款级 reason_code（§3.5.1）
                    result["failure_reason_codes"] = _unique_ordered(
                        fi["reason_code"] for fi in failure_findings)
                if advisory_findings:
                    # S0-R1 对称侧：保留缺证据类 finding 的码，供 INDETERMINATE 条款取原因码
                    result["advisory_reason_codes"] = _unique_ordered(
                        fi["reason_code"] for fi in advisory_findings)
                results.append(result)
            except ContractViolation as exc:
                # 不变式被违反：登记 FAILED，绝不"修正"成看起来合理的值
                results.append({
                    "rule_id": rid,
                    "requirement_ids": rule.get("requirement_ids") or [],
                    "verdict": "INDETERMINATE",
                    "execution_status": "FAILED",
                    "reason_code": "CONTRACT_VIOLATION",
                    "summary_counts": zero_counts(),
                    "required_for_release": bool(rule.get("required_for_release")),
                    "detail": str(exc),
                })
            findings.extend(f)

        # 未被任何规则映射的必检条款（GA-01）：必须登记成 INDETERMINATE/NOT_EXECUTED，
        # 不能凭空消失。这里同时保证：任何只看 check_results 的聚合口径也漏不掉它。
        # 兼容性条目必须与权威口径一致（契约 §3.5.1 追加项 2）：
        # clause_coverage 对 UNMAPPED 一律报 CLAUSE_NOT_COVERED_BY_RULE，兼容条目照取它，
        # 不再按 support_status 分叉出 NOT_APPROVABLE_NO_THRESHOLD（同一事实两处码不一致的遗留）。
        for cid in self.required_clause_ids():
            if self.mapped_rules(cid):
                continue
            push(make_result(
                {"rule_id": None, "requirement_ids": [cid], "required_for_release": True},
                "INDETERMINATE", "NOT_EXECUTED", "CLAUSE_NOT_COVERED_BY_RULE", zero_counts()))
        return results, findings

    def ordered_rules(self):
        """按前置条件做拓扑排序，保证被依赖的规则先执行。

        GA-04：**不得**再写 `[d for d in preconditions if d in ids]` 这种过滤——
        未知依赖的语义是"证据链不完整 ⇒ 不可执行"，不是"没有依赖"。
        未知依赖与有环由 reject_dependency_graph() 在执行前拒绝；这里只做兜底防死循环。
        """
        rules = list(self.rule_doc["rules"])
        ids = [str(r["rule_id"]) for r in rules]
        out, done = [], set()
        remaining = list(rules)
        while remaining:
            progressed = False
            # 契约 §3.5.2(1)：拓扑序并列时以 rule_id 字典序 tie-break，保证跨环境、跨运行可复现
            for r in sorted(remaining, key=lambda x: str(x["rule_id"])):
                deps = [str(d) for d in (r.get("preconditions") or [])]
                if all(d in done for d in deps if d in ids):
                    out.append(r)
                    done.add(str(r["rule_id"]))
                    remaining.remove(r)
                    progressed = True
            if not progressed:
                self.errors.append("规则存在循环依赖或未知前置，剩余：" + ",".join(
                    str(r["rule_id"]) for r in remaining))
                out.extend(remaining)
                break
        return out

    def counts(self, blocked):
        return len(self.rows) - len(blocked), len(blocked)

    def blocked_lines(self, rule):
        out = set()
        for pre in rule.get("preconditions") or []:
            out |= self.blocked_map.get(pre, set())
        return out

    def eval_lines(self, rule):
        blocked = self.blocked_lines(rule)
        eligible, _unknown, _excluded = population(rule, self.header, self.rows, self.dict)
        return [lineno for lineno, _ in self.rows if lineno not in blocked and lineno in eligible]

    # --- R01 必填字段存在
    def rule_required_field_present(self, rule, ctx):
        f, blocked = [], set()
        params = rule.get("parameters") or {}
        for field in params.get("fields") or []:
            if field not in self.header:
                f.append(self.finding(rule["rule_id"], self.dataset_locator("poi.csv"),
                                      field, "缺失整列", "字段必须存在", "FIELD_COLUMN_MISSING"))
        for lineno, row in self.rows:
            if len(row) < len(self.header):
                missing = self.header[len(row):]
                f.append(self.finding(rule["rule_id"], self.record_locator(lineno, row), ",".join(missing),
                                      "缺值", "每行字段数必须与表头一致", "FIELD_COUNT_MISMATCH"))
        return f, blocked

    # --- R02 非空
    def rule_non_empty(self, rule, ctx):
        f, blocked = [], set()
        params = rule.get("parameters") or {}
        trim = bool(params.get("trim", True))
        for lineno in self.eval_lines(rule):
            row = dict(zip(self.header, dict(self.rows)[lineno]))
            rec = self.record_locator(lineno, dict(self.rows)[lineno])
            for field in params.get("fields") or []:
                if field not in self.header:
                    continue
                v = row.get(field)
                if v is None or (v.strip() if trim else v) == "":
                    f.append(self.finding(rule["rule_id"], rec, field, v, "不得为空值", "EMPTY_VALUE"))
                    blocked.add(lineno)
        return f, blocked

    # --- R03 类型/解析
    def rule_type_parse(self, rule, ctx):
        f, blocked = [], set()
        idx = {l: r for l, r in self.rows}
        for lineno in self.eval_lines(rule):
            row = idx[lineno]
            rec = self.record_locator(lineno, row)
            rec_blocked = False
            for field in (rule.get("parameters") or {}).get("fields") or []:
                if field not in self.header or field not in self.dict:
                    continue
                v = self.field_value(row, field)
                if v is None or v.strip() == "":
                    rec_blocked = True
                    continue
                _, err = parse_value(v, self.dict[field]["data_type"])
                if err:
                    f.append(self.finding(rule["rule_id"], rec, field, v,
                                          f"类型必须为 {self.dict[field]['data_type']}", err))
                    blocked.add(lineno)
                    rec_blocked = True
            if rec_blocked and lineno not in blocked:
                blocked.add(lineno)
        # 由上游失败导致的阻断
        blocked |= set(self.eval_lines(rule)) & self.blocked_lines(rule)
        return f, blocked

    # --- R04 枚举
    def rule_enum_value(self, rule, ctx):
        f, blocked = [], set()
        idx = {l: r for l, r in self.rows}
        field = (rule.get("parameters") or {}).get("field")
        enum_values = self.dict.get(field, {}).get("enum_values") or []
        for lineno in self.eval_lines(rule):
            row = idx[lineno]
            rec = self.record_locator(lineno, row)
            v = self.field_value(row, field)
            if v is None or v.strip() == "":
                blocked.add(lineno)
                continue
            if v.strip() not in enum_values:
                f.append(self.finding(rule["rule_id"], rec, field, v,
                                      "取值必须在字典枚举内: " + "/".join(enum_values),
                                      "ENUM_VIOLATION",
                                      {"dictionary_line": self.dict[field]["source_line"]}))
        blocked |= set(self.eval_lines(rule)) & self.blocked_lines(rule)
        return f, blocked

    # --- R05 ID 唯一
    def rule_id_unique(self, rule, ctx):
        f, blocked = [], set()
        idx = {l: r for l, r in self.rows}
        field = (rule.get("parameters") or {}).get("field")
        seen = {}
        for lineno in self.eval_lines(rule):
            row = idx[lineno]
            v = (self.field_value(row, field) or "").strip()
            if v == "":
                f.append(self.finding(rule["rule_id"], self.record_locator(lineno, row), field, v,
                                      "ID 不得为空", "EMPTY_ID"))
                continue
            seen.setdefault(v, []).append(lineno)
        for v, lines in seen.items():
            if len(lines) > 1:
                for ln in lines:
                    f.append(self.finding(rule["rule_id"], self.record_locator(ln, idx[ln]), field, v,
                                          "ID 必须唯一", "DUPLICATE_ID",
                                          {"duplicate_lines": lines}))
        blocked |= set(self.eval_lines(rule)) & self.blocked_lines(rule)
        return f, blocked

    # --- R06 坐标范围
    def rule_coord_range(self, rule, ctx):
        f, blocked = [], set()
        idx = {l: r for l, r in self.rows}
        p = rule.get("parameters") or {}
        for lineno in self.eval_lines(rule):
            row = idx[lineno]
            rec = self.record_locator(lineno, row)
            lon_s, lat_s = self.field_value(row, "longitude"), self.field_value(row, "latitude")
            if lon_s is None or lat_s is None or lon_s.strip() == "" or lat_s.strip() == "":
                blocked.add(lineno)
                continue
            lon, e1 = parse_value(lon_s, "number")
            lat, e2 = parse_value(lat_s, "number")
            if e1 or e2:
                blocked.add(lineno)
                continue
            if not (p["lon_range"][0] <= lon <= p["lon_range"][1]):
                f.append(self.finding(rule["rule_id"], rec, "longitude", lon_s,
                                      f"经度须在 [{p['lon_range'][0]},{p['lon_range'][1]}]",
                                      "LONGITUDE_OUT_OF_RANGE"))
            if not (p["lat_range"][0] <= lat <= p["lat_range"][1]):
                f.append(self.finding(rule["rule_id"], rec, "latitude", lat_s,
                                      f"纬度须在 [{p['lat_range'][0]},{p['lat_range'][1]}]",
                                      "LATITUDE_OUT_OF_RANGE"))
        blocked |= set(self.eval_lines(rule)) & self.blocked_lines(rule)
        return f, blocked

    # --- R07 CRS 判定（契约 §4：四类分离，GA-03）
    def rule_crs_declaration(self, rule, ctx):
        """把原来混在一起的四件事分开判定：

        - **C1 声明一致性**：唯一可判 FAIL 的一类；证据 = 原文要求 CRS + 提交声明，
          二者都以冻结行号与逐字引用为准，严格规范比、不做别名推断。
        - **C2 元数据完备性**：缺声明时**不判 FAIL**，落 INDETERMINATE 并阻断下游空间规则。
        - **C3 坐标解释可用性**：只产 risk signal，永不参与 verdict。
        - **C4 真实性**：本系统无真值，恒不判定（写入 docs/limitations.md）。
        """
        f, blocked = [], set()
        p = rule.get("parameters") or {}
        expected = p.get("expected_crs")
        declared = str(self.crs.get("declared_crs") or "").strip()
        declared_unit = str(self.crs.get("declared_unit") or "").strip()
        all_lines = {lineno for lineno, _ in self.rows}

        # C3：量级只作风险信号（A3 的落地），不产 finding、不计 verdict、不阻断
        self._crs_magnitude_signal(declared_unit)

        # C2：缺声明 —— 无批准条款授权判 FAIL，按 A2 落 INDETERMINATE
        if not declared:
            f.append(self.finding(rule["rule_id"], self.dataset_locator("crs.json"), "declared_crs", None,
                                  "必须提交 CRS 声明才能做一致性判定；缺证据即未知，不判 FAIL",
                                  "CRS_MISSING_DECLARATION"))
            return f, set(all_lines)

        # C1 前置：要求的 CRS 必须有已批准且自校验通过的来源，否则同样缺证据
        src = self.approved_parameter_source(rule, "expected_crs")
        if not expected or src is None:
            f.append(self.finding(rule["rule_id"], self.dataset_locator("crs.json"), "expected_crs", expected,
                                  "要求的 CRS 缺少已批准来源，不得据此判定（缺证据即未知）",
                                  "CRS_EXPECTED_NOT_APPROVED"))
            return f, set(all_lines)

        # C1：声明一致性（唯一可判 FAIL）
        if normalize_crs(declared) != normalize_crs(expected):
            f.append(self.finding(
                rule["rule_id"], self.dataset_locator("crs.json"), "declared_crs", declared,
                "声明的 CRS 必须与原文要求一致；本系统不自动纠偏、不猜测真实 CRS",
                "CRS_DECLARATION_MISMATCH",
                {"expected_crs": expected, "declared_crs": declared,
                 "requirement_id": src.get("requirement_id"),
                 "document_id": src.get("document_id"),
                 "document_sha256": src.get("document_sha256"),
                 "source_line_start": src.get("source_line_start"),
                 "source_quote": src.get("source_quote")}))
            blocked = set(all_lines)   # §4.4：C1 非 PASS ⇒ 下游空间规则全批阻断
        return f, blocked

    def _crs_magnitude_signal(self, declared_unit):
        """C3：声明单位下坐标是否"看起来像经纬度"——只作风险信号，永不构成判定。"""
        if declared_unit != "metre":
            return
        degree_like = 0
        for lineno, row in self.rows:
            lon, e1 = parse_value(self.field_value(row, "longitude") or "", "number")
            lat, e2 = parse_value(self.field_value(row, "latitude") or "", "number")
            if not e1 and not e2 and abs(lon) <= 180 and abs(lat) <= 90:
                degree_like += 1
        if degree_like:
            self.add_risk_signal(
                "CRS_MAGNITUDE_RISK", "WARN",
                "声明为米单位但坐标落在经纬度量级；EPSG:3857 下原点附近的小值坐标同样合法，"
                "本项仅提示人工核对，不构成判定依据",
                {"degree_like_records": degree_like})

    def approved_parameter_source(self, rule, parameter):
        """取某参数的批准来源；来源缺失或其自身校验不过时返回 None（视同无批准证据）。"""
        src = None
        for item in (rule.get("parameter_sources") or []):
            if item.get("parameter") == parameter:
                src = item
                break
        if src is None:
            return None
        req_by_id = {r["requirement_id"]: r for r in self.req_doc["requirements"]}
        params = rule.get("parameters") or {}
        problems = self._check_parameter_source(rule, parameter, params.get(parameter), src, req_by_id)
        if any(code in SOURCE_HARD_FAILURES for code, _t, _d in problems):
            return None
        return src

    # --- R08 项目范围
    def rule_within_project_area(self, rule, ctx):
        f, blocked = [], set()
        idx = {l: r for l, r in self.rows}
        p = rule.get("parameters") or {}
        # 契约 §8.2：政策必须来自配置，禁止硬编码 inclusive
        policy = p.get("boundary_policy")
        inclusive = (policy == "inclusive")
        if policy not in BOUNDARY_POLICIES:
            # 未声明/未知政策由 reject_boundary_policy() 登记 REJECTED，此处不会到达；
            # 若到达说明配置校验被绕过，按 A2 不得给出任何业务结论。
            raise NotImplementedByStage("BOUNDARY_POLICY_UNKNOWN",
                                        "boundary_policy=%r 未批准，不得按默认政策执行" % policy)
        ring = self.project_area_ring()
        for lineno in self.eval_lines(rule):
            row = idx[lineno]
            rec = self.record_locator(lineno, row)
            lon_s, lat_s = self.field_value(row, "longitude"), self.field_value(row, "latitude")
            lon, e1 = parse_value(lon_s or "", "number")
            lat, e2 = parse_value(lat_s or "", "number")
            if e1 or e2:
                blocked.add(lineno)
                continue
            hint = "点位须落在项目范围内（%s边界）" % ("含" if inclusive else "不含")
            if not point_in_ring_or_boundary(lon, lat, ring, inclusive=inclusive):
                f.append(self.finding(rule["rule_id"], rec, "longitude/latitude", f"{lon},{lat}",
                                      hint, "OUTSIDE_PROJECT_AREA"))
        blocked |= set(self.eval_lines(rule)) & self.blocked_lines(rule)
        return f, blocked

    def project_area_ring(self):
        """取项目范围的外环。契约 §8.2：带孔 / 多部件 / 非 Polygon 一律 NOT_IMPLEMENTED。"""
        shape = self.area.get("type")
        coords = self.area.get("coordinates")
        if shape != "Polygon" or not isinstance(coords, list) or not coords:
            raise NotImplementedByStage(
                "GEOMETRY_SHAPE_UNSUPPORTED",
                "area.geojson 的几何类型 %r 不在 Stage 0 支持范围内（仅单个简单 Polygon）" % shape)
        if len(coords) != 1:
            raise NotImplementedByStage(
                "GEOMETRY_SHAPE_UNSUPPORTED",
                "带孔或多部件几何（%d 个环）Stage 0 不支持，禁止按另一个环静默执行" % len(coords))
        ring = coords[0]
        if not isinstance(ring, list) or len(ring) < 4:
            raise NotImplementedByStage(
                "GEOMETRY_SHAPE_UNSUPPORTED",
                "外环顶点数不足（%s），无法构成闭合多边形" % (len(ring) if isinstance(ring, list) else "?"))
        if ring[0] != ring[-1]:
            raise NotImplementedByStage(
                "GEOMETRY_SHAPE_UNSUPPORTED", "外环未闭合，Stage 0 不做自动闭合修正")
        return ring

    # --- R09 时效
    def rule_freshness(self, rule, ctx):
        f, blocked = [], set()
        idx = {l: r for l, r in self.rows}
        p = rule.get("parameters") or {}
        ref = dt.datetime.fromisoformat(p["reference_time"].replace("Z", "+00:00"))
        field = "source_time"
        _eligible, unknown, _excluded = population(rule, self.header, self.rows, self.dict)
        for lineno in self.eval_lines(rule):
            if lineno in unknown:
                blocked.add(lineno)
                continue
            row = idx[lineno]
            rec = self.record_locator(lineno, row)
            v = self.field_value(row, field)
            val, err = parse_value(v or "", "datetime")
            if err:
                blocked.add(lineno)
                continue
            if val.tzinfo is None:
                val = val.replace(tzinfo=dt.timezone.utc)
                f.append(self.finding(rule["rule_id"], rec, field, v,
                                      "时间必须带时区或被声明的时区解释", "TIMEZONE_UNDECLARED"))
            age = (ref - val).total_seconds() / 86400.0
            if age > p["max_age_days"]:
                f.append(self.finding(rule["rule_id"], rec, field, v,
                                      f"距基准时间不得超过 {p['max_age_days']} 天",
                                      "STALE_RECORD", {"age_days": round(age, 3)}))
            elif age < 0:
                f.append(self.finding(rule["rule_id"], rec, field, v, "不得晚于基准时间", "FUTURE_TIMESTAMP"))
        blocked |= set(self.eval_lines(rule)) & self.blocked_lines(rule)
        return f, blocked

    # --- R10 重复候选（不断言重复）
    def rule_duplicate_candidate(self, rule, ctx):
        f, blocked = [], set()
        idx = {l: r for l, r in self.rows}
        p = rule.get("parameters") or {}
        pts = []
        for lineno in self.eval_lines(rule):
            row = idx[lineno]
            lon, e1 = parse_value(self.field_value(row, "longitude") or "", "number")
            lat, e2 = parse_value(self.field_value(row, "latitude") or "", "number")
            if e1 or e2:
                blocked.add(lineno)
                continue
            pts.append((lineno, row, lon, lat))
        groups = []
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                a, b = pts[i], pts[j]
                if not p.get("name_equal", True) or (self.field_value(a[1], "name") != self.field_value(b[1], "name")):
                    continue
                d = geodesic_m(a[2], a[3], b[2], b[3])
                if d <= p["max_distance_m"]:
                    key = frozenset([a[0], b[0]])
                    if not any(key == g[0] for g in groups):
                        groups.append((key, d, a, b))
        for key, d, a, b in groups:
            f.append(self.finding(rule["rule_id"], self.record_locator(a[0], a[1]), "longitude/latitude",
                                  f"{a[2]},{a[3]} 与 {b[2]},{b[3]}",
                                  f"相距不超过 {p['max_distance_m']} 米且同名，须人工确认是否重复",
                                  "DUPLICATE_CANDIDATE",
                                  {"distance_m": round(d, 2),
                                   "peer_line": b[0], "peer_record_id": b[1][0].strip() or None}))
        blocked |= set(self.eval_lines(rule)) & self.blocked_lines(rule)
        return f, blocked


def selfResult(rule, verdict, status, reason, counts):
    """旧签名兼容包装：位置第 5 个参数改为 summary_counts 字典。T03/T04 可直接改用 make_result()。"""
    if isinstance(counts, int):
        counts = {"findings": counts, "records_blocked": 0}
    return make_result(rule, verdict, status, reason, counts)


def zero_counts():
    """完全未执行的规则：不占有任何行。

    这里刻意写 records_total = 0：若写成 total=N 且 evaluated=0，I5 会要求状态 ∈ {PARTIAL, BLOCKED}，
    与契约 §1.2 给 REJECTED / NOT_IMPLEMENTED / NOT_EXECUTED / FAILED 的定义互斥。
    「一行都没看」与「看了但没判成」是两件事，后者才进入 I1–I5 的适用范围。
    """
    return {
        "records_total": 0, "records_evaluated": 0, "records_failed": 0,
        "records_indeterminate": 0, "records_skipped_upstream": 0,
        "records_uninterpretable": 0, "records_blocked": 0, "findings": 0,
    }


def assert_contract(result):
    """组合合法性矩阵 + 统计不变式 I1–I6（契约 §1.3 / §7.1）。

    必须写成**运行时断言**而不是注释：统计口径这类 bug 会以别的形态复活。违反一律抛错，
    由 run() 兜底成 INDETERMINATE / FAILED，绝不允许静默改成"看起来合理"的值。
    """
    verdict = result.get("verdict")
    status = result.get("execution_status")
    if verdict not in VERDICTS:
        raise ContractViolation("verdict %r 不在三态词汇表 %s 内" % (verdict, list(VERDICTS)))
    if status not in EXECUTION_STATUSES:
        raise ContractViolation("execution_status %r 不在词汇表 %s 内" % (status, list(EXECUTION_STATUSES)))
    if (verdict, status) not in LEGAL_COMBOS:
        raise ContractViolation("非法组合：verdict=%s + execution_status=%s（契约 §1.3）"
                                % (verdict, status))
    reason = result.get("reason_code")
    if reason not in REASON_CODES:
        raise ContractViolation("原因码 %r 未登记；新增码必须同步 REASON_CODES 与 finding.schema.json"
                                % reason)
    # I7–I9：reason_code 与 verdict 必须相容（契约 §3.5.1）
    assert_reason_compat(verdict, reason)
    c = result.get("summary_counts") or {}
    total = c.get("records_total", 0)
    evaluated = c.get("records_evaluated", 0)
    failed = c.get("records_failed", 0)
    indet = c.get("records_indeterminate", 0)
    skipped = c.get("records_skipped_upstream", 0)
    unintr = c.get("records_uninterpretable", 0)
    blocked = c.get("records_blocked", 0)
    # I1：三类互斥口径必须刚好铺满全批
    if total != evaluated + skipped + unintr:
        raise ContractViolation("I1 违反：records_total=%d != evaluated(%d)+skipped(%d)+uninterpretable(%d)"
                                % (total, evaluated, skipped, unintr))
    # I2：failed / indeterminate 是 evaluated 的重叠子集
    if failed + indet > evaluated:
        raise ContractViolation("I2 违反：failed(%d)+indeterminate(%d) > evaluated(%d)"
                                % (failed, indet, evaluated))
    # I3：records_blocked 是派生字段
    if blocked != skipped + unintr:
        raise ContractViolation("I3 违反：records_blocked=%d != skipped(%d)+uninterpretable(%d)"
                                % (blocked, skipped, unintr))
    # I4：有失败必然是 FAIL
    if failed > 0 and verdict != "FAIL":
        raise ContractViolation("I4 违反：records_failed=%d 但 verdict=%s" % (failed, verdict))
    # I5：没跑完全批就不得标 COMPLETED（N=0 的空批不适用）
    if total > 0 and evaluated < total and status not in ("PARTIAL", "BLOCKED"):
        raise ContractViolation("I5 违反：evaluated=%d < total=%d 但 status=%s"
                                % (evaluated, total, status))
    # I6：PASS 要求零跳过、零不可解释、零失败
    if verdict == "PASS" and (skipped or unintr or failed):
        raise ContractViolation("I6 违反：verdict=PASS 但 skipped=%d uninterpretable=%d failed=%d"
                                % (skipped, unintr, failed))
    return True


def make_result(rule, verdict, status, reason, counts, detail=None):
    """构造一条 CheckResult，并强制通过契约断言。"""
    result = {
        "rule_id": rule.get("rule_id"),
        "requirement_ids": rule.get("requirement_ids") or [],
        "verdict": verdict,
        "execution_status": status,
        "reason_code": reason,
        "summary_counts": dict(counts),
        "required_for_release": bool(rule.get("required_for_release")),
    }
    if rule.get('scope'):
        result['scope'] = dict(rule['scope'])
    if detail:
        result["detail"] = detail
    assert_contract(result)
    return result


# ---------------------------------------------------------------- 聚合
def aggregate(clause_coverage, config_rejections, n_rows=None):
    """总体聚合（契约 §3.4）：以必检条款全集 U 的覆盖结果为唯一输入。

    规则级结果只作为条款级聚合的输入，不再直接参与总体聚合。

    **Stage 1：二参数兼容签名 `aggregate(results, n_rows)` 已删除**
    （最终复验报告 Stage 1 第 5 条：收敛到唯一正式接口，避免"两处判定口径"这种后门）。
    传入规则级结果会立刻 TypeError 并给出迁移说明，不会静默走另一条判定路径。
    """
    if n_rows is None or _looks_like_rule_results(clause_coverage):
        raise TypeError(
            "aggregate() 只接受三参数正式签名 aggregate(clause_coverage, config_rejections, n_rows)；"
            "二参数兼容路径（以及 _coverage_from_results）已在 Stage 1 删除。"
            "迁移方式：先 kernel.build_clause_coverage(results) 得到权威覆盖，"
            "再 aggregate(coverage, kernel.collect_config_rejections(), len(kernel.rows))")
    coverage, rejections = clause_coverage, config_rejections or []

    if rejections:
        return "INDETERMINATE", "配置校验未通过，拒绝执行：" + ",".join(sorted({
            str(r.get("rule_id") or r.get("target") or "?") for r in rejections}))
    if n_rows == 0 or not coverage:
        return "INDETERMINATE", "零记录/零必检条款不得判定通过"
    failed = [c for c in coverage if c.get("verdict") == "FAIL"]
    if failed:
        return "FAIL", "存在必检条款 FAIL：" + ",".join(
            "%s(%s)" % (c["requirement_id"], c.get("reason_code")) for c in failed)
    non_pass = [c for c in coverage if c.get("verdict") != "PASS"]
    if non_pass:
        return "INDETERMINATE", "存在必检条款未通过：" + ",".join(
            "%s(%s/%s)" % (c["requirement_id"], c.get("coverage_state"), c.get("reason_code"))
            for c in non_pass)
    return "PASS", "全部必检条款均有完整有效的 PASS 证据"


def _looks_like_rule_results(candidate):
    """识别"把规则级 results 当 clause_coverage 传进来"的旧调用（Stage 1 删除兼容路径后）。

    判据：条款级覆盖条目一定有 `requirement_id`，规则级结果一定有 `rule_id`。
    """
    if not isinstance(candidate, list) or not candidate:
        return False
    first = candidate[0]
    if not isinstance(first, dict):
        return False
    return "rule_id" in first and "requirement_id" not in first


# ---------------------------------------------------------------- 报告
def write_outputs(bundle_name, kernel, results, findings, agg, agg_reason, clause_coverage=None):
    outdir = WORK / bundle_name
    outdir.mkdir(parents=True, exist_ok=True)
    inputs = {}
    for f in ["delivery_spec.md", "dictionary.csv", "poi.csv", "area.geojson", "crs.json",
              "requirements.yaml", "approved-rules.yaml"]:
        p = kernel.dir / f
        inputs[f] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
    report = {
        "schema_version": SCHEMA_VERSION,
        "bundle": bundle_name,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "aggregate_verdict": agg,
        "aggregate_reason": agg_reason,
        "config_rejections": kernel.collect_config_rejections(),
        "risk_signals": list(kernel.risk_signals),
        "clause_coverage": clause_coverage or [],
        "check_results": results,
        "findings": findings,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "bundle": bundle_name,
        "mode": "manual",
        "mode_note": "本阶段无模型调用。规则全部来自人工批准的 approved-rules.yaml，不得标示为 live。",
        "inputs": inputs,
        "reference_time": kernel.ref_time,
        "tool_version": TOOL_VERSION,
        "python": sys.version.split()[0],
        "third_party_dependencies": [],
    }
    (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "findings.json").write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "report.md").write_text(render_md(report, manifest), encoding="utf-8", newline="\n")
    return outdir


def render_md(report, manifest):
    lines = ["# %s 验收报告（Stage 0）" % report["bundle"], ""]
    if report.get("config_rejections"):
        lines += ["> **[REJECT] 本次执行被配置校验拒绝，以下结果不构成放行依据。**", ""]
    if report.get("risk_signals"):
        lines += ["**风险信号（不构成判定依据，不产生阻断）**", ""]
        for sig in report["risk_signals"]:
            lines.append("- `%s`（%s）：%s" % (sig.get("code"), sig.get("severity"), sig.get("message")))
        lines.append("")
    lines += ["总体业务结论：**%s** — %s" % (report["aggregate_verdict"], report["aggregate_reason"]), "",
              "运行状态说明：本轮执行为 %s 模式，%s" % (manifest["mode"], manifest["mode_note"]), "",
              "## 逐条规则结果", "",
              "| 规则 | 条款 | 业务结论 | 运行状态 | 缺陷数 | 已评估 | 失败 | 待定 | 上游跳过 | 不可解释 | 阻断(派生) | 必检 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in report["check_results"]:
        rid = r["rule_id"] or "/".join(r["requirement_ids"])
        sc = r["summary_counts"]
        lines.append("| %s | %s | %s | %s | %d | %d | %d | %d | %d | %d | %d | %s |" % (
            rid, "/".join(r["requirement_ids"]), r["verdict"], r["execution_status"],
            sc.get("findings", 0), sc.get("records_evaluated", 0), sc.get("records_failed", 0),
            sc.get("records_indeterminate", 0), sc.get("records_skipped_upstream", 0),
            sc.get("records_uninterpretable", 0), sc.get("records_blocked", 0),
            "是" if r.get("required_for_release") else "否"))
    if report.get("clause_coverage"):
        lines += ["", "## 必检条款覆盖（聚合以此为准）", "",
                  "| 条款 | 覆盖状态 | 映射规则 | 业务结论 | 运行状态 | 原因码 |", "|---|---|---|---|---|---|"]
        for c in report["clause_coverage"]:
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                c.get("requirement_id"), c.get("coverage_state"),
                ",".join(c.get("mapped_rule_ids") or []) or "（无）",
                c.get("verdict"), c.get("execution_status"), c.get("reason_code")))
    if report.get("config_rejections"):
        lines += ["", "## 配置拒绝项（拒绝执行的原因）", "",
                  "| 代码 | 对象 | 说明 |", "|---|---|---|"]
        for c in report["config_rejections"]:
            lines.append("| `%s` | %s | %s |" % (c.get("code"), c.get("target"), c.get("detail")))
    lines += ["", "## 缺陷清单", ""]
    if not report["findings"]:
        lines.append("（无）")
    else:
        lines += ["| ID | 规则 | 记录位置 | 字段 | 观测值 | 约束 | 原因码 |", "|---|---|---|---|---|---|---|"]
        for f in report["findings"]:
            loc = f["record_locator"]
            lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                f["finding_id"], f["rule_id"], "%s:%s" % (loc["file"], loc.get("line", "数据集级")),
                f["field"] or "-",
                (f["observed_value"] if f["observed_value"] not in (None, "") else "（空）"),
                f["expected_constraint"], f["reason_code"]))
    lines += ["", "> 通过结论仅针对本轮已批准规则与覆盖范围，不证明数据整体真实、准确或全面合格。", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- 期望比对（记录级，契约 §9.6）
# 差异分成五类，QA 在 TRUTH_REVIEW 里按种类逐条登记：
DIFF_FIELD = "FIELD"      # 字段级不匹配（结论 / 状态 / 原因码 / finding 属性）
DIFF_COUNT = "COUNT"      # 数量不一致（六个统计字段、finding 条数、条目集合）
DIFF_MISSING = "MISSING"  # 期望登记了、实际没有
DIFF_EXTRA = "EXTRA"      # 实际有、期望未登记
DIFF_UNREG = "UNREG"      # expected 未登记该字段（**提示补登记，不算差异**）
REAL_DIFF_KINDS = (DIFF_FIELD, DIFF_COUNT, DIFF_MISSING, DIFF_EXTRA)
# per_rule 可登记的字段：结论类按字段级比，统计类按数量比
PER_RULE_VERDICT_FIELDS = ("verdict", "execution_status", "reason_code")
PER_RULE_STAT_FIELDS = ("records_total", "records_evaluated", "records_failed",
                        "records_indeterminate", "records_skipped_upstream",
                        "records_uninterpretable")
# finding 级逐条比对的字段（execution_status 取自产出该 finding 的规则结果）
FINDING_FIELDS = ("stable_key", "reason_code", "field", "observed_value", "review_state",
                  "execution_status")
# record_locator 拆成子字段比，避免整块字典比不出差异
LOCATOR_FIELDS = ("file", "line", "record_id")


def _fmt_diff_value(value):
    """差异值的稳定文本形式（dict/list 用 JSON，避免 Python  repr 的不稳定排序）。"""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _expected_rule_entry(raw):
    """per_rule 期望条目兼容两种写法：旧式 [verdict, findings] 与新式 dict。"""
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        return {"verdict": raw[0], "findings": raw[1]}
    return {}


def compare_expected(name, results, findings, agg, coverage=None, rejections=None):
    """记录级期望比对（契约 §9.6 TRUTH_REVIEW）。

    与旧实现（只比总体结论 + 缺陷数）的关键差别：**命中错行但数量相同不再算一致**。
    返回 (可读差异行, expected 文档, 结构化差异记录)。
    expected/ 下的任何文件本函数**只读不改**。
    """
    bdir = EX / name
    exp = json.loads((bdir / "expected" / "aggregate.json").read_text(encoding="utf-8"))
    records = []

    def add(kind, scope, field, expected, actual, note=""):
        records.append({"kind": kind, "scope": scope, "field": field,
                        "expected": expected, "actual": actual, "note": note})

    status_by_rule = {r.get("rule_id"): r.get("execution_status") for r in results}
    results_by_rule = {r.get("rule_id"): r for r in results if r.get("rule_id")}

    # ---- 1. 总体结论
    if exp.get("aggregate_verdict") != agg:
        add(DIFF_FIELD, "aggregate", "aggregate_verdict", exp.get("aggregate_verdict"), agg)

    # ---- 2. 逐规则：结论/状态/原因码（字段级）+ 六个统计字段与 findings 数（数量级）
    for rid, raw in (exp.get("per_rule") or {}).items():
        r = results_by_rule.get(rid)
        if r is None:
            r = next((x for x in results if rid in (x.get("requirement_ids") or [])), None)
        if r is None:
            add(DIFF_MISSING, rid, "result", raw, None, "expected 登记了该规则但没有执行结果")
            continue
        want = _expected_rule_entry(raw)
        counts = r.get("summary_counts") or {}
        for fld in PER_RULE_VERDICT_FIELDS:
            if fld not in want:
                add(DIFF_UNREG, rid, fld, None, r.get(fld), "expected 未登记该字段")
            elif r.get(fld) != want[fld]:
                add(DIFF_FIELD, rid, fld, want[fld], r.get(fld))
        for fld in PER_RULE_STAT_FIELDS:
            if fld not in want:
                add(DIFF_UNREG, rid, fld, None, counts.get(fld), "expected 未登记该字段")
            elif counts.get(fld) != want[fld]:
                add(DIFF_COUNT, rid, fld, want[fld], counts.get(fld))
        if "findings" not in want:
            add(DIFF_UNREG, rid, "findings", None, counts.get("findings"), "expected 未登记该字段")
        elif counts.get("findings") != want["findings"]:
            add(DIFF_COUNT, rid, "findings", want["findings"], counts.get("findings"))

    for rid, min_blocked in (exp.get("blocked_findings_at_least") or {}).items():
        r = results_by_rule.get(rid)
        got = ((r or {}).get("summary_counts") or {}).get("records_blocked", 0)
        if got < min_blocked:
            add(DIFF_COUNT, rid, "records_blocked(at_least)", min_blocked, got)

    # ---- 3. finding 级逐条比对（expected/findings.json 由 QA 在 T05 补登记）
    fpath = bdir / "expected" / "findings.json"
    if fpath.exists():
        exp_findings = (json.loads(fpath.read_text(encoding="utf-8")).get("findings") or [])
        actual_by_key = {}
        for fi in findings:
            actual_by_key.setdefault(fi.get("stable_key"), []).append(fi)
        used = set()
        for want_f in exp_findings:
            key = want_f.get("stable_key")
            hit = None
            for idx, fi in enumerate(actual_by_key.get(key) or []):
                if (key, idx) not in used:
                    hit = (idx, fi)
                    break
            if hit is None:
                add(DIFF_MISSING, "findings[%s]" % key, "finding", want_f, None,
                    "期望的 finding 在实际结果中不存在")
                continue
            used.add((key, hit[0]))
            fi = hit[1]
            for fld in FINDING_FIELDS:
                got = (status_by_rule.get(fi.get("rule_id")) if fld == "execution_status"
                       else fi.get(fld))
                if fld not in want_f:
                    add(DIFF_UNREG, "findings[%s]" % key, fld, None, got, "expected 未登记该字段")
                elif got != want_f[fld]:
                    add(DIFF_FIELD, "findings[%s]" % key, fld, want_f[fld], got)
            loc = fi.get("record_locator") or {}
            want_loc = want_f.get("record_locator")
            if want_loc is None:
                add(DIFF_UNREG, "findings[%s]" % key, "record_locator", None, loc,
                    "expected 未登记该字段")
            else:
                for sub in LOCATOR_FIELDS:
                    if sub not in want_loc:
                        add(DIFF_UNREG, "findings[%s]" % key, "record_locator.%s" % sub, None,
                            loc.get(sub), "expected 未登记该字段")
                    elif loc.get(sub) != want_loc.get(sub):
                        add(DIFF_FIELD, "findings[%s]" % key, "record_locator.%s" % sub,
                            want_loc.get(sub), loc.get(sub))
        for key, pool in actual_by_key.items():
            for idx, fi in enumerate(pool):
                if (key, idx) in used:
                    continue
                add(DIFF_EXTRA, "findings[%s]" % key, "finding", None,
                    {"stable_key": key, "reason_code": fi.get("reason_code")},
                    "实际存在但 expected/findings.json 未登记")
    else:
        add(DIFF_UNREG, "findings", "expected/findings.json", None, len(findings),
            "expected/findings.json 不存在：本包未做 finding 级核对")

    # ---- 4. clause_coverage（可选登记）
    cpath = bdir / "expected" / "clause_coverage.json"
    if cpath.exists():
        # 覆盖记录的字段名：requirement_id / coverage_state（契约 §3.5），兼容 clause_id / state
        want_cov = {}
        for c in (json.loads(cpath.read_text(encoding="utf-8")).get("clause_coverage") or []):
            want_cov[c.get("requirement_id") or c.get("clause_id")] = c
        got_cov = {}
        for c in (coverage or []):
            got_cov[c.get("requirement_id") or c.get("clause_id")] = c
        for cid, want_c in want_cov.items():
            got_c = got_cov.get(cid)
            if got_c is None:
                add(DIFF_MISSING, "clause_coverage", cid, want_c, None, "实际无该条款的覆盖记录")
                continue
            for fld in ("coverage_state", "verdict", "execution_status", "reason_code"):
                if fld not in want_c:
                    add(DIFF_UNREG, "clause_coverage", "%s.%s" % (cid, fld), None,
                        got_c.get(fld), "expected 未登记该字段")
                elif got_c.get(fld) != want_c[fld]:
                    add(DIFF_FIELD, "clause_coverage", "%s.%s" % (cid, fld),
                        want_c[fld], got_c.get(fld))
        for cid in got_cov:
            if cid not in want_cov:
                add(DIFF_EXTRA, "clause_coverage", cid, None, got_cov[cid], "expected 未登记该条款")
    elif coverage:
        add(DIFF_UNREG, "clause_coverage", "expected/clause_coverage.json", None,
            [{"requirement_id": c.get("requirement_id"), "coverage_state": c.get("coverage_state")}
             for c in coverage], "expected 未登记")

    # ---- 5. config_rejections
    want_rej = sorted(exp.get("config_rejections") or [])
    got_rej = sorted(r.get("code") for r in (rejections or []))
    if want_rej != got_rej:
        add(DIFF_COUNT, "config_rejections", "codes", want_rej, got_rej)

    return format_expected_diffs(results, records), exp, records


def format_expected_diffs(results, records):
    """把结构化差异渲染成可读文本。

    真实差异（FIELD/COUNT/MISSING/EXTRA）逐条打印「哪条 + 哪个字段 + 期望 vs 实际」；
    对命中差异的规则再附一行**实际全量字段**，QA 可直接照抄进 expected。
    UNREG 只提示、不算差异，因此不出现在这里（但会写进 expected_diff.json）。
    """
    lines = []
    real = [d for d in records if d.get("kind") in REAL_DIFF_KINDS]
    for d in real:
        loc = "%s.%s" % (d["scope"], d["field"]) if d.get("field") else str(d["scope"])
        line = "[%s] %s 期望=%s 实际=%s" % (d["kind"], loc,
                                       _fmt_diff_value(d.get("expected")),
                                       _fmt_diff_value(d.get("actual")))
        if d.get("note"):
            line += "（%s）" % d["note"]
        lines.append(line)
    by_rule = {}
    for r in results:
        # 条款级结果没有 rule_id，用 requirement_ids 作为键（与 compare_expected 的查找口径一致）
        by_rule[r.get("rule_id") or "/".join(r.get("requirement_ids") or [])] = r
    for rid in sorted({d["scope"] for d in real if d["scope"] in by_rule}):
        r = by_rule[rid]
        c = r.get("summary_counts") or {}
        lines.append("%s 实际全量：verdict=%s execution_status=%s reason_code=%s "
                     "total=%s evaluated=%s failed=%s indeterminate=%s skipped_upstream=%s "
                     "uninterpretable=%s findings=%s"
                     % (rid, r.get("verdict"), r.get("execution_status"), r.get("reason_code"),
                        c.get("records_total"), c.get("records_evaluated"), c.get("records_failed"),
                        c.get("records_indeterminate"), c.get("records_skipped_upstream"),
                        c.get("records_uninterpretable"), c.get("findings")))
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", action="append", help="指定示例包，可多次传入；默认全部")
    args = ap.parse_args()
    # GA-03 反例包 crs_same_unit_wrong：单位相同但 CRS 声明不同，必须 FAIL，
    # 用来钉死"只看单位、不看 CRS"或"按量级猜 CRS"这类回退实现。
    names = args.bundle or ["clean", "defective", "corrected", "ambiguous", "blocked",
                            "crs_same_unit_wrong"]

    overall_ok = True
    summary = []
    for name in names:
        bdir = EX / name
        if not bdir.exists():
            print("[MISS] bundle not found:", name)
            overall_ok = False
            continue
        k = Kernel(bdir)
        rejections = k.collect_config_rejections()
        problems = k.verify_quotes() + k.verify_parameter_sources()
        # 契约 §9.1：config_rejections 非空一律非 0 退出并打印 [REJECT]，
        # 不得因为"expected 恰好也写了 INDETERMINATE"就当作通过。
        # 完整拒绝清单（规则 ID + 原因码 + 证据）必须打到 stdout，不能只打一行标记。
        if rejections:
            overall_ok = False
            print("[REJECT] %s 配置校验未通过，拒绝执行（%d 项）：" % (name, len(rejections)))
            for r in rejections:
                print("   - [%s] %s：%s" % (r["code"], r["target"], r["detail"]))
        if problems:
            overall_ok = False
            print("[FAIL] %s 前置校验不通过（%d 项）：" % (name, len(problems)))
            for p in problems:
                print("   -", p)
        if rejections or problems:
            continue
        try:
            results, findings = k.run()
        except Exception as exc:  # noqa: BLE001 —— 门禁不得因未捕获异常给出"看起来正常"的退出码
            overall_ok = False
            print("[FAIL] %s 执行期异常：%s: %s" % (name, type(exc).__name__, exc))
            continue
        coverage = k.build_clause_coverage(results)
        agg, reason = aggregate(coverage, k.collect_config_rejections(), len(k.rows))
        outdir = write_outputs(name, k, results, findings, agg, reason, coverage)
        diffs, exp, diff_records = compare_expected(
            name, results, findings, agg, coverage=coverage,
            rejections=k.collect_config_rejections())
        # 结构化差异落盘，供 QA 在 TRUTH_REVIEW 里逐条登记（含 UNREG 提示）
        (outdir / "expected_diff.json").write_text(
            json.dumps({"bundle": name, "aggregate_verdict": agg, "diffs": diff_records},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        status = "PASS" if not diffs else "DIFF"
        if diffs:
            overall_ok = False
        summary.append((name, status, agg, len(findings), outdir))
        print("[%s] %-10s aggregate=%-13s findings=%-3d -> %s" % (status, name, agg, len(findings), outdir))
        for d in diffs:
            # 真实差异行带 [FIELD]/[COUNT]/[MISSING]/[EXTRA] 前缀；"实际全量"是给 QA 的底稿行
            print(("      - " if d.startswith("[") else "        ") + d)
    print("")
    print("ALL_OK=%s" % ("true" if overall_ok else "false"))
    return 0 if overall_ok else 1


# 登记表自检放在**模块导入期**：新增原因码忘了分类、风险信号码忘了登记，
# 都是启动即失败（RegistryError），而不是运行到某条规则才悄悄退回 FAIL。
check_registries()


if __name__ == "__main__":
    sys.exit(main())

