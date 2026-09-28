"""站内通知：把「失败任务、Worker 心跳丢失、账号异常、备份失败」汇成一条流。

通知是**聚合产物**，不是新的事实来源：真正的状态在 tasks / leases / tg_accounts 里，
`core.notifications.sync_notifications` 定期把这些事实映射成通知并靠 dedupe_key 去重，
页面只读这张表，不直接扫任务表。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk

#: 四类通知（与规划里的四条告警一一对应）
NOTIFICATION_KIND_LABELS = {
    "task_failed": "任务失败",
    "worker_lost": "Worker 心跳丢失",
    "account_abnormal": "账号异常",
    "backup_failed": "备份失败",
}

#: 前端按这个决定颜色
NOTIFICATION_LEVELS = ("info", "warning", "error", "success")

#: 每类通知默认等级
NOTIFICATION_KIND_LEVELS = {
    "task_failed": "error",
    "worker_lost": "warning",
    "account_abnormal": "warning",
    "backup_failed": "error",
}


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = uuid_pk()

    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: 点击跳转的前端路由，如 /accounts/<id>、/tasks?status=failed
    link: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tg_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    bot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bots.id", ondelete="CASCADE"), nullable=True, index=True
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    worker_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    detail: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    #: 同一件事只通知一次（如 task_failed:<task_id>）；重复产生时走 ON CONFLICT DO NOTHING
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, unique=True)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    read_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (Index("ix_notifications_read_created", "is_read", "created_at"),)
