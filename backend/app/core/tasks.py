"""任务核心：入队、按租约领取（FOR UPDATE SKIP LOCKED）、重试与收尾。

设计要点：
- 页面只写 tasks 表；Worker 只领「自己租约内的用户号」任务；API 只领 Bot 任务。
- 失败退避写入 next_run_at，超过 max_attempts 记为 failed，页面可手工重试。
- Redis 丢了不影响这里，事实以 Postgres 为准。
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Lease, Task, TaskStatus, TaskType


class TaskClaimError(RuntimeError):
    """任务被别的进程抢先处理。"""


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def backoff_seconds(attempts: int) -> int:
    """指数退避 + 抖动，避免失败任务同时重试。"""
    base = max(1, settings.task_retry_base_seconds)
    delay = min(base * (2 ** max(0, attempts - 1)), settings.task_retry_max_seconds)
    return int(delay * (0.8 + random.random() * 0.4))


async def enqueue_task(
    session: AsyncSession,
    *,
    type: TaskType,  # noqa: A002 - 与列名保持一致
    payload: Optional[dict] = None,
    account_id: Optional[uuid.UUID] = None,
    bot_id: Optional[uuid.UUID] = None,
    dialog_id: Optional[uuid.UUID] = None,
    created_by: Optional[uuid.UUID] = None,
    status: TaskStatus = TaskStatus.pending,
    priority: int = 100,
    run_after: Optional[datetime] = None,
    max_attempts: Optional[int] = None,
    dedupe_key: Optional[str] = None,
) -> Task:
    task = Task(
        type=type,
        status=status,
        account_id=account_id,
        bot_id=bot_id,
        dialog_id=dialog_id,
        payload=payload or {},
        priority=priority,
        next_run_at=run_after or _now(),
        max_attempts=max_attempts or settings.task_max_attempts,
        created_by=created_by,
        dedupe_key=dedupe_key,
    )
    if dedupe_key:
        existing = await session.scalar(select(Task).where(Task.dedupe_key == dedupe_key))
        if existing is not None:
            return existing
    try:
        # 用 SAVEPOINT 包住，去重冲突不能把外层事务（比如刚写入的消息）一起回滚
        async with session.begin_nested():
            session.add(task)
            await session.flush()
    except IntegrityError:
        if dedupe_key:
            existing = await session.scalar(select(Task).where(Task.dedupe_key == dedupe_key))
            if existing is not None:
                return existing
        raise
    return task


async def claim_tasks(
    session: AsyncSession,
    *,
    claimer_id: str,
    kind: str,
    limit: Optional[int] = None,
    account_ids: Optional[Sequence[uuid.UUID]] = None,
) -> list[Task]:
    """领取一批任务。

    kind="worker"：仅用户号任务，且该号租约属于 claimer_id。
    kind="bot"：仅 Bot 任务（API 侧执行）。
    """
    batch = limit or settings.task_batch
    stmt = (
        select(Task)
        .where(
            Task.status == TaskStatus.pending,
            Task.next_run_at <= _now(),
        )
        .order_by(Task.priority.asc(), Task.next_run_at.asc(), Task.created_at.asc())
        .limit(batch)
        .with_for_update(skip_locked=True, of=Task)
    )

    if kind == "worker":
        if account_ids is not None:
            if not account_ids:
                return []
            stmt = stmt.where(Task.account_id.in_(list(account_ids)))
        else:
            stmt = stmt.join(Lease, Lease.account_id == Task.account_id).where(
                Lease.worker_id == claimer_id, Lease.lease_until > _now()
            )
        stmt = stmt.where(Task.account_id.is_not(None))
    elif kind == "bot":
        stmt = stmt.where(Task.bot_id.is_not(None), Task.account_id.is_(None))
    else:
        raise ValueError(f"unknown claim kind: {kind}")

    tasks = list((await session.scalars(stmt)).all())
    if not tasks:
        return []

    ids = [t.id for t in tasks]
    now = _now()
    # synchronize_session=False：自增只由下面这行 SQL 负责，避免 ORM 同步与手工赋值叠加导致 attempts 翻倍
    await session.execute(
        update(Task)
        .where(Task.id.in_(ids))
        .values(
            status=TaskStatus.running,
            worker_id=claimer_id,
            started_at=now,
            attempts=Task.attempts + 1,
        )
        .execution_options(synchronize_session=False)
    )
    for task in tasks:
        # 让返回出去的对象反映刚提交的状态，省一次往返查询
        task.status = TaskStatus.running
        task.worker_id = claimer_id
        task.attempts = task.attempts + 1
        task.started_at = now
    await session.commit()
    return tasks


async def complete_task(
    session: AsyncSession, task: Task, result: Optional[Any] = None
) -> None:
    task.status = TaskStatus.completed
    # 保留执行过程中写入的实时日志（result.logs）：任务跑完清掉的话，
    # 页面上的「这一步做了什么」就永远看不到了——失败排查尤其需要它。
    previous = task.result if isinstance(task.result, dict) else {}
    if isinstance(result, dict) and previous.get("logs"):
        task.result = {**result, "logs": previous["logs"]}
    else:
        task.result = result
    task.error = ""
    task.completed_at = _now()
    await session.flush()


async def fail_task(
    session: AsyncSession,
    task: Task,
    error: str,
    *,
    retryable: bool = True,
    requeue_after: Optional[int] = None,
) -> TaskStatus:
    """记一次失败。可重试且未超上限则回到 pending，否则 failed。"""
    task.error = (error or "")[:4000]
    # 失败时更要保住实时日志：最后一步卡在哪，全靠它
    if isinstance(task.result, dict) and task.result.get("logs"):
        task.result = {**task.result, "error": task.error}
    elif task.result is None:
        task.result = {"logs": [], "error": task.error}
    # 节流拦下只是「现在不能发」，不是一次真的尝试失败：把这次计数还回去。
    # 否则等额度恢复（可能几小时）的过程中，「等待」就把重试次数耗光了——任务最后会
    # 顶着一个「失败 5 次」的结论死掉，而它其实一次都没发出去。
    if "节流拦下" in task.error and task.attempts > 0:
        task.attempts -= 1
    exhausted = task.attempts >= task.max_attempts
    if retryable and not exhausted:
        delay = requeue_after if requeue_after is not None else backoff_seconds(task.attempts)
        task.status = TaskStatus.pending
        task.next_run_at = _now() + timedelta(seconds=delay)
        task.worker_id = None
        await session.flush()
        return TaskStatus.pending

    task.status = TaskStatus.failed
    task.completed_at = _now()
    await session.flush()
    return TaskStatus.failed


async def cancel_task(session: AsyncSession, task: Task) -> None:
    task.status = TaskStatus.cancelled
    task.completed_at = _now()
    await session.flush()


async def requeue_task(session: AsyncSession, task: Task, *, reset_attempts: bool = True) -> Task:
    """页面上的「重试」。"""
    task.status = TaskStatus.pending
    task.error = ""
    task.worker_id = None
    task.next_run_at = _now()
    task.started_at = None
    task.completed_at = None
    if reset_attempts:
        task.attempts = 0
    await session.flush()
    return task


async def pending_confirmation_task(
    session: AsyncSession, *, account_id: uuid.UUID, dialog_id: uuid.UUID
) -> Optional[Task]:
    """账号上是否还有等待确认发送的任务，用于当前任务显示。"""
    return await session.scalar(
        select(Task)
        .where(
            Task.account_id == account_id,
            Task.dialog_id == dialog_id,
            Task.status.in_([TaskStatus.pending_confirmation, TaskStatus.pending]),
            Task.type == TaskType.send_message,
        )
        .order_by(Task.created_at.desc())
        .limit(1)
    )


async def due_task_metrics(session: AsyncSession) -> dict:
    """给 Prometheus / 告警用的队列计数。"""
    from sqlalchemy import func

    pending = await session.scalar(
        select(func.count()).select_from(Task).where(Task.status == TaskStatus.pending)
    )
    running = await session.scalar(
        select(func.count()).select_from(Task).where(Task.status == TaskStatus.running)
    )
    failed = await session.scalar(
        select(func.count()).select_from(Task).where(Task.status == TaskStatus.failed)
    )
    overdue = await session.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.status == TaskStatus.pending, Task.next_run_at < _now() - timedelta(minutes=5))
    )
    stuck = await session.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            Task.status == TaskStatus.running,
            Task.started_at < _now() - timedelta(minutes=30),
        )
    )
    return {
        "pending": int(pending or 0),
        "running": int(running or 0),
        "failed": int(failed or 0),
        "overdue": int(overdue or 0),
        "stuck": int(stuck or 0),
    }


async def reclaim_stale_running(
    session: AsyncSession, *, claimer_id: str, older_than_seconds: int = 1800
) -> int:
    """本进程重启后，把自己名下卡在 running 的任务放回队列。"""
    cutoff = _now() - timedelta(seconds=older_than_seconds)
    result = await session.execute(
        update(Task)
        .where(
            Task.status == TaskStatus.running,
            Task.worker_id == claimer_id,
            or_(Task.started_at.is_(None), Task.started_at < cutoff),
        )
        .values(status=TaskStatus.pending, worker_id=None, next_run_at=_now())
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


def filter_by_types(stmt, types: Iterable[TaskType]):
    return stmt.where(Task.type.in_(list(types)))


__all__ = [
    "TaskClaimError",
    "backoff_seconds",
    "enqueue_task",
    "claim_tasks",
    "complete_task",
    "fail_task",
    "cancel_task",
    "requeue_task",
    "pending_confirmation_task",
    "due_task_metrics",
    "reclaim_stale_running",
    "and_",
]


async def requeue_stale_running(session: AsyncSession, *, started_before: datetime) -> int:
    """回收「卡在执行中」的任务：把开始时间早于某个时刻、却还挂在 running 的任务放回队列。

    为什么需要：Worker 重启（部署、崩溃）时，正在执行的任务不会被它自己收尾——
    状态会一直停在 running，页面上看起来就是「执行中」永远不会结束、进度永远是 0。
    这里按「开始时间早于阈值」把它们找回来：还能重试的回到 pending（重新排队），
    次数用完了就标失败并写明原因。

    返回回收条数。
    """
    rows = list(
        (
            await session.scalars(
                select(Task).where(Task.status == TaskStatus.running, Task.started_at < started_before)
            )
        ).all()
    )
    for task in rows:
        if task.attempts >= task.max_attempts:
            task.status = TaskStatus.failed
            task.error = "任务在「执行中」被中断（Worker 重启或崩溃），且重试次数已用完"
            task.completed_at = _now()
        else:
            task.status = TaskStatus.pending
            task.started_at = None
            task.lease_until = None
            task.next_run_at = _now()
            task.error = "任务在「执行中」被中断（Worker 重启），已重新排队"
    if rows:
        await session.flush()
    return len(rows)
