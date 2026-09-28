"""API 依赖：数据库会话、JWT 登录态、按角色收敛可见账号范围。

权限模型（与 docs/API_CONTRACT.md 第 1 节一致）：
- admin：看 / 操作全部账号；
- operator：只能看 / 操作 account_assignments 里分配到的号，越权一律 403。

列表、筛选、详情、发送、检测都要过这里，避免只在某个路由上做限制造成越权。
"""

from __future__ import annotations

import logging
import uuid
from typing import AsyncIterator, Iterable, List, Optional, Sequence, Set

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.db import SessionFactory
from app.models import AccountAssignment, Dialog, DialogChannel, User, UserRole

logger = logging.getLogger(__name__)

#: auto_error=False：缺 Authorization 头时我们自己回 401（而不是 FastAPI 默认的 403）
bearer_scheme = HTTPBearer(auto_error=False, description="登录 /api/auth/login 拿到的 JWT")


async def get_session() -> AsyncIterator[AsyncSession]:
    """请求级会话。正常结束不自动提交，由各路由在改完数据后显式 commit。"""
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def load_user_by_token(session: AsyncSession, token: str) -> Optional[User]:
    """解析 JWT 并取回用户；令牌无效、用户不存在或已停用都返回 None。"""
    payload = security.decode_access_token(token)
    if not payload:
        return None
    subject = payload.get("sub")
    if not subject:
        return None
    try:
        user_id = uuid.UUID(str(subject))
    except (ValueError, TypeError):
        return None
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        return None
    return user


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """解析 `Authorization: Bearer <JWT>`，无效一律 401。"""
    if credentials is None or not credentials.credentials:
        raise _unauthorized("缺少访问令牌：请先登录并在 Authorization 头里带上 Bearer <token>")
    user = await load_user_by_token(session, credentials.credentials)
    if user is None:
        raise _unauthorized("访问令牌无效或已过期，请重新登录")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """员工管理、Bot 管理这类全局动作只给 admin。"""
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def is_admin(user: User) -> bool:
    return user.role == UserRole.admin


async def visible_account_ids(session: AsyncSession, user: User) -> Optional[List[uuid.UUID]]:
    """当前用户能看到的账号 id。

    admin 返回 None 表示「不限」；operator 返回分配列表（可能是空列表 = 什么都看不到）。
    """
    if is_admin(user):
        return None
    rows = await session.scalars(
        select(AccountAssignment.account_id).where(AccountAssignment.user_id == user.id)
    )
    return list(rows.all())


def scope_clause(column, ids: Optional[Sequence[uuid.UUID]]):
    """把可见范围拼进 where；ids=None 表示不过滤。空列表会渲染成恒假条件。"""
    if ids is None:
        return None
    return column.in_(list(ids))


async def visible_account_id_set(session: AsyncSession, user: User) -> Optional[Set[uuid.UUID]]:
    ids = await visible_account_ids(session, user)
    return None if ids is None else set(ids)


async def assert_account_access(
    session: AsyncSession, user: User, account_id: Optional[uuid.UUID]
) -> None:
    """单号权限；无权限 403。"""
    await assert_accounts_access(session, user, [account_id] if account_id else [])


async def assert_accounts_access(
    session: AsyncSession, user: User, account_ids: Iterable[Optional[uuid.UUID]]
) -> None:
    """批量版本：一次查询判完，避免在循环里逐个查库。"""
    wanted = {item for item in account_ids if item is not None}
    if not wanted:
        return
    allowed = await visible_account_id_set(session, user)
    if allowed is None:
        return
    forbidden = wanted - allowed
    if forbidden:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"账号未分配给你：{', '.join(str(item) for item in sorted(forbidden, key=str))}",
        )


async def assert_dialog_access(session: AsyncSession, user: User, dialog: Dialog) -> None:
    """会话权限：用户号会话跟着账号分配走；Bot 会话是全局的（不属于某个人）。"""
    if is_admin(user):
        return
    channel = dialog.channel.value if hasattr(dialog.channel, "value") else str(dialog.channel)
    if channel == DialogChannel.bot.value:
        return
    if dialog.account_id is None:
        return
    await assert_account_access(session, user, dialog.account_id)


__all__ = [
    "get_session",
    "get_current_user",
    "require_admin",
    "is_admin",
    "load_user_by_token",
    "visible_account_ids",
    "visible_account_id_set",
    "scope_clause",
    "assert_account_access",
    "assert_accounts_access",
    "assert_dialog_access",
    "bearer_scheme",
]
