"""通知聚合：把事实表里的四类异常映射成 `notifications` 行。

为什么不让页面直接扫任务表：铃铛要的是「一条流」，而 tasks / leases / tg_accounts 只是当前状态。
这里做的是**物化视图式**的聚合——定时（或页面首次拉取时）把事实映射成通知，
靠 `dedupe_key` 唯一约束保证同一件事只出现一次（多副本并发也安全，走 ON CONFLICT DO NOTHING）。

四类来源（与规划里的四条告警对齐）：
1. 失败任务       tasks.status=failed（近 7 天）
2. Worker 心跳丢失 worker 还持有租约，但 Redis 心跳超过 60 秒没更新
3. 账号异常       tg_accounts.status ∈ {needs_code, frozen, invalid, dead}
4. 备份失败       Redis 键 tgcc:backup:last-result 报 ok=false（由备份脚本写入，见 API_CONTRACT）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.models import (
    ACCOUNT_STATUS_LABELS,
    NOTIFICATION_KIND_LABELS,
    NOTIFICATION_KIND_LEVELS,
    TASK_TYPE_LABELS,
    AccountStatus,
    Lease,
    Notification,
    Task,
    TaskStatus,
    TgAccount,
)

logger = logging.getLogger(__name__)

#: 聚合节流键：页面每次拉通知都会尝试聚合，用这个键把并发与频率压下来
REDIS_SYNC_KEY = "tgcc:notifications:last-sync"
#: 备份结果上报键（deploy/backup.sh 侧写，API 只读）
REDIS_BACKUP_KEY = "tgcc:backup:last-result"
#: 两次聚合之间至少隔多少秒
SYNC_MIN_INTERVAL_SECONDS = 20
#: 失败任务只回看这么多天，避免老通知把铃铛淹掉
FAILED_TASK_LOOKBACK_DAYS = 7
FAILED_TASK_LIMIT = 200
ABNORMAL_ACCOUNT_LIMIT = 200
#: Worker 心跳超过这个秒数算掉线（与工作台 WORKER_STALE_SECONDS 一致）
WORKER_STALE_SECONDS = 60

#: 账号异常口径：与工作台「异常数」保持一致
ABNORMAL_STATUSES = [
    AccountStatus.needs_code.value,
    AccountStatus.frozen.value,
    AccountStatus.invalid.value,
    AccountStatus.dead.value,
]

#: 中文标题模板
KIND_TITLES = {
    "task_failed": "任务失败：{type_label}",
    "worker_lost": "Worker 心跳丢失：{worker_id}",
    "account_abnormal": "账号异常：{account_label} · {status_label}",
    "backup_failed": "数据库备份失败",
}


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _hour_key(moment: datetime) -> str:
    return moment.strftime("%Y%m%d%H")


def _parse_ts(raw) -> Optional[datetime]:
    """Redis 心跳里的 ISO 字符串 → datetime；解析不了就当没有心跳。"""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _notify(
    session: AsyncSession,
    *,
    dedupe_key: str,
    kind: str,
    title: str,
    body: str,
    link: str = "",
    level: Optional[str] = None,
    account_id=None,
    bot_id=None,
    task_id=None,
    worker_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> bool:
    """写一条通知；dedupe_key 命中已有行时什么都不做，返回是否真的新建。"""
    values = {
        "dedupe_key": dedupe_key,
        "kind": kind,
        "level": level or NOTIFICATION_KIND_LEVELS.get(kind, "warning"),
        "title": title[:200],
        "body": body,
        "link": link[:255],
        "account_id": account_id,
        "bot_id": bot_id,
        "task_id": task_id,
        "worker_id": worker_id,
        "detail": detail,
    }
    stmt = (
        pg_insert(Notification)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[Notification.dedupe_key])
        .returning(Notification.id)
    )
    created = (await session.execute(stmt)).scalar_one_or_none()
    return created is not None


async def _from_failed_tasks(session: AsyncSession, now: datetime) -> int:
    """近 7 天失败的任务 → 一条任务失败通知。"""
    since = now - timedelta(days=FAILED_TASK_LOOKBACK_DAYS)
    tasks = list(
        (
            await session.scalars(
                select(Task)
                .where(Task.status == TaskStatus.failed, Task.created_at >= since)
                .order_by(Task.created_at.desc())
                .limit(FAILED_TASK_LIMIT)
            )
        ).all()
    )
    if not tasks:
        return 0
    account_ids = {item.account_id for item in tasks if item.account_id}
    accounts = {
        row.id: row
        for row in (await session.scalars(select(TgAccount).where(TgAccount.id.in_(account_ids)))).all()
    } if account_ids else {}

    created = 0
    for task in tasks:
        type_value = task.type.value if hasattr(task.type, "value") else str(task.type)
        account = accounts.get(task.account_id)
        label = account.phone_masked if account is not None else None
        type_label = TASK_TYPE_LABELS.get(type_value, type_value)
        body = f"账号 {label} · " if label else ""
        body += (task.error or "未记录失败原因")[:300]
        body += f"（第 {task.attempts}/{task.max_attempts} 次尝试）"
        if await _notify(
            session,
            dedupe_key=f"task_failed:{task.id}",
            kind="task_failed",
            title=KIND_TITLES["task_failed"].format(type_label=type_label),
            body=body,
            link="/tasks?status=failed",
            account_id=task.account_id,
            bot_id=task.bot_id,
            task_id=task.id,
            detail={"type": type_value, "error": (task.error or "")[:300], "attempts": task.attempts},
        ):
            created += 1
    return created


async def _from_worker_gap(session: AsyncSession, redis, now: datetime) -> int:
    """持有租约但没有新鲜心跳的 Worker → 一条 Worker 丢失通知（同一个 worker 每小时最多一条）。"""
    if redis is None:
        return 0
    try:
        beats = await events.worker_heartbeats(redis)
    except Exception:  # noqa: BLE001 - Redis 抖动只影响这一类通知
        logger.warning("读取 Worker 心跳失败，跳过 Worker 丢失检测", exc_info=True)
        return 0

    heartbeat_at: dict[str, datetime] = {}
    for item in beats:
        worker_id = item.get("worker_id")
        if not worker_id:
            continue
        heartbeat_at[worker_id] = _parse_ts(item.get("ts")) or now

    rows = await session.execute(
        select(Lease.worker_id, func.count())
        .where(Lease.lease_until > now)
        .group_by(Lease.worker_id)
    )
    created = 0
    bucket = _hour_key(now)
    for worker_id, leased in rows.all():
        last = heartbeat_at.get(worker_id)
        if last is not None and (now - last) <= timedelta(seconds=WORKER_STALE_SECONDS):
            continue
        stale_for = int((now - last).total_seconds()) if last is not None else None
        body = f"仍持有 {int(leased or 0)} 个账号租约，但"
        body += f"已 {stale_for} 秒没有心跳（阈值 {WORKER_STALE_SECONDS} 秒）" if stale_for else "Redis 里没有它的心跳记录"
        body += "。处置：确认 worker 容器状态；必要时清掉这些号的租约让其它副本接管。"
        if await _notify(
            session,
            dedupe_key=f"worker_lost:{worker_id}:{bucket}",
            kind="worker_lost",
            title=KIND_TITLES["worker_lost"].format(worker_id=worker_id),
            body=body,
            link="/",
            worker_id=worker_id,
            detail={"leased_accounts": int(leased or 0), "stale_seconds": stale_for},
        ):
            created += 1
    return created


async def _from_abnormal_accounts(session: AsyncSession, now: datetime) -> int:
    """账号异常 → 一条通知；同一个号同一个状态只通知一次（状态变了会再通知）。"""
    accounts = list(
        (
            await session.scalars(
                select(TgAccount)
                .where(TgAccount.status.in_(ABNORMAL_STATUSES))
                .order_by(TgAccount.updated_at.desc())
                .limit(ABNORMAL_ACCOUNT_LIMIT)
            )
        ).all()
    )
    created = 0
    for account in accounts:
        status_value = account.status.value if hasattr(account.status, "value") else str(account.status)
        status_label = ACCOUNT_STATUS_LABELS.get(status_value, status_value)
        reason = account.status_reason or account.last_error or "没有记录原因"
        if await _notify(
            session,
            dedupe_key=f"account_abnormal:{account.id}:{status_value}",
            kind="account_abnormal",
            title=KIND_TITLES["account_abnormal"].format(
                account_label=account.phone_masked, status_label=status_label
            ),
            body=f"{reason[:300]}。处置：到账号详情里检测一次；确认不可用就停用这个号（不影响其它号）。",
            link=f"/accounts/{account.id}",
            account_id=account.id,
            detail={"status": status_value, "status_reason": account.status_reason[:200]},
        ):
            created += 1
    return created


async def _from_backup(session: AsyncSession, redis, now: datetime) -> int:
    """备份结果上报（Redis 键）→ 一条备份失败通知。

    键值约定：`{"ok": false, "kind": "daily", "ts": "ISO8601", "message": "..."}`，
    也兼容直接写 "0"/"fail"。键不存在时**不告警**（没接入上报不等于失败，避免误报）。
    """
    if redis is None:
        return 0
    try:
        raw = await redis.get(REDIS_BACKUP_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("读取备份结果失败", exc_info=True)
        return 0
    if not raw:
        return 0
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    text = str(raw).strip()
    payload: dict = {}
    ok = True
    if text.startswith("{"):
        try:
            payload = json.loads(text) or {}
        except json.JSONDecodeError:
            payload = {}
            ok = False
        else:
            ok = bool(payload.get("ok", True))
    else:
        ok = text.lower() not in ("0", "false", "fail", "failed", "error")
    if ok:
        return 0

    at = _parse_ts(payload.get("ts")) or now
    backup_kind = str(payload.get("kind") or "daily")
    message = str(payload.get("message") or "备份脚本以失败退出，请查看 deploy/postgres-backup.md 的处置步骤")[:300]
    created = await _notify(
        session,
        dedupe_key=f"backup_failed:{backup_kind}:{at.date().isoformat()}",
        kind="backup_failed",
        title=KIND_TITLES["backup_failed"],
        body=f"{backup_kind} 备份在 {at.isoformat()} 失败：{message}",
        link="/",
        detail={"kind": backup_kind, "ts": at.isoformat(), "message": message},
    )
    return 1 if created else 0


async def sync_notifications(
    session: AsyncSession,
    *,
    redis=None,
    force: bool = False,
    min_interval_seconds: int = SYNC_MIN_INTERVAL_SECONDS,
) -> dict:
    """把四类事实映射成通知。

    `force=False` 且 Redis 可用时，两次聚合之间会按 `min_interval_seconds` 节流
    （用 `SET NX EX` 抢一个短锁），避免每个页面轮询都跑一遍查询。
    Redis 不可用时不做节流，直接聚合——去重靠唯一约束，重复写不会产生重复通知。
    """
    if redis is not None and not force:
        try:
            acquired = await redis.set(REDIS_SYNC_KEY, "1", nx=True, ex=max(1, int(min_interval_seconds)))
        except Exception:  # noqa: BLE001 - 节流失败不影响正确性
            acquired = True
        if not acquired:
            return {"skipped": True, "created": 0, "by_kind": {}}

    now = _now()
    by_kind = {
        "task_failed": await _from_failed_tasks(session, now),
        "worker_lost": await _from_worker_gap(session, redis, now),
        "account_abnormal": await _from_abnormal_accounts(session, now),
        "backup_failed": await _from_backup(session, redis, now),
    }
    created = sum(by_kind.values())
    if created:
        await session.commit()
        logger.info("通知聚合新增 %s 条：%s", created, by_kind)
    return {"skipped": False, "created": created, "by_kind": by_kind}


__all__ = [
    "REDIS_SYNC_KEY",
    "REDIS_BACKUP_KEY",
    "SYNC_MIN_INTERVAL_SECONDS",
    "WORKER_STALE_SECONDS",
    "ABNORMAL_STATUSES",
    "NOTIFICATION_KIND_LABELS",
    "sync_notifications",
]
