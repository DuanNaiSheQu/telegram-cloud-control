"""群发定时计划：到点自动把一批群发 / 私信排进任务队列。

运营在「触达中心」勾上「定时队列」时写一条计划：每隔 `interval_minutes` 按 `payload`
提交一次批量动作，页面下方能看到下次执行时间、已跑次数，随时可暂停或删掉。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class CampaignSchedule(Base, TimestampMixin):
    __tablename__ = "campaign_schedules"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: 计划名（页面上显示；没给就用「动作 + 目标」拼一个）
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    #: 动作：bulk_pm / group_broadcast / material_send
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    #: 原始提交参数（目标、文本池、账号范围…）：到点直接按它展开「一号一任务」
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: 间隔（分钟）：跑完一次后顺延这么久
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    #: 发送时间窗，格式 "09:00-22:00"（与任务侧 send_window 同一语义，空 = 不限）
    send_window: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: 下一次该跑的时间
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    #: 累计跑了多少次（含手动「立即执行」）
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: 最近一次提交失败的原因（没有可用账号之类）
    last_error: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
