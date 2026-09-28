"""账号租约：Worker 认领、每 10 秒续租、退出时释放。

一个用户号同一时刻只属于一个 Worker。过期后由其他副本认领。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CLAIMABLE_STATUSES, AccountStatus, CurrentTask, Lease, TgAccount


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def acquire_leases(
    session: AsyncSession,
    *,
    worker_id: str,
    limit: int,
    ttl_seconds: int | None = None,
) -> list[uuid.UUID]:
    """认领一批没有有效租约的账号。"""
    ttl = ttl_seconds or settings.lease_ttl_seconds
    now = _now()

    stmt = (
        select(TgAccount.id)
        .outerjoin(Lease, Lease.account_id == TgAccount.id)
        .where(
            TgAccount.status.in_(list(CLAIMABLE_STATUSES)),
            or_(Lease.account_id.is_(None), Lease.lease_until < now),
        )
        .order_by(TgAccount.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True, of=TgAccount)
    )
    account_ids = list((await session.scalars(stmt)).all())
    if not account_ids:
        return []

    values = [
        {
            "account_id": account_id,
            "worker_id": worker_id,
            "lease_until": now + timedelta(seconds=ttl),
            "last_heartbeat": now,
        }
        for account_id in account_ids
    ]
    stmt_upsert = pg_insert(Lease).values(values)
    stmt_upsert = stmt_upsert.on_conflict_do_update(
        index_elements=[Lease.account_id],
        set_={
            "worker_id": stmt_upsert.excluded.worker_id,
            "lease_until": stmt_upsert.excluded.lease_until,
            "last_heartbeat": stmt_upsert.excluded.last_heartbeat,
            "updated_at": now,
        },
    )
    await session.execute(stmt_upsert)
    await session.commit()
    return account_ids


async def renew_leases(
    session: AsyncSession,
    *,
    worker_id: str,
    ttl_seconds: int | None = None,
) -> list[uuid.UUID]:
    """续租，返回仍然持有的账号。"""
    ttl = ttl_seconds or settings.lease_ttl_seconds
    now = _now()
    stmt = (
        update(Lease)
        .where(Lease.worker_id == worker_id)
        .values(lease_until=now + timedelta(seconds=ttl), last_heartbeat=now, updated_at=now)
        .returning(Lease.account_id)
    )
    account_ids = [row[0] for row in (await session.execute(stmt)).all()]
    if account_ids:
        await session.execute(
            update(TgAccount)
            .where(TgAccount.id.in_(account_ids))
            .values(last_heartbeat=now)
        )
    await session.commit()
    return account_ids


async def release_leases(session: AsyncSession, *, worker_id: str) -> list[uuid.UUID]:
    """进程退出时先放开租约，其他副本可以立刻接管。"""
    stmt = delete(Lease).where(Lease.worker_id == worker_id).returning(Lease.account_id)
    account_ids = [row[0] for row in (await session.execute(stmt)).all()]
    if account_ids:
        await session.execute(
            update(TgAccount)
            .where(TgAccount.id.in_(account_ids))
            .values(current_task=CurrentTask.idle)
        )
    await session.commit()
    return account_ids


async def release_account(session: AsyncSession, *, account_id: uuid.UUID, worker_id: str | None = None) -> bool:
    """单个号异常时只清它的租约，不重启全部连接。"""
    stmt = delete(Lease).where(Lease.account_id == account_id)
    if worker_id:
        stmt = stmt.where(Lease.worker_id == worker_id)
    result = await session.execute(stmt)
    await session.execute(
        update(TgAccount).where(TgAccount.id == account_id).values(current_task=CurrentTask.idle)
    )
    await session.commit()
    return bool(result.rowcount)


async def owned_account_ids(session: AsyncSession, *, worker_id: str) -> list[uuid.UUID]:
    stmt = select(Lease.account_id).where(Lease.worker_id == worker_id)
    return list((await session.scalars(stmt)).all())


async def lease_holders(session: AsyncSession, account_ids: Sequence[uuid.UUID]) -> dict:
    """account_id -> worker_id，页面展示用。"""
    if not account_ids:
        return {}
    stmt = select(Lease.account_id, Lease.worker_id, Lease.lease_until).where(
        Lease.account_id.in_(list(account_ids))
    )
    return {row[0]: {"worker_id": row[1], "lease_until": row[2]} for row in (await session.execute(stmt)).all()}


async def mark_status(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    status: AccountStatus,
    reason: str = "",
    error: str = "",
) -> None:
    values = {"status": status}
    if reason is not None:
        values["status_reason"] = reason
    if error:
        values["last_error"] = error[:512]
    await session.execute(update(TgAccount).where(TgAccount.id == account_id).values(**values))
    await session.commit()
