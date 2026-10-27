"""冻结基线快照：把「六包判定 + 几何边界矩阵 + 距离样本」抽成一份紧凑 JSON。

用途（最终复验报告 Stage 1 第 4 条）：替换自研几何/YAML 实现**之前**先跑一份基线，
替换**之后**再跑一份，用 `tools/compare_snapshots.py` 逐项比对。
差异必须有数学或业务依据，不能简单迁就原实现。

用法：
    python -X utf8 tools/snapshot_results.py --out acceptance/stage-1/baseline-frozen.json
    python -X utf8 tools/snapshot_results.py --out work/stage1/after-replace.json
"""
from __future__ import annotations

import argparse
import datetime as dt
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
EX = ROOT / "examples"
sys.path.insert(0, str(ROOT / "tools"))
import stage0_gate as g  # noqa: E402

BUNDLES = ["clean", "defective", "corrected", "ambiguous", "blocked", "crs_same_unit_wrong"]

# 边界矩阵：单位正方形 + 贴近边界的扰动点（1e-13 / 1e-9 用来暴露容差差异）
UNIT_RING = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
BOUNDARY_POINTS = [
    ("内点", 0.5, 0.5),
    ("左边界中点", 0.0, 0.5),
    ("右边界中点", 1.0, 0.5),
    ("下边界中点", 0.5, 0.0),
    ("上边界中点", 0.5, 1.0),
    ("顶点(0,0)", 0.0, 0.0),
    ("顶点(1,1)", 1.0, 1.0),
    ("外点", 1.5, 0.5),
    ("边界内侧1e-13", 1e-13, 0.5),
    ("边界外侧1e-13", -1e-13, 0.5),
    ("边界内侧1e-9", 1e-9, 0.5),
    ("边界外侧1e-9", -1e-9, 0.5),
]

DISTANCE_PAIRS = [
    ((116.3912, 39.9075), (116.3975, 39.9087)),
    ((116.0, 39.0), (117.0, 40.0)),
    ((0.0, 0.0), (0.0, 1.0)),
]


def bundle_snapshot(name):
    k = g.Kernel(EX / name)
    rejections = k.collect_config_rejections()
    results, findings = k.run()
    coverage = k.build_clause_coverage(results)
    agg, reason = g.aggregate(coverage, rejections, len(k.rows))
    return {
        "bundle": name,
        "aggregate": agg,
        "aggregate_reason": reason,
        "config_rejections": sorted({r["code"] for r in rejections}),
        "clause_coverage": [
            {kk: c.get(kk) for kk in ("requirement_id", "coverage_state", "verdict",
                                      "execution_status", "reason_code", "missing_rule_ids",
                                      "conflicting_rule_ids", "failure_reason_codes",
                                      "advisory_reason_codes") if c.get(kk) is not None}
            for c in coverage],
        "results": [
            {"rule_id": r.get("rule_id"), "verdict": r.get("verdict"),
             "execution_status": r.get("execution_status"), "reason_code": r.get("reason_code"),
             "counts": r.get("summary_counts")}
            for r in results],
        "findings": sorted(f.get("stable_key") for f in findings),
        "risk_signals": sorted(s["code"] for s in k.risk_signals),
    }


def geometry_snapshot():
    out = {"boundary": [], "distance": []}
    for label, x, y in BOUNDARY_POINTS:
        out["boundary"].append({
            "point": label,
            "inclusive": bool(g.point_in_ring_or_boundary(x, y, UNIT_RING, inclusive=True)),
            "exclusive": bool(g.point_in_ring_or_boundary(x, y, UNIT_RING, inclusive=False)),
            "on_boundary": bool(g.point_on_ring_boundary(x, y, UNIT_RING)),
        })
    # 真实项目范围（clean 包）的边界判定
    k = g.Kernel(EX / "clean")
    ring = k.project_area_ring()
    if ring:
        minx = min(p[0] for p in ring)
        maxy = max(p[1] for p in ring)
        out["project_area"] = {
            "ring_n": len(ring),
            "corner_inclusive": bool(g.point_in_ring_or_boundary(minx, maxy, ring, inclusive=True)),
            "corner_exclusive": bool(g.point_in_ring_or_boundary(minx, maxy, ring, inclusive=False)),
            "centroid_inclusive": bool(g.point_in_ring_or_boundary(
                (minx + maxy) / 2, 39.91, ring, inclusive=True)),
        }
    fn = getattr(g, "geodesic_m", None) or getattr(g, "haversine_m")
    out["distance_function"] = fn.__name__
    for a, b in DISTANCE_PAIRS:
        out["distance"].append({"from": list(a), "to": list(b),
                                "meters": round(float(fn(a[0], a[1], b[0], b[1])), 6)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    payload = {
        "schema_version": "stage1-snapshot-1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "label": args.label,
        "python": sys.version.split()[0],
        "bundles": [bundle_snapshot(b) for b in BUNDLES],
        "geometry": geometry_snapshot(),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[OK] 快照已写入 %s（六包 + 边界矩阵 %d 点 + 距离样本 %d 组）"
          % (out, len(payload["geometry"]["boundary"]), len(payload["geometry"]["distance"])))
    for b in payload["bundles"]:
        print("     %-20s %s" % (b["bundle"], b["aggregate"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
