"""把库里存的英文错误翻译成中文。

为什么需要它：这些错误是**过去**写进 `tg_accounts.last_error` 的英文原文，
修好「写入时翻译」只对**新产生**的错误有效——存量记录不会自己变。
而用户看的正是那些旧记录，所以要在**展示时**再翻一次。

做法是认异常类名（错误文本里带着类名），而不是猜语义：类名是稳定的，
文本内容会随 Telegram 改动，认类名不会被文案变化带偏。
"""

from __future__ import annotations

import re
from typing import Optional

#: 类名 → 中文说明。与 worker 的 FRIENDLY_ERROR_HINTS 保持同一套说法。
_ERROR_HINTS: dict[str, str] = {
    "PeerFloodError": "该号被 Telegram 限制主动发消息（被举报为垃圾信息），需要停手一段时间",
    "FloodWaitError": "触发频率限制，等待计时结束后可继续",
    "FrozenMethodInvalidError": "该号已被冻结，无法执行写操作，需要申诉解封",
    "AuthKeyUnregisteredError": "会话未被 Telegram 认可，需要重新登录",
    "AuthKeyDuplicatedError": "同一会话在别处被使用，Telegram 已永久停用该会话",
    "SessionRevokedError": "会话已被吊销，需要重新登录",
    "SessionExpiredError": "会话已过期，需要重新登录",
    "UserDeactivatedBanError": "账号已被 Telegram 封禁",
    "UserDeactivatedError": "账号已被注销",
    "PhoneNumberBannedError": "手机号已被封禁",
    "UserBannedInChannelError": "在该群/频道被禁言",
    "UserRestrictedError": "账号受到限制，部分操作不可用",
    "ChatWriteForbiddenError": "没有在该会话发言的权限",
    "UsernameNotOccupiedError": "这个用户名不存在",
    "UsernameInvalidError": "用户名格式不合法",
    "AboutTooLongError": "简介超出 Telegram 长度上限（70 字符）",
    "FirstnameInvalidError": "名字不合法",
    "UsernameOccupiedError": "用户名已被占用",
    "InviteHashExpiredError": "邀请链接已失效",
    "InviteHashInvalidError": "邀请链接无效",
}

#: 从「PeerFloodError: xxx」这类文本里抠出异常类名
_CLASS_NAME = re.compile(r"\b([A-Z][A-Za-z]+(?:Error|Exception))\b")

_HAS_CJK = re.compile(r"[\u4e00-\u9fff]")


def has_chinese(text: str) -> bool:
    return bool(_HAS_CJK.search(text or ""))


def translate_error(text: Optional[str]) -> str:
    """把存的英文错误变成「中文说明（原始英文）」。

    - 已经是中文的（新写入的记录）原样返回，不重复加工；
    - 认不出类名的原样返回，不假装翻译。
    """
    raw = (text or "").strip()
    if not raw or has_chinese(raw):
        return raw

    for match in _CLASS_NAME.finditer(raw):
        name = match.group(1)
        hint = _ERROR_HINTS.get(name)
        if hint:
            # 中文在前、原文在后：看原因用中文，排查时原始类名还在
            return f"{hint}（{raw}）"
    return raw
