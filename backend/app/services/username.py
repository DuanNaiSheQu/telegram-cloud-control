"""Telegram 用户名的清洗与校验。

踩过的坑：运营同学在表单里填 `@woieduanai`，代码原样传给 Telegram，于是报
`UsernameInvalidError: ... the username is invalid`——看起来像「这个名字不能用」，
其实是**多了个 @**。所以用户名进系统后先清洗，再按 Telegram 的规则本地校验一遍，
不合格就直接给出可读原因，不浪费一次接口调用。

Telegram 的规则（实测确认）：

- 长度 5–32；
- 只允许字母、数字、下划线；
- **不能以数字或下划线开头**（必须以字母开头）；
- **不能以下划线结尾**，也不能出现连续下划线；
- 大小写不敏感（统一转小写保存）。
"""

from __future__ import annotations

import re
from typing import Optional

#: 允许的形态：字母开头，随后 4-31 个字母/数字/下划线（总长 5-32）
USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{4,30}$")

#: 规则说明，给用户看的（与上面的正则一一对应）
USERNAME_RULE_TEXT = "5-32 位，只能是字母、数字、下划线；必须以字母开头，不能以下划线结尾"


class UsernameInvalid(ValueError):
    """用户名不符合 Telegram 规则：文案直接给到前端。"""


def normalize_username(value: Optional[str]) -> Optional[str]:
    """把用户输入整理成 Telegram 接受的形式：去掉 @ / t.me 链接 / 空白，统一小写。

    只做「明显的输入噪音」处理，格式是否合法交给 `validate_username`。
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # 支持直接粘贴 t.me 链接或 @用户名
    for prefix in ("https://", "http://"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
    if text.lower().startswith("t.me/"):
        text = text[len("t.me/"):]
    text = text.split("?")[0].split("/")[0].strip().lstrip("@")
    return text.lower() or None


def validate_username(value: str) -> str:
    """校验用户名；不合法抛 `UsernameInvalid`，合法返回规范化后的值。"""
    name = normalize_username(value)
    if not name:
        raise UsernameInvalid("用户名是空的")
    if "_" in name and ("__" in name or name.endswith("_")):
        raise UsernameInvalid(f"用户名不能以下划线结尾或出现连续下划线（{USERNAME_RULE_TEXT}）")
    if not USERNAME_RE.match(name):
        raise UsernameInvalid(f"用户名不符合规则：{USERNAME_RULE_TEXT}（当前：{name}）")
    return name


__all__ = [
    "USERNAME_RE",
    "USERNAME_RULE_TEXT",
    "UsernameInvalid",
    "normalize_username",
    "validate_username",
]
