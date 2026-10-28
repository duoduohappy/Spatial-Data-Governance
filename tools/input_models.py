"""Stage 1：执行入口的**结构化输入校验**（Pydantic，strict 模式）。

对应最终复验报告 Stage 1 第 5 条与第二轮外部复验 S1-R2-01：用标准 Schema/Pydantic 在
**实际执行入口**校验输入，不再只靠单独跑 Schema 脚本。

纪律：
- **strict=True**：不接受 `"true"` → `True`、 `"1"` → `1` 这类隐式收敛（隐式类型是错误放行的温床）；
- 文档级**未知字段 `extra="allow"`**：Schema 演进不应误杀，但已知字段的类型/取值一律从严；
- **逐规则参数判别联合（S1-R2-01）**：`parameters` 不再只是 `Dict[str, Any]`，
  而是按 `rule_type` 分派到十类 strict 参数模型（与 `schemas/rule.schema.json` 的
  anyOf 分支逐条对齐）：必填键、空必需数组、错误类型、非法枚举、未知参数键、
  未知 rule_type 一律受控拒绝，**不得忽略参数后按默认值继续执行**；
- 校验失败 ⇒ 由 `stage0_gate.Kernel.collect_config_rejections()` 登记 `INPUT_SCHEMA_INVALID`
  （target 定位到具体 rule_id），整个包**拒绝执行**（契约 §2.4 / §9.1），不是 warnings。
  validate / compare / regress 三个入口都经 `collect_config_rejections` 走**同一套**校验。
"""
from __future__ import annotations

from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 取值枚举与 stage0_gate 保持同一来源（避免两处漂移）
CLAUSE_SUPPORT_STATUSES = ("SUPPORTED", "NEEDS_CLARIFICATION", "UNSUPPORTED")
RULE_STATUSES = ("APPROVED", "READY_FOR_REVIEW", "DRAFT", "NEEDS_CLARIFICATION", "REJECTED")
RULE_TYPES = ("required_field_present", "non_empty", "type_parse", "enum_value", "id_unique",
              "coord_range", "crs_declaration", "within_project_area", "freshness",
              "duplicate_candidate")

# strict 模式下数值字段：int / float 都接受（rule.schema.json 的 "number"），
# bool 一律拒绝（bool 是 int 的子类，strict 下 Pydantic 不会放它进数值字段）。
_NUMBER = Union[int, float]

# 与 rule.schema.json 的 freshness.reference_time 同一条 pattern
_REF_TIME_PATTERN = (r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"
                     r"(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$")


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")


class _Params(BaseModel):
    """参数模型基类：**额外键一律禁止**（additionalProperties=false）。"""
    model_config = ConfigDict(strict=True, extra="forbid")


# ---------------------------------------------------------------- 十类规则参数
class PRequiredFieldPresent(_Params):
    fields: List[str] = Field(min_length=1)


class PNonEmpty(_Params):
    fields: List[str] = Field(min_length=1)
    missing_rate_policy: Literal["STRICT"]
    trim: Optional[bool] = None
    allowed_missing_rate: Optional[_NUMBER] = Field(default=None, ge=0, le=1)


class PTypeParse(_Params):
    fields: List[str] = Field(min_length=1)


class PEnumValue(_Params):
    field: str = Field(min_length=1)
    allow_alias: bool


class PIdUnique(_Params):
    field: str = Field(min_length=1)


class PCoordRange(_Params):
    lon_range: List[_NUMBER] = Field(min_length=2, max_length=2)
    lat_range: List[_NUMBER] = Field(min_length=2, max_length=2)


class PCrsDeclaration(_Params):
    expected_crs: str = Field(pattern=r"^[A-Za-z0-9_.:+-]+$", min_length=1)
    expected_from_sidecar: Optional[bool] = None


class PWithinProjectArea(_Params):
    boundary_policy: Literal["inclusive", "exclusive"]


class PFreshness(_Params):
    reference_time: str = Field(pattern=_REF_TIME_PATTERN)
    max_age_days: _NUMBER = Field(ge=0)


class PDuplicateCandidate(_Params):
    max_distance_m: _NUMBER = Field(ge=0)
    name_equal: Optional[bool] = None


# rule_type → 参数模型（与 rule.schema.json anyOf 分支一一对应）
PARAM_MODELS = {
    "required_field_present": PRequiredFieldPresent,
    "non_empty": PNonEmpty,
    "type_parse": PTypeParse,
    "enum_value": PEnumValue,
    "id_unique": PIdUnique,
    "coord_range": PCoordRange,
    "crs_declaration": PCrsDeclaration,
    "within_project_area": PWithinProjectArea,
    "freshness": PFreshness,
    "duplicate_candidate": PDuplicateCandidate,
}


class ParameterSource(_Strict):
    parameter: str
    requirement_id: str
    document_id: str
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_line_start: int = Field(ge=1)
    source_line_end: int = Field(ge=1)
    source_quote: str
    value_literal: Optional[List[Any]] = None
    unit: Optional[str] = None
    interpretation: Optional[str] = None
    reviewer: Optional[str] = None
    approved_at: Optional[str] = None


class Requirement(_Strict):
    requirement_id: str
    document_id: str
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_line_start: int = Field(ge=1)
    source_line_end: int = Field(ge=1)
    source_quote: str
    required_for_release: bool
    support_status: str = Field(pattern=r"^(SUPPORTED|NEEDS_CLARIFICATION|UNSUPPORTED)$")
    dependencies: Optional[List[str]] = None
    ambiguities: Optional[List[str]] = None


class RecordScope(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    field: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    equals: str = Field(min_length=1, max_length=80)
    requirement_id: str = Field(min_length=1)


class Rule(_Strict):
    rule_id: str
    scope: Optional[RecordScope] = None
    requirement_ids: List[str] = Field(min_length=1)
    rule_type: Literal["required_field_present", "non_empty", "type_parse", "enum_value",
                       "id_unique", "coord_range", "crs_declaration", "within_project_area",
                       "freshness", "duplicate_candidate"]
    status: str = Field(pattern=r"^(APPROVED|READY_FOR_REVIEW|DRAFT|NEEDS_CLARIFICATION|REJECTED)$")
    required_for_release: Optional[bool] = None
    version: Optional[int] = None
    reviewer: Optional[str] = None
    approved_at: Optional[str] = None
    notes: Optional[str] = None
    parameters: Optional[dict] = None
    parameter_sources: Optional[List[ParameterSource]] = None
    preconditions: Optional[List[str]] = None

    @model_validator(mode="after")
    def _validate_parameters(self):
        """逐规则参数判别（S1-R2-01）：按 rule_type 分派到对应 strict 参数模型。

        - `parameters` 缺失 / 不是映射 ⇒ 拒绝（每类规则都必须显式声明参数）；
        - 缺必填键、空必需数组、错误类型、非法枚举、未知参数键 ⇒ 拒绝；
        - 拒绝时**不得**忽略参数后按默认值继续执行（那等于换了一把没人批准过的尺子）。
        """
        if 'scope' in self.model_fields_set and self.scope is None:
            raise ValueError('Omit an absent scope; explicit null scope is invalid')
        if self.scope is not None and self.rule_type != 'freshness':
            raise ValueError('Record scope is only supported by freshness in v0.6')
        params = self.parameters
        if params is None:
            raise ValueError("缺少 parameters：%s 规则必须显式声明参数（不得按默认值执行）"
                             % self.rule_type)
        if not isinstance(params, dict):
            raise ValueError("parameters 必须是映射，实际为 %s" % type(params).__name__)
        model = PARAM_MODELS[self.rule_type]
        try:
            model.model_validate(params)
        except Exception as exc:  # noqa: BLE001 —— 取 pydantic 的错误行即可
            raise ValueError("parameters 不满足 %s 的约束：%s"
                             % (self.rule_type, _fmt(exc))) from exc
        return self


class RequirementsDoc(_Strict):
    schema_version: Optional[int] = None
    bundle: Optional[str] = None
    reference_time: Optional[str] = None
    requirements: List[Requirement]


class RulesDoc(_Strict):
    schema_version: Optional[int] = None
    bundle: Optional[str] = None
    rules: List[Rule]


def validate_inputs(req_doc, rule_doc):
    """校验两份配置文档，返回 [(target, detail)]；非空即表示输入不可信。

    target 尽量定位到具体 `rule_id`（而非只到文档名），这样：
    - 门禁输出里能逐条看是哪条规则非法；
    - `Kernel.rejected_rule_ids()` 能把被拒规则挡在业务结论之外；
    - compare 的关闭证据检查能识别"该规则被配置校验拒绝"。
    """
    problems = []
    try:
        RequirementsDoc.model_validate(req_doc)
    except Exception as exc:  # noqa: BLE001 —— pydantic 的异常类型随版本变化，取消息即可
        problems.append(("requirements.yaml", _fmt(exc)))
    if not isinstance(rule_doc, dict):
        problems.append(("approved-rules.yaml",
                         "rules 文档必须是映射，实际为 %s" % type(rule_doc).__name__))
        return problems
    rules = rule_doc.get("rules")
    if not isinstance(rules, list):
        problems.append(("approved-rules.yaml",
                         "rules 必须是列表，实际为 %s" % type(rules).__name__))
        return problems
    # 文档级字段（rules 以外）也过一遍
    try:
        RulesDoc.model_validate(dict(rule_doc, rules=[]))
    except Exception as exc:  # noqa: BLE001
        problems.append(("approved-rules.yaml", _fmt(exc)))
    for r in rules:
        if not isinstance(r, dict):
            problems.append(("approved-rules.yaml",
                             "规则项必须是映射，实际为 %s" % type(r).__name__))
            continue
        rid = r.get("rule_id")
        target = str(rid) if isinstance(rid, str) and rid.strip() else "approved-rules.yaml"
        try:
            Rule.model_validate(r)
        except Exception as exc:  # noqa: BLE001
            problems.append((target, _fmt(exc)))
    return problems


def _fmt(exc) -> str:
    """把 pydantic 的错误压成一行一条，便于在门禁输出里逐条看。"""
    try:
        errs = exc.errors()
    except Exception:  # noqa: BLE001
        return str(exc)
    lines = []
    for e in errs[:10]:
        loc = ".".join(str(x) for x in e.get("loc") or [])
        lines.append("%s: %s" % (loc or "<root>", e.get("msg")))
    if len(errs) > 10:
        lines.append("...（其余 %d 条省略）" % (len(errs) - 10))
    return " | ".join(lines)
