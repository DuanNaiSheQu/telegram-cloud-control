"""账号分组：内部标签，用来把号分给同事。"""

from __future__ import annotations

import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    assert_accounts_access,
    get_current_user,
    get_session,
)
from app.api.routers import AccountIdsRequest, group_out
from app.core.audit import write_audit
from app.models import AccountGroup, TgAccount, User
from app.schemas import GroupCreate, GroupOut, GroupUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/groups", tags=["groups"])


async def _get_group(session: AsyncSession, group_id: uuid.UUID) -> AccountGroup:
    group = await session.scalar(select(AccountGroup).where(AccountGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分组不存在")
    return group


async def _counts(session: AsyncSession) -> dict:
    rows = await session.execute(
        select(TgAccount.group_id, func.count()).group_by(TgAccount.group_id)
    )
    return {row[0]: int(row[1] or 0) for row in rows.all() if row[0] is not None}


@router.get("", response_model=List[GroupOut], summary="分组列表")
async def list_groups(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[GroupOut]:
    """带上每组账号数，前端直接渲染标签页。"""
    groups = list((await session.scalars(select(AccountGroup).order_by(AccountGroup.name))).all())
    counts = await _counts(session)
    return [group_out(item, counts.get(item.id, 0)) for item in groups]


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED, summary="新建分组")
async def create_group(
    payload: GroupCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> GroupOut:
    """分组名唯一，重名直接 409，避免前端出现两个同名标签。"""
    exists = await session.scalar(select(AccountGroup.id).where(AccountGroup.name == payload.name))
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="分组名已存在")
    group = AccountGroup(name=payload.name, description=payload.description or "")
    session.add(group)
    await session.flush()
    await write_audit(
        session,
        action="group.create",
        user_id=user.id,
        target_type="group",
        target_id=str(group.id),
        detail={"name": group.name},
    )
    await session.commit()
    return group_out(group, 0)


@router.patch("/{group_id}", response_model=GroupOut, summary="修改分组")
async def update_group(
    group_id: uuid.UUID,
    payload: GroupUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> GroupOut:
    """改名 / 改备注。"""
    group = await _get_group(session, group_id)
    if payload.name is not None and payload.name != group.name:
        exists = await session.scalar(select(AccountGroup.id).where(AccountGroup.name == payload.name))
        if exists is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="分组名已存在")
        group.name = payload.name
    if payload.description is not None:
        group.description = payload.description
    await write_audit(
        session,
        action="group.update",
        user_id=user.id,
        target_type="group",
        target_id=str(group.id),
        detail=payload.model_dump(exclude_none=True),
    )
    await session.commit()
    counts = await _counts(session)
    return group_out(group, counts.get(group.id, 0))


@router.delete("/{group_id}", summary="删除分组")
async def delete_group(
    group_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """删分组不会删号：tg_accounts.group_id 外键是 ON DELETE SET NULL，号回到「未分组」。"""
    group = await _get_group(session, group_id)
    name = group.name
    session.delete(group)
    await write_audit(
        session,
        action="group.delete",
        user_id=user.id,
        target_type="group",
        target_id=str(group_id),
        detail={"name": name},
    )
    await session.commit()
    return {"ok": True, "message": f"已删除分组「{name}」，组内账号回到未分组"}


@router.post("/{group_id}/accounts", summary="把账号加入分组")
async def add_accounts(
    group_id: uuid.UUID,
    payload: AccountIdsRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """只改 tg_accounts.group_id；operator 只能操作分配到的号。"""
    group = await _get_group(session, group_id)
    accounts = await _resolve_accounts(session, user, payload.account_ids)
    for account in accounts:
        account.group_id = group.id
    await write_audit(
        session,
        action="group.update",
        user_id=user.id,
        target_type="group",
        target_id=str(group.id),
        detail={"added": [str(item.id) for item in accounts]},
    )
    await session.commit()
    return {"ok": True, "message": f"已把 {len(accounts)} 个账号加入分组「{group.name}」"}


@router.post("/{group_id}/accounts/remove", summary="把账号移出分组")
async def remove_accounts(
    group_id: uuid.UUID,
    payload: AccountIdsRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """移出分组 = group_id 置空，号本身不动。"""
    group = await _get_group(session, group_id)
    accounts = await _resolve_accounts(session, user, payload.account_ids)
    for account in accounts:
        if account.group_id == group.id:
            account.group_id = None
    await write_audit(
        session,
        action="group.update",
        user_id=user.id,
        target_type="group",
        target_id=str(group.id),
        detail={"removed": [str(item.id) for item in accounts]},
    )
    await session.commit()
    return {"ok": True, "message": f"已把 {len(accounts)} 个账号移出分组「{group.name}」"}


async def _resolve_accounts(
    session: AsyncSession, user: User, account_ids: List[uuid.UUID]
) -> List[TgAccount]:
    if not account_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="account_ids 不能为空")
    await assert_accounts_access(session, user, account_ids)
    rows = await session.scalars(select(TgAccount).where(TgAccount.id.in_(account_ids)))
    accounts = list(rows.all())
    found = {item.id for item in accounts}
    missing = [item for item in account_ids if item not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"账号不存在：{', '.join(str(item) for item in missing)}",
        )
    return accounts
