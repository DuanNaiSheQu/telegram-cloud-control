"""用户号：脱敏展示、状态、分组、代理、加密会话。"""

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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk
from app.models.enums import AccountStatus, CurrentTask


def _enum(enum_cls, name: str):
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
    )


class AccountGroup(Base, TimestampMixin):
    """账号分组：内部标签，用来把号分给同事。"""

    __tablename__ = "account_groups"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class Proxy(Base, TimestampMixin):
    """账号固定出站地址。"""

    __tablename__ = "proxies"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scheme: Mapped[str] = mapped_column(String(16), nullable=False, default="socks5")
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    password_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    @property
    def endpoint(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"


class TgAccount(Base, TimestampMixin):
    """一个用户号。会话串加密后存这里，库里不存明文密钥。"""

    __tablename__ = "tg_accounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    phone_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phone_masked: Mapped[str] = mapped_column(String(32), nullable=False, default="未知")
    tg_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    # 号龄（天），由首次登录时间推算
    age_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    group_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_groups.id", ondelete="SET NULL"), nullable=True
    )
    proxy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proxies.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[AccountStatus] = mapped_column(
        _enum(AccountStatus, "account_status"), nullable=False, default=AccountStatus.pending, index=True
    )
    status_reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    current_task: Mapped[CurrentTask] = mapped_column(
        _enum(CurrentTask, "current_task"), nullable=False, default=CurrentTask.idle
    )

    session_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Telegram 首次成功登录时间，用于号龄
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    group: Mapped[Optional[AccountGroup]] = relationship(lazy="joined")
    proxy: Mapped[Optional[Proxy]] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("tg_user_id", name="uq_tg_accounts_tg_user_id"),
    )


class AccountAssignment(Base, TimestampMixin):
    """谁可以操作哪个号。"""

    __tablename__ = "account_assignments"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tg_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "account_id", name="uq_account_assignments_user_account"),
    )
