"""账号矩阵 schema：导入预览与结果、导入批次、批量节流、深度验活、健康快照。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.bulk import BulkScopeRequest
from app.schemas.common import ORMModel


# ---------------- 导入 ----------------

class ImportItemPreview(BaseModel):
    """预览里的一条（不回传 session 明文）。"""

    source: str
    label: str
    phone_masked: Optional[str] = None
    dc_id: Optional[int] = None
    tg_user_id: Optional[int] = None
    has_session: bool = False
    remark: str = ""
    error: Optional[str] = None


class AccountImportParseResponse(BaseModel):
    source_kind: str = ""
    total: int = 0
    ready: int = 0
    failed: int = 0
    items: List[ImportItemPreview] = Field(default_factory=list)
    tdata_available: bool = False


class AccountImportResultItem(BaseModel):
    index: int = 0
    source: str = ""
    label: str = ""
    ok: bool = False
    message: str = ""
    account_id: Optional[uuid.UUID] = None


class AccountImportResponse(BaseModel):
    ok: bool = True
    message: str = ""
    batch_id: uuid.UUID
    source_kind: str = ""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    duplicate: int = 0
    results: List[AccountImportResultItem] = Field(default_factory=list)


class AccountImportBatchOut(ORMModel):
    id: uuid.UUID
    source_kind: str = ""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    duplicate: int = 0
    proxy_id: Optional[uuid.UUID] = None
    group_id: Optional[uuid.UUID] = None
    remark: str = ""
    created_at: Optional[datetime] = None


# ---------------- 批量：节流与深度验活 ----------------

class BulkThrottleRequest(BulkScopeRequest):
    """批量设置节流：不传的字段保持不变；传 0 表示恢复按号龄自动阶梯。"""

    daily_message_limit: Optional[int] = Field(default=None, ge=0, le=2000, description="每日发送上限，0=自动阶梯")
    min_action_seconds: Optional[int] = Field(default=None, ge=0, le=3600, description="最小动作间隔（秒），0=自动")
    reset_flood: bool = Field(default=False, description="同时清掉熔断冷却与限流计数")
    start_warmup_now: bool = Field(default=False, description="把养号起点重置为现在（新号刚导入时用）")


class BulkProbeRequest(BulkScopeRequest):
    """深度验活：连得上 + 会话有效 + 读写权限探测 + 健康分复算。"""

    write_probe: bool = Field(
        default=False, description="是否额外做一次写权限探测（往自己的收藏夹发一条，可能产生一条消息）"
    )


class AccountMatrixState(BaseModel):
    """账号页展示用：健康分、风险标记与节流快照。"""

    account_id: uuid.UUID
    health_score: int = 100
    health_checked_at: Optional[datetime] = None
    risk_flags: Dict[str, Any] = Field(default_factory=dict)
    throttle: Dict[str, Any] = Field(default_factory=dict)
    device_model: str = ""
    import_source: str = ""
