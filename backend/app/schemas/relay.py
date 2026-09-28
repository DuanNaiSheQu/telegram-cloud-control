"""Bot 与转发规则 schema。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import RelayTargetKind
from app.schemas.common import ORMModel


class BotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    token: str = Field(min_length=20, description="BotFather 给的 Token，加密保存")
    relay_enabled: bool = False
    relay_target_chat_id: Optional[int] = None
    relay_target_kind: RelayTargetKind = RelayTargetKind.group
    auto_reply_enabled: bool = False
    persona_text: str = ""
    remark: str = ""


class BotUpdate(BaseModel):
    name: Optional[str] = None
    token: Optional[str] = None
    relay_enabled: Optional[bool] = None
    relay_target_chat_id: Optional[int] = None
    relay_target_kind: Optional[RelayTargetKind] = None
    auto_reply_enabled: Optional[bool] = None
    persona_text: Optional[str] = None
    remark: Optional[str] = None
    webhook_enabled: Optional[bool] = None


class BotOut(ORMModel):
    id: uuid.UUID
    name: str
    bot_username: Optional[str] = None
    bot_tg_id: Optional[int] = None
    token_masked: str = ""
    webhook_enabled: bool = True
    webhook_url: str = ""
    webhook_set_at: Optional[str] = None
    relay_enabled: bool = False
    relay_target_chat_id: Optional[int] = None
    relay_target_kind: RelayTargetKind = RelayTargetKind.group
    auto_reply_enabled: bool = False
    persona_text: str = ""
    remark: str = ""
    created_at: Optional[datetime] = None


class RelayRouteCreate(BaseModel):
    name: str = ""
    bot_id: uuid.UUID
    staff_chat_id: int
    staff_chat_title: str = ""
    target_kind: RelayTargetKind = RelayTargetKind.group
    account_id: Optional[uuid.UUID] = None
    dialog_id: Optional[uuid.UUID] = None
    enabled: bool = True
    remark: str = ""


class RelayRouteUpdate(BaseModel):
    name: Optional[str] = None
    bot_id: Optional[uuid.UUID] = None
    staff_chat_id: Optional[int] = None
    staff_chat_title: Optional[str] = None
    target_kind: Optional[RelayTargetKind] = None
    account_id: Optional[uuid.UUID] = None
    dialog_id: Optional[uuid.UUID] = None
    enabled: Optional[bool] = None
    remark: Optional[str] = None


class RelayRouteOut(ORMModel):
    id: uuid.UUID
    name: str = ""
    bot_id: uuid.UUID
    bot_name: Optional[str] = None
    bot_username: Optional[str] = None
    staff_chat_id: int
    staff_chat_title: str = ""
    target_kind: RelayTargetKind = RelayTargetKind.group
    account_id: Optional[uuid.UUID] = None
    account_label: Optional[str] = None
    dialog_id: Optional[uuid.UUID] = None
    dialog_title: Optional[str] = None
    enabled: bool = True
    remark: str = ""
    relayed_count: int = 0
    created_at: Optional[datetime] = None


class RelayLinkOut(ORMModel):
    """一条「原消息 ↔ 员工群里那条转发」。

    后四个字段不是表上的列，是列表页要用的上下文（由路由回填），
    否则「已转发记录」只能看到一串 ID，值班时没法判断转的是什么。
    """

    id: uuid.UUID
    route_id: Optional[uuid.UUID] = None
    message_id: uuid.UUID
    bot_id: uuid.UUID
    staff_chat_id: int
    staff_message_id: int
    created_at: Optional[datetime] = None

    origin_body: Optional[str] = None
    origin_sender_name: Optional[str] = None
    origin_dialog_title: Optional[str] = None
    account_label: Optional[str] = None
    origin_created_at: Optional[datetime] = None


class WebhookResult(BaseModel):
    ok: bool = True
    detail: str = ""
