"""趋势采样：一小时一行写进 `metrics_samples`，供控制台折线图查询。

口径与工作台保持一致：
- `online_accounts`：状态 healthy 且租约未过期（有 Worker 正挂着这个号）；
- `abnormal_accounts`：状态不在 {healthy, pending, disabled}（要验证码 / 冻结 / 失效 / 永久双向）；
- `tasks_succeeded` / `tasks_failed`：**区间增量**——按上次采样时间到本次之间完成 / 失败的任务数累加。

增量窗口最多回看 `MAX_INCREMENT_MINUTES`：API 停机几小时再起来时，不会把所有历史任务
堆进当前这一个小时（宁可少记，也不要造出一根假的尖峰）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccountStatus, Lease, MetricsSample, Task, TaskStatus, TgAccount

logger = logging.getLogger(__name__)

#: 采样间隔（秒）。一小时一个桶，间隔够小才能让「当前这一小时」的点保持新鲜。
SAMPLE_INTERVAL_SECONDS = 60
#: 增量窗口上限（分钟）：超过这个间隔就只统计最近这么久
MAX_INCREMENT_MINUTES = 10

#: 支持的窗口 → (跨度, 粒度)
TREND_WINDOWS: dict[str, tuple[timedelta, str]] = {
    "24h": (timedelta(hours=24), "hour"),
    "7d": (timedelta(days=7), "day"),
    "30d": (timedelta(days=30), "day"),
}


def supported_windows() -> list[str]:
    return list(TREND_WINDOWS)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _floor_hour(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


async def record_sample(session: AsyncSession, *, now: Optional[datetime] = None) -> dict:
    """采一次样并 UPSERT 进当前小时的桶；返回这次采到的数值。"""
    now = now or _now()
    bucket = _floor_hour(now)

    last_at = await session.scalar(select(func.max(MetricsSample.sampled_at)))
    if last_at is not None and last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)
    since = max(last_at, now - timedelta(minutes=MAX_INCREMENT_MINUTES)) if last_at else now - timedelta(
        seconds=SAMPLE_INTERVAL_SECONDS
    )
    if since > now:
        since = now - timedelta(seconds=SAMPLE_INTERVAL_SECONDS)

    online_subq = select(Lease.account_id).where(Lease.lease_until > now)
    total_accounts = int(await session.scalar(select(func.count()).select_from(TgAccount)) or 0)
    online_accounts = int(
        await session.scalar(
            select(func.count())
            .select_from(TgAccount)
            .where(TgAccount.status == AccountStatus.healthy.value, TgAccount.id.in_(online_subq))
        )
        or 0
    )
    abnormal_accounts = int(
        await session.scalar(
            select(func.count())
            .select_from(TgAccount)
            .where(
                TgAccount.status.notin_(
                    [
                        AccountStatus.healthy.value,
                        AccountStatus.pending.value,
                        AccountStatus.disabled.value,
                    ]
                )
            )
        )
        or 0
    )
    tasks_succeeded = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.status == TaskStatus.completed,
                Task.completed_at.isnot(None),
                Task.completed_at >= since,
                Task.completed_at <= now,
            )
        )
        or 0
    )
    tasks_failed = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.status == TaskStatus.failed,
                Task.completed_at.isnot(None),
                Task.completed_at >= since,
                Task.completed_at <= now,
            )
        )
        or 0
    )

    values = {
        "bucket": bucket,
        "total_accounts": total_accounts,
        "online_accounts": online_accounts,
        "abnormal_accounts": abnormal_accounts,
        "tasks_succeeded": tasks_succeeded,
        "tasks_failed": tasks_failed,
        "sampled_at": now,
    }
    stmt = pg_insert(MetricsSample).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[MetricsSample.bucket],
        set_={
            # 账号类是快照：直接覆盖成最新值
            "total_accounts": stmt.excluded.total_accounts,
            "online_accounts": stmt.excluded.online_accounts,
            "abnormal_accounts": stmt.excluded.abnormal_accounts,
            # 任务类是区间增量：累加（所以同一时刻只允许一个副本在采，见 api.sampler 的 leader 键）
            "tasks_succeeded": MetricsSample.__table__.c.tasks_succeeded + stmt.excluded.tasks_succeeded,
            "tasks_failed": MetricsSample.__table__.c.tasks_failed + stmt.excluded.tasks_failed,
            "sampled_at": stmt.excluded.sampled_at,
            "updated_at": now,
        },
    )
    await session.execute(stmt)
    await session.commit()
    return values


async def load_trends(
    session: AsyncSession, *, window: str = "24h", now: Optional[datetime] = None
) -> dict:
    """读趋势数据。

    24h → 逐小时（最多 24 个点）；7d / 30d → 逐天（在线 / 异常取当天采样的平均值，
    任务成败取当天合计）。没有采样的时间桶不会补 0（补 0 会画出误导性的深谷）。
    """
    spec = TREND_WINDOWS.get(window)
    if spec is None:
        raise ValueError(f"不支持的窗口：{window}")
    span, granularity = spec
    now = now or _now()
    start = now - span

    latest_sample_at = await session.scalar(select(func.max(MetricsSample.sampled_at)))

    rows: list[dict] = []
    if granularity == "hour":
        records = await session.scalars(
            select(MetricsSample)
            .where(MetricsSample.bucket >= _floor_hour(start))
            .order_by(MetricsSample.bucket.asc())
        )
        for item in records.all():
            rows.append(
                {
                    "bucket": item.bucket,
                    "online_accounts": int(item.online_accounts or 0),
                    "abnormal_accounts": int(item.abnormal_accounts or 0),
                    "tasks_succeeded": int(item.tasks_succeeded or 0),
                    "tasks_failed": int(item.tasks_failed or 0),
                }
            )
    else:
        day = func.date_trunc("day", MetricsSample.bucket)
        result = await session.execute(
            select(
                day.label("bucket"),
                func.avg(MetricsSample.online_accounts).label("online_accounts"),
                func.avg(MetricsSample.abnormal_accounts).label("abnormal_accounts"),
                func.sum(MetricsSample.tasks_succeeded).label("tasks_succeeded"),
                func.sum(MetricsSample.tasks_failed).label("tasks_failed"),
            )
            .where(MetricsSample.bucket >= start)
            .group_by(day)
            .order_by(day.asc())
        )
        for bucket, online, abnormal, succeeded, failed in result.all():
            rows.append(
                {
                    "bucket": bucket,
                    "online_accounts": int(round(float(online or 0))),
                    "abnormal_accounts": int(round(float(abnormal or 0))),
                    "tasks_succeeded": int(succeeded or 0),
                    "tasks_failed": int(failed or 0),
                }
            )

    return {
        "window": window,
        "granularity": granularity,
        "start": start,
        "end": now,
        "latest_sample_at": latest_sample_at,
        "rows": rows,
    }


__all__ = [
    "SAMPLE_INTERVAL_SECONDS",
    "MAX_INCREMENT_MINUTES",
    "TREND_WINDOWS",
    "supported_windows",
    "record_sample",
    "load_trends",
]
