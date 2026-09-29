"""工作台：在线 / 异常 / 失败任务一眼看完。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.api.deps import get_current_user, get_session, visible_account_ids
from app.api.routers import account_label, enum_value, task_out, utcnow
from app.core import events
from app.core.tasks import due_task_metrics
from app.models import (
    AccountStatus,
    Bot,
    Dialog,
    DialogChannel,
    Lease,
    Task,
    TaskStatus,
    TgAccount,
    User,
)
from app.redis_client import get_redis
from app.schemas import DashboardOut, FailedTaskOut, WorkerStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

#: Worker 心跳超过这个秒数就算掉线（规划：某台 Worker 超过 60 秒没心跳要告警）
WORKER_STALE_SECONDS = 60


def _parse_ts(raw) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


@router.get("", response_model=DashboardOut, summary="工作台汇总")
async def dashboard(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DashboardOut:
    """一次性给出页面四块（账号 / 会话 / 任务 / Worker）需要的数字，避免前端连发十几个请求。"""
    ids = await visible_account_ids(session, user)
    now = utcnow()
    out = DashboardOut(
        generated_at=now,
        # 没配 Telegram 凭据时 Worker 只认领租约不连 Telegram，页面需要明确提示
        telegram_ready=bool(settings.telegram_api_id and settings.telegram_api_hash),
    )

    # ---------- 账号 ----------
    account_scope = [TgAccount.id.in_(ids)] if ids is not None else []
    out.total_accounts = int(
        await session.scalar(select(func.count()).select_from(TgAccount).where(*account_scope)) or 0
    )
    out.abnormal_accounts = int(
        await session.scalar(
            select(func.count())
            .select_from(TgAccount)
            .where(
                *account_scope,
                TgAccount.status.notin_(
                    [
                        AccountStatus.healthy.value,
                        AccountStatus.pending.value,
                        AccountStatus.disabled.value,
                    ]
                ),
            )
        )
        or 0
    )

    lease_scope = [Lease.account_id.in_(ids)] if ids is not None else []
    out.leased_accounts = int(
        await session.scalar(
            select(func.count()).select_from(Lease).where(Lease.lease_until > now, *lease_scope)
        )
        or 0
    )
    # 在线 = 状态正常且有未过期租约（租约在但状态异常的不算“正常在线”）
    online_subq = select(Lease.account_id).where(Lease.lease_until > now)
    out.online_accounts = int(
        await session.scalar(
            select(func.count())
            .select_from(TgAccount)
            .where(*account_scope, TgAccount.status == AccountStatus.healthy.value, TgAccount.id.in_(online_subq))
        )
        or 0
    )

    # ---------- 会话 ----------
    # Bot 会话不属于某个员工号，人人可见；用户号会话跟着分配走
    if ids is None:
        dialog_scope = []
    else:
        dialog_scope = [
            (Dialog.channel == DialogChannel.bot) | (Dialog.account_id.in_(ids))
        ]
    out.total_dialogs = int(
        await session.scalar(select(func.count()).select_from(Dialog).where(*dialog_scope)) or 0
    )
    out.unread_dialogs = int(
        await session.scalar(
            select(func.count())
            .select_from(Dialog)
            .where(*dialog_scope, Dialog.unread_count > 0)
        )
        or 0
    )
    out.total_bots = int(await session.scalar(select(func.count()).select_from(Bot)) or 0)

    # ---------- 任务 ----------
    metrics = await due_task_metrics(session)
    out.tasks_pending = int(metrics.get("pending", 0))
    out.tasks_running = int(metrics.get("running", 0))
    out.tasks_failed = int(metrics.get("failed", 0))
    out.tasks_overdue = int(metrics.get("overdue", 0))
    out.tasks_stuck = int(metrics.get("stuck", 0))

    # ---------- Worker 心跳（Redis）+ 租约数（Postgres） ----------
    heartbeat_map: dict[str, dict] = {}
    try:
        for item in await events.worker_heartbeats(get_redis()):
            worker_id = item.get("worker_id")
            if worker_id:
                heartbeat_map[worker_id] = item
    except Exception:  # noqa: BLE001 - Redis 抖动不该让工作台打不开
        logger.warning("读取 Worker 心跳失败（Redis 不可用？）", exc_info=True)

    lease_rows = await session.execute(
        select(Lease.worker_id, func.count())
        .where(Lease.lease_until > now, *lease_scope)
        .group_by(Lease.worker_id)
    )
    leased_by_worker = {row[0]: int(row[1] or 0) for row in lease_rows.all()}

    workers: list[WorkerStatus] = []
    for worker_id, item in heartbeat_map.items():
        last = _parse_ts(item.get("ts"))
        stale = last is None or (now - last) > timedelta(seconds=WORKER_STALE_SECONDS)
        workers.append(
            WorkerStatus(
                worker_id=worker_id,
                last_heartbeat=last,
                online_accounts=int(item.get("online_accounts") or leased_by_worker.get(worker_id, 0)),
                leased_accounts=leased_by_worker.get(worker_id, 0),
                stale=stale,
                source="redis",
            )
        )
    known = set(heartbeat_map)
    for worker_id, count in leased_by_worker.items():
        if worker_id in known:
            continue
        # 还在持有租约但心跳键已经过期（或 Redis 刚重启）：标成过期，值班的人要能看到
        workers.append(
            WorkerStatus(
                worker_id=worker_id,
                last_heartbeat=None,
                online_accounts=count,
                leased_accounts=count,
                stale=True,
                source="database",
            )
        )
    workers.sort(key=lambda item: (item.stale, item.worker_id))
    out.workers = workers

    # ---------- 最近失败任务 ----------
    fail_stmt = (
        select(Task)
        .where(Task.status == TaskStatus.failed)
        .order_by(Task.created_at.desc())
        .limit(10)
    )
    if ids is not None:
        fail_stmt = fail_stmt.where(Task.account_id.in_(ids))
    failures = list((await session.scalars(fail_stmt)).all())
    if failures:
        account_ids = {task.account_id for task in failures if task.account_id}
        accounts = {
            row.id: row
            for row in (
                await session.scalars(select(TgAccount).where(TgAccount.id.in_(account_ids)))
            ).all()
        }
        recent: list[FailedTaskOut] = []
        for task in failures:
            recent.append(
                FailedTaskOut(
                    id=task.id,
                    type=enum_value(task.type),
                    type_label=task_out(task).type_label,
                    account_id=task.account_id,
                    account_label=account_label(accounts.get(task.account_id)),
                    error=task.error or "",
                    attempts=task.attempts,
                    max_attempts=task.max_attempts,
                    created_at=task.created_at,
                )
            )
        out.recent_failures = recent

    return out
