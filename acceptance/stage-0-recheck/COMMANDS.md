# 实际执行的命令与结果

- 日期：2026-10-26　执行人：严过关（QA）
- 环境：Windows-11-10.0.26200-SP0，Python 3.13.14，工作区 `geoacceptance`，分支 `main`
- 所有命令按本文件顺序执行，输出为**原始拷贝**（路径中的绝对路径已保留，未做美化）
- 完整原始输出：`gate.txt` / `selfcheck-guards.txt` / `schema-consistency.txt` / `deps-smoke.txt`

---

## C1　端到端门禁（六包记录级比对）

```
$ python tools/stage0_gate.py
[PASS] clean      aggregate=PASS          findings=1   -> ...\work\stage0\clean
[PASS] defective  aggregate=FAIL          findings=11  -> ...\work\stage0\defective
[PASS] corrected  aggregate=PASS          findings=1   -> ...\work\stage0\corrected
[PASS] ambiguous  aggregate=INDETERMINATE findings=1   -> ...\work\stage0\ambiguous
[PASS] blocked    aggregate=FAIL          findings=1   -> ...\work\stage0\blocked
[PASS] crs_same_unit_wrong aggregate=FAIL          findings=1   -> ...\work\stage0\crs_same_unit_wrong

ALL_OK=true
```

退出码 **0**。六包全部走**记录级**比对（`verdict / execution_status / reason_code` 字段级 +
六个统计字段 + `findings` 数量级 + `expected/findings.json` 逐条 + `expected/clause_coverage.json` 逐条）。

## C2　护栏负面自检（7 项）

```
$ python tools/selfcheck_guards.py
[PASS] A 伪造引用必须被拦截：拦截信息：A1 引用内容与第 7 行不一致
  期望: A1. 必填字段必须存在（改写后的伪引用）。
  实际: A1. 每条记录必须包含全部必填字段
[PASS] A 反向确认：未变异包不得报错：clean 原始包前置校验为空
[PASS] B 无来源阈值必须被拦截：拦截信息：[PARAMETER_VALUE_MISMATCH] R09：参数 max_age_days 的实际值 365 与其批准来源记录的值 30
[PASS] C 产物 mode 一致性检查（已产出 manifest 全部为 manual）：检查 manifest 6 个，非 manual 的 0 个
[PASS] C2 注入 mode=live 的产物必须被拦截：扫描 work/negatives 命中非 manual 1 个：['neg_live_mode']
[PASS] C2 mode=live 的 manifest 对象必须被政策校验拒绝：拦截信息：mode='live'，Stage 0 只允许 manual（本阶段无模型调用，不得标示为 live）
[PASS] C2 反向确认：改回 manual 后不得报错：manual manifest 的政策校验为空
[PASS] D 空数据不得判定通过：实际=INDETERMINATE（零记录/零必检条款不得判定通过）
[PASS] E 缺 CRS 声明不得判 FAIL（必须 INDETERMINATE）：总体=INDETERMINATE（...）；空间规则={'R06': ('INDETERMINATE','BLOCKED'), 'R08': ('INDETERMINATE','BLOCKED'), 'R10': ('INDETERMINATE','BLOCKED')}
[PASS] F 候选不得计入失败（clean R10 failed=0 / indeterminate=2）：R10 summary_counts={"findings":1,"records_blocked":0,"records_evaluated":12,"records_failed":0,"records_indeterminate":2,"records_skipped_upstream":0,"records_total":12,"records_uninterpretable":0}
[PASS] G 未知依赖必须被拒（不得静默过滤）：config_rejections 原因码=['UNKNOWN_PRECONDITION']

GUARDS_OK=true
```

退出码 **0**。7 项分组 = A / B / **C（含 C2 真注入负面）** / D / E / F / G。
「反向确认」三条（A、C2、以及"无变异不报错"）是为了排除"永远失败的假护栏"。

## C3　Schema 一致性（标准库子集实现）

```
$ python tools/check_schema_consistency.py
========================================================================
支持（参与校验）的关键字全集 [22]：$ref, additionalProperties, allOf, anyOf, const, enum,
  exclusiveMaximum, exclusiveMinimum, items, maxItems, maxLength, maximum, minItems,
  minLength, minimum, not, oneOf, pattern, properties, required, type, uniqueItems
已知但不参与校验 [8]：$schema, additionalItems, default, definitions, deprecated,
  description, examples, title

支持（参与校验）的关键字 [16]：$ref, additionalProperties, allOf, anyOf, const, enum, items,
  maxItems, maximum, minItems, minLength, minimum, pattern, properties, required, type
已知但不参与校验的关键字 [3]：$schema, description, title
子集外关键字：（无）

十类规则参数约束负例：10 条，全部按预期被拦下 = True

示例包文档校验：6 个包

登记表一致性：原因码 35（FAIL 31 / CANDIDATE 1 / INDETERMINATE 3；其中 finding 可用 19、规则级专用 16）、风险信号码 3

产物校验：report.json 6 个、run_manifest.json 6 个

[PASS] 全部一致性检查通过（子集范围内无不支持关键字被静默跳过）
SCHEMA_CONSISTENT=true
```

退出码 **0**。注意 `INDETERMINATE 3` —— 本轮把 `TIMEZONE_UNDECLARED` 从 FAIL 类移到缺证据类之后，
三分类仍互斥且完备（登记表在**模块导入期**自检，不互斥即启动失败）。

## C4　回归套件 + 对拍

```
$ python tools/recheck_probes.py --probes-script C:/Users/TempAdmin/Documents/Codex/2026-10-26/mu/outputs/stage0_independent_probes.py
...（20 项逐条输出，见 independent-results.json）
------------------------------------------------------------------------------
对拍：原独立探针 stage0_independent_probes.py 跑在当前仓库
  [OK] required_supported_clause_without_rule   实测="INDETERMINATE"
  [OK] missing_crs_declaration                  实测="INDETERMINATE"
  [OK] unexpected_crs_with_degree_unit          实测="FAIL"
  [OK] unknown_dependency                       实测="INDETERMINATE"
  [OK] mandatory_clause_downgraded              实测="INDETERMINATE"
  [OK] substring_threshold_3_in_30              实测=["[PARAMETER_VALUE_MISMATCH] ...", "[PARAMETER_SOURCE_NOT_FOUND] ..."]
  [OK] wrong_document_hash                      实测=["[DOCUMENT_HASH_MISMATCH] A1 声明的文档哈希与实际不一致 ..."]
  对拍结论：全部不再产出 PASS

==============================================================================
RECHECK_PROBES_OK=true（20/20 通过，输出：...\acceptance\stage-0-recheck\independent-results.json）
==============================================================================
```

退出码 **0**。20 项 = 原独立验收 11 项 + 上一轮新增 5 项 + 最终回归轮新增 4 项
（`NEW_i7_i9_counterexamples` / `NEW_reason_code_arrays` / `NEW_schema_registry_parity` /
`NEW_compat_path_i7_i9_failclosed`）。

## C5　修复前基准（不是猜的，是重跑出来的）

```
$ git -c core.autocrlf=false worktree add ../geoacceptance-baseline-d057c0a d057c0a
$ python stage0_independent_probes.py ../geoacceptance-baseline-d057c0a
required_supported_clause_without_rule      EXPECTED INDETERMINATE          ACTUAL PASS
missing_crs_declaration                     EXPECTED INDETERMINATE          ACTUAL FAIL
unexpected_crs_with_degree_unit             EXPECTED FAIL_OR_INDETERMINATE  ACTUAL PASS
unknown_dependency                          EXPECTED REJECT_OR_INDETERMINATE ACTUAL PASS
substring_threshold_3_in_30                 EXPECTED rejection              ACTUAL []
candidate_not_failed_but_blocked            {'findings': 1, 'records_evaluated': 11, 'records_blocked': 1}
schema_invalid_verdicts                     3
input_manifest_mismatches                   []
exclusive_boundary                          {'(0, 0.5)': True, '(1, 0.5)': False, '(0.5, 0)': True, '(0.5, 1)': False}
mandatory_clause_downgraded_in_rule         EXPECTED FAIL_OR_REJECT         ACTUAL PASS
wrong_document_hash                         EXPECTED rejection              ACTUAL []
```

结果落盘为 `baseline-independent-results.json`（11 项）。

> **踩坑记录（如实写）**：第一次建 worktree 时用了默认配置，本机 `core.autocrlf=true`，
> 检出把 LF 转成 CRLF，导致 `input_manifest_mismatches` 报出 **40 个文件全部失配**。
> 这是**检出环境**问题，不是仓库缺陷；加 `-c core.autocrlf=false` 后为 0。
> 曾作为 OPEN_ISSUES **S0-R3** 记录；**现已由 `2a22ff3` 关闭**——仓库根新增 `.gitattributes`
> 固定 LF，此后默认检出也不再失配（`INPUT_MANIFEST` 探针已回到 0 处不一致）。

## C6　expected 改动核对（**最终回归轮刷新**）

```
$ git diff --numstat examples/
24	24	examples/INPUT_MANIFEST.json
129	5	examples/TRUTH_REVIEW.md
40	16	examples/ambiguous/expected/aggregate.json
33	11	examples/ambiguous/expected/clause_coverage.json
34	12	examples/blocked/expected/aggregate.json
29	9	examples/blocked/expected/clause_coverage.json
32	12	examples/clean/expected/aggregate.json
27	9	examples/clean/expected/clause_coverage.json
32	12	examples/corrected/expected/aggregate.json
27	9	examples/corrected/expected/clause_coverage.json
34	12	examples/crs_same_unit_wrong/expected/aggregate.json
29	9	examples/crs_same_unit_wrong/expected/clause_coverage.json
53	19	examples/defective/expected/aggregate.json
41	9	examples/defective/expected/clause_coverage.json
```

说明：本轮的行数差异包含**上一轮（T05-a）已提交的部分**（per_rule 记录级结构升级、truth_review、
UNKNOWN→INDETERMINATE、clean R10 口径、A3 interpretation 等，见 `TRUTH_REVIEW.md` §3.1–§3.8），
以及**本轮新增**的 §3.9（24 条 `reason_code`）与 §3.10（18 处非空 `failure_reason_codes`
+ 118 个条目的首次登记 + 6 个包的 `truth_review.reviewed_fields`）。
`requirements.yaml` / `README.md` 上一轮已提交，本轮不再出现在 diff 中。

**行级 diff 不可用于计数**（同步脚本重写了文件缩进与键序），逐条计数见 **C11 的语义级比对**。

**核对结论**：`examples/*/expected/` 下没有 §3 之外的字段或结论变化（语义级比对"其他差异"只有
6 条 `truth_review.reviewed_fields` 文案，已在 §3.10 第 43 条登记）；
六个包的 `aggregate_verdict` 与 `findings` 条数前后完全一致。

## C7　零第三方依赖核验

```
$ grep -rE "import (geopandas|shapely|pyproj|pydantic|jsonschema|pandas|pytest)" --include=*.py .
（空）
```

退出码 1（无匹配），即**零第三方依赖**。

## C8　无 UNKNOWN 作为业务结论

```
$ grep -rn "UNKNOWN" examples/*/expected/
（空）
$ grep -rn "UNKNOWN" --include=*.py --include=*.json --include=*.md --include=*.yaml . | grep -v "^./work/"
acceptance/stage-0/TEST_RESULTS.md:60-62   # 历史记录，已在本轮补「作废标注」
docs/**                                     # 契约与任务文档中的"废止 UNKNOWN"表述
schemas/check_result.schema.json:12         # "三态业务结论；UNKNOWN 已废止（GA-06）"
tools/stage0_gate.py                        # UNKNOWN_PRECONDITION / BOUNDARY_POLICY_UNKNOWN / *_UNKNOWN_* 等**原因码**，不是 verdict
```

```
$ python -c "扫 work/stage0/*/report.json 的 check_results，统计 verdict=='UNKNOWN' 或 execution_status=='UNKNOWN'"
work/ artifacts UNKNOWN count = 0
```

**结论**：作为 **verdict 取值**的 `UNKNOWN` 已全库清零（产物侧实测 0 条）；唯一残留是
`acceptance/stage-0/TEST_RESULTS.md` 的历史输出表（已补作废标注，不做改写）。`schemas/check_result.schema.json` 的枚举为
`PASS / FAIL / INDETERMINATE`，与实际产出一致（`check_schema_consistency.py` 逐包校验了 6 个 `report.json`）。

## C9　本轮一行代码修复的独立核验

```
$ python - <<'EOF'
import re, sys; sys.path.insert(0,'tools'); import stage0_gate as g
print('registries OK:', g.check_registries())
print('TIMEZONE_UNDECLARED class =', g.classify_reason_code('TIMEZONE_UNDECLARED'))
EOF
registries OK: True
TIMEZONE_UNDECLARED class = INDETERMINATE
```

```
$ grep -rEn "T[0-9]{2}:[0-9]{2}(:[0-9]{2})?(,|$)" examples/*/poi.csv
（空）
```

即：六个包**没有任何不带时区的时间戳**，所以把 `TIMEZONE_UNDECLARED` 归位到「缺证据」类对六个包
**零影响**（回归套件 `NEW_timezone_undeclared_fails_closed` 实测六包产生 0 条该类 finding）。

## C10　重生成幂等性

```
$ python - <<'EOF'
import hashlib, subprocess
from pathlib import Path
root = Path('.')
def snap():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.glob('examples/**/*')) if p.is_file()}
a = snap(); subprocess.run(['python','tools/make_examples.py'],capture_output=True); b = snap()
subprocess.run(['python','tools/make_examples.py'],capture_output=True); c = snap()
print('第一次重生成相对基线发生变化的文件:', [k for k in a if a[k]!=b[k]] or '无')
print('第二次重生成相对第一次发生变化的文件:', [k for k in b if b[k]!=c[k]] or '无')
EOF
第一次重生成相对基线发生变化的文件: 无
第二次重生成相对第一次发生变化的文件: 无
```

重生成**不构成真值证明**（契约 §9.6）：它在这里只用于验证生成脚本里的真值字典与落盘内容一致，
以及重算 `INPUT_MANIFEST.json`。

---

## C11　24 条 expected 差异的**独立核实**（语义级，不看行号）

不采信工程师清单，也不看行级 diff（同步脚本重写了缩进与键序，行级 diff 无法计数）。
做法：把 `HEAD` 版本的 expected 与工作区版本做**逐字段语义比对**，枚举每一处叶子差异。

```
$ python - <<'EOF'
import json, subprocess
BUNDLES = ["clean","defective","corrected","ambiguous","blocked","crs_same_unit_wrong"]
def head(p): return json.loads(subprocess.run(["git","show","HEAD:"+p],
                               capture_output=True,text=True).stdout)
def cur(p):  return json.loads(open(p,encoding='utf-8').read())
def walk(a,b,path,out):
    if isinstance(a,dict) and isinstance(b,dict):
        for k in sorted(set(a)|set(b)): walk(a.get(k),b.get(k),path+"/"+str(k),out)
    elif isinstance(a,list) and isinstance(b,list):
        if len(a)==len(b):
            for i,(x,y) in enumerate(zip(a,b)): walk(x,y,path+"[%d]"%i,out)
        else: out.append((path,"LIST_LEN",len(a),len(b)))
    elif a!=b: out.append((path,"FIELD",a,b))
tot=[]
for b in BUNDLES:
    for f in ["expected/aggregate.json","expected/clause_coverage.json","expected/findings.json"]:
        p="examples/%s/%s"%(b,f); out=[]; walk(head(p),cur(p),"",out)
        tot += [(p,)+r for r in out]
rc  = [t for t in tot if t[1].endswith("/reason_code")]
frc = [t for t in tot if t[1].endswith("failure_reason_codes")]
adv = [t for t in tot if t[1].endswith("advisory_reason_codes")]
print("总差异:",len(tot),"| reason_code:",len(rc),
      "| failure:",len(frc),"非空:",len([t for t in frc if t[4]]),
      "| advisory:",len(adv),"非空:",len([t for t in adv if t[4]]))
print("其他差异:",[(t[0],t[1]) for t in tot if t not in rc and t not in frc and t not in adv])
EOF

总差异: 266 | reason_code: 24 | failure: 118 非空: 18 | advisory: 118 非空: 0
其他差异: [6 个包的 expected/aggregate.json 的 /truth_review/reviewed_fields]
```

**结论：`reason_code` 差异恰好 24 条，与工程师清单逐条一致**（clean 1 / defective 15 /
corrected 1 / ambiguous 3 / blocked 2 / crs_same_unit_wrong 2），无多无少。逐条清单（24 行）：

```
clean/expected/aggregate.json                        /per_rule/R10/reason_code    OK -> DUPLICATE_CANDIDATE
defective/expected/aggregate.json                    /per_rule/R02/reason_code    OK -> EMPTY_VALUE
defective/expected/aggregate.json                    /per_rule/R03/reason_code    OK -> TYPE_PARSE_ERROR
defective/expected/aggregate.json                    /per_rule/R04/reason_code    OK -> ENUM_VIOLATION
defective/expected/aggregate.json                    /per_rule/R05/reason_code    OK -> DUPLICATE_ID
defective/expected/aggregate.json                    /per_rule/R06/reason_code    OK -> LATITUDE_OUT_OF_RANGE
defective/expected/aggregate.json                    /per_rule/R08/reason_code    OK -> OUTSIDE_PROJECT_AREA
defective/expected/aggregate.json                    /per_rule/R09/reason_code    OK -> STALE_RECORD
defective/expected/aggregate.json                    /per_rule/R10/reason_code    OK -> ALL_RECORDS_BLOCKED
defective/expected/clause_coverage.json              /clause_coverage[1]/reason_code OK -> EMPTY_VALUE
defective/expected/clause_coverage.json              /clause_coverage[2]/reason_code OK -> TYPE_PARSE_ERROR
defective/expected/clause_coverage.json              /clause_coverage[3]/reason_code OK -> ENUM_VIOLATION
defective/expected/clause_coverage.json              /clause_coverage[4]/reason_code OK -> DUPLICATE_ID
defective/expected/clause_coverage.json              /clause_coverage[5]/reason_code OK -> LATITUDE_OUT_OF_RANGE
defective/expected/clause_coverage.json              /clause_coverage[7]/reason_code OK -> OUTSIDE_PROJECT_AREA
defective/expected/clause_coverage.json              /clause_coverage[8]/reason_code OK -> STALE_RECORD
corrected/expected/aggregate.json                    /per_rule/R10/reason_code    OK -> DUPLICATE_CANDIDATE
ambiguous/expected/aggregate.json                    /per_rule/D1/reason_code     NOT_APPROVABLE_NO_THRESHOLD -> CLAUSE_NOT_COVERED_BY_RULE
ambiguous/expected/aggregate.json                    /per_rule/D2/reason_code     NOT_APPROVABLE_NO_THRESHOLD -> CLAUSE_NOT_COVERED_BY_RULE
ambiguous/expected/aggregate.json                    /per_rule/R10/reason_code    OK -> DUPLICATE_CANDIDATE
blocked/expected/aggregate.json                      /per_rule/R07/reason_code    OK -> CRS_DECLARATION_MISMATCH
blocked/expected/clause_coverage.json                /clause_coverage[6]/reason_code OK -> CRS_DECLARATION_MISMATCH
crs_same_unit_wrong/expected/aggregate.json          /per_rule/R07/reason_code    OK -> CRS_DECLARATION_MISMATCH
crs_same_unit_wrong/expected/clause_coverage.json    /clause_coverage[6]/reason_code OK -> CRS_DECLARATION_MISMATCH
```

`expected/findings.json` 六包**零差异**（本轮不动它）。

## C12　判据 11/14/15 的**自建反例**（不复用工程师输出）

三条已固化进 `tools/recheck_probes.py`，可重复执行：

```
$ python tools/recheck_probes.py   # 20/20，其中四条为本轮新增
```

**① `NEW_i7_i9_counterexamples`** —— 12 组 `assert_reason_compat` + 3 组 `make_result` + 1 组端到端：

| 组合 | 实测 | 期望 |
|---|---|---|
| PASS + OK | NO_RAISE | 不抛 |
| PASS + EMPTY_VALUE | ContractViolation | 抛（I7） |
| PASS + DUPLICATE_CANDIDATE | ContractViolation | 抛（I7） |
| FAIL + OK | ContractViolation | 抛（I8） |
| FAIL + DUPLICATE_CANDIDATE | ContractViolation | 抛（I8：候选码不是失败码） |
| FAIL + CRS_MISSING_DECLARATION | ContractViolation | 抛（I8：缺证据码不是失败码） |
| FAIL + EMPTY_VALUE | NO_RAISE | 不抛 |
| INDETERMINATE + OK | ContractViolation | 抛（I9） |
| INDETERMINATE + EMPTY_VALUE | ContractViolation | 抛（I9：可判失败的码不得挂未定） |
| INDETERMINATE + DUPLICATE_CANDIDATE | NO_RAISE | 不抛 |
| INDETERMINATE + ALL_RECORDS_BLOCKED | NO_RAISE | 不抛 |
| INDETERMINATE + CRS_MISSING_DECLARATION | NO_RAISE | 不抛 |

`make_result` 三例（FAIL+OK / FAIL+DUPLICATE_CANDIDATE / INDETERMINATE+OK）**全部抛**
`ContractViolation`。

端到端：注入一条 `reason_code="OK"` 的 finding（绕过 `Kernel.finding` 自带的 RESULT_ONLY 校验，
模拟"规则处理器标错码"）→ 该规则落成
`{verdict: INDETERMINATE, execution_status: FAILED, reason_code: CONTRACT_VIOLATION}`，
总体 `INDETERMINATE`（**失败关闭，未放行**）。
附带事实：`Kernel.finding("OK")` 自身也抛 `ContractViolation`（第一道网），即 I8 分支是**纵深防御**。

**② `NEW_reason_code_arrays`（判据 14）** —— 去重 / 首次出现顺序 / 「第一条」= 排放顺序：

```
_unique_ordered(["A","B","A","C","B","A"]) -> ["A","B","C"]
端到端注入（行号 10 → 4 → 8，码 EMPTY_VALUE → ENUM_VIOLATION → EMPTY_VALUE）：
  emission_order       = ["EMPTY_VALUE","ENUM_VIOLATION","EMPTY_VALUE"]
  emission_lines       = [10, 4, 8]
  failure_reason_codes = ["EMPTY_VALUE","ENUM_VIOLATION"]     # 去重后保留首次出现顺序
  reason_code          = "EMPTY_VALUE"                        # 「第一条」按排放顺序，不是行号升序
```

若实现按行号重排，「第一条」会错成 `ENUM_VIOLATION` —— 这条就是用来钉死它的。
另对六包全量重算 I7–I9 与数组自洽：**0 条违反**
（clean/defective/corrected/blocked/crs 各 10 结果 + 9 条款；ambiguous 12 结果 + 11 条款）。

**③ `NEW_schema_registry_parity`（判据 15/16）** —— 声明 + **篡改反证**：

```
declared      = {failure_reason_codes: array, advisory_reason_codes: array}
unique_items  = {failure_reason_codes: true,  advisory_reason_codes: true}
enum_fail_n   = 15        enum_advisory = [CRS_MISSING_DECLARATION, CRS_EXPECTED_NOT_APPROVED, TIMEZONE_UNDECLARED]
baseline      = {exit_code: 0, consistent: true}
篡改：删掉 failure_reason_codes 枚举里的 FUTURE_TIMESTAMP
  -> exit_code 1, [REGISTRY_PARITY] check_result.schema.json 的 failure_reason_codes 枚举与
     FAIL 类 ∩ FINDING_REASON_CODES 不一致：仅 Schema 有=[]；仅代码有=['FUTURE_TIMESTAMP']
restored      = true（篡改后已还原，sha256 回到原值）
```

## C13　判据 11/12/14/15 的**全库扫描**（扫实际产物，不扫期望）

```
$ python - <<'EOF'
# 扫 work/stage0/*/report.json 的全部 check_results + clause_coverage
EOF
判据 11 违反（verdict != PASS 且 reason_code == "OK"）: []
判据 15 违反（I7 / I8 / I9 分类）: []
判据 14 问题: 无
非空 failure/advisory 登记:
  blocked R07 ['CRS_DECLARATION_MISMATCH']         crs_same_unit_wrong R07 ['CRS_DECLARATION_MISMATCH']
  defective R02 ['EMPTY_VALUE']  R03 ['TYPE_PARSE_ERROR']  R04 ['ENUM_VIOLATION']
  defective R05 ['DUPLICATE_ID'] R06 ['LATITUDE_OUT_OF_RANGE']
  defective R08 ['OUTSIDE_PROJECT_AREA']  R09 ['STALE_RECORD']
  （advisory_reason_codes 非空：0 处 —— 见 OPEN_ISSUES S0-R6）
判据 12 D1/D2 双口径:
  ambiguous: check_results {D1: CLAUSE_NOT_COVERED_BY_RULE, D2: CLAUSE_NOT_COVERED_BY_RULE}
             clause_coverage {D1: CLAUSE_NOT_COVERED_BY_RULE, D2: CLAUSE_NOT_COVERED_BY_RULE}
  -> 一致
coverage_state 出现过的态: {COVERED: 6 个包, UNMAPPED: [ambiguous]}
无正例的态: [CONFIG_REJECTED, MISSING_RESULT, NO_IMPLEMENTATION, UNAPPROVED]   # 判据 13
work/ artifacts UNKNOWN count = 0
```

## C14　判据 15 双路径 + 判据 17（手工构造 results 走两参兼容路径）

不读工程师的对照输出，自己构造。已固化为探针 `NEW_compat_path_i7_i9_failclosed`，
20/20 中的一条；下面是一次性复现命令与实测（运行于最终 HEAD `e2e9124` 之后）：

```
$ python - <<'EOF'
import sys; sys.path.insert(0,'tools'); import stage0_gate as g
def mk(rid, cid, verdict, status, reason, **over): ...   # 构造 CheckResult
# ① 仅候选 finding 的规则（映射到必检条款 A2，rule_id 必须用包内真实存在的 R02）
cand = [mk("R02","A2","INDETERMINATE","COMPLETED","OK",
           counts={"records_indeterminate":2,"findings":1})]
EOF

S1 仅候选（C2）               -> verdict=INDETERMINATE  reason=存在必检条款未通过：C2(COVERED/DUPLICATE_CANDIDATE)
   兼容 vs 权威（A2 判定字段）-> 一致：
     兼容 {requirement_id:A2, coverage_state:COVERED, verdict:INDETERMINATE,
           execution_status:COMPLETED, reason_code:DUPLICATE_CANDIDATE}
     权威 {requirement_id:A2, coverage_state:COVERED, verdict:INDETERMINATE,
           execution_status:COMPLETED, reason_code:DUPLICATE_CANDIDATE}
S5 无码可取的兜底             -> INDETERMINATE / C2(COVERED/CONTRACT_VIOLATION)   # 不回退 OK
S2 I9 违反（INDETERMINATE + EMPTY_VALUE） -> INDETERMINATE
     「兼容路径输入的 reason_code 违反 I7–I9（契约 §3.5.1）：I9 违反：INDETERMINATE 的 reason_code
       不得是可判失败的码，实际='EMPTY_VALUE'」
S3 I7 违反（PASS + EMPTY_VALUE）          -> INDETERMINATE
     「…I7 违反：PASS 的 reason_code 必须是 OK，实际='EMPTY_VALUE'」
S4 I8 违反（FAIL + OK）                   -> INDETERMINATE
     「…I8 违反：FAIL 不得携带 OK（§3.5.1：须为第一条 FAIL 类 finding 的码）」
S6 正常（PASS + OK）          -> PASS / 全部必检条款均有完整有效的 PASS 证据

六个真实包：兼容路径 vs 权威路径
  clean               PASS          / PASS           一致=True
  defective           FAIL          / FAIL           一致=False（仅理由字符串中的条款顺序）
      compat_reason = 存在必检条款 FAIL：A2(...),A3(...),A4(...),A5(...),C1(STALE_RECORD),B1(...),B3(...)
      auth_reason   = 存在必检条款 FAIL：A2(...),A3(...),A4(...),A5(...),B1(...),B3(...),C1(STALE_RECORD)
  corrected           PASS          / PASS           一致=True
  ambiguous           INDETERMINATE / INDETERMINATE  一致=True
  blocked             FAIL          / FAIL           一致=True
  crs_same_unit_wrong FAIL          / FAIL           一致=True
```

**判据 17 结论**：三例违规输入（`raised = null`）**全部返回 `INDETERMINATE` + 违规说明，
没有 traceback**。对拍时原独立探针若抛栈，可按此区分「输入违反 I7–I9」与「实现 bug」。

**判据 15 双路径结论**：仅候选规则产出 `DUPLICATE_CANDIDATE` 而非 `INDETERMINATE + OK`，
与权威路径的判定字段逐字段一致。

**一处如实记录**：`defective` 的总体理由字符串里，兼容路径与权威路径的**条款列举顺序不同**
（结论、失败条款集合、各条款原因码全部相同）。已登记为 `OPEN_ISSUES.md` **S0-R8**，不计为失败。

### C14.1　git 历史改写的独立复核

```
$ git log --oneline -8
535aa3d docs(recheck/T05-e): 回填最终回归提交 SHA 到 HANDOFF 第 4 节与第 8 节
da1d946 test(recheck): expected 同步 reason_code 全链路取值、16 项判据终验、验收材料刷新
e2e9124 fix(recheck): aggregate 兼容分支捕获契约违规，返回 INDETERMINATE 而非抛栈
8048245 docs(arch): I7-I9 违反处置统一为 fail-closed 且不丢失结论
dedc2f9 fix(recheck): 兼容路径接入 I7-I9 断言、FAIL 取值链源头去掉 OK 兜底
1fd2b21 fix(recheck): reason_code 全链路遵守 I7-I9，去重与取值链按契约 §3.5.1/§3.5.2，新字段入 Schema
f433286 fix(recheck): 规则级与条款级 reason_code 全面遵守 I7-I9，兼容条目与 clause_coverage 权威口径对齐
c16397f docs(arch): 明确 reason_code 取值链——第一条定义、附带字段去重、候选类与 CONTRACT_VIOLATION 兜底
$ git log --all --oneline | grep -c c83539c     # 0 —— 该 SHA 已不在历史中（amend 误吞后软回退重做）
```

`dedc2f9` ≡ 原 `c83539c`、`8048245` ≡ 原 `c582648`（内容相同，提交信息已修正）。
事故与修复方式登记在 `OPEN_ISSUES.md` §1.1b 与 `HANDOFF.md` §4.1。
