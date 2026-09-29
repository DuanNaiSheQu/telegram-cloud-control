"""群情报采集：无感写入群档案、成员快照与入退群事件。

「无感」在这里是三件具体的事：
1. **只读**：只用 `GetFullChannel` / `GetParticipants` 这类读接口，不发消息、不点赞、不触发任何群内可见动作；
2. **事件驱动**：入群/退群靠事件回调被动记录，不轮询、不去猜；
3. **克制主动拉取**：成员名单按页拉、页间有间隔、每天有额度（复用 `services/throttle.py` 的节奏参数），
   大群不一次性拉全量——那是触发风控的典型动作。

本模块只负责「数据怎么进库 / 怎么更新」，Telegram 调用在 worker 侧（`worker/group_intel.py`）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GroupEvent, GroupMember, GroupProfile

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _as_aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------------- 群档案 ----------------

async def upsert_profile(
    session: AsyncSession,
    *,
    account_id: Optional[uuid.UUID],
    tg_chat_id: int,
    title: str = "",
    username: Optional[str] = None,
    kind: str = "group",
    member_count: Optional[int] = None,
    about: str = "",
    invite_link: Optional[str] = None,
    is_public: bool = False,
    is_restricted: bool = False,
    creator_tg_id: Optional[int] = None,
    tg_created_at: Optional[datetime] = None,
    source: str = "profile_sync",
    raw: Optional[dict] = None,
    dialog_id: Optional[uuid.UUID] = None,
    touch_collected_at: bool = True,
) -> GroupProfile:
    """写或更新群档案。同号同群只保留一行，重复采集只刷新字段。"""
    profile = await session.scalar(
        select(GroupProfile).where(
            GroupProfile.tg_chat_id == tg_chat_id,
            GroupProfile.account_id == account_id if account_id else GroupProfile.account_id.is_(None),
        )
    )
    if profile is None:
        profile = GroupProfile(account_id=account_id, tg_chat_id=tg_chat_id)
        try:
            # 用 SAVEPOINT 包住这一插：并发采集（profile_sync / participant_sync 同时跑）会双双
            # 查到空、再一起插，后到的撞唯一约束。只回滚这个点位，别把外层事务一起打挂——
            # 一旦打挂，后面所有写入都会 PendingRollbackError。
            async with session.begin_nested():
                session.add(profile)
        except IntegrityError:
            # 别人刚建了这行：回读它，继续走下面的字段更新
            profile = await session.scalar(
                select(GroupProfile).where(
                    GroupProfile.tg_chat_id == tg_chat_id,
                    GroupProfile.account_id == account_id if account_id else GroupProfile.account_id.is_(None),
                )
            )
            if profile is None:
                raise

    if title:
        profile.title = title[:255]
    if username is not None:
        profile.username = username
    if kind:
        profile.kind = kind
    if member_count is not None:
        profile.member_count = int(member_count)
    if about:
        profile.about = about[:4000]
    if invite_link is not None:
        profile.invite_link = invite_link[:255]
    profile.is_public = bool(is_public) or bool(username)
    profile.is_restricted = bool(is_restricted)
    if creator_tg_id is not None:
        profile.creator_tg_id = int(creator_tg_id)
    if tg_created_at is not None:
        profile.tg_created_at = _as_aware(tg_created_at)
    if dialog_id is not None:
        profile.dialog_id = dialog_id
    if source:
        profile.source = source
    if raw:
        profile.raw = {**(profile.raw or {}), **raw}
    if touch_collected_at:
        profile.collected_at = _now()
    await session.flush()
    return profile


def profile_fields_from_entity(entity: Any, full: Any = None) -> dict[str, Any]:
    """把 Telethon 的 Channel / Chat（+ GetFullChannel 结果）抽成档案字段。"""
    fields: dict[str, Any] = {
        "title": str(getattr(entity, "title", "") or ""),
        "username": getattr(entity, "username", None),
        "member_count": getattr(entity, "participants_count", None),
    }
    if isinstance(entity, type(None)):
        return fields

    name = type(entity).__name__.lower()
    if "channel" in name:
        fields["kind"] = "channel" if getattr(entity, "broadcast", False) else "megagroup"
    elif "chat" in name:
        fields["kind"] = "chat"
    fields["is_restricted"] = bool(getattr(entity, "restricted", False) or getattr(entity, "scam", False))

    full_chat = getattr(full, "full_chat", None) if full is not None else None
    if full_chat is not None:
        fields["about"] = str(getattr(full_chat, "about", "") or "")
        fields["creator_tg_id"] = getattr(full_chat, "creator_id", None)
        fields["member_count"] = getattr(full_chat, "participants_count", None) or fields["member_count"]
        fields["is_restricted"] = bool(getattr(full_chat, "restricted", False))
        created = getattr(full_chat, "date", None)
        if created is not None:
            fields["tg_created_at"] = created
        export_link = getattr(full_chat, "exported_invite", None)
        if export_link is not None:
            fields["invite_link"] = getattr(export_link, "link", None)
    return fields


# ---------------- 成员 ----------------

async def upsert_member(
    session: AsyncSession,
    *,
    profile: GroupProfile,
    tg_user_id: int,
    username: Optional[str] = None,
    display_name: str = "",
    is_bot: bool = False,
    is_premium: bool = False,
    is_admin: bool = False,
    status: str = "member",
    source: str = "participant_sync",
    joined_at: Optional[datetime] = None,
    bump_message: bool = False,
    raw: Optional[dict] = None,
) -> tuple[GroupMember, bool]:
    """写或更新成员。返回 (成员行, 是否新建)。"""
    member = await session.scalar(
        select(GroupMember).where(
            GroupMember.tg_chat_id == profile.tg_chat_id, GroupMember.tg_user_id == int(tg_user_id)
        )
    )
    created = member is None
    if member is None:
        member = GroupMember(
            group_id=profile.id,
            account_id=profile.account_id,
            tg_chat_id=profile.tg_chat_id,
            tg_user_id=int(tg_user_id),
        )
        try:
            async with session.begin_nested():
                session.add(member)
        except IntegrityError:
            # 并发采集同一成员：别人刚建了这行，回读它继续更新字段
            member = await session.scalar(
                select(GroupMember).where(
                    GroupMember.tg_chat_id == profile.tg_chat_id,
                    GroupMember.tg_user_id == int(tg_user_id),
                )
            )
            if member is None:
                raise
            created = False

    if username:
        member.username = username[:64]
    if display_name:
        member.display_name = display_name[:128]
    member.is_bot = bool(is_bot) or member.is_bot
    member.is_premium = bool(is_premium) or member.is_premium
    member.is_admin = bool(is_admin) or member.is_admin
    # 状态以最新事件为准：退群/被踢要覆盖成 left / kicked
    if status:
        member.status = status
    if source:
        member.source = source
    if joined_at is not None:
        member.joined_at = _as_aware(joined_at)
    member.last_seen_at = _now()
    if bump_message:
        member.message_count = int(member.message_count or 0) + 1
    if raw:
        member.raw = {**(member.raw or {}), **raw}
    await session.flush()
    return member, created


# ---------------- 事件 ----------------

async def record_event(
    session: AsyncSession,
    *,
    account_id: Optional[uuid.UUID],
    tg_chat_id: int,
    event_type: str,
    tg_user_id: Optional[int] = None,
    actor_tg_id: Optional[int] = None,
    user_display: str = "",
    username: Optional[str] = None,
    is_bot: bool = False,
    occurred_at: Optional[datetime] = None,
    source: str = "join_event",
    raw: Optional[dict] = None,
) -> Optional[GroupEvent]:
    """记一条入/退群流水。同一 (群, 人, 类型, 时间) 只留一条（Telegram 会补推同样的更新）。"""
    moment = _as_aware(occurred_at) or _now()
    existing = await session.scalar(
        select(GroupEvent).where(
            GroupEvent.tg_chat_id == tg_chat_id,
            GroupEvent.tg_user_id == tg_user_id,
            GroupEvent.event_type == event_type,
            GroupEvent.occurred_at == moment,
        )
    )
    if existing is not None:
        return None
    event = GroupEvent(
        account_id=account_id,
        tg_chat_id=int(tg_chat_id),
        tg_user_id=int(tg_user_id) if tg_user_id is not None else None,
        event_type=event_type,
        actor_tg_id=int(actor_tg_id) if actor_tg_id is not None else None,
        user_display=(user_display or "")[:128],
        username=username,
        is_bot=bool(is_bot),
        occurred_at=moment,
        source=source,
        raw=raw or {},
    )
    try:
        # SAVEPOINT 保护：并发采集同一事件时别人可能刚插过——撞了去重约束就按
        # 「已经记过」处理，别把外层事务一起打挂
        async with session.begin_nested():
            session.add(event)
    except IntegrityError:
        return None
    logger.info(
        "群事件入库",
        extra={
            "tg_chat_id": tg_chat_id,
            "tg_user_id": tg_user_id,
            "event_type": event_type,
            "actor_tg_id": actor_tg_id,
            "is_bot": bool(is_bot),
        },
    )
    return event


def describe_chat_action(
    *, user_joined: bool, user_added: bool, user_left: bool, user_kicked: bool
) -> Optional[str]:
    """Telethon ChatAction 的四个布尔 → 事件类型。"""
    if user_joined:
        return "join"
    if user_added:
        return "invite"
    if user_left:
        return "leave"
    if user_kicked:
        return "kick"
    return None


def member_status_for_event(event_type: str) -> str:
    """事件类型 → 成员状态。"""
    if event_type in ("leave",):
        return "left"
    if event_type in ("kick",):
        return "kicked"
    return "member"


def display_name_of(entity: Any) -> str:
    """用户实体 → 展示名（与 worker/handlers 的口径保持一致）。"""
    if entity is None:
        return ""
    title = getattr(entity, "title", None)
    if title:
        return str(title)
    parts = [getattr(entity, "first_name", None), getattr(entity, "last_name", None)]
    return " ".join(part for part in parts if part).strip() or (getattr(entity, "username", None) or "")


__all__ = [
    "describe_chat_action",
    "display_name_of",
    "member_status_for_event",
    "profile_fields_from_entity",
    "record_event",
    "upsert_member",
    "upsert_profile",
]
