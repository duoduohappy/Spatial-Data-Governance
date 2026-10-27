"""逐项比对两份冻结快照（替换前 vs 替换后），输出**可审计**的差异清单。

不做"看起来差不多"的判断：任何字段变化都列出来，由人给数学或业务依据。
用法：
    python -X utf8 tools/compare_snapshots.py acceptance/stage-1/baseline-frozen.json \
                                              work/stage1/after-replace.json
退出码：0 = 无差异；2 = 有差异（需要逐条登记依据）；1 = 用法/文件错误。
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


def flat(prefix, obj):
    """把嵌套结构摊平成 {路径: 标量}。"""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flat("%s.%s" % (prefix, k) if prefix else str(k), v))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flat("%s[%d]" % (prefix, i), v))
    else:
        out[prefix] = obj
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--show-unchanged", action="store_true")
    args = ap.parse_args()
    p1, p2 = Path(args.before), Path(args.after)
    if not p1.exists() or not p2.exists():
        print("[ERR] 快照文件不存在：%s / %s" % (p1, p2))
        return 1
    a = json.loads(p1.read_text(encoding="utf-8"))
    b = json.loads(p2.read_text(encoding="utf-8"))

    # 逐包比对：以 (bundle, rule_id) 与 (bundle, requirement_id) 为键，避免顺序差异造成假差异
    def index(payload, section, key):
        out = {}
        for bundle in payload["bundles"]:
            for item in bundle[section]:
                out[(bundle["bundle"], str(item.get(key)))] = item
        return out

    diffs, unchanged = [], 0
    for section, key in [("results", "rule_id"), ("clause_coverage", "requirement_id")]:
        ia, ib = index(a, section, key), index(b, section, key)
        for k in sorted(set(ia) | set(ib), key=lambda x: (x[0], x[1])):
            va, vb = ia.get(k), ib.get(k)
            if va == vb:
                unchanged += 1
                continue
            if va is None or vb is None:
                diffs.append(("新增/缺失", "%s %s %s" % (section, k[0], k[1]),
                              "—" if va is None else json.dumps(va, ensure_ascii=False),
                              "—" if vb is None else json.dumps(vb, ensure_ascii=False)))
                continue
            fa, fb = flat("", va), flat("", vb)
            for field in sorted(set(fa) | set(fb)):
                if fa.get(field) != fb.get(field):
                    diffs.append((section, "%s / %s / %s" % (k[0], k[1], field),
                                  str(fa.get(field)), str(fb.get(field))))
    # 包级结论
    for ba, bb in zip(a["bundles"], b["bundles"]):
        for field in ("aggregate", "aggregate_reason", "config_rejections"):
            if ba.get(field) != bb.get(field):
                diffs.append(("bundle", "%s / %s" % (ba["bundle"], field),
                              str(ba.get(field)), str(bb.get(field))))
        fa = sorted(ba.get("findings") or [])
        fb = sorted(bb.get("findings") or [])
        if fa != fb:
            diffs.append(("findings", ba["bundle"],
                          "缺: %s" % [x for x in fa if x not in fb],
                          "多: %s" % [x for x in fb if x not in fa]))

    # 几何
    ga, gb = a["geometry"], b["geometry"]
    for i in range(max(len(ga["boundary"]), len(gb["boundary"]))):
        ba = ga["boundary"][i] if i < len(ga["boundary"]) else {}
        bb = gb["boundary"][i] if i < len(gb["boundary"]) else {}
        for field in ("inclusive", "exclusive", "on_boundary"):
            if ba.get(field) != bb.get(field):
                diffs.append(("boundary", "%s / %s" % (ba.get("point", "?"), field),
                              str(ba.get(field)), str(bb.get(field))))
    for i in range(max(len(ga["distance"]), len(gb["distance"]))):
        da = ga["distance"][i] if i < len(ga["distance"]) else {}
        db = gb["distance"][i] if i < len(gb["distance"]) else {}
        if da.get("meters") != db.get("meters"):
            ma, mb = float(da.get("meters", 0)), float(db.get("meters", 0))
            rel = abs(mb - ma) / ma if ma else 0.0
            diffs.append(("distance", "%s→%s" % (da.get("from"), da.get("to")),
                          "%.6f m (%s)" % (ma, ga.get("distance_function")),
                          "%.6f m (%s) 相对差 %.4f%%" % (mb, gb.get("distance_function"), rel * 100)))

    print("=" * 78)
    print("冻结快照逐项比对：%s  →  %s" % (p1.name, p2.name))
    print("=" * 78)
    if not diffs:
        print("[OK] 无差异：%d 个比对项全部一致（含六包全部规则/条款字段）" % unchanged)
        return 0
    print("[DIFF] %d 处差异（逐条登记依据，不得简单迁就原实现）：" % len(diffs))
    for kind, where, before, after in diffs:
        print("  - [%s] %s" % (kind, where))
        print("      替换前: %s" % before)
        print("      替换后: %s" % after)
    if args.show_unchanged:
        print("  （一致项 %d 个）" % unchanged)
    return 2


if __name__ == "__main__":
    sys.exit(main())
