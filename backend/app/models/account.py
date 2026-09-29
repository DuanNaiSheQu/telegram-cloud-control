"""用户号：脱敏展示、状态、分组、代理、加密会话。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk
from app.models.enums import AccountStatus, CurrentTask


def _enum(enum_cls, name: str):
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
    )


class AccountGroup(Base, TimestampMixin):
    """账号分组：自定义标签，用来把号分给同事。"""

    __tablename__ = "account_groups"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class Proxy(Base, TimestampMixin):
    """账号固定出站地址。"""

    __tablename__ = "proxies"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scheme: Mapped[str] = mapped_column(String(16), nullable=False, default="socks5")
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    password_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    @property
    def endpoint(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"


class TgAccount(Base, TimestampMixin):
    """一个用户号。会话串加密后存这里，库里不存明文密钥。"""

    __tablename__ = "tg_accounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    phone_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 手机号的确定性哈希：Fernet 密文每次不同，去重必须靠它（建档/导入都写）
    phone_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    phone_masked: Mapped[str] = mapped_column(String(32), nullable=False, default="未知")
    tg_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    # 这个号是通过哪套 API 凭据登录的（多套凭据混用时便于排查限流来源）
    api_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    # 号龄（天），由首次登录时间推算
    age_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    group_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_groups.id", ondelete="SET NULL"), nullable=True
    )
    proxy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proxies.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[AccountStatus] = mapped_column(
        _enum(AccountStatus, "account_status"), nullable=False, default=AccountStatus.pending, index=True
    )
    status_reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    current_task: Mapped[CurrentTask] = mapped_column(
        _enum(CurrentTask, "current_task"), nullable=False, default=CurrentTask.idle
    )

    session_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Telegram 首次成功登录时间，用于号龄
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # ---------- 账号矩阵：导入来源 / 设备指纹 ----------
    # 怎么进来的：manual（手工建档）/ phone（手机号列表）/ session_string / session_file / tdata
    import_source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual", index=True)
    import_batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    # 设备指纹：每个号独立（同型号大批量是典型风控特征，建档时随机化）
    device_model: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    system_version: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    app_version: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    lang_code: Mapped[str] = mapped_column(String(8), nullable=False, default="zh")
    lang_pack: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    # 对齐的官方客户端平台（android / ios / tdesktop），身份取自官方发布版本表
    client_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="", index=True)

    # ---------- 官方机制：服务端下发的限制参数 ----------
    # help.GetAppConfig 里 flood/上限类参数的快照；节流时「只收紧不放松」地参考它
    official_limits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    official_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 最近一次养号活动的时间（官方节奏：上线→翻会话→打字→下线的周期）
    warmup_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ---------- 验活：健康分与风险标记 ----------
    # 0-100，验活任务每次复算；低于阈值在账号页标黄/标红
    health_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    health_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 验活明细：{reachable, read_ok, write_ok, auth_count, dc_id, checked_at, ...}
    health_detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 风控标记：{restricted, spam_blocked, flood_strikes, last_flood_at, notes}
    risk_flags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # ---------- 节流与养号 ----------
    # 0 = 走默认阶梯（按号龄自动算），非 0 = 人工指定
    daily_message_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_action_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 养号起点（首次进入本系统的时间），阶梯按它计算号龄
    warmup_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 熔断：收到 FloodWait 时写入，期间发送类任务直接顺延
    flood_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    flood_strikes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    group: Mapped[Optional[AccountGroup]] = relationship(lazy="joined")
    proxy: Mapped[Optional[Proxy]] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("tg_user_id", name="uq_tg_accounts_tg_user_id"),
    )


class AccountImport(Base, TimestampMixin):
    """一次批量导入的批次：导入方式、逐条结果，便于回溯「这批号哪来的」。"""

    __tablename__ = "account_imports"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # phone / session_string / session_file / tdata / mixed
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="mixed")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proxies.id", ondelete="SET NULL"), nullable=True
    )
    group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_groups.id", ondelete="SET NULL"), nullable=True
    )
    # 逐条结果：[{index, source, phone_masked, ok, message, account_id}]
    results: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class AccountAssignment(Base, TimestampMixin):
    """谁可以操作哪个号。"""

    __tablename__ = "account_assignments"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tg_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "account_id", name="uq_account_assignments_user_account"),
    )
