"""GeoAcceptance CLI（Stage 1 最小模块）。

子命令：
    validate 正式检查入口：任意交付包目录，**不需要 expected 真值**
    regress  回归工具：examples 示例包跑内核并与**冻结 expected** 逐字段比对
    report   把已有 report.json / validate json 渲染成 HTML
    compare  整改复验 compare（两批次目录）
    env      环境/依赖运行验证

设计约束：**不复制判定逻辑**。内核仍是 `tools/stage0_gate.py`，本文件只做编排与呈现。

`validate` 与 `regress` 必须分开（外部复核 §七）：前者是"真实检查执行"，
后者是"与冻结真值的回归比对"。把回归当正式入口会让没有 expected 的新包无法验收。
"""
from __future__ import annotations

import argparse
import json
import sys

# 终端编码：中文输出在 GBK 终端/重定向下会抛 UnicodeEncodeError（证据链断在中途）。
# 统一把标准输出/错误固定为 UTF-8：等价于 README 建议的 `python -X utf8`，
# 且不依赖调用方是否设置 PYTHONUTF8 / PYTHONIOENCODING。
for _s in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
    if _s is not None and hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="strict")
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import stage0_gate as gate  # noqa: E402
from geoacceptance import compare as cmp  # noqa: E402
from geoacceptance import inputs, reporting, validate as vld  # noqa: E402


def cmd_validate(args):
    """正式检查：任意包目录，不需要 expected。

    --bundle 既可以是 examples/ 下的包名，也可以是任意目录（绝对/相对路径）。
    """
    target = Path(args.bundle)
    if not target.is_dir():
        # 不是目录：按 examples 下的包名解析（带路径穿越防护）
        target = inputs.safe_bundle_path(gate.EX, args.bundle)
    result = vld.validate_bundle(target.resolve())
    print(vld.render_text(result))
    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("\n[OK] 结构化结果：%s" % p)
        if args.html:
            out = reporting.write_html(p, Path(args.html))
            print("[OK] HTML 报告：%s" % out)
    elif args.html:
        print("[ERR] --html 需要与 --json 一起使用（HTML 由结构化结果渲染，避免二次判定）")
        return 2
    return 0 if result["aggregate_verdict"] == "PASS" else 2


def cmd_regress(args):
    """回归工具：examples 示例包 + 冻结 expected 逐字段比对（**不是**正式检查入口）。"""
    names = []
    for name in (args.bundle or ["clean", "defective", "corrected", "ambiguous", "blocked",
                                 "crs_same_unit_wrong"]):
        # 输入防护：包名必须落在 examples/ 之内（防路径穿越）
        inputs.safe_bundle_path(gate.EX, name)
        names.append(name)
    saved_argv = list(sys.argv)
    sys.argv = ["stage0_gate.py"] + sum([["--bundle", n] for n in names], [])
    try:
        rc = gate.main()
    finally:
        sys.argv = saved_argv
    if args.html:
        for n in names:
            rp = gate.WORK / n / "report.json"
            if rp.exists():
                out = reporting.write_html(rp, gate.WORK / n / "report.html")
                print("[HTML] %s" % out)
    return rc


def cmd_report(args):
    src = Path(args.from_json)
    if not src.exists():
        print("[ERR] report.json 不存在：%s" % src)
        return 1
    out = reporting.write_html(src, Path(args.out))
    print("[OK] HTML 报告：%s" % out)
    return 0


def _resolve_batch(root: Path, value: str) -> Path:
    """批次目录：给的是目录就用目录（任意路径），否则按 root 下的包名解析（带穿越防护）。"""
    p = Path(value)
    if p.is_dir():
        return p.resolve()
    return inputs.safe_bundle_path(root, value)


def cmd_compare(args):
    root = Path(args.root).resolve()
    before = _resolve_batch(root, args.before)
    after = _resolve_batch(root, args.after)
    result = cmp.compare_batches(before, after)
    print(cmp.render_text(result))
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("\n[OK] 结构化结果：%s" % p)
    # 只有"台账关闭 **且** 整改后批次自身通过"才算通过；其余一律非零退出
    return 0 if result["overall"] == "LEDGER_CLOSED_ACCEPTED" else 2


def cmd_env(args):
    import subprocess
    proc = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "tools" / "verify_env.py")],
                          cwd=str(ROOT), encoding="utf-8", errors="strict",
                          env={**__import__("os").environ,
                               "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    return proc.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(prog="geoacceptance", description="GeoAcceptance CLI（Stage 1）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="正式检查：任意包目录，不需要 expected")
    p_val.add_argument("--bundle", required=True, help="包目录（任意路径）或 examples 下的包名")
    p_val.add_argument("--json", default="", help="结构化结果输出路径")
    p_val.add_argument("--html", default="", help="HTML 报告输出路径（需与 --json 同时给出）")
    p_val.set_defaults(func=cmd_validate)

    p_run = sub.add_parser("regress", help="回归：示例包与冻结 expected 比对（非正式入口）")
    p_run.add_argument("--bundle", action="append", help="包名，可多次；默认六个包")
    p_run.add_argument("--html", action="store_true", help="同时渲染 HTML 报告")
    p_run.set_defaults(func=cmd_regress)

    p_rep = sub.add_parser("report", help="把 report.json 渲染成 HTML")
    p_rep.add_argument("--from-json", required=True)
    p_rep.add_argument("--out", required=True)
    p_rep.set_defaults(func=cmd_report)

    p_cmp = sub.add_parser("compare", help="整改复验 compare（两批次）")
    p_cmp.add_argument("--before", required=True, help="整改前批次目录名（位于 --root 内）")
    p_cmp.add_argument("--after", required=True, help="整改后批次目录名")
    p_cmp.add_argument("--root", default=str(ROOT / "examples"))
    p_cmp.add_argument("--out", default="", help="结构化结果输出路径")
    p_cmp.set_defaults(func=cmd_compare)

    p_env = sub.add_parser("env", help="环境与依赖运行验证")
    p_env.set_defaults(func=cmd_env)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except inputs.InputGuardError as exc:
        # 输入不合规（路径穿越 / 包不存在 / 超限 / 非 UTF-8）：
        # 失败关闭即可，但不要把栈甩给用户 —— 给出可读的一行错误与非零退出码
        print("[ERR] 输入不合规：%s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
