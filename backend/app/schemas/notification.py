"""站内通知 schema：失败任务 / Worker 心跳丢失 / 账号异常 / 备份失败。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class NotificationOut(ORMModel):
    """一条通知。`read` 对应表里的 is_read（前端字段名按 `read`）。"""

    id: uuid.UUID
    kind: str
    kind_label: str = ""
    level: str = "warning"
    title: str = ""
    body: str = ""
    link: str = ""
    account_id: Optional[uuid.UUID] = None
    account_label: Optional[str] = None
    bot_id: Optional[uuid.UUID] = None
    task_id: Optional[uuid.UUID] = None
    worker_id: Optional[str] = None
    detail: Optional[dict] = None
    read: bool = False
    read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    items: List[NotificationOut] = Field(default_factory=list)
    total: int = 0
    unread: int = 0
    page: int = 1
    page_size: int = 20
    counts_by_kind: Dict[str, int] = Field(default_factory=dict, description="未读通知按类型计数（铃铛角标）")


class NotificationReadResponse(BaseModel):
    ok: bool = True
    message: str = ""
    notification: Optional[NotificationOut] = None


class NotificationReadAllResponse(BaseModel):
    ok: bool = True
    message: str = ""
    marked: int = 0
