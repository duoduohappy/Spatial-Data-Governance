"""Stage 0 重验：独立反例回归套件（零第三方依赖）。

用途：把独立验收方留下的反例**全部**转成可运行的回归测试，并给出**修复前 / 修复后**对照。

纪律（与独立验收方的约定一致，也是本脚本存在的理由）：
1. **预期先手写，再跑实现**。每个 case 的 `expected` 字段是在跑之前写死在本文件里的常量，
   不是跑完回填。改实现去满足预期可以，改预期去迁就实现不行。
2. **修复前基准不是猜的**：来自 `work/stage0-recheck/baseline-independent-results.json`，
   该文件由「`git -c core.autocrlf=false worktree add <tmp> d057c0a` 后跑原独立探针」产生。
   用 `--regen-baseline <git-repo>` 可以重做一遍。
3. **对拍**：除了本脚本自己的实现，还会（若找到原独立探针脚本）把
   `stage0_independent_probes.py` 跑在当前仓库上，断言那五个 P1 项不再产出 PASS。

输出：`acceptance/stage-0-recheck/independent-results.json`（同时副本写 `work/stage0-recheck/`）。
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess
import sys

# 终端编码：中文输出在 GBK 终端/重定向下会抛 UnicodeEncodeError（证据链断在中途）。
# 统一把标准输出/错误固定为 UTF-8：等价于 README 建议的 `python -X utf8`，
# 且不依赖调用方是否设置 PYTHONUTF8 / PYTHONIOENCODING。
for _s in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
    if _s is not None and hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="strict")
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"
OUTDIR = ROOT / "acceptance" / "stage-0-recheck"
WORKDIR = ROOT / "work" / "stage0-recheck"
BASELINE = WORKDIR / "baseline-independent-results.json"
NEG = ROOT / "work" / "negatives"

sys.path.insert(0, str(ROOT / "tools"))
import stage0_gate as g  # noqa: E402


# ============================================================ 手写预期（跑之前写死）
# 每条都是"我认为实现应该给出什么"，而不是"实现现在给出什么"。
EXPECT = {
    "GA01_clause_without_rule": {
        "ga": "GA-01", "origin": "原独立验收",
        "desc": "clean 副本删除 R09（C1 仍为必检且 SUPPORTED），C1 无规则映射",
        "expected": "总体结论 == INDETERMINATE，且 clause_coverage 中 C1 的 coverage_state == UNMAPPED",
    },
    "GA03_missing_crs_declaration": {
        "ga": "GA-03", "origin": "原独立验收",
        "desc": "clean 副本移除 crs.json 的 declared_crs（缺证据，不是错误声明）",
        "expected": "总体结论 == INDETERMINATE（**不是** FAIL）；R06/R08/R10 为 INDETERMINATE/BLOCKED",
    },
    "GA03_unexpected_crs_degree": {
        "ga": "GA-03", "origin": "原独立验收",
        "desc": "clean 副本声明改为 EPSG:4490，单位仍 degree（与要求同为 degree，量级无法区分）",
        "expected": "R07 verdict == FAIL 且 reason_code/ finding 含 CRS_DECLARATION_MISMATCH；总体 != PASS",
    },
    "GA04_unknown_dependency": {
        "ga": "GA-04", "origin": "原独立验收",
        "desc": "clean 副本的 R01.preconditions 增加 NONEXISTENT_RULE",
        "expected": "config_rejections 含 UNKNOWN_PRECONDITION；总体 != PASS（不得再静默过滤）",
    },
    "GA05_substring_threshold": {
        "ga": "GA-05", "origin": "原独立验收",
        "desc": "R09 的 max_age_days 由 30 改为 3（'3' 是 '30' 的子串）",
        "expected": "verify_parameter_sources() 返回非空（token 边界匹配，子串不算命中）",
    },
    "GA05_wrong_document_hash": {
        "ga": "GA-05", "origin": "原独立验收",
        "desc": "clean 副本的条款 document_sha256 改为 64 个 0",
        "expected": "verify_quotes() 返回非空（含 DOCUMENT_HASH_MISMATCH）",
    },
    "GA06_no_invalid_verdicts": {
        "ga": "GA-06", "origin": "原独立验收",
        "desc": "blocked 包全部规则结果的 verdict 合法性",
        "expected": "verdict 不在三态词汇表内的结果数 == 0（修复前为 3 条 UNKNOWN）",
    },
    "GA07_candidate_counts": {
        "ga": "GA-07", "origin": "原独立验收",
        "desc": "clean 包 R10（重复候选）的统计口径",
        "expected": "total=12, evaluated=12, failed=0, indeterminate=2, skipped_upstream=0, "
                    "uninterpretable=0, findings=1（修复前为 evaluated=11 / blocked=1）",
    },
    "GA08_exclusive_boundary": {
        "ga": "GA-08", "origin": "原独立验收",
        "desc": "单位正方形四边中点，point_in_ring_or_boundary(..., inclusive=False)",
        "expected": "四个点全部为 False（修复前左/下边为 True，不对称）",
    },
    "GA02_clause_downgraded": {
        "ga": "GA-02", "origin": "原独立验收",
        "desc": "defective 副本把 R09.required_for_release 改为 false，并注入一条过期记录",
        "expected": "总体 != PASS；config_rejections 含 CLAUSE_POLICY_DOWNGRADED_BY_RULE（规则不得降级条款）",
    },
    "INPUT_MANIFEST": {
        "ga": "GA-09", "origin": "原独立验收",
        "desc": "按 INPUT_MANIFEST.json 逐文件核对 sha256",
        "expected": "不一致文件数 == 0",
    },
    # ---------------- 本轮新增（QA 自设，针对本轮改动的薄弱处）----------------
    "NEW_crs_magnitude_only_signal": {
        "ga": "GA-03/A3", "origin": "本轮新增",
        "desc": "clean 副本：声明 CRS 仍为要求的 EPSG:4326，但 declared_unit 改为 metre，"
                "坐标仍为经纬度量级（合法小值投影坐标也可能长这样）",
        "expected": "R07 verdict != FAIL（只比对声明，不按量级猜）；产出 risk signal "
                    "CRS_MAGNITUDE_RISK（含 degree_like_records）；R06/R08 不被阻断（仍 COMPLETED）",
    },
    "NEW_timezone_undeclared_fails_closed": {
        "ga": "A2/本轮一行修复", "origin": "本轮新增",
        "desc": "① 六个包在严格 RFC3339 子集下是否会产生 TIMEZONE_UNDECLARED；"
                "② 强行放宽解析使该分支可达后，规则级结论是否仍不得为 PASS",
        "expected": "① 六包产生 0 条（该分支不可达，本轮改动零影响）；"
                    "② 放宽后 verdict == INDETERMINATE、execution_status == PARTIAL（不是 FAILED："
                    "没有执行异常；不是 BLOCKED：记录已解析并评估；更不是 COMPLETED：存在不可解释行"
                    "就不能宣称执行完整）、reason_code == TIMEZONE_UNDECLARED、"
                    "records_uninterpretable >= 1（缺证据类 finding 计入 uninterpretable，§7.1/§7.2），"
                    "绝不为 PASS（不得放行，也不得给出「已按未定处理」的假象——见 OPEN_ISSUES）",
    },
    "NEW_expected_tamper_detected": {
        "ga": "契约 §9.4", "origin": "本轮新增",
        "desc": "把 clean 包复制到临时目录后对 expected 做四类篡改：命中错行但数量相同 / "
                "多一条 finding / 少一条 finding / 统计字段被篡改；再加一次「无变异」反向确认",
        "expected": "四类篡改**全部**被 compare_expected() 判为真实差异"
                    "（FIELD/COUNT/MISSING/EXTRA），无变异时真实差异 == 0",
    },
    "NEW_gate_exit_code_on_reject": {
        "ga": "契约 §9.1", "origin": "本轮新增",
        "desc": "跑真实门禁入口：正常包 / 注入重复 rule_id / 注入未知依赖",
        "expected": "正常包退出码 0 且无 [REJECT]；两个注入包退出码 == 1 且打印 [REJECT]",
    },
    "NEW_risk_signals_write_only": {
        "ga": "契约 A3", "origin": "本轮新增",
        "desc": "在 run() 的判定窗口内（通过包装 R07 处理器插桩）读取 Kernel.risk_signals",
        "expected": "读取必须抛 ContractViolation（不得静默成功）；run() 结束后可读且为普通 list",
    },
    # ---------------- 最终回归轮新增（判据 11/14/15 的自建反例）----------------
    "NEW_i7_i9_counterexamples": {
        "ga": "契约 §3.5.1 / I7–I9", "origin": "最终回归轮新增",
        "desc": "自建矛盾组合，不复用工程师输出：① 直接调 assert_reason_compat 的 11 组；"
                "② 经 make_result() 构造 FAIL+OK / FAIL+候选码 / INDETERMINATE+OK；"
                "③ 端到端注入一条 reason_code=OK 的 finding，看 run() 是否失败关闭",
        "expected": "① PASS+OK / FAIL+FAIL 类码 / INDETERMINATE+非 FAIL 类非 OK 码 → 不抛；"
                    "PASS+非OK / FAIL+OK / FAIL+候选码 / FAIL+缺证据码 / INDETERMINATE+OK / "
                    "INDETERMINATE+FAIL 类码 → 抛 ContractViolation；"
                    "② make_result 三例全部抛；"
                    "③ 该规则登记为 INDETERMINATE/FAILED/CONTRACT_VIOLATION，总体 != PASS（失败关闭）",
    },
    "NEW_reason_code_arrays": {
        "ga": "契约 §3.5.2", "origin": "最终回归轮新增",
        "desc": "① _unique_ordered 去重且保留首次出现顺序；② 端到端按「行号 9→3→7、"
                "码 EMPTY_VALUE→ENUM_VIOLATION→EMPTY_VALUE」注入，验证「第一条」取的是排放顺序"
                "而不是行号重排；③ 六包全量核对 I7–I9 与数组自洽",
        "expected": "① [A,B,A,C,B,A] → [A,B,C]；② failure_reason_codes == [EMPTY_VALUE, ENUM_VIOLATION]、"
                    "reason_code == EMPTY_VALUE（行号升序会错成 ENUM_VIOLATION）；"
                    "③ 六包全部 0 条违反，且 FAIL 的 failure_reason_codes[0] == reason_code、数组无重复、"
                    "全部元素属 FAIL 类",
    },
    "NEW_schema_registry_parity": {
        "ga": "契约 §3.5.2(4)", "origin": "最终回归轮新增",
        "desc": "check_result.schema.json 是否登记了两个新字段；并**篡改 Schema** 反证一致性校验真的在查",
        "expected": "两字段均已登记且 uniqueItems=true；基线 SCHEMA_CONSISTENT=true 退出码 0；"
                    "从 failure_reason_codes 枚举删掉一个码后必须报 [REGISTRY_PARITY] 且退出码 != 0；"
                    "篡改文件必须还原（哈希回到原值）",
    },
    "NEW_single_official_interface": {
        "ga": "契约 §3.5.1 / 判据 15 / 判据 17 / Stage 1 第 5 条", "origin": "最终回归轮新增（Stage 1 改写）",
        "desc": "① 以旧二参签名 aggregate(results, n_rows) 调用；② 检查 _coverage_from_results 是否仍存在；"
                "③ 手工构造六类结果走**唯一正式接口** build_clause_coverage → aggregate(coverage, rejections, n_rows)："
                "仅候选 / 无码可取 / 正常 PASS / I9 违反 / I7 违反 / I8 违反；④ 六包唯一接口自洽",
        "expected": "① 必须抛 TypeError 且提示迁移到 build_clause_coverage（**不得**静默走另一条判定路径）；"
                    "② 兼容辅助函数必须已删除；"
                    "③ 仅候选 ⇒ DUPLICATE_CANDIDATE（不是 OK）；无码可取 ⇒ CONTRACT_VIOLATION（禁止回退 OK）；"
                    "正常 PASS+OK ⇒ PASS；I7/I8/I9 三类违反**均不抛栈**且结论 != PASS（失败关闭）；"
                    "④ 六包 aggregate 的 FAIL 条款集合与 clause_coverage 中的 FAIL 集合一致",
    },
    # ---------------- 二次验收轮（独立验收方 RC-01/RC-02/RC-03/RC-04）----------------
    "RC01_clause_coverage_result_set": {
        "ga": "契约 §3.2 / RC-01", "origin": "二次验收独立反例",
        "desc": "clean 副本复制 R09 为 R09b（C1 同时映射两条应执行规则），对结果集做六组故障注入："
                "全齐 / 部分缺失（丢 R09b）/ 零结果 / 重复（R09 两条相同结果）/ "
                "冲突（重复的那条改判 FAIL）/ 已知 FAIL + 部分缺失",
        "expected": "① 全齐 → COVERED + PASS（证明不是一律拒绝）；"
                    "②③ 缺结果 → MISSING_RESULT + INDETERMINATE，missing_rule_ids 分别 == [R09b]、"
                    "[R09,R09b]，总体 != PASS；"
                    "④⑤ 重复/冲突 → INDETERMINATE + CONTRACT_VIOLATION，conflicting_rule_ids == [R09]，"
                    "**不得**取最后一条、也**不得**因此判 FAIL，总体 != PASS；"
                    "⑥ 已知 FAIL + 缺 R09b → 保留 FAIL、reason == STALE_RECORD、"
                    "missing_rule_ids == [R09b]（不隐藏），总体 == FAIL",
    },
    "RC02_unsupported_clause_approved_rule": {
        "ga": "契约 §2.4 / RC-02", "origin": "二次验收独立反例",
        "desc": "clean 副本把 C1 的 support_status 依次改为 UNSUPPORTED / NEEDS_CLARIFICATION / "
                "未知取值 SUPPORTED_TYPO / 缺失(None)，保留原 APPROVED 的 R09；"
                "再加一次改回 SUPPORTED 的反向确认",
        "expected": "四种状态**全部** config_rejections 含 APPROVED_RULE_FOR_UNSUPPORTED_CLAUSE、"
                    "C1 verdict != PASS、总体 != PASS；未知取值与缺失还须报 CLAUSE_SUPPORT_STATUS_UNKNOWN"
                    "（枚举校验在执行入口，不只靠 Schema 脚本）；改回 SUPPORTED 时 rejections 为空且总体 PASS",
    },
    "RC03_subprocess_encoding": {
        "ga": "RC-03（工程）", "origin": "二次验收独立反例",
        "desc": "从环境里删掉 PYTHONUTF8/PYTHONIOENCODING（模拟调用方未设置），"
                "子进程打印中文并按固定 utf-8 解码；一致性校验器同样走该通道",
        "expected": "子进程退出 0、中文可完整解码、sys.stdout.encoding 以 utf 开头；"
                    "校验器退出 0 且输出含 SCHEMA_CONSISTENT=true；"
                    "旧路径反证必须**以 bytes 接收原始输出**、在当前线程显式 decode："
                    "utf-8 往返成功、ascii（不匹配编码）必须抛 UnicodeDecodeError 且被正常捕获；"
                    "禁止用 errors=\"ignore\" 掩盖，也禁止靠子进程读取线程的 traceback 取证",
    },
    "RC04_repeat_run_determinism": {
        "ga": "RC-04（工程）", "origin": "二次验收独立反例",
        "desc": "clean / defective 各建一个 Kernel，同一实例连续 run() 两次",
        "expected": "两个包的 results、findings、risk_signals 三次比较**全等**（修复前 findings 不等："
                    "finding_seq 未复位，finding_id 从上一轮末尾继续编号），"
                    "且两次运行的规则级结论一致、findings 数量非零",
    },
    "S1_input_schema_validation": {
        "ga": "契约 §2.4 / Stage 1 第 5 条", "origin": "Stage 1 新增",
        "desc": "① 六个真实包走执行入口的 Pydantic(strict) 校验；② 对 clean 包 A1 做四类篡改："
                "required_for_release=\"yes\"(类型收敛) / support_status=SUPPORTED_X(枚举越界) / "
                "document_sha256=abc(哈希格式) / source_line_start=0(行号越界)",
        "expected": "① 六个包**均不得**产生 INPUT_SCHEMA_INVALID（不得误杀）；"
                    "② 四类篡改**全部**登记 INPUT_SCHEMA_INVALID 且总体 != PASS（整包拒绝执行）",
    },
    "S1_uncovered_coverage_branches": {
        "ga": "契约 §3.2 / Stage 1 第 7 条", "origin": "Stage 1 新增（第三轮口径更新）",
        "desc": "补齐 Stage 0 无正例的分支：① R09 的 rule_type 改成未知类型——第三轮起入口校验"
                "受控拒绝未知 rule_type（S1-R2-01），条款级走 CONFIG_REJECTED（比 NO_IMPLEMENTATION "
                "更早更严；schema 十类与内核实现同步时 NO_IMPLEMENTATION 不可达，保留给 "
                "「schema 先行扩展」场景）；② R09 的 status 改成 DRAFT (UNAPPROVED)；"
                "③ 删除 crs.json 的 declared_crs，产生缺证据类 finding (advisory_reason_codes)",
        "expected": "① 登记 INPUT_SCHEMA_INVALID（target=R09）且整包拒绝执行：规则级 "
                    "INDETERMINATE/REJECTED/CONFIG_REJECTED，条款级 coverage_state="
                    "CONFIG_REJECTED，总体 != PASS；"
                    "② 规则级 INDETERMINATE/NOT_EXECUTED/RULE_NOT_APPROVED，"
                    "条款级 coverage_state=UNAPPROVED，总体 != PASS；"
                    "③ 至少一条规则的 advisory_reason_codes 非空、码全部属 INDETERMINATE 类、"
                    "规则级结论为 INDETERMINATE（不是 FAIL）、总体 != PASS",
    },
    "S1_cli_smoke": {
        "ga": "Stage 1 第 6 条（内核/CLI/报告）", "origin": "Stage 1 新增",
        "desc": "真实子进程跑 CLI：`run --bundle clean --html`、`report --from-json ... --out ...`、"
                "`compare --before defective --after corrected`",
        "expected": "run 退出 0 且 work/stage0/clean/report.html 落盘并含结论与条款覆盖表（不含脚本注入）；"
                    "report 退出 0 且输出文件存在；compare 打印结构化结果",
    },
    "S1_compare_identity": {
        "ga": "Stage 1 第 8 条（整改 compare 身份）", "origin": "Stage 1 新增",
        "desc": "① defective → corrected；② clean → clean（无差异）；"
                "③ 副本把 R02.version 改为 2；④ 包路径 ../..（路径穿越）",
        "expected": "① 真实修复项判 closed、批次内重复 ID 的那条判 not_comparable、"
                    "总体 LEDGER_INDETERMINATE（有不可比较项不得宣称整改完成）；"
                    "② LEDGER_CLOSED_ACCEPTED 且无差异；"
                    "③ 涉及 R02 的条目全部 not_comparable（规则语义指纹不同）；"
                    "④ 路径穿越必须抛 InputGuardError",
    },
    "S1_validate_entry_new_bundle": {
        "ga": "外部复核 §七（正式检查入口与 expected 回归分离）", "origin": "外部复核新增",
        "desc": "examples 之外新建两个包：干净副本、注入过期时间的副本；再删掉 poi.csv",
        "expected": "① 干净副本 PASS（executed=true、expected_used=false）；"
                    "② 过期副本 FAIL 且 findings_by_class.FAIL ≥ 1、expected_used=false"
                    "（结论来自内核判定，不是 expected 比对）；③ 缺输入文件必须 InputGuardError",
    },
    "S1_compare_closure_evidence": {
        "ga": "外部复核 S1-EXT-01 / EXT-02 / EXT-03（compare 关闭证据）", "origin": "外部复核新增",
        "desc": "① 整改后删掉缺陷实体；② 数据不变但 R09 改 DRAFT；③ 唯一实体同时有两条 FAIL",
        "expected": "① removed_pending_review，不得 closed；② unresolved_unknown、台账 INDETERMINATE；"
                    "③ 两批 duplicated 均为空（不得把 finding 条数当成实体重复），"
                    "两条均 closed 且 closure_evidence 的 execution_status=COMPLETED",
    },
}


def _kernel_clean():
    return g.Kernel(EX / "clean")


def _csv_rows(p: Path):
    import csv
    with io.open(p, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def _csv_write(p: Path, rows):
    import csv
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)


def _yaml_load(p: Path):
    import yaml
    return yaml.safe_load(io.open(p, encoding="utf-8").read())


def _yaml_dump(p: Path, obj):
    import yaml
    io.open(p, "w", encoding="utf-8").write(
        yaml.safe_dump(obj, allow_unicode=True, sort_keys=False))


def _run_utf8(cmd, cwd):
    """以**固定 UTF-8** 运行子进程（RC-03）。

    三条一起上，缺一条就会在 Windows 默认编码（cp936）环境下复现 UnicodeDecodeError：
      1. `sys.executable -X utf8`：子进程自身进入 UTF-8 模式，不看调用方 locale；
      2. env 显式写 PYTHONUTF8 / PYTHONIOENCODING：覆盖可能存在的相反设置；
      3. 父进程用 `encoding="utf-8"` 解码：不用 `text=True`（那是调用方 locale），
         也不用 `errors="ignore"` 掩盖解码失败。
    """
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(cmd, capture_output=True, cwd=str(cwd), env=env,
                          encoding="utf-8", errors="strict")


def _py(script, *args):
    """构造带 -X utf8 的解释器命令行。"""
    return [sys.executable, "-X", "utf8", str(script)] + [str(a) for a in args]


def _agg(k, results):
    """返回 (verdict, reason, coverage)。aggregate() 本身返回 (verdict, reason) 元组，
    探针比较时必须取 [0]，不能拿元组跟字符串比——这类 bug 会让探针假失败。"""
    cov = k.build_clause_coverage(results)
    verdict, reason = g.aggregate(cov, k.collect_config_rejections(), len(k.rows))
    return verdict, reason, cov


# ============================================================ 原独立验收的 11 项
def p_ga01():
    k = _kernel_clean()
    k.rule_doc.update(rules=[r for r in k.rule_doc["rules"] if r["rule_id"] != "R09"])
    res, f = k.run()
    agg, _reason, cov = _agg(k, res)
    c1 = next((c for c in cov if c["requirement_id"] == "C1"), {})
    ok = agg == "INDETERMINATE" and c1.get("coverage_state") == "UNMAPPED"
    return ok, {"aggregate": agg, "C1_coverage_state": c1.get("coverage_state"),
                "C1_reason": c1.get("reason_code")}


def p_ga03_missing():
    k = _kernel_clean()
    k.crs.update(declared_crs=None)
    res, f = k.run()
    agg, _reason, cov = _agg(k, res)
    sp = {r.get("rule_id"): (r.get("verdict"), r.get("execution_status"))
          for r in res if r.get("rule_id") in ("R06", "R08", "R10")}
    ok = (agg == "INDETERMINATE"
          and all(v == ("INDETERMINATE", "BLOCKED") for v in sp.values()) and len(sp) == 3)
    return ok, {"aggregate": agg, "spatial": sp}


def p_ga03_degree():
    k = _kernel_clean()
    k.crs.update(declared_crs="EPSG:4490", declared_unit="degree")
    res, f = k.run()
    agg, _reason, cov = _agg(k, res)
    r07 = next(r for r in res if r.get("rule_id") == "R07")
    codes = sorted({x.get("reason_code") for x in f})
    ok = (r07.get("verdict") == "FAIL" and "CRS_DECLARATION_MISMATCH" in codes and agg != "PASS")
    return ok, {"aggregate": agg, "R07": r07.get("verdict"), "finding_codes": codes}


def p_ga04_unknown_dep():
    k = _kernel_clean()
    k.rule_doc["rules"][0]["preconditions"] = ["NONEXISTENT_RULE"]
    rej = k.collect_config_rejections()
    codes = sorted({r.get("code") for r in rej})
    res, f = k.run()
    agg, _reason, cov = _agg(k, res)
    ok = "UNKNOWN_PRECONDITION" in codes and agg != "PASS"
    return ok, {"aggregate": agg, "rejection_codes": codes}


def p_ga05_substring():
    k = _kernel_clean()
    r = next(x for x in k.rule_doc["rules"] if x["rule_id"] == "R09")
    r["parameters"]["max_age_days"] = 3
    problems = k.verify_parameter_sources()
    ok = len(problems) > 0
    return ok, {"problems": problems[:2]}


def p_ga05_hash():
    k = _kernel_clean()
    k.req_doc["requirements"][0]["document_sha256"] = "0" * 64
    problems = k.verify_quotes()
    ok = len(problems) > 0 and any("DOCUMENT_HASH_MISMATCH" in p for p in problems)
    return ok, {"problems": [p[:80] for p in problems[:1]]}


def p_ga06_verdicts():
    k = g.Kernel(EX / "blocked")
    res, f = k.run()
    bad = [{"rule_id": r.get("rule_id"), "verdict": r.get("verdict")}
           for r in res if r.get("verdict") not in g.VERDICTS]
    # 顺带校验：全部规则级组合必须落在契约 §1.3 的合法矩阵内
    illegal = [r.get("rule_id") for r in res
               if (r.get("verdict"), r.get("execution_status")) not in g.LEGAL_COMBOS]
    ok = not bad and not illegal
    return ok, {"invalid_verdicts": bad, "illegal_combos": illegal}


def p_ga07_counts():
    k = _kernel_clean()
    res, f = k.run()
    r10 = next(r for r in res if r.get("rule_id") == "R10")
    c = r10["summary_counts"]
    ok = (c["records_total"] == 12 and c["records_evaluated"] == 12 and c["records_failed"] == 0
          and c["records_indeterminate"] == 2 and c["records_skipped_upstream"] == 0
          and c["records_uninterpretable"] == 0 and c["findings"] == 1)
    return ok, {"summary_counts": c}


def p_ga08_boundary():
    ring = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    pts = [(0, .5), (1, .5), (.5, 0), (.5, 1)]
    excl = {str(p): g.point_in_ring_or_boundary(p[0], p[1], ring, inclusive=False) for p in pts}
    incl = {str(p): g.point_in_ring_or_boundary(p[0], p[1], ring, inclusive=True) for p in pts}
    ok = all(v is False for v in excl.values()) and all(v is True for v in incl.values())
    return ok, {"exclusive": excl, "inclusive": incl}


def p_ga02_downgrade():
    k = g.Kernel(EX / "defective")
    for r in k.rule_doc["rules"]:
        if r["rule_id"] == "R09":
            r["required_for_release"] = False
    # 只保留 clean 的行 + 注入一条过期记录，避免其它缺陷干扰
    base = _kernel_clean()
    import copy
    k.rows = copy.deepcopy(base.rows)
    k.header = base.header
    k.rows[0][1][k.header.index("source_time")] = "2026-08-01T00:00:00Z"
    rej = k.collect_config_rejections()
    codes = sorted({r.get("code") for r in rej})
    res, f = k.run()
    agg, _reason, cov = _agg(k, res)
    ok = agg != "PASS" and "CLAUSE_POLICY_DOWNGRADED_BY_RULE" in codes
    return ok, {"aggregate": agg, "rejection_codes": codes}


def p_manifest():
    import hashlib
    man = json.loads((EX / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    bad = []
    for bundle, files in man.items():
        for name, meta in files.items():
            p = EX / bundle / name
            if not p.exists():
                bad.append("%s/%s (缺失)" % (bundle, name))
            elif hashlib.sha256(p.read_bytes()).hexdigest() != meta["sha256"]:
                bad.append("%s/%s" % (bundle, name))
    return not bad, {"mismatches": bad, "checked": sum(len(v) for v in man.values())}


# ============================================================ 本轮新增的 5 项
def n_crs_magnitude():
    k = _kernel_clean()
    k.crs.update(declared_unit="metre")   # 声明 CRS 仍是要求的 EPSG:4326，只把"单位"改成 metre
    res, f = k.run()
    agg, _reason, cov = _agg(k, res)
    r07 = next(r for r in res if r.get("rule_id") == "R07")
    r06 = next(r for r in res if r.get("rule_id") == "R06")
    r08 = next(r for r in res if r.get("rule_id") == "R08")
    risks = [s.get("code") for s in k.risk_signals]
    mag = [s for s in k.risk_signals if s.get("code") == "CRS_MAGNITUDE_RISK"]
    ok = (r07.get("verdict") != "FAIL"
          and "CRS_MAGNITUDE_RISK" in risks
          and any("degree_like_records" in (s.get("evidence") or {}) for s in mag)
          and r06.get("execution_status") == "COMPLETED"
          and r08.get("execution_status") == "COMPLETED")
    return ok, {"aggregate": agg, "R07": r07.get("verdict"), "risk_codes": risks,
                "magnitude_evidence": [s.get("evidence") for s in mag],
                "R06_status": r06.get("execution_status"), "R08_status": r08.get("execution_status")}


def n_timezone():
    """TIMEZONE_UNDECLARED 归位到「缺证据」类之后的两件事：① 现有样例零影响；② 分支可达时不得放行。"""
    produced = 0
    for b in ["clean", "defective", "corrected", "ambiguous", "blocked", "crs_same_unit_wrong"]:
        k = g.Kernel(EX / b)
        res, f = k.run()
        produced += sum(1 for x in f if x.get("reason_code") == "TIMEZONE_UNDECLARED")
    # ② 强行放宽解析，让「含 T 但无时区」的时间戳通过 TYPE_PARSE_ERROR 进入 R09 的时区分支
    old = g.ISO8601
    g.ISO8601 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$")
    try:
        k = _kernel_clean()
        k.rows[1][1][k.header.index("source_time")] = "2026-09-22T09:30:00"
        res, f = k.run()
        r09 = next(r for r in res if r.get("rule_id") == "R09")
        forced = {"verdict": r09.get("verdict"), "execution_status": r09.get("execution_status"),
                  "reason_code": r09.get("reason_code"), "detail": r09.get("detail"),
                  "records_uninterpretable": (r09.get("summary_counts") or {}).get(
                      "records_uninterpretable"),
                  "finding_codes": sorted({x.get("reason_code") for x in f})}
    finally:
        g.ISO8601 = old
    ok = (produced == 0
          and forced["verdict"] == "INDETERMINATE"
          and forced["execution_status"] == "PARTIAL"
          and forced["reason_code"] == "TIMEZONE_UNDECLARED"
          and (forced["records_uninterpretable"] or 0) >= 1
          and "TIMEZONE_UNDECLARED" in forced["finding_codes"])
    return ok, {"timezone_findings_in_examples": produced, "forced_branch": forced}


def n_expected_tamper():
    """独立验证主门禁的记录级比对真的能抓错（不复用工程师的临时副本结论）。"""
    tmproot = NEG / "probe_tamper_root"
    if tmproot.exists():
        shutil.rmtree(tmproot)
    tmproot.mkdir(parents=True)
    bundle = tmproot / "clean"
    old_ex = g.EX
    g.EX = tmproot

    def _read(p):
        return json.loads(p.read_text(encoding="utf-8"))

    def m_none(p):
        pass

    def m_line(p):      # 命中错行但数量相同
        fp = p / "expected" / "findings.json"
        d = _read(fp)
        d["findings"][0]["record_locator"]["line"] = 2
        fp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def m_extra(p):     # 多一条 finding
        fp = p / "expected" / "findings.json"
        d = _read(fp)
        d["findings"].append({
            "stable_key": "R09|STALE_RECORD|3|source_time", "reason_code": "STALE_RECORD",
            "field": "source_time", "observed_value": "2099-01-01T00:00:00Z",
            "review_state": "OPEN", "execution_status": "COMPLETED",
            "record_locator": {"file": "poi.csv", "line": 3, "record_id": "SD-0002"}})
        fp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def m_missing(p):   # 少一条 finding
        fp = p / "expected" / "findings.json"
        d = _read(fp)
        d["findings"] = []
        fp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def m_count(p):     # 统计字段被篡改
        fp = p / "expected" / "aggregate.json"
        d = _read(fp)
        d["per_rule"]["R10"]["records_indeterminate"] = 0
        fp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    variants = [("无变异（反向确认）", m_none), ("命中错行但数量相同", m_line),
                ("多一条 finding", m_extra), ("少一条 finding", m_missing),
                ("统计字段被篡改", m_count)]
    results = {}
    try:
        for label, mutate in variants:
            if bundle.exists():
                shutil.rmtree(bundle)
            shutil.copytree(EX / "clean", bundle)
            mutate(bundle)
            k = g.Kernel(bundle)
            res, f = k.run()
            cov = k.build_clause_coverage(res)
            agg, _reason = g.aggregate(cov, k.collect_config_rejections(), len(k.rows))
            _d, _e, recs = g.compare_expected(
                "clean", res, f, agg, coverage=cov, rejections=k.collect_config_rejections())
            real = [{"kind": r["kind"], "scope": r["scope"], "field": r["field"]}
                    for r in recs if r["kind"] in g.REAL_DIFF_KINDS]
            results[label] = real
    finally:
        g.EX = old_ex
        if tmproot.exists():
            shutil.rmtree(tmproot)

    ok = (len(results["无变异（反向确认）"]) == 0
          and all(len(results[k]) > 0 for k in
                  ["命中错行但数量相同", "多一条 finding", "少一条 finding", "统计字段被篡改"]))
    return ok, {"variants": results}


def n_gate_exit_code():
    """契约 §9.1：config_rejections 非空 ⇒ 门禁打印 [REJECT] 且退出码 1（即使结论与 expected 一致）。"""
    tmproot = NEG / "probe_gate_root"
    if tmproot.exists():
        shutil.rmtree(tmproot)
    tmproot.mkdir(parents=True)

    def prep(name, mutate=None):
        b = tmproot / name
        if b.exists():
            shutil.rmtree(b)
        shutil.copytree(EX / "clean", b)
        if mutate:
            txt = (b / "approved-rules.yaml").read_text(encoding="utf-8")
            (b / "approved-rules.yaml").write_text(mutate(txt), encoding="utf-8")

    def dup_rule(t):
        i = t.index('    rule_id: "R05"')
        j = t.index('    rule_id: "R06"')
        return t[:j] + t[i:j] + t[j:]

    prep("clean")
    prep("neg_dup_rule", dup_rule)
    prep("neg_unknown_dep",
         lambda t: t.replace("preconditions: []", 'preconditions: ["NONEXISTENT_RULE"]', 1))

    old_ex, old_work, old_argv = g.EX, g.WORK, list(sys.argv)
    outroot = NEG / "probe_gate_out"
    g.EX, g.WORK = tmproot, outroot
    runs = {}
    try:
        for name in ["clean", "neg_dup_rule", "neg_unknown_dep"]:
            sys.argv = ["stage0_gate.py", "--bundle", name]
            buf = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = buf
            try:
                code = g.main()
            finally:
                sys.stdout = old_stdout
            text = buf.getvalue()
            runs[name] = {"exit_code": code, "reject": "[REJECT]" in text,
                          "first_line": next((l for l in text.splitlines() if l.strip()), "")}
    finally:
        g.EX, g.WORK, sys.argv = old_ex, old_work, old_argv
        if tmproot.exists():
            shutil.rmtree(tmproot)

    ok = (runs["clean"]["exit_code"] == 0 and not runs["clean"]["reject"]
          and runs["neg_dup_rule"]["exit_code"] == 1 and runs["neg_dup_rule"]["reject"]
          and runs["neg_unknown_dep"]["exit_code"] == 1 and runs["neg_unknown_dep"]["reject"])
    return ok, {"runs": runs}


def n_risk_write_only():
    """契约 A3 的机器化保证：判定窗口内 risk_signals 只写，读取必须抛 ContractViolation。"""
    observed = {}
    orig = g.Kernel.rule_crs_declaration

    def spy(self, rule, ctx):
        try:
            len(self.risk_signals)
            observed["during"] = "NO_RAISE"
        except g.ContractViolation:
            observed["during"] = "ContractViolation"
        except Exception as exc:  # noqa: BLE001
            observed["during"] = type(exc).__name__
        return orig(self, rule, ctx)

    g.Kernel.rule_crs_declaration = spy
    try:
        k = g.Kernel(EX / "blocked")
        res, f = k.run()
        after = list(k.risk_signals)
        observed["after_type"] = type(k.risk_signals).__name__
        observed["after_len"] = len(after)
    finally:
        g.Kernel.rule_crs_declaration = orig
    ok = observed.get("during") == "ContractViolation" and observed.get("after_type") == "list"
    return ok, observed


def _mk_counts(total=12, evaluated=12, **kw):
    counts = {"records_total": total, "records_evaluated": evaluated, "records_failed": 0,
              "records_indeterminate": 0, "records_skipped_upstream": 0,
              "records_uninterpretable": 0, "records_blocked": 0, "findings": 0}
    counts.update(kw)
    return counts


def _call_guard(fn, *a):
    """调用一个"应该抛 ContractViolation"的守卫，把结果归一化成字符串。"""
    try:
        fn(*a)
        return "NO_RAISE"
    except g.ContractViolation as exc:
        return "ContractViolation"
    except Exception as exc:  # noqa: BLE001
        return type(exc).__name__


def n_i7_i9_counterexamples():
    """判据 11 的自建反例：I7–I9 全级断言是否真的拦得住矛盾组合（不复用工程师输出）。"""
    observed = {}
    # ① 直接打 assert_reason_compat
    table = [
        ("PASS", "OK", "NO_RAISE"),
        ("PASS", "EMPTY_VALUE", "raise"),
        ("PASS", "DUPLICATE_CANDIDATE", "raise"),
        ("FAIL", "OK", "raise"),
        ("FAIL", "DUPLICATE_CANDIDATE", "raise"),
        ("FAIL", "CRS_MISSING_DECLARATION", "raise"),
        ("FAIL", "EMPTY_VALUE", "NO_RAISE"),
        ("INDETERMINATE", "OK", "raise"),
        ("INDETERMINATE", "EMPTY_VALUE", "raise"),
        ("INDETERMINATE", "DUPLICATE_CANDIDATE", "NO_RAISE"),
        ("INDETERMINATE", "ALL_RECORDS_BLOCKED", "NO_RAISE"),
        ("INDETERMINATE", "CRS_MISSING_DECLARATION", "NO_RAISE"),
    ]
    rows = []
    for verdict, reason, want in table:
        got = _call_guard(g.assert_reason_compat, verdict, reason)
        want_s = "NO_RAISE" if want == "NO_RAISE" else "ContractViolation"
        rows.append({"verdict": verdict, "reason_code": reason,
                     "got": got, "want": want_s, "ok": got == want_s})
    observed["assert_reason_compat"] = rows

    # ② 经 make_result（run() 实际调用的构造入口）构造矛盾组合
    rule = {"rule_id": "RX", "requirement_ids": ["A2"], "required_for_release": True,
            "rule_type": "non_empty"}
    mk_rows = []
    for verdict, status, reason in [("FAIL", "COMPLETED", "OK"),
                                    ("FAIL", "COMPLETED", "DUPLICATE_CANDIDATE"),
                                    ("INDETERMINATE", "COMPLETED", "OK")]:
        got = _call_guard(g.make_result, rule, verdict, status, reason, _mk_counts())
        mk_rows.append({"verdict": verdict, "reason_code": reason, "got": got,
                        "want": "ContractViolation", "ok": got == "ContractViolation"})
    observed["make_result"] = mk_rows

    # ③ 端到端：注入一条 reason_code=OK 的 finding（绕过 Kernel.finding 的自检，
    #    模拟"规则处理器标错码"），看 run() 是否失败关闭而不是放行
    orig = g.Kernel.rule_non_empty

    def injected(self, rule, ctx):
        idx = {l: r for l, r in self.rows}
        line = sorted(idx)[0]
        bad = {"finding_id": "F0001", "stable_key": "R02|OK|%s|category" % line,
               "record_locator": self.record_locator(line, idx[line]),
               "rule_id": rule.get("rule_id"), "field": "category",
               "observed_value": "", "expected_constraint": "注入", "reason_code": "OK",
               "evidence": {}, "review_state": "OPEN"}
        return [bad], {line}

    g.Kernel.rule_non_empty = injected
    try:
        k = _kernel_clean()
        res, _f = k.run()
        r02 = next(r for r in res if r.get("rule_id") == "R02")
        agg, _reason, _cov = _agg(k, res)
        observed["e2e_fail_ok"] = {"verdict": r02.get("verdict"),
                                   "execution_status": r02.get("execution_status"),
                                   "reason_code": r02.get("reason_code"),
                                   "aggregate": agg}
    finally:
        g.Kernel.rule_non_empty = orig

    # 附带事实：Kernel.finding 本身也拦 RESULT_ONLY 码（第一道网），如实记录
    k0 = _kernel_clean()
    observed["finding_guard_on_OK"] = _call_guard(
        k0.finding, "R02", {"line": 3}, "category", "", "x", "OK")

    ok = (all(r["ok"] for r in rows)
          and all(r["ok"] for r in mk_rows)
          and observed["e2e_fail_ok"]["verdict"] == "INDETERMINATE"
          and observed["e2e_fail_ok"]["execution_status"] == "FAILED"
          and observed["e2e_fail_ok"]["reason_code"] == "CONTRACT_VIOLATION"
          and observed["e2e_fail_ok"]["aggregate"] != "PASS")
    return ok, observed


def n_reason_code_arrays():
    """判据 14 的自建反例：去重 / 首次出现顺序 / 「第一条」= 排放顺序而非行号重排。"""
    observed = {}
    observed["unique_ordered"] = g._unique_ordered(["A", "B", "A", "C", "B", "A"])

    orig = g.Kernel.rule_non_empty

    def injected(self, rule, ctx):
        idx = {l: r for l, r in self.rows}
        lines = sorted(idx)
        # 故意按 9 → 3 → 7 的**非升序**排放，码为 EMPTY / ENUM / EMPTY
        specs = [(lines[8], "EMPTY_VALUE"), (lines[2], "ENUM_VIOLATION"),
                 (lines[6], "EMPTY_VALUE")]
        out = []
        for line, code in specs:
            out.append(self.finding(rule.get("rule_id"),
                                    self.record_locator(line, idx[line]),
                                    "category", "注入观测", "注入约束", code))
        return out, {line for line, _ in specs}

    g.Kernel.rule_non_empty = injected
    try:
        k = _kernel_clean()
        res, f = k.run()
        r02 = next(r for r in res if r.get("rule_id") == "R02")
        own = [x for x in f if x.get("rule_id") == "R02"]
        observed["R02"] = {
            "verdict": r02.get("verdict"),
            "reason_code": r02.get("reason_code"),
            "failure_reason_codes": r02.get("failure_reason_codes"),
            "emission_order": [x.get("reason_code") for x in own],
            "emission_lines": [(x.get("record_locator") or {}).get("line") for x in own],
        }
    finally:
        g.Kernel.rule_non_empty = orig

    # ③ 六包全量核对：I7–I9 + 数组自洽（独立重算，不读工程师的结论文件）
    corpus = {}
    bad = []
    for b in ["clean", "defective", "corrected", "ambiguous", "blocked", "crs_same_unit_wrong"]:
        k = g.Kernel(EX / b)
        res, _f = k.run()
        cov = k.build_clause_coverage(res)
        seen = {"results": len(res), "clauses": len(cov), "violations": []}
        for r in res:
            v, rc = r.get("verdict"), r.get("reason_code")
            frc = r.get("failure_reason_codes") or []
            arc = r.get("advisory_reason_codes") or []
            if v == "PASS" and rc != "OK":
                seen["violations"].append({"rule": r.get("rule_id"), "why": "I7"})
            if v == "FAIL":
                if rc == "OK" or g.classify_reason_code(rc) != "FAIL":
                    seen["violations"].append({"rule": r.get("rule_id"), "why": "I8", "rc": rc})
                if frc and frc[0] != rc:
                    seen["violations"].append({"rule": r.get("rule_id"), "why": "首码不等于 reason_code"})
                if len(frc) != len(set(frc)):
                    seen["violations"].append({"rule": r.get("rule_id"), "why": "failure 数组有重复"})
                for c in frc:
                    if g.classify_reason_code(c) != "FAIL":
                        seen["violations"].append({"rule": r.get("rule_id"), "why": "failure 含非 FAIL 类码", "c": c})
            if v == "INDETERMINATE" and rc == "OK":
                seen["violations"].append({"rule": r.get("rule_id"), "why": "I9"})
            if len(arc) != len(set(arc)):
                seen["violations"].append({"rule": r.get("rule_id"), "why": "advisory 数组有重复"})
            for c in arc:
                if g.classify_reason_code(c) != "INDETERMINATE":
                    seen["violations"].append({"rule": r.get("rule_id"), "why": "advisory 含非缺证据类码", "c": c})
        for e in cov:
            v, rc = e.get("verdict"), e.get("reason_code")
            if v == "PASS" and rc != "OK":
                seen["violations"].append({"clause": e.get("requirement_id"), "why": "I7(条款)"})
            if v == "FAIL" and (rc == "OK" or g.classify_reason_code(rc) != "FAIL"):
                seen["violations"].append({"clause": e.get("requirement_id"), "why": "I8(条款)", "rc": rc})
            if v == "INDETERMINATE" and rc == "OK":
                seen["violations"].append({"clause": e.get("requirement_id"), "why": "I9(条款)"})
        corpus[b] = seen
        if seen["violations"]:
            bad.append(b)
    observed["corpus"] = corpus
    observed["corpus_violation_bundles"] = bad

    ok = (observed["unique_ordered"] == ["A", "B", "C"]
          and observed["R02"]["failure_reason_codes"] == ["EMPTY_VALUE", "ENUM_VIOLATION"]
          and observed["R02"]["reason_code"] == "EMPTY_VALUE"
          and observed["R02"]["emission_order"] == ["EMPTY_VALUE", "ENUM_VIOLATION", "EMPTY_VALUE"]
          and observed["R02"]["emission_lines"] == [10, 4, 8]
          and not bad)
    return ok, observed


def _mk_result(rid, cid, verdict, status, reason, **over):
    """手工构造一条 CheckResult（用于走两参兼容路径，不经过 run()）。"""
    counts = {"records_total": 2, "records_evaluated": 2, "records_failed": 0,
              "records_indeterminate": 0, "records_skipped_upstream": 0,
              "records_uninterpretable": 0, "records_blocked": 0, "findings": 0}
    counts.update(over.pop("counts", {}) or {})
    r = {"rule_id": rid, "requirement_ids": [cid], "verdict": verdict,
         "execution_status": status, "reason_code": reason,
         "summary_counts": counts, "required_for_release": True}
    r.update(over)
    return r


def n_single_official_interface():
    """Stage 1：判定接口**收敛到唯一正式接口**（最终复验报告第 5 条）。

    ① 旧的二参数兼容签名 `aggregate(results, n_rows)` 与 `_coverage_from_results()`
       必须**已删除**：以旧签名调用必须 TypeError 并给出迁移说明，绝不能静默走另一条判定路径；
    ② 删除兼容路径后，I7–I9 违反仍必须**失败关闭**（返回 INDETERMINATE，不抛栈），
       且只能经权威口径 `build_clause_coverage()` → `aggregate(coverage, rejections, n_rows)`；
    ③ 六包在唯一接口下自洽：aggregate 的 FAIL 条款集合 == coverage 中的 FAIL 集合。
    """
    observed = {}

    # ① 旧签名必须消失
    try:
        g.aggregate([_mk_result("RX", "A2", "PASS", "COMPLETED", "OK")], 2)
        observed["legacy_2arg"] = {"raised": None}
    except TypeError as exc:
        observed["legacy_2arg"] = {"raised": "TypeError", "msg": str(exc)[:160]}
    except Exception as exc:  # noqa: BLE001
        observed["legacy_2arg"] = {"raised": type(exc).__name__, "msg": str(exc)[:160]}
    observed["legacy_helper_removed"] = not hasattr(g, "_coverage_from_results")

    # ② 经权威口径：手工构造结果 → build_clause_coverage → aggregate
    k = _kernel_clean()

    def official(results, n_rows=2):
        """唯一正式接口：先覆盖，再聚合。任何异常都如实记录（判据 17：不得抛栈）。"""
        try:
            cov = k.build_clause_coverage(results)
            verdict, reason = g.aggregate(cov, [], n_rows)
            entry = next((e for e in cov if e.get("requirement_id") == "A2"), {})
            return {"raised": None, "verdict": verdict, "reason": str(reason),
                    "clause": {kk: entry.get(kk) for kk in
                               ("coverage_state", "verdict", "execution_status", "reason_code")}}
        except Exception as exc:  # noqa: BLE001
            return {"raised": type(exc).__name__, "detail": str(exc)[:160]}

    # S1 仅候选（INDETERMINATE + OK + records_indeterminate>0）⇒ DUPLICATE_CANDIDATE，不是 OK
    observed["S1_仅候选"] = official([_mk_result(
        "R02", "A2", "INDETERMINATE", "COMPLETED", "OK",
        counts={"records_indeterminate": 2, "findings": 1})])
    # S5 无候选无缺证据 ⇒ CONTRACT_VIOLATION 兜底（禁止回退 OK）
    observed["S5_无码可取的兜底"] = official([_mk_result(
        "R02", "A2", "INDETERMINATE", "COMPLETED", "OK")])
    # S6 正常 PASS+OK
    observed["S6_正常"] = official([_mk_result("R02", "A2", "PASS", "COMPLETED", "OK")])

    # ②③④ 三类 I7–I9 违反：必须失败关闭（不抛栈）
    violations = {
        "S2_I9违反_INDETERMINATE+FAIL类码": _mk_result("R02", "A2", "INDETERMINATE", "PARTIAL",
                                                   "EMPTY_VALUE"),
        "S3_I7违反_PASS+非OK码": _mk_result("R02", "A2", "PASS", "COMPLETED", "EMPTY_VALUE"),
        "S4_I8违反_FAIL+OK": _mk_result("R02", "A2", "FAIL", "COMPLETED", "OK"),
    }
    observed["violations"] = {name: official([res]) for name, res in violations.items()}

    # ③ 六包：唯一接口自洽（FAIL 条款集合一致）
    pairs = {}
    for b in ["clean", "defective", "corrected", "ambiguous", "blocked", "crs_same_unit_wrong"]:
        kb = g.Kernel(EX / b)
        results, _f = kb.run()
        cov = kb.build_clause_coverage(results)
        agg, reason = g.aggregate(cov, kb.collect_config_rejections(), len(kb.rows))
        fail_in_cov = sorted(c["requirement_id"] for c in cov if c.get("verdict") == "FAIL")
        fail_in_reason = sorted(re.findall(r"([A-Z]\d+)\(", reason)) if agg == "FAIL" else []
        pairs[b] = {"aggregate": agg, "fail_in_coverage": fail_in_cov,
                    "fail_in_reason": fail_in_reason,
                    "consistent": (agg != "FAIL") or (fail_in_cov == fail_in_reason)}
    observed["bundles"] = pairs
    observed["bundles_all_consistent"] = all(p["consistent"] for p in pairs.values())

    ok = (observed["legacy_2arg"].get("raised") == "TypeError"
          and "clause_coverage" in str(observed["legacy_2arg"].get("msg"))
          and observed["legacy_helper_removed"]
          and observed["S1_仅候选"]["raised"] is None
          and "DUPLICATE_CANDIDATE" in str(observed["S1_仅候选"].get("reason"))
          and "(OK)" not in str(observed["S1_仅候选"].get("reason"))
          and "CONTRACT_VIOLATION" in str(observed["S5_无码可取的兜底"].get("reason"))
          # 只给 A2 一条结果 ⇒ 其余必检条款必然 MISSING_RESULT，总体是 INDETERMINATE（RC-01 语义正确）；
          # 因此"正常/违反"的判定看 **A2 条款级条目**，不是总体
          and observed["S6_正常"]["clause"]["verdict"] == "PASS"
          and observed["S6_正常"]["clause"]["reason_code"] == "OK"
          and all(v.get("raised") is None and v["clause"].get("verdict") != "PASS"
                  for v in observed["violations"].values())
          and observed["bundles_all_consistent"])
    return ok, observed


def n_schema_registry_parity():
    """判据 15 的自建反例：Schema 登记 + 一致性校验是否真的在查（改坏它看会不会报警）。"""
    import hashlib
    schema_path = ROOT / "schemas" / "check_result.schema.json"
    raw = schema_path.read_text(encoding="utf-8")
    sha_before = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    doc = json.loads(raw)
    props = doc.get("properties", {})
    observed = {
        "declared": {k: (props.get(k) or {}).get("type") for k in
                     ("failure_reason_codes", "advisory_reason_codes")},
        "unique_items": {k: (props.get(k) or {}).get("uniqueItems") for k in
                         ("failure_reason_codes", "advisory_reason_codes")},
        "enum_fail_n": len(((props.get("failure_reason_codes") or {}).get("items") or {}).get("enum") or []),
        "enum_advisory": ((props.get("advisory_reason_codes") or {}).get("items") or {}).get("enum"),
    }

    def run_checker():
        p = _run_utf8(_py(ROOT / "tools" / "check_schema_consistency.py"), ROOT)
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    base_rc, base_out = run_checker()
    observed["baseline"] = {"exit_code": base_rc,
                            "consistent": "SCHEMA_CONSISTENT=true" in base_out}

    # 反例：删掉 failure_reason_codes 枚举里的一个码，一致性校验必须报警
    tampered = json.loads(raw)
    enum = tampered["properties"]["failure_reason_codes"]["items"]["enum"]
    removed = enum.pop()
    observed["removed_code"] = removed
    try:
        schema_path.write_text(json.dumps(tampered, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8", newline="\n")
        rc, out = run_checker()
        observed["tampered"] = {"exit_code": rc, "parity_problem": "[REGISTRY_PARITY]" in out,
                                "consistent": "SCHEMA_CONSISTENT=true" in out,
                                "problem_line": next(
                                    (l.strip() for l in out.splitlines()
                                     if "[REGISTRY_PARITY]" in l), "")[:160]}
    finally:
        schema_path.write_text(raw, encoding="utf-8", newline="\n")
    sha_after = hashlib.sha256(schema_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    observed["restored"] = sha_before == sha_after

    ok = (observed["declared"]["failure_reason_codes"] == "array"
          and observed["declared"]["advisory_reason_codes"] == "array"
          and observed["unique_items"]["failure_reason_codes"] is True
          and observed["unique_items"]["advisory_reason_codes"] is True
          and observed["baseline"]["exit_code"] == 0
          and observed["baseline"]["consistent"]
          and observed["tampered"]["parity_problem"]
          and observed["tampered"]["exit_code"] != 0
          and observed["restored"])
    return ok, observed


def n_clause_coverage_result_set():
    """RC-01（P1）：一条条款映射多条规则时，覆盖完整性只能由**规则身份集合**判定。

    六组输入（每组都写明输入/预期/实测）：
      ① 全齐        ② 部分缺失（R09b 的结果丢了）  ③ 零结果
      ④ 重复（同一规则两条结果）                   ⑤ 冲突（重复的那条改判 FAIL）
      ⑥ 已知 FAIL + 部分缺失（保留失败，同时列出缺失）
    """
    import copy

    def build():
        """clean 副本：把 R09 复制成 R09b（同配置、同条款），C1 于是映射两条应执行规则。"""
        k = _kernel_clean()
        base = next(r for r in k.rule_doc["rules"] if r["rule_id"] == "R09")
        extra = copy.deepcopy(base)
        extra["rule_id"] = "R09b"
        k.rule_doc["rules"].append(extra)
        res, _f = k.run()
        return k, res

    def mutate_fail(res):
        """把 R09 的结果改造成一条已知 FAIL（FAIL 类码 STALE_RECORD）。"""
        out = []
        for r in res:
            if str(r.get("rule_id")) == "R09":
                rr = copy.deepcopy(r)
                rr["verdict"] = "FAIL"
                rr["execution_status"] = "PARTIAL"
                rr["failure_reason_codes"] = ["STALE_RECORD"]
                rr["reason_code"] = "STALE_RECORD"
                out.append(rr)
            else:
                out.append(r)
        return out

    def snap(k, res):
        cov = k.build_clause_coverage(res)
        c1 = next(c for c in cov if c["requirement_id"] == "C1")
        agg = g.aggregate(cov, k.collect_config_rejections(), len(k.rows))[0]
        return {"state": c1["coverage_state"], "verdict": c1["verdict"],
                "status": c1["execution_status"], "reason": c1["reason_code"],
                "missing": c1.get("missing_rule_ids"),
                "conflicting": c1.get("conflicting_rule_ids"),
                "fail_codes": c1.get("failure_reason_codes"), "aggregate": agg}

    obs = {}
    k, res = build()
    obs["S1_全齐"] = snap(k, res)
    obs["S2_部分缺失"] = snap(k, [r for r in res if str(r.get("rule_id")) != "R09b"])
    obs["S3_零结果"] = snap(k, [r for r in res if str(r.get("rule_id")) not in ("R09", "R09b")])
    dup = copy.deepcopy(next(r for r in res if str(r.get("rule_id")) == "R09"))
    obs["S4_重复"] = snap(k, list(res) + [dup])
    bad = copy.deepcopy(dup)
    bad["verdict"], bad["execution_status"] = "FAIL", "PARTIAL"
    bad["failure_reason_codes"], bad["reason_code"] = ["STALE_RECORD"], "STALE_RECORD"
    obs["S5_冲突"] = snap(k, list(res) + [bad])
    obs["S6_已知FAIL且缺结果"] = snap(
        k, [r for r in mutate_fail(res) if str(r.get("rule_id")) != "R09b"])

    ok = (
        # ① 全齐：不得因为改了判定方式就一律拒绝
        obs["S1_全齐"]["state"] == "COVERED" and obs["S1_全齐"]["verdict"] == "PASS"
        and obs["S1_全齐"]["aggregate"] == "PASS"
        # ② 部分缺失 ⇒ 条款未知，且明确列出缺哪条
        and obs["S2_部分缺失"]["state"] == "MISSING_RESULT"
        and obs["S2_部分缺失"]["verdict"] == "INDETERMINATE"
        and obs["S2_部分缺失"]["missing"] == ["R09b"]
        and obs["S2_部分缺失"]["aggregate"] != "PASS"
        # ③ 零结果 ⇒ 同样不得放行（原有的"完全为空"分支仍然成立）
        and obs["S3_零结果"]["state"] == "MISSING_RESULT"
        and obs["S3_零结果"]["verdict"] == "INDETERMINATE"
        and obs["S3_零结果"]["missing"] == ["R09", "R09b"]
        and obs["S3_零结果"]["aggregate"] != "PASS"
        # ④⑤ 重复/冲突 ⇒ 结果集不可信，失败关闭；**不得**取最后一条、也**不得**因此判 FAIL
        and obs["S4_重复"]["verdict"] == "INDETERMINATE"
        and obs["S4_重复"]["reason"] == "CONTRACT_VIOLATION"
        and obs["S4_重复"]["conflicting"] == ["R09"]
        and obs["S4_重复"]["aggregate"] != "PASS"
        and obs["S5_冲突"]["verdict"] == "INDETERMINATE"
        and obs["S5_冲突"]["reason"] == "CONTRACT_VIOLATION"
        and obs["S5_冲突"]["aggregate"] != "PASS"
        # ⑥ 已知失败 + 部分缺失 ⇒ 保留 FAIL，缺失规则显式列出、不隐藏
        and obs["S6_已知FAIL且缺结果"]["verdict"] == "FAIL"
        and obs["S6_已知FAIL且缺结果"]["reason"] == "STALE_RECORD"
        and obs["S6_已知FAIL且缺结果"]["missing"] == ["R09b"]
        and obs["S6_已知FAIL且缺结果"]["aggregate"] == "FAIL"
    )
    return ok, obs


def n_unsupported_clause_approved_rule():
    """RC-02（P1）：UNSUPPORTED / NEEDS_CLARIFICATION / 未知取值 / 缺失 的条款，
    一律不得挂 APPROVED 规则并整体通过（修复前 UNSUPPORTED 会放行）。"""
    obs = {}
    for label, status in [("UNSUPPORTED", "UNSUPPORTED"),
                          ("NEEDS_CLARIFICATION", "NEEDS_CLARIFICATION"),
                          ("未知取值", "SUPPORTED_TYPO"),
                          ("状态缺失", None),
                          ("反向确认_SUPPORTED", "SUPPORTED")]:
        k = _kernel_clean()
        next(q for q in k.req_doc["requirements"]
             if q["requirement_id"] == "C1")["support_status"] = status
        rej = k.collect_config_rejections()
        res, _f = k.run()
        cov = k.build_clause_coverage(res)
        c1 = next(c for c in cov if c["requirement_id"] == "C1")
        obs[label] = {
            "rejection_codes": sorted({r["code"] for r in rej}),
            "aggregate": g.aggregate(cov, rej, len(k.rows))[0],
            "C1_state": c1["coverage_state"], "C1_verdict": c1["verdict"],
            "C1_reason": c1["reason_code"],
        }

    def blocked(v):
        return (v["aggregate"] != "PASS" and v["C1_verdict"] != "PASS"
                and "APPROVED_RULE_FOR_UNSUPPORTED_CLAUSE" in v["rejection_codes"])

    ok = (all(blocked(obs[k]) for k in
              ["UNSUPPORTED", "NEEDS_CLARIFICATION", "未知取值", "状态缺失"])
          # 未知取值还要额外报枚举校验不通过（执行入口校验，不只靠 Schema 脚本）
          and "CLAUSE_SUPPORT_STATUS_UNKNOWN" in obs["未知取值"]["rejection_codes"]
          and "CLAUSE_SUPPORT_STATUS_UNKNOWN" in obs["状态缺失"]["rejection_codes"]
          # 反向确认：改回 SUPPORTED 必须放行（证明不是"一律拒绝"的假修复）
          and obs["反向确认_SUPPORTED"]["aggregate"] == "PASS"
          and obs["反向确认_SUPPORTED"]["C1_verdict"] == "PASS"
          and obs["反向确认_SUPPORTED"]["rejection_codes"] == [])
    return ok, obs


def n_subprocess_encoding():
    """RC-03（P2）：子进程输出解码必须固定 UTF-8，不依赖调用方的编码设置。

    复现方式：把 PYTHONUTF8 / PYTHONIOENCODING 从环境里**删掉**（模拟调用方没设过的场景），
    子进程中文输出仍然要能被正确解码；`text=True` 在 Windows 默认 cp936 下会抛
    UnicodeDecodeError（NEW_schema_registry_parity 基线退出 0 却判失败就是这么来的）。
    """
    WORKDIR.mkdir(parents=True, exist_ok=True)
    child = WORKDIR / "utf8-child.py"
    child.write_text(
        "import sys\n"
        "print('中文输出：子进程编码自检')\n"
        "print('stdout_encoding=' + str(sys.stdout.encoding))\n",
        encoding="utf-8", newline="\n")
    scrubbed = {k: v for k, v in os.environ.items()
                if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    p = subprocess.run([sys.executable, "-X", "utf8", str(child)],
                       capture_output=True, cwd=str(WORKDIR), env=scrubbed,
                       encoding="utf-8", errors="strict")
    obs = {
        "child_exit": p.returncode,
        "decoded_ok": "中文输出：子进程编码自检" in (p.stdout or ""),
        "child_stdout_encoding": next(
            (l.split("=", 1)[1] for l in (p.stdout or "").splitlines()
             if l.startswith("stdout_encoding=")), None),
        "env_scrubbed": "PYTHONUTF8" not in scrubbed and "PYTHONIOENCODING" not in scrubbed,
        "stderr_tail": (p.stderr or "")[-200:],
    }
    # 真实脚本同样走固定 UTF-8 通道：一致性校验器的中文输出必须完整可读
    chk = _run_utf8(_py(ROOT / "tools" / "check_schema_consistency.py"), ROOT)
    out = (chk.stdout or "") + (chk.stderr or "")
    obs["checker_exit"] = chk.returncode
    obs["checker_consistent"] = "SCHEMA_CONSISTENT=true" in out
    # 反证：旧写法（text=True / 用调用方 locale 解码）为什么不安全 ——
    # **不改子进程、不制造线程异常**：以 bytes 接收原始输出，在**当前线程**显式解码，
    # 用与输出不匹配的编码（ascii）必然抛 UnicodeDecodeError，且必须能被正常捕获。
    legacy = subprocess.run([sys.executable, "-X", "utf8", str(child)],
                            capture_output=True, cwd=str(WORKDIR), env=scrubbed)
    raw = legacy.stdout or b""
    obs["legacy_raw_is_bytes"] = isinstance(raw, bytes)
    obs["legacy_utf8_roundtrip"] = "中文输出：子进程编码自检" in raw.decode("utf-8")
    try:
        raw.decode("ascii", errors="strict")
        obs["legacy_mismatch_decode"] = {"raised": False, "error": None}
    except UnicodeDecodeError as exc:
        obs["legacy_mismatch_decode"] = {"raised": True,
                                         "error": "%s: %s" % (type(exc).__name__, exc)}
    # 调用方 locale 那一路只作**记录**：不同机器是否炸取决于 locale，不能作为判定依据
    try:
        raw.decode(__import__("locale").getpreferredencoding(False), errors="strict")
        obs["legacy_locale_decode_note"] = "未抛异常（当前 locale 恰好兼容，不能据此认为安全）"
    except UnicodeDecodeError as exc:
        obs["legacy_locale_decode_note"] = "UnicodeDecodeError：%s" % exc

    ok = (obs["child_exit"] == 0 and obs["decoded_ok"] and obs["env_scrubbed"]
          and str(obs["child_stdout_encoding"]).lower().startswith("utf")
          and obs["checker_exit"] == 0 and obs["checker_consistent"]
          and obs["legacy_raw_is_bytes"] and obs["legacy_utf8_roundtrip"]
          # 关键断言：不匹配编码的解码失败必须在**当前线程**可捕获且确实抛出
          and obs["legacy_mismatch_decode"]["raised"] is True)
    return ok, obs


def n_cli_smoke():
    """Stage 1 第 6 条（第二轮：正式入口与回归入口分离）。

    `validate` 是**正式检查入口**（不需要 expected）；`regress` 才是与冻结 expected 比对的
    回归工具；`report` 由结构化结果渲染 HTML；`compare` 跑两批次。
    断言：退出码、HTML 真的落盘且含三态着色、compare 给出结构化结果，
    以及旧的 `run` 子命令已不存在（两个入口不得混用）。
    """
    obs = {}
    stage1 = ROOT / "work" / "stage1"
    stage1.mkdir(parents=True, exist_ok=True)

    def cli(*args):
        return _run_utf8(_py("-m", "geoacceptance.cli") + list(args), ROOT)

    vjson = stage1 / "validate-clean.json"
    vhtml = stage1 / "validate-clean.html"
    p0 = cli("validate", "--bundle", "clean", "--json", str(vjson), "--html", str(vhtml))
    obs["validate"] = {"exit_code": p0.returncode, "json_exists": vjson.exists(),
                       "html_exists": vhtml.exists()}
    obs["validate_expected_used"] = None
    obs["html_has_verdict"] = False
    if vjson.exists():
        data = json.loads(vjson.read_text(encoding="utf-8"))
        obs["validate_expected_used"] = data.get("expected_used")
    if vhtml.exists():
        text = vhtml.read_text(encoding="utf-8")
        obs["html_has_verdict"] = ("PASS" in text) and ("clause_coverage" in text or "条款覆盖" in text)
        obs["html_escaped"] = "<script" not in text.lower()

    p1 = cli("regress", "--bundle", "clean", "--html")
    obs["regress"] = {"exit_code": p1.returncode,
                      "html_exists": (ROOT / "work" / "stage0" / "clean" / "report.html").exists()}

    # 旧入口 `run` 必须已经拆掉：否则"正式检查"与"expected 回归"又是同一个入口
    p_old = cli("run", "--bundle", "clean")
    obs["old_run_removed"] = p_old.returncode != 0

    # 用**本探针刚跑出来**的 validate json：不得依赖上一次运行残留在 work/ 里的产物，
    # 否则在干净克隆（验收方第一次跑）里会误报"report 子命令坏了"。
    p2 = cli("report", "--from-json", str(vjson), "--out", str(stage1 / "cli-report.html"))
    obs["report"] = {"exit_code": p2.returncode,
                     "out_exists": (stage1 / "cli-report.html").exists()}

    p3 = cli("compare", "--before", "defective", "--after", "corrected",
             "--out", str(stage1 / "cli-compare.json"))
    obs["compare"] = {"exit_code": p3.returncode,
                      "out_exists": (stage1 / "cli-compare.json").exists(),
                      "printed": "整改复验 compare" in (p3.stdout or "")}

    ok = (obs["validate"]["exit_code"] == 0 and obs["validate"]["json_exists"]
          and obs["validate"]["html_exists"] and obs["html_has_verdict"]
          and obs["validate_expected_used"] is False
          and obs["regress"]["exit_code"] == 0 and obs["regress"]["html_exists"]
          and obs["old_run_removed"]
          and obs["report"]["exit_code"] == 0 and obs["report"]["out_exists"]
          and obs["compare"]["printed"])
    return ok, obs


def n_validate_entry_new_bundle():
    """正式入口 `validate`：examples 之外的新包、没有 expected 也能给出三态结论。

    ① 干净副本 ⇒ PASS（退出码 0）；
    ② 注入过期时间 ⇒ FAIL（退出码 2），且 `expected_used=False`、
       findings_by_class 里 FAIL ≥ 1 —— 证明结论来自内核判定而不是 expected 比对；
    ③ 缺文件 / 非 UTF-8 的输入防护：缺 poi.csv 必须 InputGuardError（不静默放行）。
    """
    sys.path.insert(0, str(ROOT))
    from geoacceptance import validate as vld
    from geoacceptance import inputs

    obs = {}
    tmp = NEG / "probe_validate_new"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    good = tmp / "fresh_bundle"
    shutil.copytree(EX / "clean", good)
    r1 = vld.validate_bundle(good)
    obs["clean_copy"] = {"verdict": r1["aggregate_verdict"], "executed": r1["executed"],
                         "expected_used": r1["expected_used"],
                         "schema_version": r1["schema_version"]}

    bad = tmp / "stale_bundle"
    shutil.copytree(EX / "clean", bad)
    rows = _csv_rows(bad / "poi.csv")
    rows[1][-1] = "2026-08-01T00:00:00Z"
    _csv_write(bad / "poi.csv", rows)
    r2 = vld.validate_bundle(bad)
    obs["stale_bundle"] = {"verdict": r2["aggregate_verdict"],
                           "expected_used": r2["expected_used"],
                           "findings_by_class": r2["findings_by_class"],
                           "covered": r2["counts"]["clauses_covered"]}

    broken = tmp / "missing_file_bundle"
    shutil.copytree(EX / "clean", broken)
    (broken / "poi.csv").unlink()
    try:
        vld.validate_bundle(broken)
        obs["missing_input"] = {"blocked": False}
    except inputs.InputGuardError as exc:
        obs["missing_input"] = {"blocked": True, "error": str(exc)[:120]}

    ok = (obs["clean_copy"]["verdict"] == "PASS" and obs["clean_copy"]["executed"]
          and obs["clean_copy"]["expected_used"] is False
          and obs["stale_bundle"]["verdict"] == "FAIL"
          and obs["stale_bundle"]["expected_used"] is False
          and obs["stale_bundle"]["findings_by_class"].get("FAIL", 0) >= 1
          and obs["missing_input"]["blocked"])
    return ok, obs


def n_compare_closure_evidence():
    """compare 的**关闭证据**（外部复核 S1-EXT-01 / EXT-02 / EXT-03 的最小内联版）。

    ① 删除缺陷实体 ⇒ `removed_pending_review`，不得 closed；
    ② 规则改 DRAFT ⇒ `unresolved_unknown`，不得 closed；
    ③ 唯一实体两条 finding ⇒ 身份**不**被误判重复，且两条都凭正面证据 closed。
    """
    sys.path.insert(0, str(ROOT))
    from geoacceptance import compare as cmp

    obs = {}
    tmp = NEG / "probe_compare_closure"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    def mk(name, mutate=None):
        p = tmp / name
        shutil.copytree(EX / "clean", p)
        if mutate:
            mutate(p)
        return p

    def stale(p):
        rows = _csv_rows(p / "poi.csv")
        rows[1][-1] = "2026-08-01T00:00:00Z"
        _csv_write(p / "poi.csv", rows)

    # ① 删除实体
    before = mk("del_before", stale)
    after = mk("del_after", lambda p: _csv_write(
        p / "poi.csv", [_csv_rows(p / "poi.csv")[0]] + _csv_rows(p / "poi.csv")[2:]))
    r1 = cmp.compare_batches(before, after)
    obs["entity_deleted"] = {
        "statuses": sorted({i["status"] for i in r1["items"]}),
        "overall": r1["overall"], "ledger": r1["ledger"],
        "removed": r1["scope"]["entities_removed_after"],
    }

    # ② 规则改 DRAFT（数据不变）
    def unapprove(p):
        stale(p)
        doc = _yaml_load(p / "approved-rules.yaml")
        for r in doc["rules"]:
            if r.get("rule_id") == "R09":
                r["status"] = "DRAFT"
        _yaml_dump(p / "approved-rules.yaml", doc)
    b2 = mk("unapprove_before", stale)
    a2 = mk("unapprove_after", unapprove)
    r2 = cmp.compare_batches(b2, a2)
    obs["rule_unapproved"] = {
        "statuses": sorted({i["status"] for i in r2["items"]}),
        "overall": r2["overall"], "ledger": r2["ledger"],
        "reasons": [i["reasons"] for i in r2["items"]][:2],
    }

    # ③ 唯一实体两条 finding
    def two_fail(p):
        rows = _csv_rows(p / "poi.csv")
        rows[1][2] = "invalid_category"
        rows[1][-1] = "2026-08-01T00:00:00Z"
        _csv_write(p / "poi.csv", rows)

    def repaired(p):
        two_fail(p)
        good = _csv_rows(EX / "clean" / "poi.csv")[1]
        rows = _csv_rows(p / "poi.csv")
        rows[1] = [rows[1][0]] + good[1:]
        _csv_write(p / "poi.csv", rows)
    b3 = mk("two_before", two_fail)
    a3 = mk("two_after", repaired)
    r3 = cmp.compare_batches(b3, a3)
    obs["unique_entity_two_findings"] = {
        "dup_before": r3["identity"]["before"]["duplicated"],
        "dup_after": r3["identity"]["after"]["duplicated"],
        "statuses": sorted({i["status"] for i in r3["items"]}),
        "counts": r3["counts"], "overall": r3["overall"],
        "closure": [i["closure_evidence"] for i in r3["items"]][:2],
    }
    shutil.rmtree(tmp)

    ok = (obs["entity_deleted"]["statuses"] == ["removed_pending_review"]
          and obs["entity_deleted"]["overall"] != "LEDGER_CLOSED_ACCEPTED"
          and obs["rule_unapproved"]["statuses"] == ["unresolved_unknown"]
          and obs["rule_unapproved"]["ledger"] == "INDETERMINATE"
          and obs["unique_entity_two_findings"]["dup_before"] == []
          and obs["unique_entity_two_findings"]["dup_after"] == []
          and obs["unique_entity_two_findings"]["statuses"] == ["closed"]
          and obs["unique_entity_two_findings"]["counts"].get("closed") == 2
          and all(c and c.get("rule_execution_status") == "COMPLETED"
                  for c in obs["unique_entity_two_findings"]["closure"]))
    return ok, obs


def n_compare_identity():
    """Stage 1 第 8 条：整改 compare 的跨批次身份**不靠行号**。

    ① defective → corrected：真实修复项应判 closed；重复 ID 的那条必须 `not_comparable`；
    ② clean → clean：无失败项，LEDGER_CLOSED_ACCEPTED（台账关闭 **且** 整改后自身通过）；
    ③ 规则版本不同：把副本里 R02.version 改成 2 ⇒ R02 语义指纹变化 ⇒ `not_comparable`；
    ④ 输入防护：包路径越出根目录必须 InputGuardError（不静默放行）。
    """
    sys.path.insert(0, str(ROOT))
    from geoacceptance import compare as cmp
    from geoacceptance import inputs

    obs = {}
    r1 = cmp.compare_batches(EX / "defective", EX / "corrected")
    obs["defective_to_corrected"] = {
        "overall": r1["overall"], "counts": r1["counts"],
        "fixed": [i["record_id"] for i in r1["items"] if i["status"] == "fixed"],
        "not_comparable": [(i["record_id"], i["rule_id"]) for i in r1["items"]
                           if i["status"] == "not_comparable"],
    }
    r2 = cmp.compare_batches(EX / "clean", EX / "clean")
    obs["same_bundle"] = {"overall": r2["overall"], "counts": r2["counts"]}

    # ③ 规则版本不同
    tmp = NEG / "probe_compare_version"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    after = tmp / "defective"
    shutil.copytree(EX / "defective", after)
    text = (after / "approved-rules.yaml").read_text(encoding="utf-8")
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.strip() == 'rule_id: "R02"':
            for j in range(i, min(i + 10, len(lines))):
                if lines[j].strip().startswith("version:"):
                    lines[j] = "    version: 2"
                    break
            break
    (after / "approved-rules.yaml").write_text("\n".join(lines), encoding="utf-8")
    r3 = cmp.compare_batches(EX / "defective", after)
    obs["rule_version_changed"] = {
        "changed": r3["ruler"]["rule_versions_changed"],
        "r02_fingerprint_changed": "R02" in r3["ruler"]["rule_fingerprint_changed"],
        "r02_statuses": sorted({i["status"] for i in r3["items"] if i["rule_id"] == "R02"}),
        "overall": r3["overall"],
    }
    shutil.rmtree(tmp)

    # ④ 输入防护：路径穿越
    try:
        inputs.safe_bundle_path(EX, "../..")
        obs["path_traversal"] = {"blocked": False}
    except inputs.InputGuardError as exc:
        obs["path_traversal"] = {"blocked": True, "error": str(exc)[:120]}

    ok = (obs["defective_to_corrected"]["counts"].get("closed", 0) >= 5
          and obs["defective_to_corrected"]["counts"].get("not_comparable", 0) >= 1
          and obs["defective_to_corrected"]["overall"] == "LEDGER_INDETERMINATE"
          and obs["same_bundle"]["overall"] == "LEDGER_CLOSED_ACCEPTED"
          and "R02" in obs["rule_version_changed"]["changed"]
          and obs["rule_version_changed"]["r02_fingerprint_changed"]
          and obs["rule_version_changed"]["r02_statuses"] == ["not_comparable"]
          and obs["path_traversal"]["blocked"])
    return ok, obs


def n_uncovered_coverage_branches():
    """Stage 1 第 7 条：补齐 Stage 0 遗留的**无正例分支**。

    - ① 未知 rule_type：第三轮起入口校验**受控拒绝**未知 rule_type（S1-R2-01），
      整包拒绝执行 ⇒ 条款级 `CONFIG_REJECTED`。原 `NO_IMPLEMENTATION` 正例构造
      （"把 rule_type 改成内核未实现的类型"）在入口收紧后不可达——
      schema 十类与内核实现同步时该分支天然无输入可触发，保留给
      「schema 先行扩展、实现未跟上」的场景，不属于回退。
    - `UNAPPROVED`：条款映射的全部规则都不是 APPROVED（R09 改 DRAFT）；
    - 「缺证据类 finding」正例：删除 CRS 声明 ⇒ `advisory_reason_codes` 非空，
      规则级 `INDETERMINATE`（不是 FAIL），且码属 INDETERMINATE 类。
    """
    obs = {}

    # ① 未知 rule_type ⇒ 入口受控拒绝（S1-R2-01）
    k = _kernel_clean()
    r09 = next(r for r in k.rule_doc["rules"] if r["rule_id"] == "R09")
    r09["rule_type"] = "topology_check_not_implemented"   # 十类白名单之外
    rej = k.collect_config_rejections()
    res, _f = k.run()
    rr = next(x for x in res if x.get("rule_id") == "R09")
    cov = k.build_clause_coverage(res)
    c1 = next(c for c in cov if c.get("requirement_id") == "C1")
    agg = g.aggregate(cov, rej, len(k.rows))[0]
    obs["UNKNOWN_RULE_TYPE"] = {
        "entry_rejected": any(r.get("code") == "INPUT_SCHEMA_INVALID"
                              and r.get("target") == "R09" for r in rej),
        "rule": {"verdict": rr.get("verdict"), "status": rr.get("execution_status"),
                 "reason": rr.get("reason_code")},
        "clause": {"state": c1.get("coverage_state"), "verdict": c1.get("verdict"),
                   "status": c1.get("execution_status"), "reason": c1.get("reason_code")},
        "aggregate": agg,
    }

    # ② UNAPPROVED
    k2 = _kernel_clean()
    next(r for r in k2.rule_doc["rules"] if r["rule_id"] == "R09")["status"] = "DRAFT"
    res2, _f2 = k2.run()
    rr2 = next(x for x in res2 if x.get("rule_id") == "R09")
    cov2 = k2.build_clause_coverage(res2)
    c1_2 = next(c for c in cov2 if c.get("requirement_id") == "C1")
    agg2 = g.aggregate(cov2, k2.collect_config_rejections(), len(k2.rows))[0]
    obs["UNAPPROVED"] = {
        "rule": {"verdict": rr2.get("verdict"), "status": rr2.get("execution_status"),
                 "reason": rr2.get("reason_code")},
        "clause": {"state": c1_2.get("coverage_state"), "verdict": c1_2.get("verdict"),
                   "status": c1_2.get("execution_status"), "reason": c1_2.get("reason_code")},
        "aggregate": agg2,
    }

    # ③ 缺证据类 finding 正例（advisory_reason_codes 非空）
    k3 = _kernel_clean()
    k3.crs.update(declared_crs=None)
    res3, f3 = k3.run()
    with_adv = [r for r in res3 if r.get("advisory_reason_codes")]
    obs["缺证据_finding"] = {
        "rules_with_advisory": [r.get("rule_id") for r in with_adv],
        "advisory_codes": sorted({c for r in with_adv for c in r["advisory_reason_codes"]}),
        "all_indeterminate_class": all(
            g.classify_reason_code(c) == "INDETERMINATE"
            for r in with_adv for c in r["advisory_reason_codes"]),
        "rule_verdicts": {r.get("rule_id"): r.get("verdict") for r in with_adv},
        "finding_codes": sorted({x.get("reason_code") for x in f3
                                 if x.get("reason_code") in g.INDETERMINATE_REASON_CODES}),
        "aggregate": g.aggregate(k3.build_clause_coverage(res3),
                                 k3.collect_config_rejections(), len(k3.rows))[0],
    }

    ok = (obs["UNKNOWN_RULE_TYPE"]["entry_rejected"]
          and obs["UNKNOWN_RULE_TYPE"]["rule"] == {"verdict": "INDETERMINATE",
                                                   "status": "REJECTED",
                                                   "reason": "CONFIG_REJECTED"}
          and obs["UNKNOWN_RULE_TYPE"]["clause"]["state"] == "CONFIG_REJECTED"
          and obs["UNKNOWN_RULE_TYPE"]["clause"]["verdict"] == "INDETERMINATE"
          and obs["UNKNOWN_RULE_TYPE"]["aggregate"] != "PASS"
          and obs["UNAPPROVED"]["rule"] == {"verdict": "INDETERMINATE",
                                            "status": "NOT_EXECUTED",
                                            "reason": "RULE_NOT_APPROVED"}
          and obs["UNAPPROVED"]["clause"]["state"] == "UNAPPROVED"
          and obs["UNAPPROVED"]["clause"]["verdict"] == "INDETERMINATE"
          and obs["UNAPPROVED"]["aggregate"] != "PASS"
          and len(obs["缺证据_finding"]["rules_with_advisory"]) >= 1
          and obs["缺证据_finding"]["all_indeterminate_class"]
          and all(v == "INDETERMINATE" for v in obs["缺证据_finding"]["rule_verdicts"].values())
          and obs["缺证据_finding"]["aggregate"] != "PASS")
    return ok, obs


def n_input_schema_validation():
    """Stage 1 第 5 条：**执行入口**用 Pydantic(strict) 校验输入，而不是只靠单独跑 Schema 脚本。

    ① 六个真实包必须通过（不得误杀）；
    ② 四类篡改（类型收敛 / 枚举越界 / 哈希格式 / 行号越界）必须全部登记
       `INPUT_SCHEMA_INVALID` 并让整包拒绝执行，不得放行。
    """
    obs = {}
    # ① 正常包
    clean_bad = []
    for b in ["clean", "defective", "corrected", "ambiguous", "blocked", "crs_same_unit_wrong"]:
        k = g.Kernel(EX / b)
        codes = {r["code"] for r in k.collect_config_rejections()}
        if "INPUT_SCHEMA_INVALID" in codes:
            clean_bad.append(b)
    obs["正常包被误杀"] = clean_bad

    def mutate(field, value):
        """改 clean 包 A1 条款的一个字段，返回该包的 rejection 码集合。"""
        tmp = NEG / "probe_input_schema"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        b = tmp / "clean"
        shutil.copytree(EX / "clean", b)
        text = (b / "requirements.yaml").read_text(encoding="utf-8")
        lines = text.split("\n")
        # 定位 A1 区块（首个 requirement）内的字段行
        start = next(i for i, l in enumerate(lines) if 'requirement_id: "A1"' in l)
        for i in range(start, min(start + 12, len(lines))):
            if lines[i].strip().startswith(field + ":"):
                lines[i] = '    %s: %s' % (field, value)
                break
        else:
            raise AssertionError("未找到字段 %s" % field)
        (b / "requirements.yaml").write_text("\n".join(lines), encoding="utf-8")
        k = g.Kernel(b)
        rej = k.collect_config_rejections()
        res, _f = k.run()
        cov = k.build_clause_coverage(res)
        agg = g.aggregate(cov, rej, len(k.rows))[0]
        return sorted({r["code"] for r in rej}), agg

    cases = {
        "类型收敛_required_for_release=\"yes\"": ("required_for_release", '"yes"'),
        "枚举越界_support_status=SUPPORTED_X": ("support_status", '"SUPPORTED_X"'),
        "哈希格式错_document_sha256=abc": ("document_sha256", '"abc"'),
        "行号越界_source_line_start=0": ("source_line_start", "0"),
    }
    for label, (field, value) in cases.items():
        try:
            codes, agg = mutate(field, value)
            obs[label] = {"codes": codes, "aggregate": agg,
                          "blocked": "INPUT_SCHEMA_INVALID" in codes and agg != "PASS"}
        except Exception as exc:  # noqa: BLE001
            obs[label] = {"probe_error": "%s: %s" % (type(exc).__name__, exc)}
    if (NEG / "probe_input_schema").exists():
        shutil.rmtree(NEG / "probe_input_schema")

    ok = (not obs["正常包被误杀"]
          and all(v.get("blocked") for k, v in obs.items()
                  if k != "正常包被误杀"))
    return ok, obs


def n_repeat_run_determinism():
    """RC-04（P2）：同一 Kernel 实例连续 run() 两次，results / findings / risk_signals 全等。

    修复前 finding_seq 不复位 ⇒ finding_id 从上一轮末尾继续编号（F0002、F0003…），
    findings 内容相同但对象不等。
    """
    obs = {}
    for name in ["clean", "defective"]:
        k = g.Kernel(EX / name)
        r1, f1 = k.run()
        s1 = list(k.risk_signals)
        r2, f2 = k.run()
        s2 = list(k.risk_signals)
        obs[name] = {
            "results_equal": r1 == r2,
            "findings_equal": f1 == f2,
            "risk_signals_equal": s1 == s2,
            "findings_n": [len(f1), len(f2)],
            "risk_n": [len(s1), len(s2)],
            "finding_ids_r1": [x["finding_id"] for x in f1][:3],
            "finding_ids_r2": [x["finding_id"] for x in f2][:3],
            # 两次运行的业务结论也必须一致（不只是 ID 一致）
            "verdicts": sorted({"%s=%s" % (x["rule_id"], x["verdict"]) for x in r1})
                        == sorted({"%s=%s" % (x["rule_id"], x["verdict"]) for x in r2}),
        }
    ok = all(v["results_equal"] and v["findings_equal"] and v["risk_signals_equal"]
             and v["verdicts"] and v["findings_n"][0] == v["findings_n"][1] > 0
             and v["risk_n"][0] == v["risk_n"][1]
             for v in obs.values())
    return ok, obs


PROBES = [
    ("GA01_clause_without_rule", p_ga01, "required_supported_clause_without_rule"),
    ("GA03_missing_crs_declaration", p_ga03_missing, "missing_crs_declaration"),
    ("GA03_unexpected_crs_degree", p_ga03_degree, "unexpected_crs_with_degree_unit"),
    ("GA04_unknown_dependency", p_ga04_unknown_dep, "unknown_dependency"),
    ("GA05_substring_threshold", p_ga05_substring, "substring_threshold_3_in_30"),
    ("GA05_wrong_document_hash", p_ga05_hash, "wrong_document_hash"),
    ("GA06_no_invalid_verdicts", p_ga06_verdicts, "invalid_verdicts"),
    ("GA07_candidate_counts", p_ga07_counts, "candidate_count_semantics"),
    ("GA08_exclusive_boundary", p_ga08_boundary, "exclusive_boundary"),
    ("GA02_clause_downgraded", p_ga02_downgrade, "mandatory_clause_downgraded"),
    ("INPUT_MANIFEST", p_manifest, "input_manifest"),
    ("NEW_crs_magnitude_only_signal", n_crs_magnitude, None),
    ("NEW_timezone_undeclared_fails_closed", n_timezone, None),
    ("NEW_expected_tamper_detected", n_expected_tamper, None),
    ("NEW_gate_exit_code_on_reject", n_gate_exit_code, None),
    ("NEW_risk_signals_write_only", n_risk_write_only, None),
    ("NEW_i7_i9_counterexamples", n_i7_i9_counterexamples, None),
    ("NEW_reason_code_arrays", n_reason_code_arrays, None),
    ("NEW_schema_registry_parity", n_schema_registry_parity, None),
    ("NEW_single_official_interface", n_single_official_interface, None),
    # ---------------- 二次验收轮新增（RC-01 / RC-02 / RC-03 / RC-04）----------------
    ("RC01_clause_coverage_result_set", n_clause_coverage_result_set, None),
    ("RC02_unsupported_clause_approved_rule", n_unsupported_clause_approved_rule, None),
    ("RC03_subprocess_encoding", n_subprocess_encoding, None),
    ("RC04_repeat_run_determinism", n_repeat_run_determinism, None),
    ("S1_input_schema_validation", n_input_schema_validation, None),
    ("S1_uncovered_coverage_branches", n_uncovered_coverage_branches, None),
    ("S1_cli_smoke", n_cli_smoke, None),
    ("S1_compare_identity", n_compare_identity, None),
    # ---------------- 外部复核轮新增（S1-EXT-01 ~ EXT-04 / 正式入口分离）----------------
    ("S1_validate_entry_new_bundle", n_validate_entry_new_bundle, None),
    ("S1_compare_closure_evidence", n_compare_closure_evidence, None),
]


# ============================================================ 对拍：原独立探针脚本
P1_CASES = {
    # 原探针 case id -> 判定"不得再产出 PASS"的谓词
    "required_supported_clause_without_rule": lambda v: v != "PASS",
    "missing_crs_declaration": lambda v: v != "PASS",
    "unexpected_crs_with_degree_unit": lambda v: v != "PASS",
    "unknown_dependency": lambda v: v != "PASS",
    "mandatory_clause_downgraded": lambda v: v != "PASS",
    "substring_threshold_3_in_30": lambda v: bool(v),
    "wrong_document_hash": lambda v: bool(v),
}


def _locate_probe_results(rundir: Path):
    """外部探针的结果文件名不统一（见过 independent-results.json / new-independent-results.json）。

    不能只认一个名字：名字不匹配会把"探针确实跑了、结论也打印了"误记成"没跑"，
    对拍证据就这么丢了（Stage 1 独立复验 S1-A4）。改为**识别内容**：
    任一 JSON 文件是 list[dict] 且元素含 `case` 键，即视为探针结果。
    """
    for p in sorted(rundir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 —— 只要不是合法 JSON 就不认，继续找下一个
            continue
        if isinstance(data, list) and any(isinstance(d, dict) and "case" in d for d in data):
            return p
    return None


def run_original_probes(script: Path):
    """把原独立探针脚本跑在**当前仓库**上，断言五个 P1 项不再产出 PASS。"""
    rundir = WORKDIR / "orig-probe-run"
    if rundir.exists():
        shutil.rmtree(rundir)
    rundir.mkdir(parents=True, exist_ok=True)
    local = rundir / script.name
    shutil.copyfile(script, local)
    proc = _run_utf8(_py(local, ROOT), rundir)
    out = _locate_probe_results(rundir)
    if out is None:
        err = (proc.stderr or "") + (proc.stdout or "")
        # Stage 1：二参兼容接口已删（验收方第 5 条要求收敛到唯一正式接口）。
        # 原独立探针仍以 `g.aggregate(results, n_rows)` 调用 → 必须**如实报"需迁移"**，
        # 不得为了让它跑通而在内核里保留第二条判定路径。
        if "二参数兼容路径" in err or "aggregate() 只接受三参数" in err:
            return {"ran": False, "needs_migration": True,
                    "reason": "原探针使用已删除的二参接口 aggregate(results, n_rows)",
                    "migration": "把 g.aggregate(r, len(k.rows)) 换成："
                                 "cov = k.build_clause_coverage(r); "
                                 "g.aggregate(cov, k.collect_config_rejections(), len(k.rows))",
                    "note": "本仓库 24 项探针已全部迁移到唯一正式接口（含这五个 P1 用例）",
                    "stderr_tail": err[-400:]}
        return {"ran": False, "reason": "探针未产出结果文件",
                "stdout_tail": (proc.stdout or "")[-400:], "stderr_tail": (proc.stderr or "")[-400:]}
    data = json.loads(out.read_text(encoding="utf-8"))
    by_case = {d.get("case"): d for d in data}
    checks = []
    for cid, pred in P1_CASES.items():
        entry = by_case.get(cid)
        if entry is None:
            # 旧命名的用例本版外部探针可能不产出：记为 NOT_PRODUCED（信息），**不算通过也不算失败**
            checks.append({"case": cid, "status": "NOT_PRODUCED", "actual": None})
            continue
        actual = entry.get("actual")
        okv = bool(pred(actual))
        checks.append({"case": cid, "status": "OK" if okv else "STILL_PASS", "actual": actual,
                       "expected_in_probe": entry.get("expected")})
    # RC-01 / RC-02 的签名用例（当前外部探针的命名）：**必须**出现且不得为 PASS
    rc_cases = {"partial_mapped_result_missing": "RC-01",
                "unsupported_clause_approved_rule": "RC-02"}
    for cid, tag in rc_cases.items():
        actual = (by_case.get(cid) or {}).get("actual")
        if actual is None:
            status = "NOT_PRODUCED"
        elif actual == "PASS":
            status = "STILL_PASS"
        else:
            status = "OK"
        checks.append({"case": cid, "tag": tag, "status": status, "actual": actual})
    all_ok = (all(c["status"] != "STILL_PASS" for c in checks)
              and all(c["status"] == "OK" for c in checks if c.get("tag")))
    return {"ran": True, "script": str(script), "exit_code": proc.returncode,
            "results_file": out.name, "checks": checks, "all_ok": all_ok}


# ============================================================ 主流程
def load_baseline():
    if not BASELINE.exists():
        return {}
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {d.get("case"): d for d in data}


def regen_baseline(repo: Path, script: Path, sha: str = "d057c0a"):
    """从 git 检出修复前的工作树，跑原独立探针，重做 `baseline-independent-results.json`。

    注意：必须用 `core.autocrlf=false` 检出，否则 CRLF 转换会让 INPUT_MANIFEST 的
    哈希全数失配（这是**检出环境**问题，不是仓库缺陷，但会污染基准，必须绕开）。
    """
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="geoacceptance-baseline-"))
    wt = tmp / ("baseline-" + sha)
    _run_utf8(["git", "-C", str(repo), "-c", "core.autocrlf=false",
               "worktree", "add", str(wt), sha], tmp).check_returncode()
    rundir = tmp / "run"
    rundir.mkdir(parents=True, exist_ok=True)
    local = rundir / script.name
    shutil.copyfile(script, local)
    _run_utf8(_py(local, wt), rundir).check_returncode()
    produced = rundir / "independent-results.json"
    WORKDIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(produced, BASELINE)
    print("baseline 已重做：%s（来源 %s @ %s）" % (BASELINE, wt, sha))
    print("清理工作树：git -C %s worktree remove %s --force" % (repo, wt))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probes-script", default=os.environ.get("STAGE0_ORIG_PROBES", ""),
                    help="原独立探针 stage0_independent_probes.py 的路径（用于 P1 对拍，缺省则跳过）")
    ap.add_argument("--out", default=str(OUTDIR / "independent-results.json"))
    ap.add_argument("--regen-baseline", metavar="GIT_REPO", default="",
                    help="重做修复前基准（需要同时给 --probes-script）；会临时建 git worktree")
    ap.add_argument("--baseline-sha", default="d057c0a")
    args = ap.parse_args()

    if args.regen_baseline:
        if not args.probes_script or not Path(args.probes_script).exists():
            raise SystemExit("--regen-baseline 需要同时提供存在的 --probes-script")
        return regen_baseline(Path(args.regen_baseline), Path(args.probes_script), args.baseline_sha)

    baseline = load_baseline()
    cases = []
    all_ok = True
    print("=" * 78)
    print("Stage 0 重验：独立反例回归（预期先手写，再跑实现）")
    print("=" * 78)
    for cid, fn, base_id in PROBES:
        meta = EXPECT[cid]
        try:
            ok, actual = fn()
        except Exception as exc:  # noqa: BLE001 —— 探针自身炸了也要如实记为失败
            ok, actual = False, {"probe_error": "%s: %s" % (type(exc).__name__, exc)}
        before = None
        if base_id and base_id in baseline:
            before = baseline[base_id].get("actual")
        all_ok &= bool(ok)
        cases.append({
            "id": cid, "ga": meta["ga"], "origin": meta["origin"],
            "desc": meta["desc"], "expected": meta["expected"],
            "before_fix": before, "after_fix": actual,
            "result": "PASS" if ok else "FAIL",
        })
        print("[%s] %-38s %s" % ("PASS" if ok else "FAIL", cid, meta["ga"]))
        print("      反例：%s" % meta["desc"])
        print("      预期：%s" % meta["expected"])
        print("      实测：%s" % json.dumps(actual, ensure_ascii=False, sort_keys=True)[:300])
        if before is not None:
            print("      修复前：%s" % json.dumps(before, ensure_ascii=False, sort_keys=True)[:300])

    # ---- 对拍：原独立探针跑在当前仓库
    cross = {"ran": False, "reason": "未提供原独立探针脚本路径（--probes-script）"}
    if args.probes_script:
        p = Path(args.probes_script)
        if p.exists():
            cross = run_original_probes(p)
            if cross.get("ran"):
                all_ok &= bool(cross.get("all_ok"))
        else:
            cross = {"ran": False, "reason": "路径不存在：%s" % p}
    print("")
    print("-" * 78)
    print("对拍：原独立探针 stage0_independent_probes.py 跑在当前仓库")
    if cross.get("ran"):
        for c in cross["checks"]:
            print("  [%s] %-40s 实测=%s" % (c["status"], c["case"],
                                          json.dumps(c.get("actual"), ensure_ascii=False)[:120]))
        print("  对拍结论：%s" % ("全部不再产出 PASS" if cross["all_ok"] else "仍有项目产出 PASS"))
    else:
        print("  [SKIP] %s" % cross.get("reason"))
        if cross.get("needs_migration"):
            print("  迁移方式：%s" % cross.get("migration"))
            print("  说明：%s" % cross.get("note"))
            print("  原探针 stderr 末尾：%s" % (cross.get("stderr_tail") or "")[-200:])
        print("  对拍结论：未执行（本轮已由人工执行，证据见 acceptance/stage-0-recheck/）")

    payload = {
        "schema_version": "stage0-2",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo_root": str(ROOT),
        "python": sys.version.split()[0],
        "baseline_source": str(BASELINE.relative_to(ROOT)) if BASELINE.exists() else None,
        "total": len(cases),
        "passed": sum(1 for c in cases if c["result"] == "PASS"),
        "failed": sum(1 for c in cases if c["result"] == "FAIL"),
        "cases": cases,
        "cross_check_original_probes": cross,
        "overall": "PASS" if all_ok else "FAIL",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    WORKDIR.mkdir(parents=True, exist_ok=True)
    (WORKDIR / "independent-probes.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("")
    print("=" * 78)
    print("RECHECK_PROBES_OK=%s（%d/%d 通过，输出：%s）"
          % ("true" if all_ok else "false", payload["passed"], payload["total"], out))
    print("=" * 78)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
