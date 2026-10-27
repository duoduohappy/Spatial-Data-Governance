"""输入防护：路径穿越、文件大小、编码。

Stage 1 第 6 条要求"输入防护"。这里只做**确定性**的防护，不做启发式猜测：
- 包目录必须位于给定根目录之内（拒绝 `../`、绝对路径逃逸、符号链接逃逸）；
- 单文件超过上限直接报错（不静默截断，避免"读了一半"被当成完整证据）；
- 文本必须是 UTF-8（非 UTF-8 明确报错，不用 errors="ignore" 掩盖）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

DEFAULT_MAX_BYTES = 20 * 1024 * 1024   # 20 MiB：Stage 1 示例规模远小于此，留出余量


class InputGuardError(Exception):
    """输入不合规：一律显式抛出，由 CLI 转成非零退出，不做"降级继续"。"""


def safe_bundle_path(root: Path, name: str) -> Path:
    """把用户给的包名/相对路径限制在 root 之内（防路径穿越）。"""
    if not name or name.strip() != name:
        raise InputGuardError("包名不得为空或带空白：%r" % name)
    root = root.resolve()
    target = (root / name).resolve()
    if target == root or root not in target.parents:
        raise InputGuardError("包路径越出项目根目录：%s（root=%s）" % (target, root))
    if not target.is_dir():
        raise InputGuardError("包目录不存在：%s" % target)
    return target


def read_text_capped(path: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    """读取 UTF-8 文本；超限或非 UTF-8 一律报错（不截断、不 ignore）。"""
    path = Path(path)
    if not path.exists():
        raise InputGuardError("文件不存在：%s" % path)
    size = path.stat().st_size
    if size > max_bytes:
        raise InputGuardError("文件 %s 大小 %d 字节超过上限 %d 字节（拒绝读取，不静默截断）"
                              % (path, size, max_bytes))
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputGuardError("文件 %s 不是 UTF-8：%s" % (path, exc))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bundle_input_hashes(bundle: Path, names=("delivery_spec.md", "dictionary.csv", "poi.csv",
                                             "area.geojson", "crs.json", "requirements.yaml",
                                             "approved-rules.yaml")) -> dict:
    """列出包内输入文件的 sha256（缺文件记为 None，不伪造）。"""
    out = {}
    for n in names:
        p = bundle / n
        out[n] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    return out
