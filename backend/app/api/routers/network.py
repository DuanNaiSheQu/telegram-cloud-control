"""网络：账号固定的出站地址（代理）。

用户名 / 口令加密入库（`security.encrypt_secret`），接口只回 `has_auth`，永不回明文。
"""

from __future__ import annotations

import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.api.deps import assert_accounts_access, get_current_user, get_session
from app.api.routers import AccountIdsRequest, proxy_out
from app.core.audit import write_audit
from app.models import Proxy, TgAccount, User
from app.schemas import ProxyCreate, ProxyOut, ProxyUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proxies", tags=["network"])


async def _get_proxy(session: AsyncSession, proxy_id: uuid.UUID) -> Proxy:
    proxy = await session.scalar(select(Proxy).where(Proxy.id == proxy_id))
    if proxy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="代理不存在")
    return proxy


async def _counts(session: AsyncSession) -> dict:
    rows = await session.execute(select(TgAccount.proxy_id, func.count()).group_by(TgAccount.proxy_id))
    return {row[0]: int(row[1] or 0) for row in rows.all() if row[0] is not None}


@router.get("", response_model=List[ProxyOut], summary="代理列表")
async def list_proxies(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[ProxyOut]:
    """endpoint 形如 socks5://host:port；has_auth 表示存了用户名 / 口令。"""
    proxies = list((await session.scalars(select(Proxy).order_by(Proxy.name))).all())
    counts = await _counts(session)
    return [proxy_out(item, counts.get(item.id, 0)) for item in proxies]


@router.post("", response_model=ProxyOut, status_code=status.HTTP_201_CREATED, summary="新建代理")
async def create_proxy(
    payload: ProxyCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProxyOut:
    """代理名唯一；用户名 / 口令加密保存。"""
    exists = await session.scalar(select(Proxy.id).where(Proxy.name == payload.name))
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="代理名已存在")
    proxy = Proxy(
        name=payload.name,
        scheme=payload.scheme,
        host=payload.host,
        port=payload.port,
        username_enc=security.encrypt_secret(payload.username) if payload.username else None,
        password_enc=security.encrypt_secret(payload.password) if payload.password else None,
        enabled=payload.enabled,
        remark=payload.remark or "",
    )
    session.add(proxy)
    await session.flush()
    await write_audit(
        session,
        action="proxy.create",
        user_id=user.id,
        target_type="proxy",
        target_id=str(proxy.id),
        detail={"name": proxy.name, "endpoint": proxy.endpoint, "has_auth": bool(proxy.username_enc)},
    )
    await session.commit()
    return proxy_out(proxy, 0)


@router.patch("/{proxy_id}", response_model=ProxyOut, summary="修改代理")
async def update_proxy(
    proxy_id: uuid.UUID,
    payload: ProxyUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProxyOut:
    """不传 username / password 就保持原值（前端留空 = 不改）。"""
    proxy = await _get_proxy(session, proxy_id)
    if payload.name is not None and payload.name != proxy.name:
        exists = await session.scalar(select(Proxy.id).where(Proxy.name == payload.name))
        if exists is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="代理名已存在")
        proxy.name = payload.name
    for field in ("scheme", "host", "port", "enabled", "remark"):
        value = getattr(payload, field)
        if value is not None:
            setattr(proxy, field, value)
    if payload.username is not None:
        proxy.username_enc = security.encrypt_secret(payload.username) if payload.username else None
    if payload.password is not None:
        proxy.password_enc = security.encrypt_secret(payload.password) if payload.password else None

    await write_audit(
        session,
        action="proxy.update",
        user_id=user.id,
        target_type="proxy",
        target_id=str(proxy.id),
        detail=payload.model_dump(exclude_none=True, exclude={"username", "password"}),
    )
    await session.commit()
    counts = await _counts(session)
    return proxy_out(proxy, counts.get(proxy.id, 0))


@router.delete("/{proxy_id}", summary="删除代理")
async def delete_proxy(
    proxy_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """删代理不会删号：tg_accounts.proxy_id 外键是 ON DELETE SET NULL，号变成直连。"""
    proxy = await _get_proxy(session, proxy_id)
    name = proxy.name
    session.delete(proxy)
    await write_audit(
        session,
        action="proxy.delete",
        user_id=user.id,
        target_type="proxy",
        target_id=str(proxy_id),
        detail={"name": name},
    )
    await session.commit()
    return {"ok": True, "message": f"已删除代理「{name}」，使用它的账号改为直连"}


@router.post("/{proxy_id}/accounts", summary="把账号挂到这个代理上")
async def bind_accounts(
    proxy_id: uuid.UUID,
    payload: AccountIdsRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """一个号同一时刻只用一个出站地址；worker 认领时读取这个字段。"""
    proxy = await _get_proxy(session, proxy_id)
    if not payload.account_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="account_ids 不能为空")
    await assert_accounts_access(session, user, payload.account_ids)
    rows = await session.scalars(select(TgAccount).where(TgAccount.id.in_(payload.account_ids)))
    accounts = list(rows.all())
    for account in accounts:
        account.proxy_id = proxy.id
    await write_audit(
        session,
        action="proxy.update",
        user_id=user.id,
        target_type="proxy",
        target_id=str(proxy.id),
        detail={"bound": [str(item.id) for item in accounts]},
    )
    await session.commit()
    return {"ok": True, "message": f"已把 {len(accounts)} 个账号挂到代理「{proxy.name}」"}
