"""Telegram 云控后端。

版本号只有一处真源：仓库根目录的 `VERSION` 文件（前后端共用，避免各写各的）。
读取失败时回退到一个常量，保证任何环境下都能起来。
"""

from pathlib import Path

_FALLBACK = "0.3.0"


def _read_version() -> str:
    for candidate in (
        Path(__file__).resolve().parents[2] / "VERSION",  # 仓库根
        Path(__file__).resolve().parents[1] / "VERSION",  # backend/VERSION（打包场景）
    ):
        try:
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            continue
    return _FALLBACK


__version__ = _read_version()
