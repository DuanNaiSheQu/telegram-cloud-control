"""CSV 导出：账号 / 会话 / 消息 / 任务 / 审计。

契约（docs/API_CONTRACT.md 第 11 节）：
- `GET /api/export/{accounts,dialogs,messages,tasks,audit}.csv`；
- 查询参数与对应列表接口一致（筛选 + `sort`/`order` + `q`），但**不受 page/page_size 影响**：
  导出的就是当前筛选条件下的全部数据；
- 流式响应：`text/csv; charset=utf-8`，首字节是 UTF-8 BOM（Excel 打开中文不乱码），
  附件名形如 `accounts_20260928T130707Z.csv`（UTC 时间戳）；
- 最多 `MAX_EXPORT_ROWS` 行；真实条数与是否截断放在 `X-Export-Total` / `X-Export-Truncated` 头里
  （浏览器要读这两个头，所以显式加了 `Access-Control-Expose-Headers`）；
- 每次导出都写一条 `export.download` 审计：谁在什么时候导了哪张表。

实现细节：响应体是异步生成器，而 FastAPI 的 yield 依赖会在响应开始发送前关闭，
所以**不复用请求级 session**，生成器里自己开一个 SessionFactory 会话，分批（EXPORT_BATCH 行）
查库、逐行 yield，最后在 finally 里关掉会话。任何一批查库失败只记日志并结束流，
不把「已经发出去一半的 CSV」变成 500。
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, List, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    assert_account_access,
    assert_dialog_access,
    get_current_user,
    get_session,
    visible_account_ids,
)
from app.api.routers import build_order_by, ensure_utc, enum_value
from app.api.routers.accounts import ACCOUNT_SORT_FIELDS
from app.api.routers.audit import AUDIT_SORT_FIELDS
from app.api.routers.dialogs import DIALOG_SORT_FIELDS, MESSAGE_SORT_FIELDS, dialog_conditions
from app.api.routers.tasks import TASK_SORT_FIELDS, task_filter_conditions
from app.core.audit import ACTION_LABELS, write_audit
from app.db import SessionFactory
from app.models import (
    ACCOUNT_STATUS_LABELS,
    CURRENT_TASK_LABELS,
    TASK_STATUS_LABELS,
    TASK_TYPE_LABELS,
    AccountStatus,
    AuditLog,
    Bot,
    CurrentTask,
    Dialog,
    DialogChannel,
    DialogKind,
    Lease,
    Message,
    MessageDirection,
    MessageStatus,
    Task,
    TaskStatus,
    TaskType,
    TgAccount,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["export"])

#: 单次导出行数上限：再多就该走数据库直连或分批导，别让一个请求拖住连接池
MAX_EXPORT_ROWS = 50_000
#: 每次查库的行数
EXPORT_BATCH = 1000

DIALOG_CHANNEL_LABELS = {"user_account": "用户号", "bot": "官方 Bot"}
DIALOG_KIND_LABELS = {"private": "私信", "group": "群聊"}
DIRECTION_LABELS = {"incoming": "收到", "outgoing": "发出"}
MESSAGE_STATUS_LABELS = {
    "received": "已接收",
    "pending": "待发送",
    "sent": "已发送",
    "failed": "发送失败",
}


# ---------------- 公共工具 ----------------

def _iso(value: Optional[datetime]) -> str:
    return value.isoformat() if value else ""


def _cell(value: Any) -> Any:
    """CSV 单元格。

    文本以 = + - @ 开头时 Excel 会当公式执行（CSV 注入），加一个前导单引号；
    数字与 None 原样处理，避免把负数变成文本。
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, str):
        if value[:1] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + value
        return value
    return value


def _filename(kind: str) -> str:
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{kind}_{stamp}.csv"


def _csv_response(
    kind: str,
    header: Sequence[str],
    total: int,
    fetch: Callable[[AsyncSession, int, int], Awaitable[List[Sequence[Any]]]],
    *,
    truncated: bool,
) -> StreamingResponse:
    """把「分批取数」包装成带 BOM 的流式 CSV 响应。"""

    async def body():
        yield "\ufeff".encode("utf-8")  # BOM：Excel 打开中文不乱码
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(list(header))
        yield buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)

        offset = 0
        emitted = 0
        try:
            async with SessionFactory() as session:
                while emitted < MAX_EXPORT_ROWS:
                    limit = min(EXPORT_BATCH, MAX_EXPORT_ROWS - emitted)
                    try:
                        rows = await fetch(session, offset, limit)
                    except Exception:  # noqa: BLE001 - 头已经发出去了，只能记日志收尾
                        logger.warning("导出 %s 时查询失败，已提前结束流", kind, exc_info=True)
                        return
                    if not rows:
                        return
                    for row in rows:
                        writer.writerow([_cell(value) for value in row])
                        emitted += 1
                    yield buffer.getvalue().encode("utf-8")
                    buffer.seek(0)
                    buffer.truncate(0)
                    if len(rows) < limit:
                        return
                    offset += len(rows)
        except Exception:  # noqa: BLE001
            logger.warning("导出 %s 中途失败", kind, exc_info=True)

    filename = _filename(kind)
    return StreamingResponse(
        body(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Total": str(total),
            "X-Export-Truncated": "true" if truncated else "false",
            # 浏览器要读上面两个头 + 文件名
            "Access-Control-Expose-Headers": "Content-Disposition, X-Export-Total, X-Export-Truncated",
            "Cache-Control": "no-store",
        },
    )


async def _count(session: AsyncSession, stmt) -> int:
    """把带 where / join 的 select 包成 count(*)。"""
    return int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


async def _audit_export(
    session: AsyncSession,
    user: User,
    *,
    kind: str,
    total: int,
    filters: dict,
) -> None:
    await write_audit(
        session,
        action="export.download",
        user_id=user.id,
        target_type="export",
        target_id=kind,
        detail={"kind": kind, "rows": total, "filters": {k: str(v) for k, v in filters.items() if v is not None}},
    )
    await session.commit()


# ---------------- 账号 ----------------

ACCOUNT_HEADER = [
    "手机号(脱敏)", "用户名", "用户ID", "显示名", "号龄(天)", "群数量", "分组", "代理",
    "状态", "状态说明", "当前任务", "最后心跳", "最后检测", "最后错误", "备注",
    "Worker", "租约到期", "建档时间", "账号ID",
]


@router.get("/accounts.csv", summary="导出账号 CSV（带当前筛选条件）")
async def export_accounts(
    group_id: Optional[uuid.UUID] = Query(default=None),
    status_filter: Optional[AccountStatus] = Query(default=None, alias="status"),
    current_task: Optional[CurrentTask] = Query(default=None),
    phone: Optional[str] = Query(default=None),
    keyword: Optional[str] = Query(default=None),
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出账号表当前筛选结果；operator 只导出分配给他的号。"""
    ids = await visible_account_ids(session, user)
    conditions = []
    if ids is not None:
        conditions.append(TgAccount.id.in_(ids))
    if group_id is not None:
        conditions.append(TgAccount.group_id == group_id)
    if status_filter is not None:
        conditions.append(TgAccount.status == status_filter)
    if current_task is not None:
        conditions.append(TgAccount.current_task == current_task)
    for raw in (phone, keyword):
        if raw and raw.strip():
            pattern = f"%{raw.strip()}%"
            conditions.append(
                or_(
                    TgAccount.phone_masked.ilike(pattern),
                    TgAccount.username.ilike(pattern),
                    TgAccount.display_name.ilike(pattern),
                )
            )

    order_by = build_order_by(
        sort=sort, order=order, mapping=ACCOUNT_SORT_FIELDS,
        default_field="created_at", default_order="desc", tiebreaker=TgAccount.id,
    )
    total = await _count(session, select(TgAccount.id).where(*conditions))

    async def fetch(db: AsyncSession, offset: int, limit: int) -> List[Sequence[Any]]:
        stmt = (
            select(TgAccount, Lease.worker_id, Lease.lease_until)
            .outerjoin(Lease, Lease.account_id == TgAccount.id)
            .where(*conditions)
            .order_by(*order_by)
            .offset(offset)
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        out = []
        for account, worker_id, lease_until in rows:
            status_value = enum_value(account.status)
            out.append(
                [
                    account.phone_masked, account.username, account.tg_user_id, account.display_name,
                    account.age_days, account.group_count,
                    account.group.name if account.group else "",
                    account.proxy.endpoint if account.proxy else "",
                    ACCOUNT_STATUS_LABELS.get(status_value, status_value), account.status_reason,
                    CURRENT_TASK_LABELS.get(enum_value(account.current_task), ""),
                    _iso(account.last_heartbeat), _iso(account.last_checked_at), account.last_error,
                    account.remark, worker_id or "", _iso(lease_until), _iso(account.created_at),
                    str(account.id),
                ]
            )
        return out

    await _audit_export(
        session, user, kind="accounts", total=total,
        filters={"group_id": group_id, "status": status_filter, "current_task": current_task, "phone": phone, "keyword": keyword},
    )
    return _csv_response("accounts", ACCOUNT_HEADER, total, fetch, truncated=total > MAX_EXPORT_ROWS)


# ---------------- 会话 ----------------

DIALOG_HEADER = [
    "会话ID", "通道", "类型", "账号", "标题", "用户名", "对方", "成员数", "未读",
    "最近消息时间", "最近消息预览", "置顶", "建档时间",
]


@router.get("/dialogs.csv", summary="导出会话 CSV")
async def export_dialogs(
    channel: Optional[DialogChannel] = Query(default=None),
    kind: Optional[DialogKind] = Query(default=None),
    account_id: Optional[uuid.UUID] = Query(default=None),
    bot_id: Optional[uuid.UUID] = Query(default=None),
    keyword: Optional[str] = Query(default=None, description="标题 / 对方 / 用户名 / 最近预览 / 消息正文"),
    q: Optional[str] = Query(default=None, description="keyword 的别名"),
    only_unread: bool = Query(default=False),
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出会话；`q` / `keyword` 跨标题与正文搜索（与列表接口同口径）。"""
    ids = await visible_account_ids(session, user)
    conditions = dialog_conditions(ids)
    if channel is not None:
        conditions.append(Dialog.channel == channel)
    if kind is not None:
        conditions.append(Dialog.kind == kind)
    if account_id is not None:
        await assert_account_access(session, user, account_id)
        conditions.append(Dialog.account_id == account_id)
    if bot_id is not None:
        conditions.append(Dialog.bot_id == bot_id)
    if only_unread:
        conditions.append(Dialog.unread_count > 0)
    for raw in (q, keyword):
        if raw and raw.strip():
            pattern = f"%{raw.strip()}%"
            conditions.append(
                or_(
                    Dialog.title.ilike(pattern),
                    Dialog.peer_display.ilike(pattern),
                    Dialog.username.ilike(pattern),
                    Dialog.last_message_preview.ilike(pattern),
                    Dialog.id.in_(select(Message.dialog_id).where(Message.body.ilike(pattern)).limit(500)),
                )
            )

    order_by = build_order_by(
        sort=sort, order=order, mapping=DIALOG_SORT_FIELDS,
        default_field="last_message_at", default_order="desc", nulls_last=True, tiebreaker=Dialog.id,
    )
    total = await _count(session, select(Dialog).where(*conditions))

    async def fetch(db: AsyncSession, offset: int, limit: int) -> List[Sequence[Any]]:
        stmt = (
            select(Dialog, TgAccount.phone_masked)
            .outerjoin(TgAccount, TgAccount.id == Dialog.account_id)
            .where(*conditions)
            .order_by(*order_by)
            .offset(offset)
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        return [
            [
                str(dialog.id),
                DIALOG_CHANNEL_LABELS.get(enum_value(dialog.channel), ""),
                DIALOG_KIND_LABELS.get(enum_value(dialog.kind), ""),
                phone_masked or "",
                dialog.title, dialog.username, dialog.peer_display, dialog.member_count,
                dialog.unread_count, _iso(dialog.last_message_at), dialog.last_message_preview,
                dialog.is_pinned, _iso(dialog.created_at),
            ]
            for dialog, phone_masked in rows
        ]

    await _audit_export(
        session, user, kind="dialogs", total=total,
        filters={"channel": channel, "kind": kind, "account_id": account_id, "bot_id": bot_id, "q": q or keyword},
    )
    return _csv_response("dialogs", DIALOG_HEADER, total, fetch, truncated=total > MAX_EXPORT_ROWS)


# ---------------- 消息 ----------------

MESSAGE_HEADER = [
    "时间", "会话标题", "账号", "通道", "方向", "状态", "发送人", "正文",
    "有媒体", "媒体类型", "TG消息ID", "会话ID", "消息ID",
]


def _message_conditions(
    ids: Optional[List[uuid.UUID]],
    *,
    q: Optional[str],
    channel: Optional[DialogChannel],
    kind: Optional[DialogKind],
    account_id: Optional[uuid.UUID],
    dialog_id: Optional[uuid.UUID],
    direction: Optional[MessageDirection],
    status_filter: Optional[MessageStatus],
) -> list:
    """消息的筛选条件；可见范围靠 join dialogs 判定（用户号会话跟着账号分配走）。"""
    conditions = []
    if ids is not None:
        conditions.append((Dialog.channel == DialogChannel.bot) | (Dialog.account_id.in_(ids)))
    if dialog_id is not None:
        conditions.append(Message.dialog_id == dialog_id)
    if account_id is not None:
        conditions.append(Dialog.account_id == account_id)
    if channel is not None:
        conditions.append(Message.channel == channel)
    if kind is not None:
        conditions.append(Dialog.kind == kind)
    if direction is not None:
        conditions.append(Message.direction == direction)
    if status_filter is not None:
        conditions.append(Message.status == status_filter)
    if q and q.strip():
        conditions.append(Message.body.ilike(f"%{q.strip()}%"))
    return conditions


@router.get("/messages.csv", summary="导出消息 CSV（支持正文搜索 q=）")
async def export_messages(
    q: Optional[str] = Query(default=None, description="正文关键词"),
    channel: Optional[DialogChannel] = Query(default=None),
    kind: Optional[DialogKind] = Query(default=None),
    account_id: Optional[uuid.UUID] = Query(default=None),
    dialog_id: Optional[uuid.UUID] = Query(default=None),
    direction: Optional[MessageDirection] = Query(default=None),
    status_filter: Optional[MessageStatus] = Query(default=None, alias="status"),
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出消息；带 `dialog_id` 时会先校验该会话是否可见（越权 403）。"""
    if dialog_id is not None:
        dialog = await session.scalar(select(Dialog).where(Dialog.id == dialog_id))
        if dialog is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
        await assert_dialog_access(session, user, dialog)
    if account_id is not None:
        await assert_account_access(session, user, account_id)

    ids = await visible_account_ids(session, user)
    conditions = _message_conditions(
        ids, q=q, channel=channel, kind=kind, account_id=account_id,
        dialog_id=dialog_id, direction=direction, status_filter=status_filter,
    )
    order_by = build_order_by(
        sort=sort, order=order, mapping=MESSAGE_SORT_FIELDS,
        default_field="created_at", default_order="desc", tiebreaker=Message.id,
    )
    total = await _count(
        session, select(Message.id).join(Dialog, Dialog.id == Message.dialog_id).where(*conditions)
    )

    async def fetch(db: AsyncSession, offset: int, limit: int) -> List[Sequence[Any]]:
        stmt = (
            select(Message, Dialog.title, TgAccount.phone_masked)
            .join(Dialog, Dialog.id == Message.dialog_id)
            .outerjoin(TgAccount, TgAccount.id == Dialog.account_id)
            .where(*conditions)
            .order_by(*order_by)
            .offset(offset)
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        return [
            [
                _iso(message.created_at), title, phone_masked or "",
                DIALOG_CHANNEL_LABELS.get(enum_value(message.channel), ""),
                DIRECTION_LABELS.get(enum_value(message.direction), ""),
                MESSAGE_STATUS_LABELS.get(enum_value(message.status), ""),
                message.sender_name, message.body, message.has_media, message.media_type,
                message.tg_message_id, str(message.dialog_id), str(message.id),
            ]
            for message, title, phone_masked in rows
        ]

    await _audit_export(
        session, user, kind="messages", total=total,
        filters={"q": q, "channel": channel, "dialog_id": dialog_id, "account_id": account_id},
    )
    return _csv_response("messages", MESSAGE_HEADER, total, fetch, truncated=total > MAX_EXPORT_ROWS)


# ---------------- 任务 ----------------

TASK_HEADER = [
    "建档时间", "类型", "状态", "账号", "Bot", "优先级", "尝试次数", "最大尝试", "Worker",
    "错误", "下次执行", "开始时间", "完成时间", "创建人", "任务ID",
]


@router.get("/tasks.csv", summary="导出任务 CSV")
async def export_tasks(
    status_filter: Optional[TaskStatus] = Query(default=None, alias="status"),
    type_filter: Optional[TaskType] = Query(default=None, alias="type"),
    account_id: Optional[uuid.UUID] = Query(default=None),
    bot_id: Optional[uuid.UUID] = Query(default=None),
    only_failed: bool = Query(default=False),
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出任务；operator 只导出自己号上的任务（Bot 任务对他不可见）。"""
    ids = await visible_account_ids(session, user)
    conditions = task_filter_conditions(ids, status_filter, type_filter, account_id, bot_id, only_failed)
    order_by = build_order_by(
        sort=sort, order=order, mapping=TASK_SORT_FIELDS,
        default_field="created_at", default_order="desc", tiebreaker=Task.id,
    )
    total = await _count(session, select(Task.id).where(*conditions))

    async def fetch(db: AsyncSession, offset: int, limit: int) -> List[Sequence[Any]]:
        stmt = (
            select(Task, TgAccount.phone_masked, Bot.name, User.username)
            .outerjoin(TgAccount, TgAccount.id == Task.account_id)
            .outerjoin(Bot, Bot.id == Task.bot_id)
            .outerjoin(User, User.id == Task.created_by)
            .where(*conditions)
            .order_by(*order_by)
            .offset(offset)
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        out = []
        for task, phone_masked, bot_name, username in rows:
            type_value = enum_value(task.type)
            status_value = enum_value(task.status)
            out.append(
                [
                    _iso(task.created_at), TASK_TYPE_LABELS.get(type_value, type_value),
                    TASK_STATUS_LABELS.get(status_value, status_value),
                    phone_masked or "", bot_name or "", task.priority, task.attempts, task.max_attempts,
                    task.worker_id or "", task.error, _iso(task.next_run_at), _iso(task.started_at),
                    _iso(task.completed_at), username or "", str(task.id),
                ]
            )
        return out

    await _audit_export(
        session, user, kind="tasks", total=total,
        filters={"status": status_filter, "type": type_filter, "account_id": account_id, "only_failed": only_failed},
    )
    return _csv_response("tasks", TASK_HEADER, total, fetch, truncated=total > MAX_EXPORT_ROWS)


# ---------------- 审计 ----------------

AUDIT_HEADER = ["时间", "动作", "动作名", "操作人", "账号", "目标类型", "目标ID", "详情", "IP"]


@router.get("/audit.csv", summary="导出审计 CSV")
async def export_audit(
    action: Optional[str] = Query(default=None),
    user_id: Optional[uuid.UUID] = Query(default=None),
    account_id: Optional[uuid.UUID] = Query(default=None),
    bot_id: Optional[uuid.UUID] = Query(default=None),
    from_: Optional[datetime] = Query(default=None, alias="from", description="ISO8601，created_at >= from"),
    to: Optional[datetime] = Query(default=None, description="ISO8601，created_at <= to"),
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出审计；operator 只导出与自己相关的记录（自己操作的或自己号上的）。

    时间范围参数与列表接口一致（`from`/`to`，作用在 created_at 上，闭区间）。
    """
    conditions = []
    ids = await visible_account_ids(session, user)
    if ids is not None:
        conditions.append(or_(AuditLog.user_id == user.id, AuditLog.account_id.in_(ids)))
    if action:
        conditions.append(AuditLog.action == action)
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if account_id is not None:
        conditions.append(AuditLog.account_id == account_id)
    if bot_id is not None:
        conditions.append(AuditLog.bot_id == bot_id)
    if from_ is not None or to is not None:
        start, end = ensure_utc(from_), ensure_utc(to)
        if start is not None and end is not None and start > end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="时间范围不合法：from 不能晚于 to"
            )
        if start is not None:
            conditions.append(AuditLog.created_at >= start)
        if end is not None:
            conditions.append(AuditLog.created_at <= end)

    order_by = build_order_by(
        sort=sort, order=order, mapping=AUDIT_SORT_FIELDS,
        default_field="created_at", default_order="desc", tiebreaker=AuditLog.id,
    )
    total = await _count(session, select(AuditLog.id).where(*conditions))

    async def fetch(db: AsyncSession, offset: int, limit: int) -> List[Sequence[Any]]:
        stmt = (
            select(AuditLog, User.username, TgAccount.phone_masked)
            .outerjoin(User, User.id == AuditLog.user_id)
            .outerjoin(TgAccount, TgAccount.id == AuditLog.account_id)
            .where(*conditions)
            .order_by(*order_by)
            .offset(offset)
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        out = []
        for log, username, phone_masked in rows:
            detail = ""
            if log.detail is not None:
                try:
                    detail = json.dumps(log.detail, ensure_ascii=False)
                except (TypeError, ValueError):
                    detail = str(log.detail)
            out.append(
                [
                    _iso(log.created_at), log.action, ACTION_LABELS.get(log.action, log.action),
                    username or "", phone_masked or "", log.target_type, log.target_id,
                    detail, log.client_ip,
                ]
            )
        return out

    await _audit_export(
        session, user, kind="audit", total=total,
        filters={"action": action, "user_id": user_id, "account_id": account_id, "from": from_, "to": to},
    )
    return _csv_response("audit", AUDIT_HEADER, total, fetch, truncated=total > MAX_EXPORT_ROWS)
