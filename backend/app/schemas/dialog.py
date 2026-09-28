"""会话与消息 schema。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import DialogChannel, DialogKind, MessageDirection, MessageStatus
from app.schemas.common import ORMModel


class DialogOut(ORMModel):
    id: uuid.UUID
    channel: DialogChannel
    channel_label: str = ""
    kind: DialogKind
    kind_label: str = ""
    account_id: Optional[uuid.UUID] = None
    account_label: Optional[str] = None
    bot_id: Optional[uuid.UUID] = None
    bot_label: Optional[str] = None
    tg_chat_id: int
    title: str = ""
    username: Optional[str] = None
    member_count: Optional[int] = None
    peer_display: str = ""
    unread_count: int = 0
    is_pinned: bool = False
    last_message_at: Optional[datetime] = None
    last_message_preview: str = ""


class MessageOut(ORMModel):
    id: uuid.UUID
    dialog_id: uuid.UUID
    channel: DialogChannel
    direction: MessageDirection
    direction_label: str = ""
    status: MessageStatus
    status_label: str = ""
    body: str = ""
    tg_message_id: Optional[int] = None
    sender_tg_id: Optional[int] = None
    sender_name: str = ""
    has_media: bool = False
    media_type: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None


class DialogListResponse(BaseModel):
    items: List[DialogOut]
    total: int
    page: int = 1
    page_size: int = 20


class MessageListResponse(BaseModel):
    items: List[MessageOut]
    total: int
    dialog: DialogOut
    has_more: bool = False


class MessagePageResponse(BaseModel):
    """跨会话的消息搜索分页（GET /api/messages），不带单个 dialog 上下文。"""

    items: List[MessageOut]
    total: int
    page: int = 1
    page_size: int = 20


class SendMessageRequest(BaseModel):
    dialog_id: uuid.UUID
    text: str = Field(min_length=1, max_length=4096)
    draft_id: Optional[uuid.UUID] = Field(
        default=None, description="由 AI 草稿发送时带上，发送后草稿标记为已发送"
    )


class SendMessageResponse(BaseModel):
    ok: bool = True
    message: MessageOut
    task_id: Optional[uuid.UUID] = None
    status: MessageStatus
    detail: str = ""


class SyncDialogsRequest(BaseModel):
    account_ids: Optional[List[uuid.UUID]] = None
    scope: str = Field(default="all", description="all | selected")


class SyncMessagesRequest(BaseModel):
    """路径带 dialog_id 时 body 里可以不再重复传（路由会以后者为准）。"""

    dialog_id: Optional[uuid.UUID] = None
    limit: int = Field(default=50, ge=1, le=500)


class DraftRequest(BaseModel):
    """路径带 dialog_id 时 body 里可以不再重复传。"""

    dialog_id: Optional[uuid.UUID] = None
    instruction: str = Field(default="", max_length=500)


class DraftOut(ORMModel):
    id: uuid.UUID
    dialog_id: uuid.UUID
    body: str
    status: str = "pending"
    model: str = ""
    created_at: Optional[datetime] = None
