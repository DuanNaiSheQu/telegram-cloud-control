"""账号详情聚合 schema：前端右侧抽屉一次拉完所需数据。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.account import AccountOut, GroupOut, ProxyOut
from app.schemas.audit import AuditOut
from app.schemas.dialog import DialogOut, MessageOut
from app.schemas.task import TaskOut


class LeaseDetail(BaseModel):
    """账号租约。`active=false` 表示租约已过期（页面不该显示「在线」）。"""

    worker_id: Optional[str] = None
    lease_until: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    active: bool = False


class DialogStats(BaseModel):
    total: int = 0
    group: int = 0
    private: int = 0
    unread: int = 0


class TaskStats(BaseModel):
    pending: int = 0
    pending_confirmation: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0


class AccountOverviewOut(BaseModel):
    """一个号的全部上下文：账号本身 + 分组 / 代理 + 租约 + 统计 + 最近若干行明细。"""

    account: AccountOut
    group: Optional[GroupOut] = None
    proxy: Optional[ProxyOut] = None
    lease: Optional[LeaseDetail] = None
    dialog_stats: DialogStats = Field(default_factory=DialogStats)
    task_stats: TaskStats = Field(default_factory=TaskStats)
    recent_dialogs: List[DialogOut] = Field(default_factory=list, description="最近 20 个会话")
    recent_messages: List[MessageOut] = Field(default_factory=list, description="最近 50 条消息（按时间倒序）")
    recent_tasks: List[TaskOut] = Field(default_factory=list, description="最近 20 条任务")
    recent_audit: List[AuditOut] = Field(default_factory=list, description="最近 20 条审计")
    generated_at: Optional[datetime] = None
