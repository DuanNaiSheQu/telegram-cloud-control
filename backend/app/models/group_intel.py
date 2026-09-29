"""群情报：群档案、群成员、入退群事件流。

「无感采集」的数据底座——只在号**已经**在群里时被动记录：
- 入群/退群事件由 Worker 的事件回调捕获（不发言、不点赞、不做任何可见动作）；
- 群档案与成员名单按需主动拉取（只读接口 + 节流限速，避免触发风控）。

三张表的关系：`group_profiles` 是群主档（一号一群一行），
`group_members` 是成员快照（事件增量与主动同步两条来源），
`group_events` 是不可变的入/退群流水。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk

#: 采集来源（写进 source 字段，便于回溯这条数据怎么来的）
COLLECT_SOURCES = ("join_event", "participant_sync", "message", "manual", "profile_sync")
COLLECT_SOURCE_LABELS = {
    "join_event": "入群事件",
    "participant_sync": "成员同步",
    "message": "群内发言",
    "manual": "人工补录",
    "profile_sync": "群资料同步",
}

#: 事件类型（入群/退群/被踢/被邀请）
GROUP_EVENT_TYPES = ("join", "leave", "kick", "invite")
GROUP_EVENT_LABELS = {
    "join": "入群",
    "leave": "退群",
    "kick": "被移除",
    "invite": "被邀请入群",
}

#: 成员状态
MEMBER_STATUSES = ("member", "left", "kicked")


class GroupProfile(Base, TimestampMixin):
    """群档案：一号一群一行（同一个群被多个号采集时分别记）。"""

    __tablename__ = "group_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tg_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    dialog_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dialogs.id", ondelete="SET NULL"), nullable=True
    )
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # group / megagroup / channel / chat
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="group")
    member_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    about: Mapped[str] = mapped_column(Text, nullable=False, default="")
    invite_link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    creator_tg_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    tg_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 采集进度：档案什么时候采的、成员名单同步到多少人
    collected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    member_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    member_sampled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="profile_sync")
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("account_id", "tg_chat_id", name="uq_group_profiles_account_chat"),
        Index("ix_group_profiles_member_count", "member_count"),
    )


class GroupMember(Base, TimestampMixin):
    """群成员快照：唯一键是 (群, 用户)，反复采集只更新不重复。"""

    __tablename__ = "group_members"

    id: Mapped[uuid.UUID] = uuid_pk()
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("group_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tg_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="participant_sync")
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tg_chat_id", "tg_user_id", name="uq_group_members_chat_user"),
        Index("ix_group_members_chat_status", "tg_chat_id", "status"),
    )


class GroupEvent(Base, TimestampMixin):
    """入/退群流水（不可变）：谁在什么时候进/出了哪个群，被谁拉进来的。"""

    __tablename__ = "group_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tg_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    tg_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False, default="join", index=True)
    # 谁把他拉进来的（Telethon 的 added_by）；自加入时为空
    actor_tg_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    user_display: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="join_event")
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_group_events_chat_time", "tg_chat_id", "occurred_at"),
        # 同一个人同一时刻的同一类事件只记一次（Telegram 会补推更新）
        UniqueConstraint("tg_chat_id", "tg_user_id", "event_type", "occurred_at", name="uq_group_events_dedupe"),
    )


class KeywordWatch(Base, TimestampMixin):
    """关键词监听规则：群里有人聊到这些词就记下来并告警。

    为什么需要：私信/群发是「我找别人」，监听是「别人找我」——有人问「怎么开卡」时第一时间知道，
    比事后翻聊天记录有用得多。规则命中写进 `group_events`（event_type="keyword"），不另建流水表。
    """

    __tablename__ = "keyword_watches"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 关键词列表：命中任意一个即算命中（OR）
    keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # 生效范围：留空 = 所有已同步会话；填了就只看这些（tg_chat_id 列表）
    tg_chat_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # 用哪些号监听：留空 = 所有在线的号
    account_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    # 是否推送通知（页面铃铛）
    notify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ReplyRule(Base, TimestampMixin):
    """账号自动回复规则：收到消息命中关键词就自动回一句。

    与「关键词监听」的区别：监听只记录（给人看），回复规则会**真的发消息**——
    所以它带冷却时间（同一会话 N 秒内只回一次），避免刷屏或被判定成机器人；
    发出去的每条同样走账号的节流与每日配额，不会绕过防封机制。
    """

    __tablename__ = "reply_rules"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    reply_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 匹配方式：contains 包含 / exact 完全相等 / regex 正则
    match_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="contains")
    # 生效范围：private 仅私信 / group 仅群聊 / both 都回
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="private")
    account_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    # 同一会话的冷却秒数（0 = 不限制，但不建议）
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
