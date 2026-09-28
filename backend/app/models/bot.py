"""自己的官方 Bot：Token 加密保存，转发目标与自动回复资料分开存。"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Enum, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk
from app.models.enums import RelayTargetKind


class Bot(Base, TimestampMixin):
    __tablename__ = "bots"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    bot_username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    bot_tg_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_secret: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    webhook_set_at: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # 转发目标（员工群）。relay_target_kind=group 时填群 chat_id
    relay_target_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    relay_target_kind: Mapped[RelayTargetKind] = mapped_column(
        Enum(
            RelayTargetKind,
            name="relay_target_kind",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=RelayTargetKind.group,
    )
    relay_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 官方 Bot 按自己的资料自动回复
    auto_reply_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    persona_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")
