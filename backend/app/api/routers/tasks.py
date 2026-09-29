"""任务中心：队列看得见、失败能重试、排错能取消。

重试 / 取消都走 `core.tasks` 里已有的 requeue_task / cancel_task，
保证状态流转与 Worker 侧的认领逻辑一致（退避、attempts 归零等）。
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, visible_account_ids
from app.api.routers import build_order_by, dedupe, enum_value, publish_task_safely, task_out
from app.core.audit import write_audit
from app.core.tasks import cancel_task, requeue_task
from app.models import (
    TASK_STATUS_LABELS,
    TASK_TYPE_LABELS,
    Bot,
    Task,
    TaskStatus,
    TaskType,
    TgAccount,
    User,
)
from app.schemas import (
    TaskActionResponse,
    TaskBulkRetryItem,
    TaskBulkRetryRequest,
    TaskBulkRetryResponse,
    TaskListResponse,
    TaskOut,
)

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

#: 允许**批量**重试的任务类型（Lead 定稿）：只放「读/探测/同步/改自己资料/转发」这类不会对外发消息的动作。
#: 发送类（send_message）与登录类（login_*）、Bot 回复类（bot_reply / reply_to_origin）批量重试等于
#: 批量发出或批量登录，与规划「不做这些」冲突，只能在任务详情里单独重试。
BULK_RETRY_ALLOWED_TYPES = (
    TaskType.sync_dialogs,
    TaskType.sync_messages,
    TaskType.account_check,
    TaskType.update_profile,
    TaskType.relay_to_staff,
    TaskType.bulk_pm,
    TaskType.group_broadcast,
    TaskType.material_send,
    TaskType.join_group,
    TaskType.leave_group,
    TaskType.force_add_member,
    TaskType.storm_chat,
    TaskType.persona_chat,
    TaskType.collect_group,
    TaskType.collect_members,
    TaskType.collect_link,
    TaskType.sync_official,
    TaskType.warmup_activity,
    TaskType.appeal_spam,
)

#: 被类型过滤拦下时给前端的统一提示
BULK_RETRY_TYPE_BLOCKED_MESSAGE = "该任务类型不允许批量重试，请在任务详情里单独重试"

#: 任务列表允许的排序字段（白名单）
TASK_SORT_FIELDS = {
    "created_at": Task.created_at,
    "updated_at": Task.updated_at,
    "status": Task.status,
    "type": Task.type,
    "priority": Task.priority,
    "attempts": Task.attempts,
    "next_run_at": Task.next_run_at,
    "started_at": Task.started_at,
    "completed_at": Task.completed_at,
}


async def _load_task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await session.scalar(select(Task).where(Task.id == task_id))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task


def task_filter_conditions(
    ids: Optional[List[uuid.UUID]],
    status_filter: Optional[TaskStatus],
    type_filter: Optional[TaskType],
    account_id: Optional[uuid.UUID],
    bot_id: Optional[uuid.UUID],
    only_failed: bool,
    batch: Optional[str] = None,
) -> list:
    """任务列表 / 导出的公共筛选条件（多个调用方共用一份，口径才不会走偏）。"""
    conditions = []
    if batch:
        conditions.append(Task.payload["batch_id"].astext == batch)
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


@router.get("/{task_id}/logs", summary="任务实时日志（执行过程中的每一步）")
async def task_logs(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """给任务详情/展开行用：读执行过程中写入的进度与日志。

    多账户任务（例如一批号各发一批私信）每一号是一条任务，这里给的是**这一条**的实时进度：
    `stage` 当前阶段、`detail` 最近一步做了什么的文字、`logs` 最近 50 条时间线。
    """
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    ids = await visible_account_ids(session, user)
    if ids is not None and task.account_id is not None and task.account_id not in set(ids):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该任务不属于分配给你的账号")

    result = task.result if isinstance(task.result, dict) else {}
    return {
        "task_id": str(task.id),
        "type": enum_value(task.type),
        "type_label": TASK_TYPE_LABELS.get(enum_value(task.type), enum_value(task.type)),
        "status": enum_value(task.status),
        "status_label": TASK_STATUS_LABELS.get(enum_value(task.status), enum_value(task.status)),
        "stage": result.get("stage") or ("done" if enum_value(task.status) == "completed" else ""),
        "detail": result.get("detail") or "",
        "progress": {
            key: result.get(key)
            for key in ("sent", "total", "joined", "fetched", "target_count")
            if result.get(key) is not None
        },
        "logs": result.get("logs") or [],
        "error": task.error or "",
        "started_at": task.started_at,
        "completed_at": task.completed_at,
    }


@router.get("", response_model=TaskListResponse, summary="任务列表（分页 + 状态汇总）")
async def list_tasks(
    status_filter: Optional[TaskStatus] = Query(default=None, alias="status"),
    type_filter: Optional[TaskType] = Query(default=None, alias="type"),
    account_id: Optional[uuid.UUID] = Query(default=None),
    bot_id: Optional[uuid.UUID] = Query(default=None),
    only_failed: bool = Query(default=False, description="只看失败与等待确认的任务"),
    batch: Optional[str] = Query(
        default=None,
        description=(
            "按批次筛选：同一次提交（选 N 个号做同一件事）生成的任务共享 payload.batch_id，"
            "传它就能只看这一批，而不是在一堆单条任务里翻"
        ),
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: Optional[str] = Query(default=None, description="排序字段，见 TASK_SORT_FIELDS"),
    order: Optional[str] = Query(default=None, description="asc | desc，默认 desc"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskListResponse:
    """counts 用同一批筛选条件（但不含 status），所以点状态标签时数字不会乱跳。"""
    ids = await visible_account_ids(session, user)
    conditions = task_filter_conditions(ids, status_filter, type_filter, account_id, bot_id, only_failed, batch)

    total = await session.scalar(select(func.count()).select_from(Task).where(*conditions))
    order_by = build_order_by(
        sort=sort,
        order=order,
        mapping=TASK_SORT_FIELDS,
        default_field="created_at",
        default_order="desc",
        tiebreaker=Task.id,
    )
    tasks = list(
        (
            await session.scalars(
                select(Task)
                .where(*conditions)
                .order_by(*order_by)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )

    count_conditions = task_filter_conditions(ids, None, type_filter, account_id, bot_id, only_failed, batch)
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


@router.post("/bulk/retry", response_model=TaskBulkRetryResponse, summary="批量重试任务（最多 200 条）")
async def bulk_retry_tasks(
    payload: TaskBulkRetryRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskBulkRetryResponse:
    """对一批任务执行单条重试的同一套语义（failed / pending_confirmation → pending，attempts 归零）。

    逐条给结果，**不会因为某一条不可重试就整体失败**：
    - 任务不存在 → `ok:false, "任务不存在"`；
    - operator 拿到不属于自己账号的任务 → `ok:false, "账号未分配给你"`（不 500、不泄露任务内容）；
    - 类型不在白名单（发送类 / 登录类 / Bot 回复类）→ `ok:false, "该任务类型不允许批量重试，请在任务详情里单独重试"`；
    - 状态不可重试（已在执行 / 已完成 / 已取消）→ `ok:false, "当前状态「…」不能重试…"`；
    - 重复传同一个 id 只处理一次。

    类型白名单见 `BULK_RETRY_ALLOWED_TYPES`：批量只重试同步 / 检测 / 改自己资料 / 转发这类动作，
    **不给**批量发出消息与批量登录留口子（单条 `/{task_id}/retry` 不受此限制）。

    注意：这个路由必须排在 `/{task_id}/retry` 之前，否则 "bulk" 会被当作 UUID 去解析（422）。
    """
    wanted = dedupe(payload.task_ids)
    if not wanted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="task_ids 不能为空")

    ids = await visible_account_ids(session, user)
    allowed = None if ids is None else set(ids)
    found: Dict[uuid.UUID, Task] = {
        item.id: item
        for item in (await session.scalars(select(Task).where(Task.id.in_(wanted)))).all()
    }

    results: List[TaskBulkRetryItem] = []
    retried: List[Task] = []
    blocked_types = 0
    for task_id in wanted:
        task = found.get(task_id)
        if task is None:
            results.append(TaskBulkRetryItem(task_id=task_id, ok=False, message="任务不存在"))
            continue
        if allowed is not None and (task.account_id is None or task.account_id not in allowed):
            results.append(TaskBulkRetryItem(task_id=task_id, ok=False, message="账号未分配给你"))
            continue
        # 类型先于状态判断：发送类 / 登录类无论什么状态都不允许批量重试
        if task.type not in BULK_RETRY_ALLOWED_TYPES:
            blocked_types += 1
            results.append(
                TaskBulkRetryItem(task_id=task_id, ok=False, message=BULK_RETRY_TYPE_BLOCKED_MESSAGE)
            )
            continue
        if task.status not in RETRYABLE_STATUSES:
            status_label = task.status.value if hasattr(task.status, "value") else str(task.status)
            results.append(
                TaskBulkRetryItem(
                    task_id=task_id,
                    ok=False,
                    message=f"当前状态「{status_label}」不能重试：只允许失败或等待确认的任务",
                )
            )
            continue
        await requeue_task(session, task)
        retried.append(task)
        results.append(TaskBulkRetryItem(task_id=task_id, ok=True, message="已重新排队，等待 Worker 领取"))

    failed = len(results) - len(retried)
    await write_audit(
        session,
        action="task.bulk_retry",
        user_id=user.id,
        target_type="task_batch",
        target_id=str(len(wanted)),
        detail={
            "requested": len(wanted),
            "succeeded": len(retried),
            "failed": failed,
            "blocked_types": blocked_types,
            "task_ids": [str(item) for item in wanted[:200]],
        },
    )
    await session.commit()
    for task in retried:
        await publish_task_safely(
            {"task_id": str(task.id), "type": enum_value(task.type), "ok": True, "detail": "已重新排队"}
        )
    logger.info("批量重试任务 by=%s 成功=%s 失败=%s", user.username, len(retried), failed)
    return TaskBulkRetryResponse(
        ok=failed == 0,
        requested=len(wanted),
        succeeded=len(retried),
        failed=failed,
        results=results,
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
