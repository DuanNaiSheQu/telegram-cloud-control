"""账号可用性判定：哪些号还能承接触达动作。

冻结（frozen）的号并不是「连不上」——它能读消息、能上报在线状态，所以列表里看着正常；
但 Telegram 会拒绝它的**所有写操作**（发消息、改资料、加群、退群），
把触达任务派给它等于白占一条任务、还要多挨一次限流。

所以：**触达动作**（私信 / 群发 / 素材群发 / 加群 / 退群 / 强拉 / 改资料 / 吵群 / 拟人发言）
只派给正常可用的号；而**运维动作**（账号检测、申诉解封、官方养号、同步会话）对冻结号仍有意义，
不受这里限制。
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from app.models import AccountStatus, TgAccount

#: 不能承接触达动作的状态
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
    """该号现在能不能承接触达动作。"""
    status = account.status
    if hasattr(status, "value"):
        status = AccountStatus(status.value)
    return status not in MARKETING_BLOCKED_STATUSES and bool(account.session_enc)


def block_reason(account: TgAccount) -> str:
    """不能用于触达的原因（给用户看的）。"""
    if not account.session_enc:
        return "没有会话（需要先导入或登录）"
    status = account.status
    if hasattr(status, "value"):
        status = AccountStatus(status.value)
    return BLOCK_REASONS.get(status, "当前状态不可用")


def split_marketing_usable(rows: Iterable[TgAccount]) -> Tuple[List[TgAccount], List[Tuple[TgAccount, str]]]:
    """按能否承接触达动作分组：返回 (可用, [(不可用, 原因)])。"""
    usable: List[TgAccount] = []
    blocked: List[Tuple[TgAccount, str]] = []
    for row in rows:
        if is_marketing_usable(row):
            usable.append(row)
        else:
            blocked.append((row, block_reason(row)))
    return usable, blocked


# 出现这些异常说明这个号已经实质上用不了了：会话被 Telegram 撤销、号被注销、会话被顶掉。
# 与"冻结"不同——冻结有解冻可能，所以只标记不归档；这些则是修不回来的，归到归档区。
ARCHIVE_WHEN = (
    "AuthKeyUnregistered",
    "AuthKeyDuplicated",
    "SessionRevoked",
    "SessionExpired",
    "UserDeactivated",
    "UserDeactivatedBan",
    "PhoneNumberBanned",
    "PhoneNumberInvalid",
)


def archive_reason_for(exc: BaseException) -> str:
    """按异常给出人能看懂的原因，写进归档记录。"""
    name = type(exc).__name__
    text = str(exc)
    mapping = {
        "AuthKeyUnregistered": "会话已被 Telegram 撤销，需要重新登录这个号",
        "AuthKeyDuplicated": "会话在别处被使用过（同号两处登录），密钥已失效",
        "SessionRevoked": "会话被撤销",
        "SessionExpired": "会话已过期，需要重新登录",
        "UserDeactivated": "账号已被注销",
        "UserDeactivatedBan": "账号已被 Telegram 封禁",
        "PhoneNumberBanned": "手机号被封禁",
        "PhoneNumberInvalid": "手机号无效",
    }
    for key, human in mapping.items():
        if key in name:
            return human
    return f"{name}: {text[:160]}"


def should_archive(exc: BaseException) -> bool:
    name = type(exc).__name__
    return any(key in name for key in ARCHIVE_WHEN)
