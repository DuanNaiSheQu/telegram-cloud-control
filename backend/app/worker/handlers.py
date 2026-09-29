"""NewMessage 事件 → 入库（services.inbound）→ 推页面 → 对 incoming 写转发任务。

事件来自持有租约的那个号，`event.message.out` 决定方向：
收到的算 incoming，本号从手机发出的算 outgoing（status=sent）。
去重靠 `ingest_message` 里的 `tg_message_id`。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Tuple

from telethon.tl import types as tl_types

from app.db import session_scope
from app.models import Dialog, DialogChannel, DialogKind, Message, MessageDirection, MessageStatus
from app.services.keyword_watch import load_rules as keyword_load_rules
from app.services.keyword_watch import scan as keyword_scan
from app.services.keyword_watch import record_hit as record_keyword_hit
from app.services.inbound import ingest_message, publish_message
from app.services.relay import enqueue_relays

logger = logging.getLogger(__name__)

#: 只写少量元数据，不把整个 Telethon 对象塞进 raw
_RAW_KEYS = ("post", "via_bot_id", "grouped_id", "media_ttl", "noforwards")


def display_name_of_entity(entity: Any) -> str:
    """用户 / 群 / 频道对象 → 展示名。"""
    if entity is None:
        return ""
    title = getattr(entity, "title", None)
    if title:
        return str(title)
    parts = [getattr(entity, "first_name", None), getattr(entity, "last_name", None)]
    name = " ".join(part for part in parts if part).strip()
    if name:
        return name
    return getattr(entity, "username", None) or ""


def dialog_kind_of(*, chat: Any = None, is_private: bool = False, is_group: bool = False) -> DialogKind:
    """群 / 频道算 group，其余算 private。"""
    if chat is not None:
        if isinstance(chat, (tl_types.Chat, tl_types.ChatForbidden, tl_types.Channel, tl_types.ChannelForbidden)):
            return DialogKind.group
        if isinstance(chat, (tl_types.User, tl_types.UserEmpty)):
            return DialogKind.private
    return DialogKind.group if is_group else DialogKind.private


def media_type_of(message: Any) -> Optional[str]:
    """按 media 类型给一个短标签，没有媒体返回 None。"""
    try:
        if message is None or message.media is None:
            return None
        if isinstance(message.media, tl_types.MessageMediaWebPage):
            return None  # 链接预览不算媒体
        if message.photo is not None:
            return "photo"
        if message.sticker is not None:
            return "sticker"
        if message.gif is not None:
            return "gif"
        if message.video_note is not None:
            return "video_note"
        if message.video is not None:
            return "video"
        if message.voice is not None:
            return "voice"
        if message.audio is not None:
            return "audio"
        if message.document is not None:
            return "document"
        if message.contact is not None:
            return "contact"
        if message.geo is not None:
            return "geo"
        if message.poll is not None:
            return "poll"
        if getattr(message, "action", None) is not None:
            return "service"
        return "other"
    except Exception:  # noqa: BLE001 - 媒体判定不能影响入库
        return None


def raw_meta_of(message: Any) -> dict:
    """少量元数据：够排查，不占空间。"""
    raw: dict = {}
    for key in _RAW_KEYS:
        value = getattr(message, key, None)
        if value not in (None, False, 0):
            raw[key] = value if isinstance(value, (int, str, bool)) else str(value)
    if getattr(message, "fwd_from", None) is not None:
        raw["forwarded"] = True
    date = getattr(message, "date", None)
    if isinstance(date, datetime):
        raw["date"] = date.astimezone(timezone.utc).isoformat()
    return raw


@dataclass(slots=True)
class MessageData:
    """一条待入库消息的全部字段（事件与历史同步共用）。"""

    tg_chat_id: int
    kind: DialogKind = DialogKind.private
    title: str = ""
    username: Optional[str] = None
    peer_display: str = ""
    member_count: Optional[int] = None
    body: str = ""
    tg_message_id: Optional[int] = None
    direction: MessageDirection = MessageDirection.incoming
    status: MessageStatus = MessageStatus.received
    sender_tg_id: Optional[int] = None
    sender_name: str = ""
    reply_to_tg_message_id: Optional[int] = None
    has_media: bool = False
    media_type: Optional[str] = None
    raw: Optional[dict] = None

    @property
    def is_outgoing(self) -> bool:
        """本号自己发出的消息。"""
        return self.direction == MessageDirection.outgoing


def message_data_from_telethon(
    *,
    message: Any,
    chat: Any = None,
    tg_chat_id: Optional[int] = None,
    kind: Optional[DialogKind] = None,
    title: Optional[str] = None,
    username: Optional[str] = None,
    peer_display: Optional[str] = None,
    member_count: Optional[int] = None,
    sender_name: str = "",
) -> MessageData:
    """Telethon 消息 → MessageData；显式传入的会话信息优先（历史同步用）。"""
    chat_id = tg_chat_id
    if chat_id is None:
        chat_id = getattr(message, "chat_id", None)
    if chat_id is None and chat is not None:
        chat_id = getattr(chat, "id", None)
    resolved_kind = kind or dialog_kind_of(
        chat=chat,
        is_private=bool(getattr(message, "is_private", False)),
        is_group=bool(getattr(message, "is_group", False)),
    )
    chat_title = title if title is not None else display_name_of_entity(chat)
    resolved_username = username if username is not None else getattr(chat, "username", None)
    resolved_member_count = (
        member_count if member_count is not None else getattr(chat, "participants_count", None)
    )
    peer = peer_display if peer_display is not None else chat_title
    outgoing = bool(getattr(message, "out", False))
    body = getattr(message, "message", None) or ""
    media_type = media_type_of(message)
    return MessageData(
        tg_chat_id=int(chat_id or 0),
        kind=resolved_kind,
        title=chat_title or "",
        username=resolved_username or None,
        peer_display=peer or chat_title or "",
        member_count=resolved_member_count,
        body=body,
        tg_message_id=getattr(message, "id", None),
        direction=MessageDirection.outgoing if outgoing else MessageDirection.incoming,
        status=MessageStatus.sent if outgoing else MessageStatus.received,
        sender_tg_id=getattr(message, "sender_id", None),
        # 发送者显示名：显式传入的优先；为空时从消息对象自己榨一次——
        # 实时事件走 event.sender，历史同步 / 实体未缓存时这里能兜住，
        # 否则群聊里别人发的消息在页面上只会显示「对方」，看不出是谁说的。
        sender_name=sender_name or _sender_name_from_message(message),
        reply_to_tg_message_id=getattr(message, "reply_to_msg_id", None),
        has_media=media_type is not None and media_type != "service",
        media_type=media_type,
        raw=raw_meta_of(message),
    )


async def persist_message(
    session: Any, *, account_id: uuid.UUID, data: MessageData, count_unread: bool = True
) -> Tuple[Dialog, Message, bool]:
    """写一条用户号消息（tg_message_id 去重），返回 (会话, 消息, 是否新建)。

    count_unread=False 用于补历史消息：老消息不该点亮未读角标。
    """
    return await ingest_message(
        session,
        channel=DialogChannel.user_account,
        account_id=account_id,
        direction=data.direction,
        status=data.status,
        tg_chat_id=data.tg_chat_id,
        kind=data.kind,
        title=data.title,
        username=data.username,
        peer_display=data.peer_display,
        member_count=data.member_count,
        body=data.body,
        tg_message_id=data.tg_message_id,
        sender_tg_id=data.sender_tg_id,
        sender_name=data.sender_name,
        reply_to_tg_message_id=data.reply_to_tg_message_id,
        has_media=data.has_media,
        media_type=data.media_type,
        raw=data.raw,
        count_unread=count_unread,
    )


#: 关键词规则缓存：消息来了直接用内存里的规则匹配，每 60 秒回库刷一次。
#: 改动最多滞后一分钟生效，换来的是「每条消息零 DB 查询」。
_KEYWORD_CACHE: dict[str, Any] = {"at": 0.0, "rules": []}
_KEYWORD_TTL = 60.0


async def _keyword_rules(session: Any) -> list[dict]:
    import time

    now = time.monotonic()
    if now - float(_KEYWORD_CACHE.get("at") or 0) < _KEYWORD_TTL:
        return list(_KEYWORD_CACHE.get("rules") or [])
    try:
        rules = await keyword_load_rules(session)
    except Exception:  # noqa: BLE001 - 读规则失败不该影响消息入库
        logger.debug("读取关键词规则失败，沿用上一份缓存")
        return list(_KEYWORD_CACHE.get("rules") or [])
    _KEYWORD_CACHE["at"] = now
    _KEYWORD_CACHE["rules"] = rules
    return rules


async def handle_telethon_message(
    *,
    worker_id: str,
    account_id: uuid.UUID,
    redis: Any,
    message: Any,
    chat: Any = None,
    sender_name: str = "",
) -> Optional[Tuple[Dialog, Message, bool]]:
    """一条事件消息的完整处理：入库 → 推页面 → 收到的消息写转发任务。"""
    data = message_data_from_telethon(message=message, chat=chat, sender_name=sender_name)
    if not data.tg_chat_id:
        logger.warning(
            "消息缺少 chat_id，跳过",
            extra={"worker_id": worker_id, "account_id": str(account_id), "tg_message_id": data.tg_message_id},
        )
        return None

    async with session_scope() as session:
        dialog, row, created = await persist_message(session, account_id=account_id, data=data)
        if not created:
            return dialog, row, False
        await publish_message(redis, dialog, row)
        if row.direction == MessageDirection.incoming:
            tasks = await enqueue_relays(session, dialog=dialog, message=row)
            if tasks:
                logger.info(
                    "已写转发任务",
                    extra={
                        "worker_id": worker_id,
                        "account_id": str(account_id),
                        "dialog_id": str(dialog.id),
                        "message_id": str(row.id),
                        "tasks": len(tasks),
                    },
                )
        # 关键词监听：有人聊到规则里的词就记一条事件（与入退群流水同一时间线）
        try:
            rules = await _keyword_rules(session)
            if rules:
                hits = keyword_scan(
                    rules,
                    tg_chat_id=dialog.tg_chat_id,
                    account_id=str(account_id),
                    text=row.body or "",
                )
                for rule, keyword in hits:
                    await record_keyword_hit(
                        session,
                        account_id=account_id,
                        tg_chat_id=dialog.tg_chat_id,
                        tg_user_id=row.sender_tg_id,
                        user_display=row.sender_name or "",
                        keyword=keyword,
                        text=row.body or "",
                        rule_id=rule.get("id"),
                        rule_name=rule.get("name") or "",
                    )
                    if rule.get("notify"):
                        await publish_keyword_notice(
                            redis,
                            rule_name=rule.get("name") or "",
                            keyword=keyword,
                            chat_title=dialog.title or "",
                            sender=row.sender_name or "",
                            text=(row.body or "")[:200],
                        )
        except Exception:  # noqa: BLE001 - 监听失败不能影响消息入库
            logger.debug("关键词监听处理失败", exc_info=True)
        logger.info(
            "新消息已入库",
            extra={
                "worker_id": worker_id,
                "account_id": str(account_id),
                "dialog_id": str(dialog.id),
                "message_id": str(row.id),
                "direction": row.direction.value,
                "tg_message_id": row.tg_message_id,
            },
        )
        return dialog, row, True


async def resolve_chat(event: Any) -> Any:
    """取事件里的 chat 实体；拿不到就返回 None（标题退化成 chat_id）。"""
    chat = getattr(event, "chat", None)
    if chat is not None:
        return chat
    try:
        return await event.get_chat()
    except Exception:  # noqa: BLE001 - 拿不到实体不影响入库
        return None


def sender_name_of(event: Any) -> str:
    """群消息里的发送人显示名；取不到就算了。"""
    sender = getattr(event, "sender", None)
    if sender is None:
        return ""
    return display_name_of_entity(sender)


def make_new_message_handler(
    *, worker_id: str, account_id: uuid.UUID, redis: Any
) -> Callable[[Any], Awaitable[None]]:
    """给一个号造 NewMessage 处理器；兜住所有异常，不打挂 Worker。"""

    async def _handler(event: Any) -> None:
        try:
            message = getattr(event, "message", None)
            if message is None:
                return
            chat = await resolve_chat(event)
            await handle_telethon_message(
                worker_id=worker_id,
                account_id=account_id,
                redis=redis,
                message=message,
                chat=chat,
                sender_name=sender_name_of(event),
            )
        except Exception:  # noqa: BLE001 - 单条事件失败不能影响这个号的其它消息
            logger.exception(
                "处理新消息事件失败",
                extra={"worker_id": worker_id, "account_id": str(account_id)},
            )

    return _handler


__all__ = [
    "MessageData",
    "dialog_kind_of",
    "display_name_of_entity",
    "handle_telethon_message",
    "make_new_message_handler",
    "media_type_of",
    "message_data_from_telethon",
    "persist_message",
    "raw_meta_of",
    "resolve_chat",
]
