"""依赖冒烟：只报告，不自动安装。

Stage 0 内核零第三方依赖；本脚本用于记录 Stage 1 起将要引入的依赖在当前环境中的可用状态，
并对缺失项给出明确的安装命令。缺什么如实写什么，不允许假装已验证。
"""
import importlib
import platform
import subprocess
import sys

# 终端编码：中文输出在 GBK 终端/重定向下会抛 UnicodeEncodeError（证据链断在中途）。
# 统一把标准输出/错误固定为 UTF-8：等价于 README 建议的 `python -X utf8`，
# 且不依赖调用方是否设置 PYTHONUTF8 / PYTHONIOENCODING。
for _s in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
    if _s is not None and hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="strict")

TARGETS = [
    ("yaml", "Stage 0+：配置文件读写（发行包名 PyYAML；当前 Stage 0 未使用，自研极简解析器代替）", "pip install pyyaml"),
    ("pydantic", "Stage 1+：数据对象与 Schema 校验", "pip install pydantic"),
    ("jsonschema", "Stage 1+：Schema 一致性校验", "pip install jsonschema"),
    ("fastapi", "Stage 1+：HTTP API", "pip install fastapi uvicorn"),
    ("geopandas", "Stage 1+：空间数据读写", "pip install geopandas"),
    ("shapely", "Stage 1+：几何谓词与拓扑", "pip install shapely"),
    ("pyproj", "Stage 1+：坐标系变换与测地距离", "pip install pyproj"),
    ("pandas", "Stage 1+：字段级剖析", "pip install pandas"),
    ("pytest", "Stage 1+：单元与集成测试", "pip install pytest"),
]


def main():
    print("python=%s platform=%s" % (sys.version.split()[0], platform.platform()))
    print("")
    print("%-12s %-6s %s" % ("模块", "状态", "用途"))
    print("-" * 78)
    missing = []
    for name, purpose, cmd in TARGETS:
        try:
            mod = importlib.import_module(name)
            ver = getattr(mod, "__version__", "?")
            print("%-12s %-6s %s  (版本 %s)" % (name, "OK", purpose, ver))
        except Exception:
            print("%-12s %-6s %s" % (name, "MISSING", purpose))
            missing.append((name, cmd))
    print("")
    print("当前环境可执行且不需要安装的重跑记录：")
    try:
        out = subprocess.run([sys.executable, "-m", "pip", "--version"],
                             capture_output=True, text=True)
        print("  pip:", out.stdout.strip() or out.stderr.strip())
    except Exception as e:
        print("  pip 不可用:", e)
    print("")
    if missing:
        print("缺失项（未安装，Stage 1 开工前需要处理）：")
        for name, cmd in missing:
            print("  - %s -> %s" % (name, cmd))
    else:
        print("缺失项：无")
    print("")
    print("Stage 0 门槛要求：零第三方依赖即可完成端到端实例。本环境的 Stage 0 依赖满足情况：满足")
    return 0


if __name__ == "__main__":
    sys.exit(main())
