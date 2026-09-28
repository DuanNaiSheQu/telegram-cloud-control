"""会话：用户号的群聊/私信，以及 Bot 收到的私信与它所在群的消息。"""

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
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk
from app.models.enums import DialogChannel, DialogKind


def _enum(enum_cls, name: str):
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
    )


class Dialog(Base, TimestampMixin):
    __tablename__ = "dialogs"

    id: Mapped[uuid.UUID] = uuid_pk()

    # 来源：用户号（Worker 持有租约）或官方 Bot（API Webhook）
    channel: Mapped[DialogChannel] = mapped_column(
        _enum(DialogChannel, "dialog_channel"), nullable=False, index=True
    )
    kind: Mapped[DialogKind] = mapped_column(
        _enum(DialogKind, "dialog_kind"), nullable=False, default=DialogKind.private, index=True
    )

    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tg_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    bot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Telegram 侧的 peer / chat id
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    member_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 对方是谁（私信时用于来源标注）
    peer_display: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_message_preview: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    account = relationship("TgAccount", lazy="selectin")
    bot = relationship("Bot", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("account_id", "tg_chat_id", name="uq_dialogs_account_chat"),
        UniqueConstraint("bot_id", "tg_chat_id", name="uq_dialogs_bot_chat"),
    )
