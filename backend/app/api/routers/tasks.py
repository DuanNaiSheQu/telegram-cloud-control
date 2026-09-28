"""任务中心：队列看得见、失败能重试、排错能取消。

重试 / 取消都走 `core.tasks` 里已有的 requeue_task / cancel_task，
保证状态流转与 Worker 侧的认领逻辑一致（退避、attempts 归零等）。
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, visible_account_ids
from app.api.routers import enum_value, publish_task_safely, task_out
from app.core.audit import write_audit
from app.core.tasks import cancel_task, requeue_task
from app.models import Bot, Task, TaskStatus, TaskType, TgAccount, User
from app.schemas import TaskActionResponse, TaskListResponse, TaskOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])

#: 允许重试的状态（契约：failed / pending_confirmation → pending，attempts 归零）
RETRYABLE_STATUSES = (TaskStatus.failed, TaskStatus.pending_confirmation)
#: 允许取消的状态：已经在跑的也允许（Worker 下一次检查状态时会跳过）
CANCELLABLE_STATUSES = (
    TaskStatus.pending,
    TaskStatus.pending_confirmation,
    TaskStatus.running,
)


async def _load_task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await session.scalar(select(Task).where(Task.id == task_id))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task


def _conditions(
    ids: Optional[List[uuid.UUID]],
    status_filter: Optional[TaskStatus],
    type_filter: Optional[TaskType],
    account_id: Optional[uuid.UUID],
    bot_id: Optional[uuid.UUID],
    only_failed: bool,
) -> list:
    conditions = []
    if ids is not None:
        # operator 只看自己号上的任务；Bot 任务不属于任何员工号，对 operator 隐藏
        conditions.append(Task.account_id.in_(ids))
    if status_filter is not None:
        conditions.append(Task.status == status_filter)
    if type_filter is not None:
        conditions.append(Task.type == type_filter)
    if account_id is not None:
        conditions.append(Task.account_id == account_id)
    if bot_id is not None:
        conditions.append(Task.bot_id == bot_id)
    if only_failed:
        conditions.append(Task.status.in_([TaskStatus.failed, TaskStatus.pending_confirmation]))
    return conditions


async def _enrich(session: AsyncSession, tasks: List[Task]) -> List[TaskOut]:
    """批量补 account_label / bot_label / created_by_name，避免 N+1。"""
    account_ids = {item.account_id for item in tasks if item.account_id}
    bot_ids = {item.bot_id for item in tasks if item.bot_id}
    user_ids = {item.created_by for item in tasks if item.created_by}
    accounts = {
        row.id: row
        for row in (await session.scalars(select(TgAccount).where(TgAccount.id.in_(account_ids)))).all()
    } if account_ids else {}
    bots = {
        row.id: row
        for row in (await session.scalars(select(Bot).where(Bot.id.in_(bot_ids)))).all()
    } if bot_ids else {}
    users = {
        row.id: row
        for row in (await session.scalars(select(User).where(User.id.in_(user_ids)))).all()
    } if user_ids else {}
    return [
        task_out(item, accounts.get(item.account_id), bots.get(item.bot_id), users.get(item.created_by))
        for item in tasks
    ]


@router.get("", response_model=TaskListResponse, summary="任务列表（分页 + 状态汇总）")
async def list_tasks(
    status_filter: Optional[TaskStatus] = Query(default=None, alias="status"),
    type_filter: Optional[TaskType] = Query(default=None, alias="type"),
    account_id: Optional[uuid.UUID] = Query(default=None),
    bot_id: Optional[uuid.UUID] = Query(default=None),
    only_failed: bool = Query(default=False, description="只看失败与等待确认的任务"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskListResponse:
    """counts 用同一批筛选条件（但不含 status），所以点状态标签时数字不会乱跳。"""
    ids = await visible_account_ids(session, user)
    conditions = _conditions(ids, status_filter, type_filter, account_id, bot_id, only_failed)

    total = await session.scalar(select(func.count()).select_from(Task).where(*conditions))
    tasks = list(
        (
            await session.scalars(
                select(Task)
                .where(*conditions)
                .order_by(Task.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )

    count_conditions = _conditions(ids, None, type_filter, account_id, bot_id, only_failed)
    rows = await session.execute(
        select(Task.status, func.count()).where(*count_conditions).group_by(Task.status)
    )
    counts = {item.value: 0 for item in TaskStatus}
    for status_value, count in rows.all():
        counts[enum_value(status_value)] = int(count or 0)

    return TaskListResponse(
        items=await _enrich(session, tasks),
        total=int(total or 0),
        page=page,
        page_size=page_size,
        counts=counts,
    )


@router.get("/{task_id}", response_model=TaskOut, summary="任务详情")
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskOut:
    """带失败原因、重试次数、Worker id，排障时看这一条就够。"""
    task = await _load_task(session, task_id)
    ids = await visible_account_ids(session, user)
    if ids is not None and (task.account_id is None or task.account_id not in set(ids)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该任务不属于分配给你的账号")
    enriched = await _enrich(session, [task])
    return enriched[0]


@router.post("/{task_id}/retry", response_model=TaskActionResponse, summary="重试任务")
async def retry_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskActionResponse:
    """只有失败 / 等待确认的任务能重试，attempts 归零后立刻可被领取。"""
    task = await _load_task(session, task_id)
    ids = await visible_account_ids(session, user)
    if ids is not None and (task.account_id is None or task.account_id not in set(ids)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该任务不属于分配给你的账号")
    if task.status not in RETRYABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态「{task.status.value}」不能重试：只允许失败或等待确认的任务",
        )
    await requeue_task(session, task)
    await write_audit(
        session,
        action="task.retry",
        user_id=user.id,
        account_id=task.account_id,
        bot_id=task.bot_id,
        target_type="task",
        target_id=str(task.id),
        detail={"type": enum_value(task.type)},
    )
    await session.commit()
    enriched = await _enrich(session, [task])
    await publish_task_safely(
        {"task_id": str(task.id), "type": enum_value(task.type), "ok": True, "detail": "已重新排队"}
    )
    logger.info("任务重试 task_id=%s by=%s", task.id, user.username)
    return TaskActionResponse(ok=True, task=enriched[0], message="已重新排队，等待 Worker 领取")


@router.post("/{task_id}/cancel", response_model=TaskActionResponse, summary="取消任务")
async def cancel_task_endpoint(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskActionResponse:
    """已完成 / 已失败的不能再取消；正在执行的任务取消后 Worker 会跳过后续步骤。"""
    task = await _load_task(session, task_id)
    ids = await visible_account_ids(session, user)
    if ids is not None and (task.account_id is None or task.account_id not in set(ids)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该任务不属于分配给你的账号")
    if task.status not in CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态「{task.status.value}」不能取消：只有待执行 / 等待确认 / 执行中的任务可以取消",
        )
    await cancel_task(session, task)
    await write_audit(
        session,
        action="task.cancel",
        user_id=user.id,
        account_id=task.account_id,
        bot_id=task.bot_id,
        target_type="task",
        target_id=str(task.id),
        detail={"type": enum_value(task.type)},
    )
    await session.commit()
    enriched = await _enrich(session, [task])
    await publish_task_safely(
        {"task_id": str(task.id), "type": enum_value(task.type), "ok": False, "detail": "已取消"}
    )
    logger.info("任务取消 task_id=%s by=%s", task.id, user.username)
    return TaskActionResponse(ok=True, task=enriched[0], message="已取消该任务")
