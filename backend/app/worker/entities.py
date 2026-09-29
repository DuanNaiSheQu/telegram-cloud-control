"""会话/用户目标的实体解析：把各种 id 形态统一成 Telethon 实体。

踩过的坑：Telegram 的 id 有**两套**，而数据库里存的是哪一套取决于同步时怎么写的：

| 对象 | 原始 id（get_entity 的入参形态） | 说明 |
|---|---|---|
| 用户 | 正数，如 `8966880282` | 直接可用 |
| 普通群 | 负数，如 `-123456789` | 直接可用 |
| 频道 / 超级群 | **要带 `-100` 前缀**，如 `-1004337589332` | 原始 id 是 `4337589332`（正数） |

把频道的原始 id（正数）直接传给 `get_entity()`，Telethon 会当成**用户**去找，报
`Could not find the input entity for PeerUser(user_id=...)`——看起来像「这个会话不存在」，
其实是 id 形态不对。这里统一处理，避免每个调用点各自踩一遍。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: 频道/超级群 id 前缀（Telegram 的约定：-100 + 原始 id）
CHANNEL_ID_PREFIX = "-100"


def candidate_ids(raw: Any) -> list[Any]:
    """按「最可能命中」的顺序给出候选 id。

    - 负数（`-100xxx` 或 `-xxx`）：原样试；
    - 正数：先试频道形态 `-100{id}`（超群/频道最常见），再试原值（用户）；字符串形态也兼容。
    """
    text = str(raw).strip()
    if not text.lstrip("-").isdigit():
        return [raw]  # 用户名 / 链接，交给调用方
    number = int(text)
    if number < 0:
        return [number]
    channel_form = int(f"{CHANNEL_ID_PREFIX}{number}")
    return [channel_form, number, text]


async def resolve_entity(client: Any, raw: Any) -> Any:
    """把会话 id / 用户名解析成实体，自动处理频道 id 前缀问题。

    全都失败时抛最后一个异常（由调用方决定怎么包装文案）。
    """
    candidates = candidate_ids(raw)
    last_error: Optional[BaseException] = None
    for index, candidate in enumerate(candidates):
        try:
            entity = await client.get_entity(candidate)
            if index > 0:
                logger.info(
                    "会话 id 形态修正后解析成功",
                    extra={"original": str(raw), "resolved_with": str(candidate)},
                )
            return entity
        except Exception as exc:  # noqa: BLE001 - 换下一个候选继续试
            last_error = exc
    # 兜底一：拉一次会话列表把 Telethon 的实体缓存填上。
    # 有些群/频道没有公开用户名，或执行号还没入群，缓存里就什么都没有；
    # 拉一次 dialogs 能把「该号确实在的那些会话」补进缓存，之后按 id 就能解析。
    try:
        await client.get_dialogs(limit=200)
        for candidate in candidates:
            try:
                return await client.get_entity(candidate)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
    except Exception as exc:  # noqa: BLE001 - 拉列表失败不阻塞，继续走下面的兜底
        logger.debug("预热会话缓存失败：%s", exc)

    # 兜底二：交给 telethon 用它的缓存直接处理原始值（例如已同步过的用户名）
    try:
        return await client.get_entity(raw)
    except Exception as exc:  # noqa: BLE001
        last_error = exc
    assert last_error is not None
    raise last_error


__all__ = ["CHANNEL_ID_PREFIX", "candidate_ids", "resolve_entity"]

async def resolve_chat_entity(
    client: Any,
    raw: Any,
    *,
    session: Any = None,
    username_hint: str = "",
) -> Any:
    """解析「会话」实体，带上用户名兜底。

    为什么需要：执行号**不在某个群里**时，它的 Telethon 实体缓存里没有这个群，
    按 id（`-100xxx`）解析必然失败（`Could not find the input entity for PeerChannel`）。
    而用户名是公开的，任何号都能解析到——所以先想办法拿到用户名：

    1. 调用方给的 `username_hint`（通常来自会话行）；
    2. 否则从数据库里按 `tg_chat_id` 反查会话行拿用户名；
    3. 都没有再退回按 id 解析（内部还会拉一次 dialogs 预热缓存）。
    """
    if not isinstance(raw, (int, str)) or not str(raw).lstrip("-").isdigit():
        return await resolve_entity(client, raw)  # 用户名 / 链接，直接交给底层

    name = (username_hint or "").strip().lstrip("@")
    if not name and session is not None:
        try:
            from sqlalchemy import select

            from app.models import Dialog

            row = await session.scalar(select(Dialog).where(Dialog.tg_chat_id == int(raw)).limit(1))
            if row is not None:
                name = (getattr(row, "username", None) or "").strip().lstrip("@")
        except Exception as exc:  # noqa: BLE001 - 查不到只是少一条回退路径
            logger.debug("按 tg_chat_id 反查用户名失败：%s", exc)
    if name:
        try:
            entity = await client.get_entity(f"@{name}")
            logger.info("按用户名解析会话成功", extra={"tg_chat_id": str(raw), "username": name})
            return entity
        except Exception as exc:  # noqa: BLE001
            logger.debug("按用户名解析失败（改用 id）：%s", exc)
    return await resolve_entity(client, raw)
