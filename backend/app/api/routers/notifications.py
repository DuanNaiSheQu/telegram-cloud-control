"""站内通知：失败任务 / Worker 心跳丢失 / 账号异常 / 备份失败。

事实在 tasks / leases / tg_accounts 里，通知是聚合产物（`core.notifications.sync_notifications`）。
列表接口在返回前会尝试聚合一次（20 秒节流），所以刚失败的任务下一次刷新就能看到，
不必等后台协程；聚合失败只记日志，绝不让铃铛打不开。

可见范围：
- admin：全部通知；
- operator：与自己分配账号相关的通知 + 全局通知（`account_id` 为 null 的 Worker / 备份类）。
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, visible_account_ids
from app.api.routers import build_order_by, utcnow
from app.core.audit import write_audit
from app.core.notifications import sync_notifications
from app.models import (
    NOTIFICATION_KIND_LABELS,
    NOTIFICATION_LEVELS,
    Notification,
    TgAccount,
    User,
)
from app.redis_client import get_redis
from app.schemas import (
    NotificationListResponse,
    NotificationOut,
    NotificationReadAllResponse,
    NotificationReadResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

#: 通知列表允许的排序字段（白名单）
NOTIFICATION_SORT_FIELDS = {
    "created_at": Notification.created_at,
    "updated_at": Notification.updated_at,
    "kind": Notification.kind,
    "level": Notification.level,
    "is_read": Notification.is_read,
}


def _visibility_conditions(ids: Optional[List[uuid.UUID]]) -> list:
    """admin（ids=None）不过滤；operator 看自己号相关的 + 全局的。"""
    if ids is None:
        return []
    return [or_(Notification.account_id.is_(None), Notification.account_id.in_(ids))]


def _out(item: Notification, account: Optional[TgAccount] = None) -> NotificationOut:
    return NotificationOut(
        id=item.id,
        kind=item.kind,
        kind_label=NOTIFICATION_KIND_LABELS.get(item.kind, item.kind),
        level=item.level,
        title=item.title,
        body=item.body,
        link=item.link,
        account_id=item.account_id,
        account_label=account.phone_masked if account is not None else None,
        bot_id=item.bot_id,
        task_id=item.task_id,
        worker_id=item.worker_id,
        detail=item.detail if isinstance(item.detail, dict) else None,
        read=bool(item.is_read),
        read_at=item.read_at,
        created_at=item.created_at,
    )


async def _load_visible(
    session: AsyncSession, user: User, notification_id: uuid.UUID
) -> Notification:
    """取一条通知并校验可见性：不存在 404，别人的号上的一律 403。"""
    item = await session.scalar(select(Notification).where(Notification.id == notification_id))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知不存在")
    ids = await visible_account_ids(session, user)
    if ids is not None and item.account_id is not None and item.account_id not in set(ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="该通知不属于分配给你的账号"
        )
    return item


@router.get("", response_model=NotificationListResponse, summary="通知流（铃铛）")
async def list_notifications(
    unread_only: bool = Query(default=False, description="只看未读"),
    kind: Optional[str] = Query(default=None, description="task_failed | worker_lost | account_abnormal | backup_failed"),
    level: Optional[str] = Query(default=None, description="info | warning | error | success"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: Optional[str] = Query(default=None, description="排序字段，见 NOTIFICATION_SORT_FIELDS"),
    order: Optional[str] = Query(default=None, description="asc | desc，默认 desc"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> NotificationListResponse:
    """默认按时间倒序。`unread` / `counts_by_kind` 只看可见范围，不受 kind / level 筛选影响
    （铃铛角标要的是总数，不会因为当前筛选成某一类就变小）。"""
    # 前端把「全部」渲染成空字符串时按不筛选处理，别让 ?kind= 这种请求 400
    kind = (kind or "").strip() or None
    level = (level or "").strip() or None
    if kind is not None and kind not in NOTIFICATION_KIND_LABELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"kind 只能是 {' / '.join(NOTIFICATION_KIND_LABELS)}",
        )
    if level is not None and level not in NOTIFICATION_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"level 只能是 {' / '.join(NOTIFICATION_LEVELS)}",
        )

    # 先聚合一次：失败任务 / 账号异常这些刚发生的事，刷新就能看到
    try:
        await sync_notifications(session, redis=get_redis())
    except Exception:  # noqa: BLE001 - 聚合失败也要能看历史通知
        logger.warning("通知聚合失败（继续返回已有通知）", exc_info=True)
        await session.rollback()

    ids = await visible_account_ids(session, user)
    scope = _visibility_conditions(ids)
    conditions = list(scope)
    if unread_only:
        conditions.append(Notification.is_read.is_(False))
    if kind is not None:
        conditions.append(Notification.kind == kind)
    if level is not None:
        conditions.append(Notification.level == level)

    total = int(await session.scalar(select(func.count()).select_from(Notification).where(*conditions)) or 0)
    unread = int(
        await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(*scope, Notification.is_read.is_(False))
        )
        or 0
    )
    counts_by_kind: Dict[str, int] = {key: 0 for key in NOTIFICATION_KIND_LABELS}
    rows = await session.execute(
        select(Notification.kind, func.count())
        .where(*scope, Notification.is_read.is_(False))
        .group_by(Notification.kind)
    )
    for kind_value, count in rows.all():
        counts_by_kind[str(kind_value)] = int(count or 0)

    order_by = build_order_by(
        sort=sort,
        order=order,
        mapping=NOTIFICATION_SORT_FIELDS,
        default_field="created_at",
        default_order="desc",
        tiebreaker=Notification.id,
    )
    items = list(
        (
            await session.scalars(
                select(Notification)
                .where(*conditions)
                .order_by(*order_by)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    account_ids = {item.account_id for item in items if item.account_id}
    accounts = {
        row.id: row
        for row in (await session.scalars(select(TgAccount).where(TgAccount.id.in_(account_ids)))).all()
    } if account_ids else {}

    return NotificationListResponse(
        items=[_out(item, accounts.get(item.account_id)) for item in items],
        total=total,
        unread=unread,
        page=page,
        page_size=page_size,
        counts_by_kind=counts_by_kind,
    )


@router.post("/read-all", response_model=NotificationReadAllResponse, summary="全部标记为已读")
async def read_all_notifications(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> NotificationReadAllResponse:
    """只影响当前用户可见的未读通知（operator 不会顺手把别人的标记掉）。"""
    ids = await visible_account_ids(session, user)
    scope = _visibility_conditions(ids)
    items = list(
        (
            await session.scalars(
                select(Notification).where(*scope, Notification.is_read.is_(False))
            )
        ).all()
    )
    now = utcnow()
    for item in items:
        item.is_read = True
        item.read_at = now
        item.read_by = user.id
    if items:
        await write_audit(
            session,
            action="notification.read_all",
            user_id=user.id,
            target_type="notification_batch",
            target_id=str(len(items)),
            detail={"marked": len(items)},
        )
        await session.commit()
    return NotificationReadAllResponse(
        ok=True, message=f"已把 {len(items)} 条通知标记为已读", marked=len(items)
    )


@router.post("/{notification_id}/read", response_model=NotificationReadResponse, summary="标记单条已读")
async def read_notification(
    notification_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> NotificationReadResponse:
    """幂等：已读的再点一次仍然返回 ok。"""
    item = await _load_visible(session, user, notification_id)
    already = bool(item.is_read)
    if not already:
        item.is_read = True
        item.read_at = utcnow()
        item.read_by = user.id
        await write_audit(
            session,
            action="notification.read",
            user_id=user.id,
            account_id=item.account_id,
            target_type="notification",
            target_id=str(item.id),
            detail={"kind": item.kind},
        )
        await session.commit()

    account = None
    if item.account_id is not None:
        account = await session.scalar(select(TgAccount).where(TgAccount.id == item.account_id))
    return NotificationReadResponse(
        ok=True,
        message="这条通知本来就已经读过了" if already else "已标记为已读",
        notification=_out(item, account),
    )
