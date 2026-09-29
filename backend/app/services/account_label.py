"""账号展示标签：明文手机号 > 用户名 > Telegram 用户 ID > 兜底。

抽到 services 层是为了让 API 路由与批量操作共用同一套口径——
`phone_masked` 可能是导入时的目录标签（tdata 导入的 `tdata#0`），对外没有辨识度，不能当手机号用。
"""

from __future__ import annotations

import re
from typing import Optional

from app import security
from app.models import TgAccount

#: 手机号的形态（明文或脱敏：`+959791178160` / `+9597****8160`）
_PHONE_RE = re.compile(r"^\+?\d[\d\s*]{5,}$")


def account_label(account: Optional[TgAccount]) -> Optional[str]:
    """账号展示名：明文手机号 > 脱敏手机号 > @用户名 > ID:{tg_user_id} > 导入标签 > 短 id。"""
    if account is None:
        return None
    # 明文手机号优先（不脱敏）
    if getattr(account, "phone_enc", None):
        try:
            plain = (security.decrypt_secret(account.phone_enc) or "").strip()
            if plain:
                return plain
        except Exception:  # noqa: BLE001 - 解不开不能让接口挂
            pass
    masked = (account.phone_masked or "").strip()
    if masked and masked != "未知" and _PHONE_RE.match(masked):
        return masked
    if account.username:
        return f"@{account.username}"
    if account.tg_user_id:
        return f"ID:{account.tg_user_id}"
    if masked and masked != "未知":
        return masked
    return str(account.id)[:8]
