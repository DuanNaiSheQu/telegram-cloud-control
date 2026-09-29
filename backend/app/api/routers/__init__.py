"""路由层公共工具：出参序列化、中文标签、分页与请求体小工具。

为什么集中放在这里：账号、会话、任务、转发、审计几个路由都要给同一行数据补
「脱敏手机号 / 中文标签 / 租约信息」，只写一份才不会出现各页面字段对不上的情况。
本模块只依赖 config / models / schemas / services，不导入任何具体子路由，避免循环导入。
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional, Sequence

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import inspect as sa_inspect

from app import security
from app.config import settings
from app.models import (
    ACCOUNT_STATUS_LABELS,
    CURRENT_TASK_LABELS,
    TASK_STATUS_LABELS,
    TASK_TYPE_LABELS,
    AccountGroup,
    Bot,
    Dialog,
    Message,
    Proxy,
    Task,
    TgAccount,
    User,
)
from app.schemas import (
    AccountOut,
    BotOut,
    DialogOut,
    GroupOut,
    MessageOut,
    ProxyOut,
    TaskOut,
)

logger = logging.getLogger(__name__)

#: enums.py 里只有账号 / 任务 / 当前任务三张中文表，会话与消息的中文标签放在这里补
DIALOG_CHANNEL_LABELS = {"user_account": "用户号", "bot": "官方 Bot"}
DIALOG_KIND_LABELS = {"private": "私信", "group": "群聊"}
MESSAGE_DIRECTION_LABELS = {"incoming": "收到", "outgoing": "发出"}
MESSAGE_STATUS_LABELS = {
    "received": "已接收",
    "pending": "待发送",
    "sent": "已发送",
    "failed": "发送失败",
}
RELAY_TARGET_LABELS = {"group": "群聊", "private": "私信"}


class AccountIdsRequest(BaseModel):
    """分组 / 代理 / 分配接口共用的请求体。"""

    account_ids: List[uuid.UUID] = Field(default_factory=list)


def enum_value(value: Any) -> str:
    """枚举取字符串值；已经是 str 的原样返回。"""
    return value.value if hasattr(value, "value") else str(value)


def ensure_utc(value: Optional[datetime]) -> Optional[datetime]:
    """查询参数里的 ISO8601 可能不带时区：按 UTC 补齐，避免和 timestamptz 比较时报错。"""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def user_label(user: Optional[User]) -> Optional[str]:
    if user is None:
        return None
    return user.display_name or user.username


#: 展示标签统一在 services 层实现（路由与批量操作同口径）
from app.services.account_label import account_label  # noqa: E402


def unloaded_attr(obj: Any, name: str, default: Any = None) -> Any:
    """安全读取 ORM 属性。

    新建（还没 flush 过关系）的对象上访问 relationship 会在异步会话里触发懒加载并抛
    MissingGreenlet；这里先看 SQLAlchemy 的 unloaded 状态，没加载就当没有。
    """
    if obj is None:
        return default
    try:
        state = sa_inspect(obj)
    except Exception:  # noqa: BLE001 - 非 ORM 对象
        return getattr(obj, name, default)
    if name in state.unloaded:
        return default
    return getattr(obj, name, default)


# ---------------- 账号 ----------------

def account_out(account: TgAccount, lease: Optional[dict] = None) -> AccountOut:
    """AccountOut 里 group_name / proxy_endpoint / worker_id / lease_until 是派生字段，
    从租约表和 joined 关系上补齐。"""
    out = AccountOut.model_validate(account)
    # 不脱敏：直接给出完整手机号（有就显示真号；没有则空，前端会说明原因）
    if account.phone_enc:
        try:
            out.phone = security.decrypt_secret(account.phone_enc) or ""
        except Exception:  # noqa: BLE001 - 解不开（密钥轮换/脏数据）不能让接口挂
            out.phone = ""
    out.display_label = account_label(account) or account.phone_masked or ""
    out.status_label = ACCOUNT_STATUS_LABELS.get(enum_value(account.status), "")
    out.current_task_label = CURRENT_TASK_LABELS.get(enum_value(account.current_task), "")
    group = unloaded_attr(account, "group")
    proxy = unloaded_attr(account, "proxy")
    out.group_name = group.name if isinstance(group, AccountGroup) else None
    out.proxy_endpoint = proxy.endpoint if isinstance(proxy, Proxy) else None
    if lease:
        out.worker_id = lease.get("worker_id")
        out.lease_until = lease.get("lease_until")
    return out


# ---------------- 会话 / 消息 ----------------

def dialog_out(
    dialog: Dialog,
    account: Optional[TgAccount] = None,
    bot: Optional[Bot] = None,
) -> DialogOut:
    out = DialogOut.model_validate(dialog)
    out.channel_label = DIALOG_CHANNEL_LABELS.get(enum_value(dialog.channel), "")
    out.kind_label = DIALOG_KIND_LABELS.get(enum_value(dialog.kind), "")
    account = account if account is not None else unloaded_attr(dialog, "account")
    bot = bot if bot is not None else unloaded_attr(dialog, "bot")
    if account is not None:
        out.account_label = account_label(account)
    elif dialog.account_id is not None:
        out.account_label = str(dialog.account_id)[:8]
    if bot is not None:
        out.bot_label = f"@{bot.bot_username}" if bot.bot_username else bot.name
    elif dialog.bot_id is not None:
        out.bot_label = str(dialog.bot_id)[:8]
    return out


def message_out(message: Message) -> MessageOut:
    out = MessageOut.model_validate(message)
    out.direction_label = MESSAGE_DIRECTION_LABELS.get(enum_value(message.direction), "")
    out.status_label = MESSAGE_STATUS_LABELS.get(enum_value(message.status), "")
    return out


# ---------------- 任务 ----------------

def task_out(
    task: Task,
    account: Optional[TgAccount] = None,
    bot: Optional[Bot] = None,
    user: Optional[User] = None,
) -> TaskOut:
    out = TaskOut.model_validate(task)
    out.type_label = TASK_TYPE_LABELS.get(enum_value(task.type), enum_value(task.type))
    out.status_label = TASK_STATUS_LABELS.get(enum_value(task.status), enum_value(task.status))
    out.account_label = account_label(account)
    if bot is not None:
        out.bot_label = f"@{bot.bot_username}" if bot.bot_username else bot.name
    out.created_by_name = user_label(user)
    return out


# ---------------- Bot / 分组 / 代理 ----------------

def bot_out(bot: Bot) -> BotOut:
    """Token 明文永不出口，只回 123456...abcd。"""
    out = BotOut.model_validate(bot)
    try:
        out.token_masked = security.mask_token(security.decrypt_secret(bot.token_enc))
    except Exception:  # noqa: BLE001 - 解不开（密钥轮换了）也不能把接口打挂
        out.token_masked = "****"
    out.webhook_url = settings.webhook_url(bot.id)
    return out


def group_out(group: AccountGroup, account_count: int = 0) -> GroupOut:
    out = GroupOut.model_validate(group)
    out.account_count = account_count
    return out


def proxy_out(proxy: Proxy, account_count: int = 0) -> ProxyOut:
    out = ProxyOut.model_validate(proxy)
    out.endpoint = proxy.endpoint
    out.has_auth = bool(proxy.username_enc or proxy.password_enc)
    out.account_count = account_count
    return out


# ---------------- 小工具 ----------------

#: 允许的排序方向
SORT_ORDERS = ("asc", "desc")


def build_order_by(
    *,
    sort: Optional[str],
    order: Optional[str],
    mapping: "dict[str, Any]",
    default_field: str,
    default_order: str = "desc",
    nulls_last: bool = False,
    tiebreaker: Any = None,
) -> List[Any]:
    """把 `sort=&order=` 翻译成 order_by 子句。

    只允许白名单里的字段（防止拿任意列排序拖库）；给不出中文提示就白名单兜底。
    列表接口都走这里，字段名和报错文案才一致。
    """
    if order is not None and str(order).strip().lower() not in SORT_ORDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="order 只能是 asc 或 desc"
        )
    field = (sort or default_field).strip()
    if field not in mapping:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的排序字段：{field}；可用字段：{'、'.join(sorted(mapping))}",
        )
    direction = (order or default_order).strip().lower()
    column = mapping[field]
    clause = column.asc() if direction == "asc" else column.desc()
    if nulls_last:
        clause = clause.nulls_last()
    clauses: List[Any] = [clause]
    if tiebreaker is not None and tiebreaker is not column:
        # 有并列值时保持分页稳定（否则翻页可能重复 / 漏行）
        clauses.append(tiebreaker.desc())
    return clauses


def parse_uuid(value: Any) -> Optional[uuid.UUID]:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def parse_uuid_csv(raw: Optional[str]) -> List[uuid.UUID]:
    """`?account_ids=a,b,c` 形式。"""
    if not raw:
        return []
    out: List[uuid.UUID] = []
    for chunk in str(raw).replace(";", ",").split(","):
        parsed = parse_uuid(chunk.strip())
        if parsed is not None:
            out.append(parsed)
    return out


def dedupe(items: Iterable[uuid.UUID]) -> List[uuid.UUID]:
    seen: dict[uuid.UUID, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen.keys())


async def publish_safely(dialog: Dialog, message: Message) -> None:
    """把新消息推给页面订阅。Redis 抖动只影响实时性，绝不能让它把入库/发送请求打挂。"""
    from app.redis_client import get_redis
    from app.services import inbound

    try:
        await inbound.publish_message(get_redis(), dialog, message)
    except Exception:  # noqa: BLE001
        logger.warning("推送消息到 Redis 失败（不影响数据）", exc_info=True)


async def publish_task_safely(payload: dict) -> None:
    from app.core import events
    from app.redis_client import get_redis

    try:
        await events.publish_task_event(get_redis(), payload)
    except Exception:  # noqa: BLE001
        logger.warning("推送任务事件到 Redis 失败（不影响数据）", exc_info=True)


def rows_to_accounts(rows: Sequence[Any]) -> List[TgAccount]:
    return [row for row in rows if isinstance(row, TgAccount)]


__all__ = [
    "AccountIdsRequest",
    "DIALOG_CHANNEL_LABELS",
    "DIALOG_KIND_LABELS",
    "MESSAGE_DIRECTION_LABELS",
    "MESSAGE_STATUS_LABELS",
    "RELAY_TARGET_LABELS",
    "SORT_ORDERS",
    "account_label",
    "account_out",
    "bot_out",
    "build_order_by",
    "dedupe",
    "ensure_utc",
    "dialog_out",
    "enum_value",
    "group_out",
    "message_out",
    "parse_uuid",
    "parse_uuid_csv",
    "proxy_out",
    "publish_safely",
    "publish_task_safely",
    "rows_to_accounts",
    "task_out",
    "unloaded_attr",
    "user_label",
    "utcnow",
]
