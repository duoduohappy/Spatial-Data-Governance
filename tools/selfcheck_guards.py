"""负面自检：验证护栏真的会拦住问题，而不是写上去好看。

上一轮独立验收点名：原来的 C 项只是"检查现有 manifest 的 mode 是否为 manual"，
属于**静态一致性检查**，不是负面测试——它从未证明"往里塞一个 live 产物会被拦"。
本轮按契约 §9.5 重排为 7 项（打印 8 行，C 与 C2 同属 C 组）：

  A. 伪造引用     —— 篡改 source_quote 使其与原文行内容不一致（真注入负面）
  B. 无来源阈值   —— 把 R09 的 max_age_days 改成原文中不存在的数字（真注入负面）
  C. 产物 mode 一致性检查 —— 已产出的 manifest 必须全部为 manual（**一致性**检查，非负面）
  C2. 冒用 live   —— **真注入负面**：真实写入一个 mode=live 的 manifest 并跑同一检查，断言被拦截；
                     同时反向确认"改回 manual 后不报错"（证明不是永远失败的假护栏）
  D. 空数据不得判定通过 —— 清空 poi.csv 数据行（真注入负面）
  E. 缺 CRS 声明不得判 FAIL —— 移除 declared_crs，总体必须为 INDETERMINATE（真注入负面）
  F. 候选不得计入失败 —— clean 的 R10 records_failed==0 且 records_indeterminate==2（口径断言）
  G. 未知依赖必须被拒 —— 注入 NONEXISTENT_RULE 后 config_rejections 非空（真注入负面）

"真负面"的两条硬性要求：
  1. 变异必须**真实发生**（文件真写盘或对象真改字段），不是只检查既有产物；
  2. 必须同时给出**反向确认**（未变异时检查不报错），否则"永远失败"的护栏同样是假的。

任一项没有拦住，本脚本以非 0 退出。
"""
import json
import shutil
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
TMP = ROOT / "work" / "negatives"
STAGE0_OUT = ROOT / "work" / "stage0"


def copy_bundle(src: str, dst: str) -> Path:
    s, d = EX / src, TMP / dst
    if d.exists():
        shutil.rmtree(d)
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(s, d)
    # 期望结果随主包一起复制；负面用例不改动期望文件
    return d


def run_gate(bundle_dir: Path):
    """直接以 Kernel 方式复用 stage0_gate 的前置校验逻辑。"""
    sys.path.insert(0, str(ROOT / "tools"))
    import stage0_gate as g
    k = g.Kernel(bundle_dir)
    # 引用逐字一致 + 来源文档哈希 + 结构化参数来源（契约 §6.2）
    return k.verify_quotes() + k.verify_parameter_sources()


def check(name, condition, detail):
    status = "PASS" if condition else "FAIL"
    print("[%s] %s：%s" % (status, name, detail))
    return bool(condition)


# ---------------------------------------------------------------- C / C2 共用的 mode 政策
def stage0_mode_problems(manifest: dict):
    """Stage 0 的 mode 政策（契约 §1 / 门禁 docstring）：本阶段无模型调用，mode 必须为 manual。

    返回问题列表；为空表示通过。与 schemas/run_manifest.schema.json 的 enum 是两回事：
    Schema 允许 live/replay/manual（留给后续阶段），**Stage 0 的政策**只允许 manual。
    """
    problems = []
    if not isinstance(manifest, dict):
        return ["manifest 不是对象：%r" % type(manifest).__name__]
    mode = manifest.get("mode")
    if mode != "manual":
        problems.append("mode=%r，Stage 0 只允许 manual（本阶段无模型调用，不得标示为 live）" % mode)
    return problems


def scan_manifest_dir(d: Path):
    """扫一个目录（或 work/stage0）下的全部 run_manifest.json，返回非 manual 的清单。"""
    bad = []
    for m in sorted(d.glob("*/run_manifest.json")):
        data = json.loads(m.read_text(encoding="utf-8"))
        if stage0_mode_problems(data):
            bad.append(str(m))
    return bad


def main():
    ok = True
    sys.path.insert(0, str(ROOT / "tools"))

    # A. 伪造引用（真注入负面：真实改写 requirements.yaml 后跑前置校验）
    d = copy_bundle("clean", "neg_fake_quote")
    req = d / "requirements.yaml"
    text = req.read_text(encoding="utf-8")
    text = text.replace('source_quote: "A1. 每条记录必须包含全部必填字段。"',
                        'source_quote: "A1. 必填字段必须存在（改写后的伪引用）。"')
    req.write_text(text, encoding="utf-8")
    problems = run_gate(d)
    ok &= check("A 伪造引用必须被拦截", any("不一致" in p or "越界" in p for p in problems),
                "拦截信息：" + (problems[0][:70] if problems else "未拦截"))
    # 反向确认：未变异的原始包不得报错，否则护栏是"永远失败"的假护栏
    ok &= check("A 反向确认：未变异包不得报错", not run_gate(copy_bundle("clean", "neg_fake_quote_base")),
                "clean 原始包前置校验为空")

    # B. 无来源阈值（真注入负面）
    d = copy_bundle("clean", "neg_threshold")
    rules = d / "approved-rules.yaml"
    text = rules.read_text(encoding="utf-8")
    text = text.replace("max_age_days: 30", "max_age_days: 365")
    rules.write_text(text, encoding="utf-8")
    problems = run_gate(d)
    ok &= check("B 无来源阈值必须被拦截", any("找不到来源" in p or "PARAMETER" in p for p in problems),
                "拦截信息：" + (problems[0][:70] if problems else "未拦截"))

    # C. 产物 mode 一致性检查（**不是**负面测试，只是产物自检；负面路径在 C2）
    manifests = list(STAGE0_OUT.glob("*/run_manifest.json"))
    bad = scan_manifest_dir(STAGE0_OUT)
    ok &= check("C 产物 mode 一致性检查（已产出 manifest 全部为 manual）",
                bool(manifests) and not bad,
                "检查 manifest %d 个，非 manual 的 %d 个" % (len(manifests), len(bad)))

    # C2. 冒用 live 的**真注入负面路径**
    #  (1) 真实写一个 mode=live 的 manifest 到 work/negatives/neg_live_mode/
    #  (2) 对**该目录**跑与 C 项同一个扫描函数，必须被拦截
    #  (3) 对同一个 manifest 对象跑 Stage 0 政策校验，必须返回非空问题
    #  (4) 反向确认：把 mode 改回 manual 后，同一函数不报错
    live_dir = TMP / "neg_live_mode"
    if live_dir.exists():
        shutil.rmtree(live_dir)
    live_dir.mkdir(parents=True, exist_ok=True)
    src_manifest = STAGE0_OUT / "clean" / "run_manifest.json"
    if src_manifest.exists():
        base_manifest = json.loads(src_manifest.read_text(encoding="utf-8"))
    else:  # 产物缺失时退化为一个最小合法骨架，保证护栏仍可运行
        base_manifest = {"schema_version": "stage0-2", "bundle": "clean", "mode": "manual",
                         "inputs": {}, "tool_version": "stage0-gate/0.2.0 (stdlib)"}
    live_manifest = dict(base_manifest)
    live_manifest["mode"] = "live"
    live_manifest["mode_note"] = "注入用例：冒充 live 以验证护栏会拦截"
    (live_dir / "run_manifest.json").write_text(
        json.dumps(live_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    injected_bad = scan_manifest_dir(TMP)
    ok &= check("C2 注入 mode=live 的产物必须被拦截",
                any("neg_live_mode" in p.replace("\\", "/") for p in injected_bad),
                "扫描 work/negatives 命中非 manual %d 个：%s"
                % (len(injected_bad), [Path(p).parent.name for p in injected_bad]))
    obj_problems = stage0_mode_problems(live_manifest)
    ok &= check("C2 mode=live 的 manifest 对象必须被政策校验拒绝", bool(obj_problems),
                "拦截信息：" + (obj_problems[0] if obj_problems else "未拦截"))
    manual_manifest = dict(base_manifest)
    manual_manifest["mode"] = "manual"
    ok &= check("C2 反向确认：改回 manual 后不得报错", not stage0_mode_problems(manual_manifest),
                "manual manifest 的政策校验为空")

    # D. 空数据不得判定通过（真注入负面：真实清空 poi.csv 数据行）
    import stage0_gate as g
    d = copy_bundle("clean", "neg_empty_rows")
    poi = d / "poi.csv"
    lines = poi.read_text(encoding="utf-8").split("\n")
    poi.write_text("\n".join([lines[0], ""]), encoding="utf-8")
    k = g.Kernel(d)
    results, findings = k.run()
    coverage = k.build_clause_coverage(results)
    agg, reason = g.aggregate(coverage, k.collect_config_rejections(), len(k.rows))
    ok &= check("D 空数据不得判定通过", agg == "INDETERMINATE",
                "实际=%s（%s）" % (agg, reason))

    # E. 缺 CRS 声明不得判 FAIL（契约 §4.4 / A2：缺证据 ⇒ INDETERMINATE）
    k = g.Kernel(EX / "clean")
    k.crs.update(declared_crs=None)
    results, findings = k.run()
    coverage = k.build_clause_coverage(results)
    agg, reason = g.aggregate(coverage, k.collect_config_rejections(), len(k.rows))
    spatial = {r.get("rule_id"): (r.get("verdict"), r.get("execution_status"))
               for r in results if r.get("rule_id") in ("R06", "R08", "R10")}
    spatial_ok = all(v == ("INDETERMINATE", "BLOCKED") for v in spatial.values()) and len(spatial) == 3
    ok &= check("E 缺 CRS 声明不得判 FAIL（必须 INDETERMINATE）",
                agg == "INDETERMINATE" and spatial_ok,
                "总体=%s（%s）；空间规则=%s" % (agg, reason, spatial))

    # F. 候选不得计入失败（契约 §7.2：DUPLICATE_CANDIDATE 不是失败）
    k = g.Kernel(EX / "clean")
    results, findings = k.run()
    r10 = next(r for r in results if r.get("rule_id") == "R10")
    c10 = r10.get("summary_counts") or {}
    ok &= check("F 候选不得计入失败（clean R10 failed=0 / indeterminate=2）",
                c10.get("records_failed") == 0 and c10.get("records_indeterminate") == 2
                and c10.get("records_evaluated") == 12 and c10.get("findings") == 1,
                "R10 summary_counts=%s" % json.dumps(c10, ensure_ascii=False, sort_keys=True))

    # G. 未知依赖必须被拒（GA-04：不得再静默过滤）
    d = copy_bundle("clean", "neg_unknown_dep")
    rules = d / "approved-rules.yaml"
    text = rules.read_text(encoding="utf-8")
    text = text.replace("preconditions: []", "preconditions: [\"NONEXISTENT_RULE\"]", 1)
    rules.write_text(text, encoding="utf-8")
    k = g.Kernel(d)
    rejections = k.collect_config_rejections()
    codes = sorted({r.get("code") for r in rejections})
    ok &= check("G 未知依赖必须被拒（不得静默过滤）",
                "UNKNOWN_PRECONDITION" in codes,
                "config_rejections 原因码=%s" % (codes or "空（未拦截）"))

    print("")
    print("GUARDS_OK=%s" % ("true" if ok else "false"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
