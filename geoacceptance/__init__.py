"""GeoAcceptance Stage 1 最小包：CLI / 报告 / 整改 compare / 输入防护。

**不复制判定逻辑**：内核（Kernel、规则、聚合、契约断言）仍在 `tools/stage0_gate.py`。
本包只提供"内核之外"的能力，避免像 Stage 0 的兼容路径那样出现第二条判定口径。
"""
VERSION = "stage1/0.1.0"

__all__ = ["VERSION", "inputs", "compare", "reporting", "cli"]
