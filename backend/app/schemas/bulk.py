"""批量账号操作 schema（严格限定在规划允许的范围内）。

规划「不做这些」是硬约束：批量私信、批量群发、素材群发、批量加群、批量退群、强拉进群、
批量改资料、吵群、多号装真人。所以这里只提供六个动作：
检测、同步会话、分配/取消分配、改分组、改代理、停用/启用，
**连字段都不给**批量发送之类的能力，避免以后有人顺手复用。
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel, Field

#: 单个请求最多处理多少个号：防止误点「全部」把任务表灌爆或把事务拖长
BULK_MAX_ACCOUNTS = 500


class BulkScopeRequest(BaseModel):
    """批量操作的公共选择器：要么明确点名账号，要么给一个范围。

    `scope` 取值：`selected`（配合 `account_ids`）/ `all`（当前可见范围内全部）/
    `group:<分组ID>`（某个分组的号）。operator 的 `all` 只覆盖分配给他的号。
    """

    account_ids: Optional[List[uuid.UUID]] = Field(
        default=None, description="scope=selected 时的账号列表；operator 里出现未分配的号一律 403"
    )
    scope: str = Field(default="selected", description="selected | all | group:<分组ID>")
    limit: int = Field(
        default=200, ge=1, le=BULK_MAX_ACCOUNTS, description=f"本次最多处理多少个号（上限 {BULK_MAX_ACCOUNTS}）"
    )
    dispatch: str = Field(
        default="each",
        description=(
            "目标怎么分给账号：each=每个号都处理全部目标（默认）；"
            "round_robin=目标按账号轮流切分，一个目标只由一个号处理——多号并行、互不重复"
        ),
    )


class BulkSyncRequest(BulkScopeRequest):
    """批量同步会话（只写 sync_dialogs 任务，由 Worker 执行）。"""


class BulkCheckRequest(BulkScopeRequest):
    """批量检测（写 account_check 任务并续一次租约）。"""


class BulkAssignRequest(BulkScopeRequest):
    """批量分配 / 取消分配（仅 admin）。"""

    user_id: uuid.UUID = Field(description="员工 id")
    mode: str = Field(default="assign", description="assign（分配）| unassign（取消分配）")


class BulkGroupRequest(BulkScopeRequest):
    """批量改分组；`group_id=null` 表示移出分组。"""

    group_id: Optional[uuid.UUID] = Field(default=None, description="传 null = 移出分组")


class BulkProxyRequest(BulkScopeRequest):
    """批量改代理；`proxy_id=null` 表示改为直连。"""

    proxy_id: Optional[uuid.UUID] = Field(default=None, description="传 null = 改为直连")


class BulkStatusRequest(BulkScopeRequest):
    """批量停用 / 启用。"""

    enabled: bool = Field(default=True, description="true=启用（healthy/pending），false=停用并清租约")


class BulkAccountResult(BaseModel):
    """单个账号的处理结果；前端逐行展示。"""

    account_id: uuid.UUID
    account_label: str = ""
    ok: bool = True
    message: str = ""
    task_id: Optional[uuid.UUID] = None
    #: 仅批量检测回填（与单号检测同口径）
    reachable: Optional[bool] = None
    status: Optional[str] = None
    status_label: Optional[str] = None


class BulkResultResponse(BaseModel):
    """批量操作统一回执：总数 / 成功 / 失败 / 跳过 + 逐账号明细。"""

    ok: bool = True
    action: str = ""
    message: str = ""
    requested: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    truncated: bool = False
    task_ids: List[uuid.UUID] = Field(default_factory=list)
    items: List[BulkAccountResult] = Field(default_factory=list)
