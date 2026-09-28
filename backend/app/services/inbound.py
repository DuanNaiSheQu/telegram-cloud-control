"""两条连接进同一张收件箱：用户号（Worker）与官方 Bot（API Webhook）都走这里入库。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.models import Bot, Dialog, DialogChannel, DialogKind, Message, MessageDirection, MessageStatus


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def preview_of(body: str, limit: int = 120) -> str:
    text = (body or "").replace("\n", " ").strip()
    return text[:limit]


async def upsert_dialog(
    session: AsyncSession,
    *,
    channel: DialogChannel,
    kind: DialogKind,
    tg_chat_id: int,
    account_id: Optional[uuid.UUID] = None,
    bot_id: Optional[uuid.UUID] = None,
    title: str = "",
    username: Optional[str] = None,
    peer_display: str = "",
    member_count: Optional[int] = None,
) -> Dialog:
    dialog = await session.scalar(
        select(Dialog).where(
            Dialog.channel == channel,
            Dialog.account_id == account_id if account_id else Dialog.account_id.is_(None),
            Dialog.bot_id == bot_id if bot_id else Dialog.bot_id.is_(None),
            Dialog.tg_chat_id == tg_chat_id,
        )
    )
    if dialog is None:
        dialog = Dialog(
            channel=channel,
            kind=kind,
            tg_chat_id=tg_chat_id,
            account_id=account_id,
            bot_id=bot_id,
            title=title or peer_display or str(tg_chat_id),
            username=username,
            peer_display=peer_display or title or str(tg_chat_id),
            member_count=member_count,
        )
        session.add(dialog)
        await session.flush()
        return dialog

    # 只在有新值时更新，避免把已有标题覆盖成空
    if title:
        dialog.title = title
    if username:
        dialog.username = username
    if peer_display:
        dialog.peer_display = peer_display
    if member_count is not None:
        dialog.member_count = member_count
    # 群聊类型是粘性的：同一个 peer 不可能既是群又是私信。
    # 调用方没显式给 kind 时会落到默认值 private，不能因此把群聊降级。
    if kind == DialogKind.group and dialog.kind != DialogKind.group:
        dialog.kind = DialogKind.group
    await session.flush()
    return dialog


async def message_exists(
    session: AsyncSession, *, dialog_id: uuid.UUID, tg_message_id: Optional[int]
) -> bool:
    if tg_message_id is None:
        return False
    found = await session.scalar(
        select(Message.id).where(
            Message.dialog_id == dialog_id, Message.tg_message_id == tg_message_id
        )
    )
    return found is not None


async def ingest_message(
    session: AsyncSession,
    *,
    channel: DialogChannel,
    direction: MessageDirection,
    tg_chat_id: int,
    kind: DialogKind = DialogKind.private,
    account_id: Optional[uuid.UUID] = None,
    bot_id: Optional[uuid.UUID] = None,
    title: str = "",
    username: Optional[str] = None,
    peer_display: str = "",
    member_count: Optional[int] = None,
    body: str = "",
    tg_message_id: Optional[int] = None,
    sender_tg_id: Optional[int] = None,
    sender_name: str = "",
    reply_to_tg_message_id: Optional[int] = None,
    has_media: bool = False,
    media_type: Optional[str] = None,
    raw: Optional[Any] = None,
    status: MessageStatus = MessageStatus.received,
    created_by: Optional[uuid.UUID] = None,
    count_unread: bool = True,
) -> Tuple[Dialog, Message, bool]:
    """写入一条消息。返回 (会话, 消息, 是否新建)。已存在的 tg_message_id 不重复写。"""
    dialog = await upsert_dialog(
        session,
        channel=channel,
        kind=kind,
        tg_chat_id=tg_chat_id,
        account_id=account_id,
        bot_id=bot_id,
        title=title,
        username=username,
        peer_display=peer_display,
        member_count=member_count,
    )

    if await message_exists(session, dialog_id=dialog.id, tg_message_id=tg_message_id):
        return dialog, await session.scalar(
            select(Message).where(
                Message.dialog_id == dialog.id, Message.tg_message_id == tg_message_id
            )
        ), False  # type: ignore[return-value]

    message = Message(
        dialog_id=dialog.id,
        channel=channel,
        direction=direction,
        status=status,
        body=body or "",
        tg_message_id=tg_message_id,
        sender_tg_id=sender_tg_id,
        sender_name=sender_name or "",
        reply_to_tg_message_id=reply_to_tg_message_id,
        has_media=has_media,
        media_type=media_type,
        raw=raw,
        created_by=created_by,
    )
    session.add(message)
    await session.flush()

    dialog.last_message_at = message.created_at or _now()
    dialog.last_message_preview = preview_of(body)
    if direction == MessageDirection.incoming:
        # count_unread=False 用于补历史消息（sync_messages）：老消息不该再点亮未读角标
        if count_unread:
            dialog.unread_count = (dialog.unread_count or 0) + 1
    else:
        dialog.unread_count = 0
    await session.flush()
    return dialog, message, True


def message_payload(dialog: Dialog, message: Message) -> dict:
    """WebSocket / Redis 推送载荷。"""
    return {
        "dialog_id": str(dialog.id),
        "message": {
            "id": str(message.id),
            "dialog_id": str(dialog.id),
            "channel": dialog.channel.value if hasattr(dialog.channel, "value") else str(dialog.channel),
            "direction": message.direction.value
            if hasattr(message.direction, "value")
            else str(message.direction),
            "status": message.status.value if hasattr(message.status, "value") else str(message.status),
            "body": message.body,
            "tg_message_id": message.tg_message_id,
            "sender_name": message.sender_name,
            "sender_tg_id": message.sender_tg_id,
            "has_media": message.has_media,
            "media_type": message.media_type,
            "created_at": (message.created_at or _now()).isoformat(),
        },
        "dialog": {
            "id": str(dialog.id),
            "title": dialog.title,
            "kind": dialog.kind.value if hasattr(dialog.kind, "value") else str(dialog.kind),
            "channel": dialog.channel.value
            if hasattr(dialog.channel, "value")
            else str(dialog.channel),
            "unread_count": dialog.unread_count,
            "last_message_preview": dialog.last_message_preview,
            "last_message_at": (dialog.last_message_at or _now()).isoformat(),
        },
    }


async def bot_auto_reply_config(session: AsyncSession, bot_id: uuid.UUID) -> Optional[Bot]:
    bot = await session.scalar(select(Bot).where(Bot.id == bot_id))
    if bot is None or not bot.auto_reply_enabled:
        return None
    return bot


async def publish_message(redis, dialog: Dialog, message: Message) -> None:
    if redis is None:
        return
    await events.publish_new_message(redis, message_payload(dialog, message))
