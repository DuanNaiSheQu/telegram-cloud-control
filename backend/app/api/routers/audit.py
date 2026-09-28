"""审计日志：谁在什么时间对哪个号做了什么。

operator 只能看到与自己相关的记录（自己操作的，或分配到自己账号上的），
admin 看全部。
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, visible_account_ids
from app.api.routers import account_label, user_label
from app.core.audit import ACTION_LABELS
from app.models import AuditLog, TgAccount, User
from app.schemas import AuditListResponse, AuditOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditListResponse, summary="审计列表")
async def list_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    action: Optional[str] = Query(default=None, description="动作名，如 message.send"),
    user_id: Optional[uuid.UUID] = Query(default=None),
    account_id: Optional[uuid.UUID] = Query(default=None),
    bot_id: Optional[uuid.UUID] = Query(default=None),
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

    total = await session.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
    logs = list(
        (
            await session.scalars(
                select(AuditLog)
                .where(*conditions)
                .order_by(AuditLog.created_at.desc())
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
