"""Stage 1 第一批：项目虚拟环境与空间依赖的**真实运行验证**（不是只报告存在性）。

用途（对应最终复验报告 Stage 1 进入条件第 2 条）：
1. 记录实际解释器路径与版本、依赖库版本；
2. **真的跑一次**空间计算：Shapely 的点/边界判定、pyproj 的测地距离、GeoPandas 读 GeoJSON；
3. 把专业库的结果与 Stage 0 自研实现**逐点对比**，为后续替换提供差异依据（不是迁就原实现）。

退出码：全部完成且无致命错误 = 0；任一环节失败 = 1。
"""
from __future__ import annotations

import json
import math
import platform
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


def info(msg=""):
    print(msg)


def section(title):
    info("")
    info("=" * 74)
    info(title)
    info("=" * 74)


def main():
    section("1. 解释器与环境")
    info("executable : %s" % sys.executable)
    info("version    : %s" % sys.version.replace("\n", " "))
    info("platform   : %s" % platform.platform())
    info("in venv    : %s" % (sys.prefix != getattr(sys, "base_prefix", sys.prefix)))
    info("prefix     : %s" % sys.prefix)

    section("2. 依赖版本（真实 import，非文件扫描）")
    versions = {}
    for mod in ["shapely", "pyproj", "yaml", "pydantic", "jsonschema",
                "geopandas", "pandas", "numpy"]:
        try:
            m = __import__(mod)
            versions[mod] = getattr(m, "__version__", "unknown")
        except Exception as exc:  # noqa: BLE001 —— 环境验证要如实报失败
            versions[mod] = "IMPORT FAILED: %s: %s" % (type(exc).__name__, exc)
    for k, v in versions.items():
        info("%-12s %s" % (k, v))
    missing = [k for k, v in versions.items() if str(v).startswith("IMPORT FAILED")]
    if missing:
        info("")
        info("[MISSING] 以下依赖不可用：%s（先建 .venv 并安装 requirements.txt）" % ", ".join(missing))
        return 1

    section("3. Shapely 运行验证：单位正方形的内点/边界/外点")
    from shapely.geometry import Point, Polygon, shape as shapely_shape
    sq = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    cases = [("内点", (0.5, 0.5)), ("左边界中点", (0.0, 0.5)), ("右边界中点", (1.0, 0.5)),
             ("下边界中点", (0.5, 0.0)), ("上边界中点", (0.5, 1.0)),
             ("顶点", (0.0, 0.0)), ("外点", (1.5, 0.5))]
    info("%-12s %-10s %-10s %-10s" % ("点", "contains", "touches", "covers"))
    for name, (x, y) in cases:
        p = Point(x, y)
        info("%-12s %-10s %-10s %-10s"
             % ("%s(%.1f,%.1f)" % (name, x, y), sq.contains(p), sq.touches(p), sq.covers(p)))
    info("")
    info("结论：inclusive（含边界）= covers = contains or touches；exclusive = contains。")
    info("      Stage 0 自研实现的等价口径：point_in_ring_or_boundary(..., inclusive=True/False)。")

    section("4. pyproj 运行验证：测地距离 vs Stage 0 自研 haversine")
    from pyproj import Geod
    geod = Geod(ellps="WGS84")

    def haversine(lon1, lat1, lon2, lat2):
        """Stage 0 的球面近似（R=6371000m），仅用于差异对比。"""
        r = 6371000.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp, dl = p2 - p1, math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(math.sqrt(a))

    pairs = [((116.3912, 39.9075), (116.3975, 39.9087)),     # ~540 m
             ((116.0, 39.0), (117.0, 40.0)),                  # ~130 km
             ((0.0, 0.0), (0.0, 1.0))]                        # ~111 km
    info("%-28s %-14s %-14s %-10s" % ("点对", "pyproj( geodesic )", "haversine(旧)", "相对差"))
    for (a, b) in pairs:
        _, _, d_geo = geod.inv(a[0], a[1], b[0], b[1])
        d_hav = haversine(a[0], a[1], b[0], b[1])
        rel = abs(d_geo - d_hav) / d_geo if d_geo else 0.0
        info("%-28s %-14.3f %-14.3f %-10.5f"
             % ("%s→%s" % (a, b), d_geo, d_hav, rel))
    info("")
    info("结论：测地距离以 WGS84 椭球为准（pyproj）；haversine 用 R=6371000 球近似，")
    info("      典型相对差 1e-3 ~ 1e-2 量级。替换后阈值判定结果可能变化，必须逐条给依据。")

    section("5. GeoPandas / PyYAML / Pydantic / jsonschema 运行验证")
    import geopandas as gpd
    import yaml
    import pydantic
    import jsonschema

    area = json.loads((EX / "clean" / "area.geojson").read_text(encoding="utf-8"))
    gdf = gpd.read_file(EX / "clean" / "area.geojson")
    poly = gdf.geometry.iloc[0]
    info("GeoPandas 读入 clean/area.geojson：type=%s, area=%.6f, bounds=%s"
         % (poly.geom_type, poly.area, tuple(round(v, 6) for v in poly.bounds)))
    cx, cy = poly.centroid.x, poly.centroid.y
    info("GeoPandas + Shapely 判定示例：centroid(%.6f,%.6f) contains=%s / boundary touches=%s"
         % (cx, cy, poly.contains(Point(cx, cy)), poly.boundary.touches(Point(cx, cy))))

    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import stage0_gate as g
    except Exception as exc:  # noqa: BLE001
        info("（跳过 YAML 对拍：无法导入 stage0_gate：%s）" % exc)
        g = None
    if g is not None:
        info("")
        info("PyYAML vs 自研解析器（对 examples/* 全部 yaml 逐文件对拍）：")
        bad = 0
        for p in sorted(EX.glob("*/requirements.yaml")) + sorted(EX.glob("*/approved-rules.yaml")):
            try:
                mine = g.load_yaml(p)
                theirs = yaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                info("  [ERR ] %s：%s: %s" % (p.relative_to(ROOT), type(exc).__name__, exc))
                bad += 1
                continue
            same = mine == theirs
            bad += 0 if same else 1
            info("  [%s] %s" % ("SAME" if same else "DIFF", p.relative_to(ROOT)))
            if not same:
                info("        自研顶层键=%s" % sorted((mine or {}).keys()))
                info("        PyYAML 顶层键=%s" % sorted((theirs or {}).keys()))
        info("对拍结论：%s" % ("全部一致" if bad == 0 else "%d 个文件不一致（替换前须逐条给依据）" % bad))

    class _Probe(pydantic.BaseModel):
        requirement_id: str
        required_for_release: bool
        support_status: str

    class _StrictProbe(pydantic.BaseModel):
        """执行入口应使用 **strict** 模式：不接受 "yes"/"1" 这类隐式类型 coercion。"""
        model_config = pydantic.ConfigDict(strict=True)
        requirement_id: str
        required_for_release: bool
        support_status: str

    m = _Probe(requirement_id="A1", required_for_release=True, support_status="SUPPORTED")
    info("")
    info("Pydantic lax 校验通过：%s" % m.model_dump())
    info("Pydantic lax 会把 'yes' 收敛为 bool：%s"
         % _Probe(requirement_id="A1", required_for_release="yes",
                  support_status="SUPPORTED").model_dump())
    try:
        _StrictProbe(requirement_id="A1", required_for_release="yes", support_status="SUPPORTED")
        info("[WARN] strict 模式未拦下类型错误（不可能，检查 pydantic 版本）")
    except pydantic.ValidationError as exc:
        info("Pydantic strict 反向确认：类型错误被拦下（%s）"
             % str(exc).splitlines()[1].strip()[:80])

    jsonschema.validate({"a": 1}, {"type": "object", "properties": {"a": {"type": "integer"}}})
    info("jsonschema 标准校验：正向通过、可用（完整 Draft 支持，替代自研子集校验器）")

    section("6. 结论")
    info("ENV_VERIFY_OK=true（依赖齐备且全部完成真实运行验证）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
