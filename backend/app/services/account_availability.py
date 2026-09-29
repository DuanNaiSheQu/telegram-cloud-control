"""账号可用性判定：哪些号还能承接营销动作。

冻结（frozen）的号并不是「连不上」——它能读消息、能上报在线状态，所以列表里看着正常；
但 Telegram 会拒绝它的**所有写操作**（发消息、改资料、加群、退群），
把营销任务派给它等于白占一条任务、还要多挨一次限流。

所以：**营销动作**（私信 / 群发 / 素材群发 / 加群 / 退群 / 强拉 / 改资料 / 吵群 / 拟人发言）
只派给正常可用的号；而**运维动作**（账号检测、申诉解封、官方养号、同步会话）对冻结号仍有意义，
不受这里限制。
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from app.models import AccountStatus, TgAccount

#: 不能承接营销动作的状态
#: - frozen：被 Telegram 冻结，写操作一律被拒
#: - dead：永久双向 / 已封禁
#: - invalid：会话失效或号已注销
#: - disabled：被人工停用
MARKETING_BLOCKED_STATUSES = (
    AccountStatus.frozen,
    AccountStatus.dead,
    AccountStatus.invalid,
    AccountStatus.disabled,
)

#: 给运营看的原因
BLOCK_REASONS = {
    AccountStatus.frozen: "已被 Telegram 冻结（写操作会被拒，先申诉或换号）",
    AccountStatus.dead: "号已失效（永久双向 / 已封禁）",
    AccountStatus.invalid: "会话失效或号已注销，需要重新登录",
    AccountStatus.disabled: "已被人工停用（批量启用后可再用）",
}


def is_marketing_usable(account: TgAccount) -> bool:
    """该号现在能不能承接营销动作。"""
    status = account.status
    if hasattr(status, "value"):
        status = AccountStatus(status.value)
    return status not in MARKETING_BLOCKED_STATUSES and bool(account.session_enc)


def block_reason(account: TgAccount) -> str:
    """不能用于营销的原因（给用户看的）。"""
    if not account.session_enc:
        return "没有会话（需要先导入或登录）"
    status = account.status
    if hasattr(status, "value"):
        status = AccountStatus(status.value)
    return BLOCK_REASONS.get(status, "当前状态不可用")


def split_marketing_usable(rows: Iterable[TgAccount]) -> Tuple[List[TgAccount], List[Tuple[TgAccount, str]]]:
    """按能否承接营销动作分组：返回 (可用, [(不可用, 原因)])。"""
    usable: List[TgAccount] = []
    blocked: List[Tuple[TgAccount, str]] = []
    for row in rows:
        if is_marketing_usable(row):
            usable.append(row)
        else:
            blocked.append((row, block_reason(row)))
    return usable, blocked
