"""员工分配：谁可以操作哪个号（account_assignments）。

这是 operator 权限的唯一来源：`deps.visible_account_ids` 读的就是这张表。
管理员工属于管理员动作，所以这里全部要求 admin。
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin
from app.api.routers import parse_uuid_csv
from app.core.audit import write_audit
from app.models import AccountAssignment, TgAccount, User
from app.schemas import AssignmentCreate, AssignmentOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assignments", tags=["assignments"])


async def _assignment_out(session: AsyncSession, user: User) -> AssignmentOut:
    rows = await session.scalars(
        select(AccountAssignment.account_id).where(AccountAssignment.user_id == user.id)
    )
    account_ids = list(rows.all())
    return AssignmentOut(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        account_ids=account_ids,
        account_count=len(account_ids),
    )


@router.get("", response_model=List[AssignmentOut], summary="员工分配总览")
async def list_assignments(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> List[AssignmentOut]:
    """每个员工一行，带他名下的账号 id 列表。"""
    users = list((await session.scalars(select(User).order_by(User.username))).all())
    return [await _assignment_out(session, item) for item in users]


@router.post("", response_model=AssignmentOut, summary="把账号分配给员工")
async def create_assignments(
    payload: AssignmentCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> AssignmentOut:
    """重复分配自动跳过（唯一约束 user_id+account_id），不会报错。"""
    target = await session.scalar(select(User).where(User.id == payload.user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="员工不存在")
    if not payload.account_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="account_ids 不能为空")

    accounts = list(
        (await session.scalars(select(TgAccount).where(TgAccount.id.in_(payload.account_ids)))).all()
    )
    found = {item.id for item in accounts}
    missing = [item for item in payload.account_ids if item not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"账号不存在：{', '.join(str(item) for item in missing)}",
        )

    existing = set(
        (
            await session.scalars(
                select(AccountAssignment.account_id).where(AccountAssignment.user_id == target.id)
            )
        ).all()
    )
    added = [item for item in payload.account_ids if item not in existing]
    for account_id in added:
        session.add(AccountAssignment(user_id=target.id, account_id=account_id))
    await session.flush()
    await write_audit(
        session,
        action="account.assign",
        user_id=admin.id,
        target_type="user",
        target_id=str(target.id),
        detail={"added": [str(item) for item in added]},
    )
    await session.commit()
    return await _assignment_out(session, target)


@router.delete("", summary="取消分配")
async def delete_assignments(
    user_id: uuid.UUID = Query(..., description="员工 id"),
    account_ids: Optional[str] = Query(default=None, description="逗号分隔的账号 id；不传 = 清空该员工全部分配"),
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict:
    """取消后该员工立刻看不到这些号（可见范围每次都实时查库，不做缓存）。"""
    target = await session.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="员工不存在")

    ids = parse_uuid_csv(account_ids)
    stmt = delete(AccountAssignment).where(AccountAssignment.user_id == user_id)
    if ids:
        stmt = stmt.where(AccountAssignment.account_id.in_(ids))
    result = await session.execute(stmt)
    removed = int(result.rowcount or 0)
    await write_audit(
        session,
        action="account.unassign",
        user_id=admin.id,
        target_type="user",
        target_id=str(target.id),
        detail={"removed": [str(item) for item in ids] if ids else "all", "count": removed},
    )
    await session.commit()
    message = (
        f"已取消 {removed} 个账号的分配"
        if ids
        else f"已清空该员工的全部账号分配（{removed} 个）"
    )
    return {"ok": True, "message": message}
