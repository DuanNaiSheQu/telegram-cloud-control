"""群情报 schema：采集请求、群档案、成员、事件流。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

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


class CollectLinkRequest(BulkScopeRequest):
    """按群链接采集：粘贴若干链接，自动解析群、可选加入、采档案与群员。"""

    links: List[str] = Field(description="群链接，每行一个：t.me/xxx、t.me/+hash、@username、数字 ID 都支持")
    join_if_missing: bool = Field(
        default=False,
        description="号不在群里时是否自动加入（加入会产生一条入群系统消息，且按高风险动作计费）",
    )
    leave_after: bool = Field(default=False, description="采完就退出——留人不留痕，适合一次性采集号")
    member_limit: int = Field(default=200, ge=0, le=500, description="每群采多少成员；0 表示只采群档案")

    @model_validator(mode="after")
    def _check_links(self):
        cleaned = [str(item).strip() for item in (self.links or []) if str(item).strip()]
        cleaned = list(dict.fromkeys(cleaned))
        if not cleaned:
            raise ValueError("至少给一个群链接")
        if len(cleaned) > 50:
            raise ValueError("单次最多提交 50 个链接，请分批")
        self.links = cleaned
        return self


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


class CollectMessagesRequest(BaseModel):
    """采集群内对话：成员名单被群主隐藏时的替代方案（对话照样能读）。"""

    profile_id: uuid.UUID = Field(description="群档案 id")
    account_ids: Optional[List[uuid.UUID]] = Field(default=None, description="执行账号（留空按 scope）")
    scope: str = Field(default="selected", description="selected / all / group:<分组ID>")
    days: int = Field(default=7, ge=1, le=365, description="只扫最近多少天的消息")
    exclude_admins: bool = Field(default=False, description="跳过管理员的发言")
    exclude_bots: bool = Field(default=True, description="跳过机器人")
    limit: int = Field(default=1000, ge=10, le=5000, description="最多扫多少条消息")
    keywords: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="只捞聊到这些词的人（留空=全量扫；命中走 Telegram 服务端搜索，比本地过滤准）",
    )


class InspectGroupsRequest(BaseModel):
    """筛群：批量体检群链接（只读）。"""

    links: List[str] = Field(default_factory=list, min_length=1, max_length=200, description="群链接 / @用户名，一行一个")
    account_id: Optional[uuid.UUID] = Field(default=None, description="用哪个号体检（留空自动挑一个可用的）")
    min_interval: float = Field(default=2.0, ge=0.5, le=30, description="每条之间最小间隔（秒）")
    max_interval: float = Field(default=6.0, ge=0.5, le=60, description="最大间隔（秒）")


class KeywordWatchRequest(BaseModel):
    """新建关键词监听规则。"""

    name: str = Field(default="", max_length=64, description="规则名（留空自动取前几个词）")
    keywords: List[str] = Field(default_factory=list, description="关键词，命中任意一个即记录")
    tg_chat_ids: List[int] = Field(default_factory=list, description="只监听这些群；留空 = 全部")
    account_ids: List[uuid.UUID] = Field(default_factory=list, description="只用这些号监听；留空 = 全部在线号")
    enabled: bool = Field(default=True, description="是否启用")
    notify: bool = Field(default=True, description="命中时推通知")


class KeywordWatchUpdate(BaseModel):
    """改规则：只传要改的字段。"""

    name: Optional[str] = None
    keywords: Optional[List[str]] = None
    tg_chat_ids: Optional[List[int]] = None
    account_ids: Optional[List[uuid.UUID]] = None
    enabled: Optional[bool] = None
    notify: Optional[bool] = None
