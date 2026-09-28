"""审计与工作台 schema。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel

from app.schemas.common import ORMModel


class AuditOut(ORMModel):
    id: uuid.UUID
    action: str
    action_label: str = ""
    user_id: Optional[uuid.UUID] = None
    user_name: Optional[str] = None
    account_id: Optional[uuid.UUID] = None
    account_label: Optional[str] = None
    bot_id: Optional[uuid.UUID] = None
    target_type: str = ""
    target_id: str = ""
    detail: Optional[Any] = None
    client_ip: str = ""
    created_at: Optional[datetime] = None


class AuditListResponse(BaseModel):
    items: List[AuditOut]
    total: int
    page: int = 1
    page_size: int = 20


class WorkerStatus(BaseModel):
    worker_id: str
    last_heartbeat: Optional[datetime] = None
    online_accounts: int = 0
    leased_accounts: int = 0
    stale: bool = False
    source: str = "redis"


class FailedTaskOut(ORMModel):
    id: uuid.UUID
    type: str
    type_label: str = ""
    account_id: Optional[uuid.UUID] = None
    account_label: Optional[str] = None
    error: str = ""
    attempts: int = 0
    max_attempts: int = 5
    created_at: Optional[datetime] = None


class DashboardOut(BaseModel):
    total_accounts: int = 0
    online_accounts: int = 0
    abnormal_accounts: int = 0
    leased_accounts: int = 0
    total_dialogs: int = 0
    unread_dialogs: int = 0
    total_bots: int = 0
    tasks_pending: int = 0
    tasks_running: int = 0
    tasks_failed: int = 0
    tasks_overdue: int = 0
    tasks_stuck: int = 0
    workers: List[WorkerStatus] = []
    recent_failures: List[FailedTaskOut] = []
    generated_at: Optional[datetime] = None
