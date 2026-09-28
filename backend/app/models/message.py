"""消息：方向、正文、Telegram 消息 ID、发送人。"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk
from app.models.enums import DialogChannel, MessageDirection, MessageStatus


def _enum(enum_cls, name: str):
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
    )


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    dialog_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dialogs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[DialogChannel] = mapped_column(
        _enum(DialogChannel, "dialog_channel"), nullable=False
    )
    direction: Mapped[MessageDirection] = mapped_column(
        _enum(MessageDirection, "message_direction"), nullable=False, index=True
    )
    status: Mapped[MessageStatus] = mapped_column(
        _enum(MessageStatus, "message_status"), nullable=False, default=MessageStatus.received
    )

    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tg_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    sender_tg_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    reply_to_tg_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    has_media: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    media_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    raw: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)

    # 谁触发的（员工确认发送时记录操作者）
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index(
            "uq_messages_dialog_tg_message",
            "dialog_id",
            "tg_message_id",
            unique=True,
            postgresql_where=text("tg_message_id IS NOT NULL"),
        ),
        Index("ix_messages_dialog_created", "dialog_id", "created_at"),
    )
