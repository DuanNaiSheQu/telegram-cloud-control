"""账号、分组、代理、分配、检测 schema。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AccountStatus, CurrentTask
from app.schemas.common import ORMModel


# ---------------- 账号 ----------------

class AccountCreate(BaseModel):
    phone: str = Field(min_length=5, max_length=32, description="带国家码的手机号")
    group_id: Optional[uuid.UUID] = None
    proxy_id: Optional[uuid.UUID] = None
    remark: str = ""


class AccountUpdate(BaseModel):
    group_id: Optional[uuid.UUID] = None
    proxy_id: Optional[uuid.UUID] = None
    remark: Optional[str] = None
    display_name: Optional[str] = None
    status: Optional[AccountStatus] = Field(
        default=None, description="只允许改为 disabled（停用）或 healthy（启用）"
    )


class AccountOut(ORMModel):
    id: uuid.UUID
    phone_masked: str
    # 明文手机号（自建系统，运营需要看完整号码；没有则空——比如 tdata / 会话导入的号）
    phone: str = ""
    # 展示用标签：真手机号 > @用户名 > ID:{tg_user_id}（phone_masked 可能是导入目录标签，如 tdata#0）
    display_label: str = ""
    username: Optional[str] = None
    tg_user_id: Optional[int] = None
    api_id: Optional[int] = None
    display_name: str = ""
    age_days: Optional[int] = None
    group_count: int = 0
    group_id: Optional[uuid.UUID] = None
    group_name: Optional[str] = None
    proxy_id: Optional[uuid.UUID] = None
    proxy_endpoint: Optional[str] = None
    status: AccountStatus
    status_label: str = ""
    status_reason: str = ""
    current_task: CurrentTask
    current_task_label: str = ""
    last_heartbeat: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    last_error: str = ""
    worker_id: Optional[str] = None
    lease_until: Optional[datetime] = None
    remark: str = ""
    created_at: Optional[datetime] = None

    # ---------- 账号矩阵 ----------
    import_source: str = "manual"
    device_model: str = ""
    # 对齐的官方客户端平台（android / ios / tdesktop）；空表示还没对齐
    client_kind: str = ""
    health_score: int = 100
    health_checked_at: Optional[datetime] = None
    health_detail: dict = {}
    risk_flags: dict = {}
    daily_message_limit: int = 0
    min_action_seconds: int = 0
    flood_until: Optional[datetime] = None
    flood_strikes: int = 0
    warmup_started_at: Optional[datetime] = None


class AccountSummary(BaseModel):
    total: int = 0
    healthy: int = 0
    abnormal: int = 0
    new_this_week: int = 0
    online: int = 0
    leased: int = 0


class AccountListResponse(BaseModel):
    items: List[AccountOut]
    total: int
    page: int = 1
    page_size: int = 20
    summary: Optional[AccountSummary] = None


# ---------------- 登录 ----------------

class LoginStartRequest(BaseModel):
    """登录第一步。

    两种用法：
    - 新号：只给 phone（会先建档）；
    - 已有号重新登录：只给 account_id 即可，phone 用库里加密保存的号码，不必让值班的人
      对着脱敏号（861****2551）重敲一遍。
    """

    phone: Optional[str] = Field(default=None, min_length=5, max_length=32)
    group_id: Optional[uuid.UUID] = None
    proxy_id: Optional[uuid.UUID] = None
    account_id: Optional[uuid.UUID] = Field(
        default=None, description="对已有账号重新登录时传；此时 phone 可省略"
    )

    @model_validator(mode="after")
    def _require_phone_or_account(self) -> "LoginStartRequest":
        if not self.phone and not self.account_id:
            raise ValueError("phone 与 account_id 至少要有一个")
        return self


class LoginStepResponse(BaseModel):
    account_id: uuid.UUID
    step: str = Field(description="code_required | password_required | done")
    message: str = ""
    task_id: Optional[uuid.UUID] = None


class LoginCodeRequest(BaseModel):
    account_id: uuid.UUID
    code: str = Field(min_length=3, max_length=16)


class LoginPasswordRequest(BaseModel):
    account_id: uuid.UUID
    password: str = Field(min_length=1, max_length=128)


# ---------------- 检测 ----------------

class CheckRequest(BaseModel):
    account_ids: Optional[List[uuid.UUID]] = None
    scope: str = Field(default="selected", description="selected | all | group")


class CheckResultOut(BaseModel):
    account_id: uuid.UUID
    phone_masked: str = ""
    reachable: bool = False
    status: AccountStatus
    status_label: str = ""
    message: str = ""
    task_id: Optional[uuid.UUID] = None


# ---------------- 分组 / 代理 ----------------

class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = ""


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class GroupOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str = ""
    account_count: int = 0
    created_at: Optional[datetime] = None


class ProxyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    scheme: str = Field(default="socks5", pattern="^(socks5|socks4|http|https|mtproxy)$")
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    enabled: bool = True
    remark: str = ""


class ProxyUpdate(BaseModel):
    name: Optional[str] = None
    scheme: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    enabled: Optional[bool] = None
    remark: Optional[str] = None


class ProxyOut(ORMModel):
    id: uuid.UUID
    name: str
    scheme: str
    host: str
    port: int
    endpoint: str = ""
    has_auth: bool = False
    enabled: bool = True
    remark: str = ""
    account_count: int = 0
    created_at: Optional[datetime] = None


# ---------------- 分配 ----------------

class AssignmentCreate(BaseModel):
    user_id: uuid.UUID
    account_ids: List[uuid.UUID]


class AssignmentOut(BaseModel):
    user_id: uuid.UUID
    username: str = ""
    display_name: str = ""
    account_ids: List[uuid.UUID] = []
    account_count: int = 0


class AssignableAccounts(BaseModel):
    items: List[AccountOut]
    total: int
