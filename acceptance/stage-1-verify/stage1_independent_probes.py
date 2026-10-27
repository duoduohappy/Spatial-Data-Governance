#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GeoAcceptance Stage 1 独立复验探针（不复用仓库自带 tools/recheck_probes.py）。

用法：
    python -X utf8 stage1_independent_probes.py <仓库根目录> [--out 结果.json]

纪律（与仓库同一套公理）：
- 每条探针给「依据 / 输入 / 预期 / 实测」，不写"应该没问题"；
- 预期值来自**独立参考**（精确有理数算术、解析公式、手写结构），不来自被测实现；
- 实测与预期不符即记为缺陷，**不做任何迁就**；
- 不做的事（缺证据）一律记 INDETERMINATE，不写成通过。
"""
from __future__ import annotations

import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction as F
from pathlib import Path

REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(".").resolve()
OUT = None
if "--out" in sys.argv:
    OUT = Path(sys.argv[sys.argv.index("--out") + 1])

sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO))
import stage0_gate as gate  # noqa: E402
from geoacceptance import inputs as gin  # noqa: E402
from geoacceptance import reporting as grep  # noqa: E402
from geoacceptance import compare as gcmp  # noqa: E402

EX = REPO / "examples"
TMP = Path(tempfile.mkdtemp(prefix="ga-s1-"))
RESULTS = []


def probe(pid, title, basis, given, expected, fn):
    try:
        actual = fn()
        ok = bool(actual.get("ok"))
    except Exception as exc:  # 探针自身崩溃也算失败，但不隐藏
        actual = {"ok": False, "raised": "%s: %s" % (type(exc).__name__, exc)}
        ok = False
    rec = {"id": pid, "title": title, "basis": basis, "given": given,
           "expected": expected, "actual": actual, "ok": ok}
    RESULTS.append(rec)
    print("[%s] %s  —— %s" % ("PASS" if ok else "FAIL", pid, title))
    print("      依据：%s" % basis)
    print("      输入：%s" % given)
    print("      预期：%s" % expected)
    print("      实测：%s" % json.dumps(actual, ensure_ascii=False)[:1200])
    print("")
    return ok


# ---------------------------------------------------------------- 独立参考实现
def exact_point_class(pt, ring):
    """用**精确有理数算术**判定点相对多边形的位置（不依赖 Shapely，也不用容差）。

    返回 (严格内部, 在边界上)；闭包内 = 内部 or 边界。
    依据：多边形边界由线段组成；点在闭线段上 ⇔ 叉积为 0 且坐标落在包围盒内（精确）；
    严格内部用射线法（精确比较，无浮点误差）。
    """
    x, y = pt
    r = list(ring)
    if r[0] != r[-1]:
        r.append(r[0])
    n = len(r) - 1
    on_b = False
    for i in range(n):
        (x1, y1), (x2, y2) = r[i], r[i + 1]
        cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
        if cross == 0 and min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
            on_b = True
            break
    inside = False
    if not on_b:
        for i in range(n):
            (x1, y1), (x2, y2) = r[i], r[i + 1]
            if (y1 > y) != (y2 > y):
                xint = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                if x < xint:
                    inside = not inside
    return inside, on_b


def haversine_m(lon1, lat1, lon2, lat2, r=6371008.8):
    """Stage 0 的球近似（独立重写，用于确认替换确实生效、差异量级有依据）。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def meridian_arc(lat1_deg, lat2_deg, n=200000):
    """WGS84 子午线弧长（Simpson 数值积分，独立解析参考）。

    M(φ) = a(1-e²) / (1-e²·sin²φ)^{3/2}
    """
    a = 6378137.0
    f = 1.0 / 298.257223563
    e2 = 2 * f - f * f

    def m(phi):
        s = math.sin(phi)
        return a * (1 - e2) / ((1 - e2 * s * s) ** 1.5)

    lo, hi = math.radians(lat1_deg), math.radians(lat2_deg)
    if n % 2:
        n += 1
    h = (hi - lo) / n
    total = m(lo) + m(hi)
    for i in range(1, n):
        total += (4 if i % 2 else 2) * m(lo + i * h)
    return total * h / 3.0


# ---------------------------------------------------------------- P1 几何谓词
UNIT_RING = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
L_RING = [(0.0, 0.0), (4.0, 0.0), (4.0, 1.0), (1.0, 1.0), (1.0, 4.0), (0.0, 4.0)]
UNIT_PTS = [(0.5, 0.5), (0.5, 0.0), (0.0, 0.0), (1.0, 1.0), (1.5, 0.5),
            (0.5, -1e-9), (0.5, 1e-9), (1e-13, 0.5), (-1e-13, 0.5),
            (1 - 1e-13, 0.5), (1 + 1e-13, 0.5), (0.25, 0.75), (0.0, 1.0)]
L_PTS = [(2.0, 0.5), (0.5, 2.0), (2.0, 2.0), (4.0, 1.0), (1.0, 1.0),
         (2.0, 0.0), (0.0, 0.0), (5.0, 0.5), (1.0, 2.0), (0.5, 0.5)]


def p1_geometry():
    """Shapely 谓词 ⇔ 精确有理数算术真值（含 1e-13 量级边界扰动点）。"""
    mismatches = []
    notable = []
    for ring, pts, tag in ((UNIT_RING, UNIT_PTS, "unit"), (L_RING, L_PTS, "L")):
        fring = [(F(float(x)), F(float(y))) for x, y in ring]
        for (x, y) in pts:
            p = (F(float(x)), F(float(y)))
            inside, on_b = exact_point_class(p, fring)
            want = {"exclusive": inside, "inclusive": inside or on_b, "on_boundary": on_b}
            got = {
                "exclusive": bool(gate.point_in_ring_or_boundary(x, y, ring, inclusive=False)),
                "inclusive": bool(gate.point_in_ring_or_boundary(x, y, ring, inclusive=True)),
                "on_boundary": bool(gate.point_on_ring_boundary(x, y, ring)),
            }
            if got != want:
                mismatches.append({"poly": tag, "point": (x, y), "want": want, "got": got})
            if abs(x) < 1e-8 or abs(x - 1) < 1e-8 or abs(y) < 1e-8 or abs(y - 1) < 1e-8:
                notable.append({"poly": tag, "point": (x, y), "truth": want})
    return {"ok": not mismatches, "cases": len(UNIT_PTS) + len(L_PTS),
            "mismatches": mismatches, "near_boundary_truth": notable}


# ---------------------------------------------------------------- P2 测地距离
def p2_distance():
    """pyproj 测地距离 ⇔ 独立解析参考（赤道弧长 / 子午线积分），并确认与球近似确有差异。"""
    a = 6378137.0
    eq = gate.geodesic_m(0.0, 0.0, 1.0, 0.0)
    eq_ref = a * math.pi / 180.0
    rel_eq = abs(eq - eq_ref) / eq_ref

    mer = gate.geodesic_m(0.0, 0.0, 0.0, 1.0)
    mer_ref = meridian_arc(0.0, 1.0)
    rel_mer = abs(mer - mer_ref) / mer_ref

    pairs = [((116.3912, 39.9075), (116.3975, 39.9087)),
             ((116.0, 39.0), (117.0, 40.0)),
             ((0.0, 0.0), (0.0, 1.0))]
    diffs = []
    for (lo1, la1), (lo2, la2) in pairs:
        g = gate.geodesic_m(lo1, la1, lo2, la2)
        h = haversine_m(lo1, la1, lo2, la2)
        diffs.append({"pair": [list((lo1, la1)), list((lo2, la2))],
                      "geodesic": round(g, 6), "haversine": round(h, 6),
                      "rel_pct": round(abs(g - h) / h * 100, 6)})
    ok = (rel_eq < 1e-12 and rel_mer < 1e-9
          and all(0.001 < d["rel_pct"] < 1.0 for d in diffs))
    return {"ok": ok, "equator_m": round(eq, 6), "equator_ref_m": round(eq_ref, 6),
            "rel_err_equator": rel_eq,
            "meridian_m": round(mer, 6), "meridian_ref_m": round(mer_ref, 6),
            "rel_err_meridian": rel_mer, "vs_haversine": diffs}


# ---------------------------------------------------------------- P3 YAML
TRICKY = """base: &base
  unit: m
  tol: 0.5
items:
  - name: a
    <<: *base
  - name: b
    <<: *base
    tol: 1.5
text: |
  第一行
  第二行
quoted_num: "42"
bool_like: "yes"
empty:
preconditions:
nested:
  - - 1
    - 2
unicode: "中文 ✓"
float_seq: [1, 2.5, -3]
"""
EXPECT_TRICKY = {
    "base": {"unit": "m", "tol": 0.5},
    "items": [{"name": "a", "unit": "m", "tol": 0.5},
              {"name": "b", "unit": "m", "tol": 1.5}],
    "text": "第一行\n第二行\n",
    "quoted_num": "42",
    "bool_like": "yes",
    "empty": None,
    "preconditions": [],
    "nested": [[1, 2]],
    "unicode": "中文 ✓",
    "float_seq": [1, 2.5, -3],
}


def p3_yaml():
    """PyYAML 解析 ⇔ 手写期望结构（锚点/合并键/块标量/类型不收敛/序列空值归一）。"""
    p = TMP / "tricky.yaml"
    p.write_text(TRICKY, encoding="utf-8")
    got = gate.load_yaml(p)
    multi = TMP / "multi.yaml"
    multi.write_text("a: 1\n---\nb: 2\n", encoding="utf-8")
    multi_behavior = None
    try:
        gate.load_yaml(multi)
        multi_behavior = "NO_RAISE（静默取首个文档：风险）"
    except Exception as exc:
        multi_behavior = "%s: %s" % (type(exc).__name__, str(exc)[:80])
    return {"ok": got == EXPECT_TRICKY and not str(multi_behavior).startswith("NO_RAISE"),
            "parsed": got, "expected": EXPECT_TRICKY,
            "multi_document": multi_behavior}


# ---------------------------------------------------------------- P4 执行入口 Pydantic
def _variant_bundle(name, mutate):
    dst = TMP / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(EX / "clean", dst)
    rp = dst / "requirements.yaml"
    text = rp.read_text(encoding="utf-8")
    rp.write_text(mutate(text), encoding="utf-8")
    return dst


def p4_entry_validation():
    """执行入口必须拒收隐式类型/未知枚举（零隐式收敛），且拒绝后不得判 PASS。"""
    out = {}
    # ① required_for_release: "yes"（字符串）→ strict 必须拒
    b1 = _variant_bundle("p4-yes", lambda t: t.replace("required_for_release: true",
                                                       'required_for_release: "yes"'))
    k1 = gate.Kernel(b1)
    rej1 = k1.collect_config_rejections()
    res1, _ = k1.run()
    cov1 = k1.build_clause_coverage(res1)
    agg1, _ = gate.aggregate(cov1, rej1, len(k1.rows))
    out["string_bool"] = {"rejections": sorted({r["code"] for r in rej1}), "aggregate": agg1}

    # ② support_status 未知枚举 "MAYBE" → 必须拒
    b2 = _variant_bundle("p4-maybe", lambda t: t.replace('support_status: "SUPPORTED"',
                                                         'support_status: "MAYBE"'))
    k2 = gate.Kernel(b2)
    rej2 = k2.collect_config_rejections()
    res2, _ = k2.run()
    cov2 = k2.build_clause_coverage(res2)
    agg2, _ = gate.aggregate(cov2, rej2, len(k2.rows))
    out["unknown_enum"] = {"rejections": sorted({r["code"] for r in rej2}), "aggregate": agg2}

    # ③ 反向确认：pydantic **lax** 会把 "yes" 收敛成 True（所以入口必须用 strict）
    from pydantic import BaseModel, ConfigDict
    class LaxM(BaseModel):
        model_config = ConfigDict(strict=False, extra="allow")
        required_for_release: bool
    lax = LaxM.model_validate({"required_for_release": "yes"})
    out["lax_reverse_confirm"] = {"input": "yes", "lax_value": lax.required_for_release}

    ok = ("INPUT_SCHEMA_INVALID" in out["string_bool"]["rejections"]
          and out["string_bool"]["aggregate"] != "PASS"
          and "INPUT_SCHEMA_INVALID" in out["unknown_enum"]["rejections"]
          and out["unknown_enum"]["aggregate"] != "PASS"
          and out["lax_reverse_confirm"]["lax_value"] is True)
    return {"ok": ok, **out}


# ---------------------------------------------------------------- P5 接口唯一性
def p5_single_interface():
    import inspect
    sig = str(inspect.signature(gate.aggregate))
    has_legacy = hasattr(gate, "_coverage_from_results")
    two_arg = None
    try:
        gate.aggregate([], 3)
        two_arg = "NO_RAISE（存在第二判定路径：禁止）"
    except TypeError as exc:
        two_arg = "TypeError: %s" % str(exc)[:60]
    except Exception as exc:
        two_arg = "%s: %s" % (type(exc).__name__, str(exc)[:60])
    ok = (not has_legacy) and str(two_arg).startswith("TypeError") and "clause_coverage" in sig
    return {"ok": ok, "signature": sig, "legacy_helper_present": has_legacy,
            "two_arg_call": two_arg}


# ---------------------------------------------------------------- P6 CLI
def _cli(args, cwd, env=None):
    e = dict(os.environ)
    e["PYTHONPATH"] = str(REPO)
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    if env:
        e.update(env)
    pr = subprocess.run([sys.executable, "-X", "utf8", "-m", "geoacceptance.cli"] + args,
                        cwd=str(cwd), env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return pr.returncode, pr.stdout.decode("utf-8", errors="replace")


def p6_cli():
    """CLI 必须跨目录可跑（内部用绝对 ROOT），且路径穿越/不存在包名必须失败关闭。"""
    other = TMP / "elsewhere"
    other.mkdir(exist_ok=True)
    rc_ok, out_ok = _cli(["run", "--bundle", "clean"], other)
    rc_trav, out_trav = _cli(["run", "--bundle", "../clean"], other)
    rc_miss, out_miss = _cli(["run", "--bundle", "no_such_bundle"], other)
    ok = rc_ok == 0 and rc_trav != 0 and rc_miss != 0
    return {"ok": ok,
            "run_other_cwd": {"rc": rc_ok, "tail": out_ok.strip()[-120:]},
            "traversal": {"rc": rc_trav, "tail": out_trav.strip()[-200:]},
            "missing_bundle": {"rc": rc_miss, "tail": out_miss.strip()[-200:]}}


# ---------------------------------------------------------------- P7 HTML 转义
def p7_html_escape():
    """报告渲染必须转义：注入串不得以可执行标签形式出现在 HTML 里（S0-09 闭合验证）。"""
    payload = '<script>alert("x")</script> & \'q\' "d"'
    report = {"bundle": payload, "aggregate_verdict": "FAIL", "aggregate_reason": payload,
              "schema_version": "stage0-2", "tool_version": payload, "generated_at": payload,
              "clause_coverage": [{"requirement_id": payload, "coverage_state": "COVERED",
                                   "verdict": "FAIL", "execution_status": "COMPLETED",
                                   "reason_code": payload, "failure_reason_codes": [payload]}],
              "check_results": [{"rule_id": payload, "requirement_ids": [payload],
                                 "verdict": "FAIL", "execution_status": "COMPLETED",
                                 "reason_code": payload,
                                 "summary_counts": {"records_failed": 1}}],
              "findings": [{"finding_id": payload, "rule_id": payload,
                            "record_locator": {"record_id": payload}, "field": payload,
                            "reason_code": payload, "observed_value": payload}]}
    html = grep.render_html(report)
    ok = ("<script" not in html) and ("&lt;script&gt;" in html) and ("&amp;" in html)
    return {"ok": ok, "raw_script_tag_present": "<script" in html,
            "escaped_present": "&lt;script&gt;" in html, "amp_escaped": "&amp;" in html,
            "html_len": len(html)}


# ---------------------------------------------------------------- P8 compare 身份
def _copy_bundle(name, dst):
    if Path(dst).exists():
        shutil.rmtree(dst)
    shutil.copytree(EX / name, dst)
    return Path(dst)


def _shuffle_poi(bundle: Path, seed=7):
    p = bundle / "poi.csv"
    lines = p.read_text(encoding="utf-8").splitlines()
    header, body = lines[0], lines[1:]
    random.Random(seed).shuffle(body)
    p.write_text("\n".join([header] + body) + "\n", encoding="utf-8")


def _dupe_first_record(bundle: Path):
    p = bundle / "poi.csv"
    lines = p.read_text(encoding="utf-8").splitlines()
    lines.append(lines[1])  # 复制第一条数据行 ⇒ 制造重复 record_id
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def p8_compare_identity():
    """compare 必须按 record_id 匹配：乱序不影响结果；重复/缺失标识 ⇒ not_comparable。"""
    b = _copy_bundle("defective", TMP / "cmp-before")
    a1 = _copy_bundle("corrected", TMP / "cmp-after")
    r_base = gcmp.compare_batches(b, a1)
    a2 = _copy_bundle("corrected", TMP / "cmp-after-shuffled")
    _shuffle_poi(a2)
    r_shuf = gcmp.compare_batches(b, a2)
    a3 = _copy_bundle("corrected", TMP / "cmp-after-dup")
    _dupe_first_record(a3)
    r_dup = gcmp.compare_batches(b, a3)
    dup_items = [i for i in r_dup["items"] if i["status"] == "not_comparable"]
    ok = (r_base["counts"] == r_shuf["counts"]
          and r_base["overall"] == r_shuf["overall"]
          and r_dup["overall"] == "INDETERMINATE"
          and dup_items)
    return {"ok": ok,
            "baseline_counts": r_base["counts"], "baseline_overall": r_base["overall"],
            "shuffled_counts": r_shuf["counts"], "shuffled_overall": r_shuf["overall"],
            "identity": r_base["identity"],
            "dup_overall": r_dup["overall"],
            "dup_not_comparable_n": len(dup_items),
            "dup_sample": dup_items[0] if dup_items else None}


# ---------------------------------------------------------------- P9 重跑确定性
def p9_determinism():
    """同一实例重跑、跨实例重跑均必须产生相同的 findings（RC-04 回归）。"""
    k = gate.Kernel(EX / "defective")
    _, f1 = k.run()
    _, f2 = k.run()
    s1 = sorted(x.get("stable_key") for x in f1)
    s2 = sorted(x.get("stable_key") for x in f2)
    k2 = gate.Kernel(EX / "defective")
    _, f3 = k2.run()
    s3 = sorted(x.get("stable_key") for x in f3)
    return {"ok": s1 == s2 == s3, "n": len(s1),
            "same_instance_equal": s1 == s2, "cross_instance_equal": s1 == s3}


# ---------------------------------------------------------------- P10 依赖缺失失败关闭
def _run_blocked(mod_name):
    block = TMP / ("block-" + mod_name)
    block.mkdir(exist_ok=True)
    (block / (mod_name + ".py")).write_text("raise ImportError('blocked by verifier')\n",
                                            encoding="utf-8")
    e = dict(os.environ)
    e["PYTHONPATH"] = str(block) + os.pathsep + str(REPO)
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    pr = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "tools" / "stage0_gate.py")],
                        cwd=str(REPO), env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return pr.returncode, pr.stdout.decode("utf-8", errors="replace")


def p10_dep_failfast():
    """shapely / pyproj / yaml 缺失时必须启动即失败并给出安装命令，不得静默回退。"""
    out = {}
    ok = True
    for mod in ("shapely", "pyproj", "yaml"):
        rc, txt = _run_blocked(mod)
        good = rc != 0 and "pip install -r requirements.txt" in txt and "ALL_OK=true" not in txt
        ok = ok and good
        out[mod] = {"rc": rc, "mentions_install_cmd": "pip install -r requirements.txt" in txt,
                    "head": txt.strip()[:160]}
    return {"ok": ok, **out}


# ---------------------------------------------------------------- P11 编码独立性
def p11_encoding():
    """不设置 PYTHONUTF8 / -X utf8 时（终端/重定向为 GBK），回归套件不得中途崩溃。"""
    e = dict(os.environ)
    e.pop("PYTHONUTF8", None)
    e.pop("PYTHONIOENCODING", None)
    pr = subprocess.run([sys.executable, str(REPO / "tools" / "recheck_probes.py")],
                        cwd=str(REPO), env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    txt = pr.stdout.decode("utf-8", errors="replace")
    pr2 = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "tools" / "recheck_probes.py")],
                         cwd=str(REPO), env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    txt2 = pr2.stdout.decode("utf-8", errors="replace")
    return {"ok": pr.returncode == 0,
            "plain_rc": pr.returncode, "plain_tail": txt.strip()[-260:],
            "utf8_rc": pr2.returncode,
            "utf8_ok": "RECHECK_PROBES_OK=true" in txt2,
            "utf8_tail": txt2.strip()[-120:]}


# ---------------------------------------------------------------- P12 冻结快照复现
def _index(payload, section, key):
    out = {}
    for b in payload.get("bundles", []):
        for item in b.get(section, []):
            out[(b["bundle"], item.get(key))] = item
    return out


def p12_snapshot_repro():
    """自实现比对（不复用 compare_snapshots）：六包判定零差异，几何差异恰为已登记的 7 项。"""
    base = json.loads((REPO / "acceptance" / "stage-1" / "baseline-frozen.json")
                      .read_text(encoding="utf-8"))
    snap = TMP / "snap.json"
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    pr = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "tools" / "snapshot_results.py"),
                         "--out", str(snap), "--label", "verifier"],
                        cwd=str(REPO), env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if pr.returncode != 0:
        return {"ok": False, "snapshot_rc": pr.returncode,
                "out": pr.stdout.decode("utf-8", errors="replace")[:400]}
    cur = json.loads(snap.read_text(encoding="utf-8"))
    diffs = {"rule": [], "clause": [], "aggregate": [], "findings": []}
    for b_old, b_new in zip(base["bundles"], cur["bundles"]):
        if b_old["bundle"] != b_new["bundle"]:
            diffs["aggregate"].append("包顺序不一致")
            continue
        if b_old["aggregate"] != b_new["aggregate"]:
            diffs["aggregate"].append("%s: %s → %s" % (b_old["bundle"], b_old["aggregate"],
                                                        b_new["aggregate"]))
        if sorted(b_old["findings"]) != sorted(b_new["findings"]):
            diffs["findings"].append(b_old["bundle"])
        for sect in ("results", "clause_coverage"):
            k_old = {i.get("rule_id") or i.get("requirement_id"): i for i in b_old[sect]}
            k_new = {i.get("rule_id") or i.get("requirement_id"): i for i in b_new[sect]}
            for kk in sorted(set(k_old) | set(k_new), key=str):
                if k_old.get(kk) != k_new.get(kk):
                    diffs["rule" if sect == "results" else "clause"].append(
                        "%s/%s" % (b_old["bundle"], kk))
    geo_old = {g["point"]: g for g in base["geometry"]["boundary"]}
    geo_new = {g["point"]: g for g in cur["geometry"]["boundary"]}
    fields = ("inclusive", "exclusive", "on_boundary")
    bound_pts, field_flips = [], 0
    for p in geo_old:
        for k in fields:
            if geo_old[p][k] != geo_new[p][k]:
                field_flips += 1
        if {k: geo_old[p][k] for k in fields} != {k: geo_new[p][k] for k in fields}:
            bound_pts.append(p)
    dist_diffs = []
    do = {tuple(d["from"] + d["to"]): d["meters"] for d in base["geometry"]["distance"]}
    dn = {tuple(d["from"] + d["to"]): d["meters"] for d in cur["geometry"]["distance"]}
    for kk in do:
        if abs(do[kk] - dn[kk]) > 1e-6:
            dist_diffs.append({"pair": list(kk), "before": do[kk], "after": dn[kk],
                               "rel_pct": round(abs(dn[kk] - do[kk]) / do[kk] * 100, 6)})
    # 已登记的差异：2 个边界扰动点（共 4 个字段翻转，均由精确谓词纠正）+ 3 组距离（椭球 vs 球）
    ok = (not diffs["rule"] and not diffs["clause"] and not diffs["aggregate"]
          and not diffs["findings"]
          and sorted(bound_pts) == sorted(["边界内侧1e-13", "边界外侧1e-13"])
          and field_flips == 4 and len(dist_diffs) == 3)
    return {"ok": ok, "judgement_diffs": diffs, "boundary_points_changed": bound_pts,
            "boundary_field_flips": field_flips,
            "distance_diffs": dist_diffs,
            "distance_fn": cur["geometry"].get("distance_function")}


# ---------------------------------------------------------------- P13 文档与实现一致性
def p13_doc_consistency():
    """文档现状说明必须与代码一致（最终复验 B 项的同源要求）。"""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    s0_open = (REPO / "acceptance" / "stage-0" / "OPEN_ISSUES.md").read_text(encoding="utf-8")
    # 「零第三方依赖」在 Stage 0 语境下是史实，不算矛盾；**未限定范围**的写法才算
    unqualified = [ln for ln in readme.splitlines()
                   if "零第三方依赖" in ln and not ("Stage 0" in ln or "冻结" in ln)]
    checks = {
        "README 出现未限定范围的『零第三方依赖』": (bool(unqualified), False),
        "内核 TOOL_VERSION 仍标 (stdlib)（Stage 1 起已非纯标准库）":
            ("(stdlib)" in gate.TOOL_VERSION, False),
        "README 版本号与代码 TOOL_VERSION 一致":
            (("stage0-gate/0.2.0" in readme) and gate.TOOL_VERSION.startswith("stage0-gate/0.2.0"),
             True),
        "README 仍写『五个示例包』（实际六包）": ("五个示例包" in readme, False),
        "Stage 0 OPEN_ISSUES 仍写『五个示例包』": ("五个示例包" in s0_open, False),
    }
    bad = {k: v for k, v in checks.items() if v[0] != v[1]}
    return {"ok": not bad, "checks": {k: {"actual": v[0], "want": v[1]}
                                      for k, v in checks.items()},
            "inconsistent": sorted(bad)}


def main():
    print("=" * 78)
    print("Stage 1 独立复验探针（仓库：%s）" % REPO)
    print("解释器：%s" % sys.version.split()[0])
    print("=" * 78)
    print("")

    probe("S1-P01", "几何谓词 ⇔ 精确有理数算术真值",
          "多边形边界=闭线段；点在闭线段上 ⇔ 叉积为 0 且在包围盒内（精确）；"
          "严格内部用射线法精确比较。1e-13 量级扰动点由精确算术给出真值。",
          "单位正方形 13 点 + 凹多边形（L 形）10 点，含顶点、边中点、凹顶点、1e-13 内外扰动",
          "gate 的 exclusive/inclusive/on_boundary 与精确真值**逐点一致**（旧 1e-12 容差"
          "会把多边形外的点算进 inclusive，替换后必须纠正）", p1_geometry)

    probe("S1-P02", "测地距离 ⇔ 独立解析参考",
          "赤道弧长 = a·Δλ（a=6378137，精确）；子午线弧长 = ∫M(φ)dφ，M(φ)=a(1-e²)/(1-e²sin²φ)^1.5，"
          "Simpson 积分独立求得；球近似 R=6371008.8 与椭球的相对差应在 1e-3%~1% 量级。",
          "(0,0)→(1,0)、(0,0)→(0,1) 与冻结的三组点对",
          "赤道相对误差 <1e-12、子午线 <1e-9；与 haversine 相对差落在 0.001%~1%（替换确实生效）",
          p2_distance)

    probe("S1-P03", "PyYAML 解析 ⇔ 手写期望结构",
          "YAML 1.1 语义：锚点/合并键/块标量/引号保留字符串类型；空值归一（GA-09）；"
          "多文档必须显式报错而不是静默取首个（静默取首文档=证据被吞）。",
          "自造 tricky.yaml（锚点+<<合并+块标量+引号数字+'yes'+空值+嵌套序列+中文）与 multi.yaml",
          "解析结果 == 手写期望；multi.yaml 必须抛错（不得 NO_RAISE）", p3_yaml)

    probe("S1-P04", "执行入口 Pydantic strict 校验",
          "零隐式类型收敛：strict 下 bool 字段不接受 'yes'；support_status 只允许三值枚举；"
          "校验失败 ⇒ 登记 INPUT_SCHEMA_INVALID ⇒ 整包拒绝执行（契约 §2.4/§9.1）。"
          "反向确认：lax 会把 'yes' 收敛成 True，故入口必须 strict。",
          "clean 包的两份变体：① required_for_release 改成字符串 \"yes\"；② support_status=MAYBE",
          "两种变体都出现 INPUT_SCHEMA_INVALID 且总体 != PASS；lax 反向确认为 True",
          p4_entry_validation)

    probe("S1-P05", "判定接口唯一性",
          "最终复验 Stage 1 第 5 条：删除/收敛旧二参兼容路径，测试迁到唯一正式接口"
          "（build_clause_coverage → aggregate(coverage, rejections, n_rows)）。",
          "inspect.signature(aggregate)、hasattr(_coverage_from_results)、二参调用",
          "签名为三参且含 clause_coverage；兼容辅助函数不存在；二参调用抛 TypeError",
          p5_single_interface)

    probe("S1-P06", "CLI 跨目录与路径穿越失败关闭",
          "CLI 内部应以绝对 ROOT 定位资源（换 cwd 仍可跑）；safe_bundle_path 必须拒绝越出根目录；"
          "包名不存在必须报错退出（不得静默跑默认包）。",
          "在仓库外目录执行：run --bundle clean / run --bundle ../clean / run --bundle no_such_bundle",
          "clean ⇒ rc=0；穿越与不存在的包 ⇒ rc != 0", p6_cli)

    probe("S1-P07", "HTML 报告转义",
          "S0-09 遗留项：报告中的条款原文、观测值来自外部文件，渲染必须 html.escape，"
          "否则交付报告本身就是注入载体。",
          "构造含 <script>alert(\"x\")</script> 与 & 的 report.json 字段",
          "输出中不含未转义 <script，且含 &lt;script&gt; 与 &amp;", p7_html_escape)

    probe("S1-P08", "整改 compare 的身份策略",
          "最终复验 Stage 1 第 8 条：身份不要只靠行号；缺稳定标识或重复 ⇒ not_comparable ⇒ "
          "不得宣称整改完成（总体 INDETERMINATE）。",
          "defective→corrected 基线；整改后批次 poi.csv 行序打乱；再复制一行制造重复 record_id",
          "乱序后 counts/overall 与基线**完全一致**（证明按 record_id 而非行号）；"
          "重复 ID ⇒ 出现 not_comparable 且 overall=INDETERMINATE", p8_compare_identity)

    probe("S1-P09", "重跑确定性（RC-04 回归）",
          "同一实例/跨实例重跑必须产生相同 findings；运行局部状态必须在 run() 开头复位。",
          "defective 包：同实例 run() 两次 + 新实例 run() 一次，比较 stable_key 排序",
          "三者完全相同", p9_determinism)

    probe("S1-P10", "依赖缺失失败关闭",
          "Stage 1 起几何/距离/YAML 依赖专业库；缺失时若静默回退到旧实现，"
          "等于拿近似结果冒充权威结果（A2：缺证据不得放行）。",
          "PYTHONPATH 注入 shapely.py / pyproj.py / yaml.py，import 即抛 ImportError",
          "三者均：退出码 != 0、输出含安装命令、且不得出现 ALL_OK=true", p10_dep_failfast)

    probe("S1-P11", "终端编码独立性",
          "最终复验 A 项：脚本不得依赖调用方设置 PYTHONUTF8；在 GBK 终端/重定向下"
          "中途崩溃会让证据链断在中途（连结果 JSON 都写不出来）。",
          "不设 PYTHONUTF8/PYTHONIOENCODING、stdout 重定向到管道跑 recheck_probes.py；"
          "再用 -X utf8 跑一次对照",
          "两种调用都应 rc=0（或至少给出可诊断的明确报错）；-X utf8 下 28/28", p11_encoding)

    probe("S1-P12", "冻结快照可复现（自实现比对）",
          "最终复验 Stage 1 第 4 条：替换后逐项比较，差异必须有数学或业务依据。",
          "acceptance/stage-1/baseline-frozen.json 与新生成快照（六包 + 边界矩阵 + 距离）",
          "六包规则/条款/总体/findings **零差异**；边界差异恰为 2 个扰动点（共 4 个字段翻转，"
          "均由精确谓词纠正）、距离差异恰为 3 组（椭球 vs 球，相对差 0.003%~0.56%）",
          p12_snapshot_repro)

    probe("S1-P13", "文档现状与实现一致性",
          "最终复验 B 项：材料之间不得互相矛盾；Stage 1 已引入第三方依赖后，"
          "『零第三方依赖』『(stdlib)』『五个示例包』等旧表述必须随之更新。",
          "README.md / acceptance/stage-0/OPEN_ISSUES.md / gate.TOOL_VERSION",
          "五项一致性检查全部为『无矛盾』", p13_doc_consistency)

    n_ok = sum(1 for r in RESULTS if r["ok"])
    payload = {
        "schema_version": "stage1-verify-1",
        "repo_root": str(REPO),
        "python": sys.version.split()[0],
        "probes": RESULTS,
        "counts": {"total": len(RESULTS), "ok": n_ok, "fail": len(RESULTS) - n_ok},
        "all_ok": n_ok == len(RESULTS),
    }
    if OUT:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("结果 JSON：%s" % OUT)
    print("=" * 78)
    print("STAGE1_PROBES_OK=%s（%d/%d 通过）" % (str(n_ok == len(RESULTS)).lower(),
                                                n_ok, len(RESULTS)))
    print("=" * 78)
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
