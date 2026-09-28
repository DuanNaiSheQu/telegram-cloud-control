"""Telegram Webhook（无 JWT）。

处理顺序按契约第 7 节：校验 secret → update_id 去重 → 普通消息入库 + 转发任务 + Bot 自动回复
→ 员工群里的回复送回原会话。

一条铁律：**除了 secret 不对回 403，其余一律 200**。Telegram 在非 2xx 时会不断重试，
一次业务异常可能演变成重试风暴，所以业务错误只记 JSON 日志（带 bot_id / update_id）。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from aiogram.types import Update
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.api.deps import get_session
from app.config import settings
from app.core import events
from app.core.audit import write_audit
from app.core.tasks import enqueue_task
from app.models import Bot, DialogChannel, DialogKind, MessageDirection, TaskType
from app.redis_client import get_redis
from app.services import inbound, relay

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])

#: 能收到就处理：私信、群、超级群；频道消息 Bot 一般收不到，忽略
HANDLED_CHAT_TYPES = {"private", "group", "supergroup"}


def _chat_kind(chat_type: str) -> DialogKind:
    return DialogKind.private if chat_type == "private" else DialogKind.group


def _full_name(user: Any) -> str:
    if user is None:
        return ""
    name = " ".join(part for part in [getattr(user, "first_name", ""), getattr(user, "last_name", "")] if part)
    return name or (f"@{user.username}" if getattr(user, "username", None) else str(getattr(user, "id", "")))


@router.post("/webhook/{bot_id}/{secret}", summary="Telegram 回调（无 JWT）")
async def telegram_webhook(
    bot_id: uuid.UUID,
    secret: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """顺序：secret 校验（否则 403）→ 去重 → 解析 update → 业务处理（异常只记日志，仍回 200）。"""
    if not security.constant_time_equals(secret, settings.webhook_secret):
        logger.warning("Webhook secret 不匹配 bot_id=%s", bot_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook 密钥不匹配")

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - 非 JSON 请求体
        logger.warning("Webhook 请求体不是 JSON bot_id=%s", bot_id)
        return {"ok": True, "detail": "请求体不是 JSON，已忽略"}

    update_id = payload.get("update_id")
    if update_id is not None:
        try:
            if await events.seen_update(get_redis(), bot_id, int(update_id)):
                # Telegram 重试同一条更新：直接丢弃（重复投递不能变成两次转发）
                return {"ok": True, "detail": "duplicate update ignored"}
        except Exception:  # noqa: BLE001 - Redis 挂了宁可重复处理也不能丢消息
            logger.warning("Webhook 去重失败（Redis 不可用）bot_id=%s update_id=%s", bot_id, update_id)

    try:
        update = Update.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - Telegram 加了新字段 / 结构变化
        logger.warning(
            "Webhook update 解析失败 bot_id=%s update_id=%s：%s", bot_id, update_id, exc
        )
        return {"ok": True, "detail": "update 解析失败，已忽略"}

    try:
        await _handle_update(session, bot_id=bot_id, update=update)
        await session.commit()
    except Exception:  # noqa: BLE001 - 业务异常只记日志，绝不回非 2xx
        await session.rollback()
        logger.exception(
            "Webhook 处理失败 bot_id=%s update_id=%s",
            bot_id,
            update_id,
            extra={"bot_id": str(bot_id), "update_id": update_id},
        )
    return {"ok": True, "detail": ""}


async def _handle_update(session: AsyncSession, *, bot_id: uuid.UUID, update: Update) -> None:
    """一条 update 的完整业务处理。异常向上抛，由入口统一吞掉并记日志。"""
    message = update.message or update.edited_message
    if message is None:
        # 回调按钮、群成员变化等暂时不处理，直接 200
        return
    chat = message.chat
    chat_type = str(getattr(chat.type, "value", chat.type))
    if chat_type not in HANDLED_CHAT_TYPES:
        return
    from_user = message.from_user
    if from_user is not None and from_user.is_bot:
        # Bot 自己发的消息不要再入库，否则自动回复会打转
        return

    bot_row = await session.scalar(select(Bot).where(Bot.id == bot_id))
    if bot_row is None:
        logger.warning("Webhook 指向的 Bot 不存在 bot_id=%s", bot_id)
        return

    body = message.text or message.caption or ""
    content_type = str(getattr(message.content_type, "value", message.content_type))
    reply_to_id = message.reply_to_message.message_id if message.reply_to_message else None

    # ---- 员工群里的回复：不放进收件箱，直接按 relay_links 送回原会话 ----
    try:
        staff_ids = await relay.staff_chat_ids(session)
    except Exception:  # noqa: BLE001
        staff_ids = set()
    if chat.id in staff_ids and message.reply_to_message is not None:
        origin = await relay.find_origin_by_staff_reply(
            session, staff_chat_id=chat.id, staff_message_id=message.reply_to_message.message_id
        )
        if origin is not None and body.strip():
            _link, origin_message, dialog = origin
            await enqueue_task(
                session,
                type=TaskType.reply_to_origin,
                bot_id=bot_id,
                dialog_id=dialog.id,
                payload={
                    "dialog_id": str(dialog.id),
                    "text": body,
                    "staff_chat_id": chat.id,
                    "staff_message_id": message.message_id,
                    "origin_message_id": str(origin_message.id),
                },
                priority=30,
                dedupe_key=f"reply:{bot_id}:{chat.id}:{message.message_id}",
            )
            logger.info(
                "员工群回复已入队 bot_id=%s dialog_id=%s staff_message_id=%s",
                bot_id,
                dialog.id,
                message.message_id,
                extra={"bot_id": str(bot_id), "dialog_id": str(dialog.id)},
            )
        return

    # ---- 普通消息：入库 → 转发任务 → （可选）Bot 自动回复 → 推页面 ----
    dialog, msg, created = await inbound.ingest_message(
        session,
        channel=DialogChannel.bot,
        direction=MessageDirection.incoming,
        tg_chat_id=chat.id,
        kind=_chat_kind(chat_type),
        bot_id=bot_id,
        title=getattr(chat, "title", "") or "",
        username=getattr(chat, "username", None) or getattr(from_user, "username", None),
        peer_display=getattr(chat, "title", "") or _full_name(from_user),
        body=body,
        tg_message_id=message.message_id,
        sender_tg_id=getattr(from_user, "id", None),
        sender_name=_full_name(from_user),
        reply_to_tg_message_id=reply_to_id,
        has_media=content_type != "text",
        media_type=content_type,
        raw={"update_id": update.update_id, "message": message.model_dump(mode="json", exclude_none=True)},
    )
    if not created:
        # 同一条 Telegram 消息重复投递（去重键过期 / Redis 重启）：不再产生副作用
        logger.info("Webhook 消息已存在，跳过后续任务 bot_id=%s tg_message_id=%s", bot_id, message.message_id)
        return

    relay_tasks = await relay.enqueue_relays(session, dialog=dialog, message=msg)
    reply_task: Optional[Any] = None
    if bot_row.auto_reply_enabled and body.strip():
        reply_task = await enqueue_task(
            session,
            type=TaskType.bot_reply,
            bot_id=bot_id,
            dialog_id=dialog.id,
            payload={"dialog_id": str(dialog.id), "message_id": str(msg.id)},
            priority=80,
            dedupe_key=f"botreply:{msg.id}",
        )
    await write_audit(
        session,
        action="message.receive",
        bot_id=bot_id,
        target_type="message",
        target_id=str(msg.id),
        detail={"dialog_id": str(dialog.id), "tg_chat_id": chat.id, "chat_type": chat_type},
    )
    await session.flush()
    try:
        await inbound.publish_message(get_redis(), dialog, msg)
    except Exception:  # noqa: BLE001 - Redis 挂了只影响实时推送，不能把入库事务回滚掉
        logger.warning("推送新消息失败（Redis 不可用）bot_id=%s dialog_id=%s", bot_id, dialog.id)

    logger.info(
        "Webhook 已入库 bot_id=%s dialog_id=%s message_id=%s relay_tasks=%s auto_reply=%s",
        bot_id,
        dialog.id,
        msg.id,
        len(relay_tasks),
        bool(reply_task),
        extra={"bot_id": str(bot_id), "dialog_id": str(dialog.id)},
    )


__all__ = ["router"]
