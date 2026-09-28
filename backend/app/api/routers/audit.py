"""审计日志：谁在什么时间对哪个号做了什么。

operator 只能看到与自己相关的记录（自己操作的，或分配到自己账号上的），
admin 看全部。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, visible_account_ids
from app.api.routers import account_label, build_order_by, ensure_utc, user_label
from app.core.audit import ACTION_LABELS
from app.models import AuditLog, TgAccount, User
from app.schemas import AuditListResponse, AuditOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])

#: 审计列表允许的排序字段（白名单）
AUDIT_SORT_FIELDS = {
    "created_at": AuditLog.created_at,
    "updated_at": AuditLog.updated_at,
    "action": AuditLog.action,
    "target_type": AuditLog.target_type,
}


@router.get("", response_model=AuditListResponse, summary="审计列表")
async def list_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    action: Optional[str] = Query(default=None, description="动作名，如 message.send"),
    user_id: Optional[uuid.UUID] = Query(default=None),
    account_id: Optional[uuid.UUID] = Query(default=None),
    bot_id: Optional[uuid.UUID] = Query(default=None),
    from_: Optional[datetime] = Query(
        default=None, alias="from", description="ISO8601，created_at >= from（含）"
    ),
    to: Optional[datetime] = Query(default=None, description="ISO8601，created_at <= to（含）"),
    sort: Optional[str] = Query(default=None, description="排序字段，见 AUDIT_SORT_FIELDS"),
    order: Optional[str] = Query(default=None, description="asc | desc，默认 desc"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AuditListResponse:
    """时间倒序；中文动作名用 core.audit.ACTION_LABELS，避免前端再维护一份映射。"""
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

    total = await session.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
    order_by = build_order_by(
        sort=sort,
        order=order,
        mapping=AUDIT_SORT_FIELDS,
        default_field="created_at",
        default_order="desc",
        tiebreaker=AuditLog.id,
    )
    logs = list(
        (
            await session.scalars(
                select(AuditLog)
                .where(*conditions)
                .order_by(*order_by)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )

    # 一次性把涉及的用户与账号查出来，避免 N+1
    user_ids = {item.user_id for item in logs if item.user_id}
    account_ids = {item.account_id for item in logs if item.account_id}
    users = {
        row.id: row
        for row in (await session.scalars(select(User).where(User.id.in_(user_ids)))).all()
    } if user_ids else {}
    accounts = {
        row.id: row
        for row in (await session.scalars(select(TgAccount).where(TgAccount.id.in_(account_ids)))).all()
    } if account_ids else {}

    items = []
    for log in logs:
        out = AuditOut.model_validate(log)
        out.action_label = ACTION_LABELS.get(log.action, log.action)
        out.user_name = user_label(users.get(log.user_id)) if log.user_id else None
        out.account_label = account_label(accounts.get(log.account_id)) if log.account_id else None
        items.append(out)

    return AuditListResponse(items=items, total=int(total or 0), page=page, page_size=page_size)
