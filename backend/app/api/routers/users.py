"""员工账号管理：新建 / 改角色 / 改口令 / 停用 / 删除（仅 admin）。

保护性规则写在路由里：不能停用或删除自己，也不能删掉最后一个管理员，
否则会出现「谁也进不去控制台」的死局。
"""

from __future__ import annotations

import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.api.deps import get_session, require_admin
from app.api.routers.auth import user_out
from app.core.audit import write_audit
from app.models import AccountAssignment, User, UserRole
from app.schemas import UserCreate, UserOut, UserUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


async def _get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="员工不存在")
    return user


async def _admin_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.admin, User.is_active.is_(True))
        )
        or 0
    )


@router.get("", response_model=List[UserOut], summary="员工列表")
async def list_users(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> List[UserOut]:
    """只给管理员；account_count 是每个员工分配到的账号数。"""
    users = list((await session.scalars(select(User).order_by(User.username))).all())
    return [await user_out(session, item) for item in users]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="新建员工")
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserOut:
    """口令只存 bcrypt 哈希。"""
    exists = await session.scalar(select(User.id).where(User.username == payload.username))
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    user = User(
        username=payload.username,
        display_name=payload.display_name or payload.username,
        password_hash=security.hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await write_audit(
        session,
        action="user.create",
        user_id=admin.id,
        target_type="user",
        target_id=str(user.id),
        detail={"username": user.username, "role": user.role.value},
    )
    await session.commit()
    return await user_out(session, user)


@router.patch("/{user_id}", response_model=UserOut, summary="修改员工")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserOut:
    """改显示名 / 角色 / 启用状态 / 重置口令。"""
    user = await _get_user(session, user_id)
    changes: dict = {}
    target_role = payload.role if payload.role is not None else user.role
    target_active = payload.is_active if payload.is_active is not None else user.is_active

    # 自己把自己降级 / 停用会让当前会话立刻失效，直接拦住更清楚
    if user.id == admin.id and (target_role != UserRole.admin or not target_active):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能把自己降级或停用（请让另一位管理员操作）",
        )
    # 最后一个管理员不能被降级或停用
    if (
        user.role == UserRole.admin
        and (target_role != UserRole.admin or not target_active)
        and await _admin_count(session) <= 1
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少要保留一个启用状态的管理员")

    if payload.display_name is not None:
        user.display_name = payload.display_name
        changes["display_name"] = payload.display_name
    if payload.role is not None:
        user.role = payload.role
        changes["role"] = payload.role.value
    if payload.is_active is not None:
        user.is_active = payload.is_active
        changes["is_active"] = payload.is_active
    if payload.password is not None:
        user.password_hash = security.hash_password(payload.password)
        changes["password"] = "reset"

    await write_audit(
        session,
        action="user.update",
        user_id=admin.id,
        target_type="user",
        target_id=str(user.id),
        detail=changes,
    )
    await session.commit()
    return await user_out(session, user)


@router.delete("/{user_id}", summary="删除员工")
async def delete_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict:
    """删员工会级联删掉他的分配；审计行保留（user_id 置空），历史操作仍可追溯。"""
    user = await _get_user(session, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除自己")
    if user.role == UserRole.admin and await _admin_count(session) <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少要保留一个管理员")

    assignments = await session.scalar(
        select(func.count()).select_from(AccountAssignment).where(AccountAssignment.user_id == user.id)
    )
    username = user.username
    await write_audit(
        session,
        action="user.delete",
        user_id=admin.id,
        target_type="user",
        target_id=str(user.id),
        detail={"username": username, "assignments": int(assignments or 0)},
    )
    await session.delete(user)
    await session.commit()
    return {"ok": True, "message": f"已删除员工 {username}"}
