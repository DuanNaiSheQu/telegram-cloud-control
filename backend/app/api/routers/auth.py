"""登录控制台：签发 JWT、查当前用户、退出。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.api.deps import get_current_user, get_session
from app.config import settings
from app.core.audit import write_audit
from app.models import AccountAssignment, User
from app.schemas import LoginRequest, TokenResponse, UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


async def user_out(session: AsyncSession, user: User) -> UserOut:
    """UserOut.account_count = 该员工被分配到的账号数（管理员显示全部账号数）。"""
    from app.models import UserRole

    if user.role == UserRole.admin:
        from app.models import TgAccount

        count = await session.scalar(select(func.count()).select_from(TgAccount))
    else:
        count = await session.scalar(
            select(func.count())
            .select_from(AccountAssignment)
            .where(AccountAssignment.user_id == user.id)
        )
    out = UserOut.model_validate(user)
    out.account_count = int(count or 0)
    return out


@router.post("/login", response_model=TokenResponse, summary="口令登录换 JWT")
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    """校验口令后签发 JWT；失败只回「用户名或密码错误」，不区分是哪个错（避免枚举账号）。"""
    user = await session.scalar(select(User).where(User.username == payload.username))
    if user is None or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该员工已被停用")

    user.last_login_at = func.now()
    await write_audit(
        session,
        action="login",
        user_id=user.id,
        target_type="user",
        target_id=str(user.id),
        detail={"username": user.username},
    )
    await session.commit()
    await session.refresh(user)

    token = security.create_access_token(
        str(user.id), extra={"username": user.username, "role": user.role.value}
    )
    logger.info("员工登录控制台 username=%s role=%s", user.username, user.role.value)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        user=await user_out(session, user),
    )


@router.get("/me", response_model=UserOut, summary="当前登录用户")
async def me(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> UserOut:
    """前端刷新页面时用它恢复登录态。"""
    return await user_out(session, user)


@router.post("/logout", summary="退出登录")
async def logout(user: User = Depends(get_current_user)) -> dict:
    """JWT 无状态：服务端不维护会话，客户端丢掉 token 即可（审计已有登录记录）。"""
    logger.info("员工退出控制台 username=%s", user.username)
    return {"ok": True, "message": "已退出登录，请在客户端清除本地令牌"}
