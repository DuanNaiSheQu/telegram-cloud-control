"""任务队列（Postgres 表）+ 账号租约。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk
from app.models.enums import TaskStatus, TaskType


def _enum(enum_cls, name: str):
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
    )


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = uuid_pk()
    type: Mapped[TaskType] = mapped_column(_enum(TaskType, "task_type"), nullable=False, index=True)
    status: Mapped[TaskStatus] = mapped_column(
        _enum(TaskStatus, "task_status"), nullable=False, default=TaskStatus.pending, index=True
    )

    # 用户号任务挂 account_id（Worker 执行）；Bot 任务挂 bot_id（API 执行）
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tg_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    bot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=True, index=True
    )
    dialog_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dialogs.id", ondelete="SET NULL"), nullable=True
    )

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")

    worker_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, unique=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_tasks_claim", "status", "next_run_at", "priority"),
        Index("ix_tasks_account_status", "account_id", "status"),
        Index("ix_tasks_bot_status", "bot_id", "status"),
    )


class Lease(Base):
    """账号租约：每个用户号同一时刻只属于一个 Worker。"""

    __tablename__ = "leases"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tg_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
