"""任务中心 schema。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import TaskStatus, TaskType
from app.schemas.common import ORMModel


class TaskOut(ORMModel):
    id: uuid.UUID
    type: TaskType
    type_label: str = ""
    status: TaskStatus
    status_label: str = ""
    account_id: Optional[uuid.UUID] = None
    account_label: Optional[str] = None
    bot_id: Optional[uuid.UUID] = None
    bot_label: Optional[str] = None
    dialog_id: Optional[uuid.UUID] = None
    payload: dict = {}
    result: Optional[Any] = None
    priority: int = 100
    attempts: int = 0
    max_attempts: int = 5
    error: str = ""
    worker_id: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_by_name: Optional[str] = None
    next_run_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class TaskListResponse(BaseModel):
    items: List[TaskOut]
    total: int
    page: int = 1
    page_size: int = 20
    counts: dict = Field(default_factory=dict, description="按状态汇总")


class TaskCreateRequest(BaseModel):
    type: TaskType
    account_id: Optional[uuid.UUID] = None
    bot_id: Optional[uuid.UUID] = None
    dialog_id: Optional[uuid.UUID] = None
    payload: dict = Field(default_factory=dict)
    priority: int = 100


class TaskActionResponse(BaseModel):
    ok: bool = True
    task: Optional[TaskOut] = None
    message: str = ""


# ---------------- 批量重试 ----------------

class TaskBulkRetryRequest(BaseModel):
    """批量重试：一次最多 200 条，逐条给结果（不因为某条不可重试就整体失败）。"""

    task_ids: List[uuid.UUID] = Field(default_factory=list, max_length=200, description="最多 200 个任务 id")


class TaskBulkRetryItem(BaseModel):
    task_id: uuid.UUID
    ok: bool = False
    message: str = ""


class TaskBulkRetryResponse(BaseModel):
    ok: bool = True
    requested: int = 0
    succeeded: int = 0
    failed: int = 0
    results: List[TaskBulkRetryItem] = Field(default_factory=list)
