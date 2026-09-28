"""转发：用哪个 Bot、转发到哪个员工聊天，以及原消息与员工群那条转发的对应。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk
from app.models.enums import DraftStatus, RelayTargetKind


def _enum(enum_cls, name: str):
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
    )


class RelayRoute(Base, TimestampMixin):
    """一条转发规则：某个 Bot 把哪些来源的消息发到哪个员工聊天。"""

    __tablename__ = "relay_routes"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    staff_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    staff_chat_title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    target_kind: Mapped[RelayTargetKind] = mapped_column(
        _enum(RelayTargetKind, "relay_target_kind"), nullable=False, default=RelayTargetKind.group
    )

    # 来源过滤：为空表示不过滤
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tg_accounts.id", ondelete="CASCADE"), nullable=True
    )
    dialog_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dialogs.id", ondelete="CASCADE"), nullable=True
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class RelayLink(Base, TimestampMixin):
    """原消息 ID 对应员工群里那条转发，用于把员工回复送回原会话。"""

    __tablename__ = "relay_links"

    id: Mapped[uuid.UUID] = uuid_pk()
    route_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("relay_routes.id", ondelete="SET NULL"), nullable=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=False
    )
    staff_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    staff_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        Index(
            "uq_relay_links_staff_message",
            "staff_chat_id",
            "staff_message_id",
            unique=True,
        ),
    )


class ReplyDraft(Base, TimestampMixin):
    """未发送的 AI 草稿。只停在输入框，员工点发送才出去。"""

    __tablename__ = "reply_drafts"

    id: Mapped[uuid.UUID] = uuid_pk()
    dialog_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dialogs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DraftStatus] = mapped_column(
        _enum(DraftStatus, "draft_status"), nullable=False, default=DraftStatus.pending, index=True
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    sent_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    sent_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
