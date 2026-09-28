"""群情报 schema：采集请求、群档案、成员、事件流。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.bulk import BulkScopeRequest
from app.schemas.common import ORMModel


class GroupCollectRequest(BulkScopeRequest):
    """批量采集请求：对选中的号，采它们已加入的群。"""

    dialog_ids: Optional[List[uuid.UUID]] = Field(
        default=None, description="只采这些会话（已同步的群）；不给就采该号已加入的全部群"
    )
    limit_groups: int = Field(default=30, ge=1, le=300, description="每个号最多采多少个群")
    sample_members: int = Field(
        default=0, ge=0, le=500, description="每个群顺带抽样多少个成员；0 表示只采群档案"
    )
    with_members: bool = Field(
        default=False, description="是否额外为每个群排队一条「采集群成员」任务（用更大额度拉名单）"
    )
    member_limit: int = Field(default=200, ge=1, le=500, description="with_members 时每个群采多少成员")


class GroupProfileOut(ORMModel):
    id: uuid.UUID
    account_id: Optional[uuid.UUID] = None
    dialog_id: Optional[uuid.UUID] = None
    tg_chat_id: int
    title: str = ""
    username: Optional[str] = None
    kind: str = "group"
    member_count: Optional[int] = None
    about: str = ""
    invite_link: Optional[str] = None
    is_public: bool = False
    is_restricted: bool = False
    creator_tg_id: Optional[int] = None
    tg_created_at: Optional[datetime] = None
    collected_at: Optional[datetime] = None
    member_synced_at: Optional[datetime] = None
    member_sampled: int = 0
    source: str = "profile_sync"


class GroupProfileListResponse(BaseModel):
    items: List[GroupProfileOut]
    total: int
    page: int = 1
    page_size: int = 20
    # 汇总：群数、成员总数（已采集到的）、今日入群事件数
    summary: Dict[str, Any] = Field(default_factory=dict)


class GroupMemberOut(ORMModel):
    id: uuid.UUID
    group_id: uuid.UUID
    tg_chat_id: int
    tg_user_id: int
    username: Optional[str] = None
    display_name: str = ""
    is_bot: bool = False
    is_premium: bool = False
    is_admin: bool = False
    status: str = "member"
    source: str = "participant_sync"
    joined_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    message_count: int = 0


class GroupMemberListResponse(BaseModel):
    items: List[GroupMemberOut]
    total: int
    page: int = 1
    page_size: int = 20
    counts: Dict[str, int] = Field(default_factory=dict)


class GroupEventOut(ORMModel):
    id: uuid.UUID
    account_id: Optional[uuid.UUID] = None
    tg_chat_id: int
    tg_user_id: Optional[int] = None
    event_type: str
    event_type_label: str = ""
    actor_tg_id: Optional[int] = None
    user_display: str = ""
    username: Optional[str] = None
    is_bot: bool = False
    occurred_at: Optional[datetime] = None
    group_title: Optional[str] = None


class GroupEventListResponse(BaseModel):
    items: List[GroupEventOut]
    total: int
    page: int = 1
    page_size: int = 50
    counts: Dict[str, int] = Field(default_factory=dict)


class GroupIntelStats(BaseModel):
    groups: int = 0
    members: int = 0
    bots: int = 0
    events_today: int = 0
    joins_today: int = 0
    leaves_today: int = 0
    watching: bool = True
