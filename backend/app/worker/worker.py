"""Worker 主循环：认领租约 → 维持用户号长连接 → 续租 + 心跳 → 执行任务 → 优雅退出。

一个用户号同一时刻只属于一个 Worker；退出（SIGTERM/SIGINT）时先断开连接再放开租约。
没配 `TELEGRAM_API_ID/HASH` 时不崩：只认领租约、发心跳，不建连接。
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any, Optional

from sqlalchemy import case, exists, func, literal, select, update

from app.config import settings
from app.core import events as core_events
from app.core import leases as lease_core
from app.core.tasks import claim_tasks, reclaim_stale_running
from app.db import dispose_engine, session_scope
from app.models import (
    AccountStatus,
    CurrentTask,
    Dialog,
    Task,
    TaskStatus,
    TaskType,
    TgAccount,
)
from app.redis_client import close_redis, get_redis
from app.worker import metrics
from app.worker.task_runner import ClaimedTask, TaskRunner
from app.worker.telethon_account import AccountConnection, proxy_backend_available, snapshot_from_row

logger = logging.getLogger(__name__)

#: 一批任务里同时执行的上限，别把一批号同时打过载
TASK_CONCURRENCY = 10  # 默认值；实际用 settings.task_concurrency
#: 同时建连的上限
CONNECT_CONCURRENCY = 10
#: Worker 心跳 TTL（告警阈值 60 秒）
WORKER_HEARTBEAT_TTL = 60
#: 单号心跳 TTL
ACCOUNT_HEARTBEAT_TTL = 120


def _status_value(status: Any) -> str:
    """枚举 / 字符串统一成库里的取值。"""
    return status.value if hasattr(status, "value") else str(status)


class Worker:
    """用户号 Worker：租约、连接、心跳、任务。"""

    def __init__(self) -> None:
        self.worker_id: str = settings.resolve_worker_id()
        self.redis = get_redis()
        self.log = logging.getLogger("app.worker")
        #: 本进程持有的账号（租约内）
        self.held: set[uuid.UUID] = set()
        #: account_id -> 连接对象
        self.connections: dict[uuid.UUID, AccountConnection] = {}
        self.stopping = asyncio.Event()
        self.runner = TaskRunner(self)
        self.started_at = time.time()
        self.telegram_ready = bool(settings.telegram_api_id and settings.telegram_api_hash)
        self._last_renew = 0.0
        self._heartbeat_sent_at: Optional[float] = None
        # 任务并发：多账号是并行的（各走各的连接），这里限制的是「同时在跑多少条」
        self._task_semaphore = asyncio.Semaphore(max(1, int(settings.task_concurrency)))
        self._idle_logged = False
        self._stopped = False

    # ---------------- 生命周期 ----------------

    def request_stop(self, *_: Any) -> None:
        """信号处理：只置标志，循环把这一轮跑完再退。"""
        self.log.info("收到退出信号，准备优雅退出", extra={"worker_id": self.worker_id})
        self.stopping.set()

    async def startup(self) -> None:
        """启动：回收自己名下的僵尸任务 + 打启动横幅。"""
        # 先把身份暴露给 Prometheus，告警正文里就能直接写出 worker_id
        metrics.set_worker_info(self.worker_id)
        try:
            async with session_scope() as session:
                recovered = await reclaim_stale_running(
                    session,
                    claimer_id=self.worker_id,
                    older_than_seconds=max(60, settings.lease_ttl_seconds * 2),
                )
        except Exception:  # noqa: BLE001 - 数据库暂时不通也要能起来重试
            self.log.exception("回收僵尸任务失败", extra={"worker_id": self.worker_id})
            recovered = 0
        self.log.info(
            "Worker 启动",
            extra={
                "worker_id": self.worker_id,
                "pid": os.getpid(),
                "component": "worker",
                "accounts_per_replica": settings.accounts_per_replica,
                "lease_ttl_seconds": settings.lease_ttl_seconds,
                "lease_renew_seconds": settings.lease_renew_seconds,
                "task_poll_interval": settings.task_poll_interval,
                "metrics_port": settings.worker_metrics_port,
                "telegram_ready": self.telegram_ready,
                "reclaimed_tasks": recovered,
            },
        )
        if not self.telegram_ready:
            self.log.warning(
                "未配置 TELEGRAM_API_ID/TELEGRAM_API_HASH，Worker 空转：只认领租约、发心跳，不建任何 Telegram 连接",
                extra={"worker_id": self.worker_id},
            )
        elif not proxy_backend_available():
            self.log.warning(
                "环境里没有 python-socks / PySocks：配了代理的号无法建连，会在 last_error 里写明原因",
                extra={"worker_id": self.worker_id},
            )

    async def run_forever(self) -> None:
        """主循环：每轮认领租约、维护连接、续租心跳、执行任务。"""
        await self.startup()
        while not self.stopping.is_set():
            try:
                await self._tick()
            except Exception:  # noqa: BLE001 - 单轮异常不能让 Worker 退出
                self.log.exception("Worker 主循环单轮异常，继续运行", extra={"worker_id": self.worker_id})
            self._publish_metrics()
            if self.stopping.is_set():
                break
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=max(0.2, settings.task_poll_interval))
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        """优雅退出：断开全部连接 → 释放租约 → 关闭 Redis / 数据库连接。"""
        if self._stopped:
            return
        self._stopped = True
        self.log.info(
            "开始优雅退出：断开连接并释放租约",
            extra={"worker_id": self.worker_id, "held": len(self.held)},
        )
        for conn in list(self.connections.values()):
            try:
                await conn.disconnect()
            except Exception:  # noqa: BLE001
                self.log.exception("断开用户号失败", extra=conn.log_extra())
        self.connections.clear()
        released = 0
        try:
            async with session_scope() as session:
                released = len(await lease_core.release_leases(session, worker_id=self.worker_id))
        except Exception:  # noqa: BLE001
            self.log.exception("释放租约失败", extra={"worker_id": self.worker_id})
        self.held.clear()
        metrics.set_online_accounts(0)
        metrics.set_leased_accounts(0)
        try:
            await self.redis.delete(core_events.worker_heartbeat_key(self.worker_id))
        except Exception:  # noqa: BLE001 - Redis 挂了不影响退出
            self.log.debug("清理心跳键失败", extra={"worker_id": self.worker_id})
        self.log.info("已释放 %d 个租约，Worker 退出", released, extra={"worker_id": self.worker_id, "released": released})
        await close_redis()
        await dispose_engine()

    # ---------------- 连接与租约 ----------------

    def get_connection(self, account_id: uuid.UUID) -> Optional[AccountConnection]:
        """取本进程持有的连接对象。"""
        return self.connections.get(account_id)

    async def invalidate_connection(self, account_id: uuid.UUID, *, drop: bool = False) -> None:
        """让某个号重连（登录成功后换会话）或直接放开（租约已清 / 号不可用）。"""
        conn = self.connections.get(account_id)
        if conn is None:
            if drop:
                self.held.discard(account_id)
            return
        await conn.disconnect()
        if drop:
            self.connections.pop(account_id, None)
            self.held.discard(account_id)
            self.log.info("已放开该号", extra={"worker_id": self.worker_id, "account_id": str(account_id)})
        else:
            conn.attempts = 0
            conn.next_attempt_at = 0.0

    async def _drop_account(self, account_id: uuid.UUID, *, reason: str) -> None:
        """断开并放开某个号（租约丢了 / 号已停用）。"""
        await self.invalidate_connection(account_id, drop=True)
        self.log.warning(
            "已放开该号",
            extra={"worker_id": self.worker_id, "account_id": str(account_id), "reason": reason},
        )

    async def _acquire_leases(self) -> None:
        """认领到 accounts_per_replica 为止。"""
        capacity = settings.accounts_per_replica - len(self.held)
        if capacity <= 0:
            return
        try:
            async with session_scope() as session:
                acquired = await lease_core.acquire_leases(
                    session, worker_id=self.worker_id, limit=capacity
                )
        except Exception:  # noqa: BLE001 - 数据库抖动，下一轮再试
            self.log.exception("认领租约失败", extra={"worker_id": self.worker_id})
            return
        if acquired:
            self.held.update(acquired)
            self.log.info(
                "认领到新账号",
                extra={"worker_id": self.worker_id, "acquired": len(acquired), "held": len(self.held)},
            )

    async def _maintain_connections(self) -> None:
        """为持有的号建 / 保持连接，最多 accounts_per_replica 个。"""
        if not self.held:
            return
        try:
            async with session_scope() as session:
                rows = list(await session.scalars(select(TgAccount).where(TgAccount.id.in_(list(self.held)))))
        except Exception:  # noqa: BLE001
            self.log.exception("读取账号行失败", extra={"worker_id": self.worker_id})
            return
        by_id = {row.id: row for row in rows}

        # 状态已经不该被认领的号：立刻放开
        for account_id, row in by_id.items():
            if _status_value(row.status) in (AccountStatus.dead.value, AccountStatus.disabled.value):
                await self._drop_account(account_id, reason=f"账号状态为 {_status_value(row.status)}")

        semaphore = asyncio.Semaphore(CONNECT_CONCURRENCY)
        pending: list[Any] = []
        for account_id in list(self.held):
            row = by_id.get(account_id)
            if row is None:
                continue
            snapshot = snapshot_from_row(row)
            conn = self.connections.get(account_id)
            if conn is None:
                conn = AccountConnection(snapshot, worker_id=self.worker_id, redis=self.redis)
                self.connections[account_id] = conn
            else:
                needs_reconnect = conn.update_snapshot(snapshot)
                if needs_reconnect:
                    self.log.info(
                        "会话或代理有变化，重连该号",
                        extra={"worker_id": self.worker_id, "account_id": str(account_id)},
                    )
                    await conn.disconnect()
            pending.append(self._connect_one(conn, semaphore))
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await self._consume_check_requests()

    async def _connect_one(self, conn: AccountConnection, semaphore: asyncio.Semaphore) -> None:
        """建连（受并发上限约束），永久不可用的号立刻放开。"""
        async with semaphore:
            try:
                await conn.ensure_connected()
            except Exception:  # noqa: BLE001 - 连接层不该抛，兜一层
                self.log.exception("建连异常", extra=conn.log_extra())
        if conn.fatal_status is not None:
            await self._drop_account(conn.account_id, reason=f"账号状态为 {conn.fatal_status.value}")

    async def _consume_check_requests(self) -> None:
        """页面「检测」按钮：立刻续一次租约，并在线时读一次状态。"""
        consumed = False
        for account_id in list(self.held):
            try:
                requested = await core_events.consume_check_request(self.redis, account_id)
            except Exception:  # noqa: BLE001 - Redis 抖动就当没有请求
                self.log.debug("读取检测请求失败", extra={"worker_id": self.worker_id})
                return
            if not requested:
                continue
            consumed = True
            conn = self.connections.get(account_id)
            if conn is None or not conn.online:
                continue
            await conn.refresh_identity()
            self.log.info(
                "已响应检测请求",
                extra={"worker_id": self.worker_id, "account_id": str(account_id)},
            )
        if consumed:
            try:
                async with session_scope() as session:
                    await lease_core.renew_leases(
                        session, worker_id=self.worker_id, ttl_seconds=settings.lease_ttl_seconds
                    )
            except Exception:  # noqa: BLE001
                metrics.record_lease_renew_failure()
                self.log.warning("检测请求触发的续租失败", extra={"worker_id": self.worker_id})

    # ---------------- 续租 / 心跳 / 展示状态 ----------------

    async def _renew_cycle(self) -> None:
        """每 lease_renew_seconds 一次：续租 + 两种心跳 + 指标 + current_task。"""
        self._last_renew = time.monotonic()
        renewed: Optional[list[uuid.UUID]] = None
        try:
            async with session_scope() as session:
                renewed = await lease_core.renew_leases(
                    session, worker_id=self.worker_id, ttl_seconds=settings.lease_ttl_seconds
                )
        except Exception:  # noqa: BLE001
            metrics.record_lease_renew_failure()
            self.log.error(
                "租约续期失败，租约过期后别的副本会接管这些号",
                exc_info=True,
                extra={"worker_id": self.worker_id, "held": len(self.held)},
            )
        if renewed is not None:
            lost = self.held - set(renewed)
            self.held = set(renewed)
            for account_id in lost:
                await self._drop_account(account_id, reason="租约已不属于本进程")
        await self._write_heartbeats()
        await self._refresh_status_metrics()
        await self._update_current_tasks()

    async def _write_heartbeats(self) -> None:
        """写 Worker 心跳（TTL 60s）与每个号的心跳（TTL 120s）。"""
        online = sum(1 for conn in self.connections.values() if conn.online)
        try:
            await core_events.set_worker_heartbeat(
                self.redis,
                self.worker_id,
                {
                    "online_accounts": online,
                    "leased_accounts": len(self.held),
                    "telegram_ready": self.telegram_ready,
                    "uptime_seconds": int(time.time() - self.started_at),
                },
                ttl=WORKER_HEARTBEAT_TTL,
            )
            self._heartbeat_sent_at = time.monotonic()
        except Exception:  # noqa: BLE001 - Redis 丢了只影响页面
            self.log.warning("写 Worker 心跳失败（Redis）", extra={"worker_id": self.worker_id})

        async def _beat(account_id: uuid.UUID) -> None:
            conn = self.connections.get(account_id)
            try:
                await core_events.set_account_heartbeat(
                    self.redis,
                    account_id,
                    {
                        "online": bool(conn.online) if conn else False,
                        "status": "unknown" if conn is None else _status_value(conn.snapshot.status),
                    },
                    ttl=ACCOUNT_HEARTBEAT_TTL,
                )
            except Exception:  # noqa: BLE001
                logger.debug("写账号心跳失败", extra={"account_id": str(account_id)})

        if self.held:
            await asyncio.gather(*(_beat(account_id) for account_id in list(self.held)), return_exceptions=True)

    async def _refresh_status_metrics(self) -> None:
        """按状态统计账号数量，给 Prometheus 用。"""
        try:
            async with session_scope() as session:
                rows = (
                    await session.execute(select(TgAccount.status, func.count()).group_by(TgAccount.status))
                ).all()
        except Exception:  # noqa: BLE001
            return
        counts = {_status_value(status): int(count) for status, count in rows}
        metrics.set_account_status_counts(counts)

    async def _update_current_tasks(self) -> None:
        """维护 tg_accounts.current_task：同步 / 等待确认 / 转发 / 空闲。"""
        if not self.held:
            return
        held_ids = list(self.held)
        sync_exists = exists(
            select(Task.id).where(
                Task.account_id == TgAccount.id,
                Task.type.in_([TaskType.sync_dialogs, TaskType.sync_messages]),
                Task.status.in_([TaskStatus.pending, TaskStatus.running]),
            )
        )
        send_exists = exists(
            select(Task.id).where(
                Task.account_id == TgAccount.id,
                Task.type == TaskType.send_message,
                Task.status.in_([TaskStatus.pending, TaskStatus.pending_confirmation]),
            )
        )
        # 转发任务只认这个号自己的会话：用 join 显式关联，避免子查询被错误关联到别的号
        relay_exists = exists(
            select(Task.id)
            .join(Dialog, Dialog.id == Task.dialog_id)
            .where(
                Task.type == TaskType.relay_to_staff,
                Task.status.in_([TaskStatus.pending, TaskStatus.running]),
                Dialog.account_id == TgAccount.id,
            )
            .correlate(TgAccount)
        )
        # 注意：CASE 的分支要显式带上列类型，否则 asyncpg 会报 text 与枚举不匹配
        enum_type = TgAccount.current_task.type
        current = case(
            (sync_exists, literal(CurrentTask.syncing.value, enum_type)),
            (send_exists, literal(CurrentTask.awaiting_confirm.value, enum_type)),
            (relay_exists, literal(CurrentTask.relaying.value, enum_type)),
            else_=literal(CurrentTask.idle.value, enum_type),
        )
        try:
            async with session_scope() as session:
                await session.execute(
                    update(TgAccount).where(TgAccount.id.in_(held_ids)).values(current_task=current)
                )
        except Exception as exc:  # noqa: BLE001 - 展示字段，不值得打断主循环
            self.log.warning(
                "更新 current_task 失败",
                extra={"worker_id": self.worker_id, "error": f"{type(exc).__name__}: {exc}"},
            )

    # ---------------- 任务 ----------------

    async def _execute_tasks(self) -> None:
        """领一批属于自己租约的任务，按类型分派执行（并发上限 5）。"""
        if not self.held:
            return
        try:
            async with session_scope() as session:
                tasks = await claim_tasks(
                    session,
                    claimer_id=self.worker_id,
                    kind="worker",
                    # 一轮多领一点，否则并发度上不去（领 5 条时最多只能同时跑 5 条）
                    limit=max(settings.task_batch, settings.task_concurrency * 2),
                    account_ids=list(self.held),
                )
        except Exception:  # noqa: BLE001
            self.log.exception("领取任务失败", extra={"worker_id": self.worker_id})
            return
        if not tasks:
            return
        self.log.info(
            "领取到任务",
            extra={"worker_id": self.worker_id, "count": len(tasks), "types": [_status_value(t.type) for t in tasks]},
        )
        claims = [ClaimedTask.from_orm(task) for task in tasks]
        results = await asyncio.gather(*(self._run_claim(claim) for claim in claims), return_exceptions=True)
        for claim, item in zip(claims, results):
            if isinstance(item, BaseException):
                self.log.error(
                    "任务协程异常",
                    exc_info=item,
                    extra={"worker_id": self.worker_id, "task_id": str(claim.id), "task_type": claim.type},
                )

    async def _run_claim(self, claim: ClaimedTask) -> bool:
        """跑一条任务（信号量限流）。"""
        async with self._task_semaphore:
            return await self.runner.run(claim)

    # ---------------- 每轮 ----------------

    async def _tick(self) -> None:
        """一轮：认领 → 连接 → 续租心跳 → 任务。"""
        await self._acquire_leases()
        if self.telegram_ready:
            await self._maintain_connections()
        else:
            self._log_idle_once()
        now = time.monotonic()
        if self._last_renew == 0.0 or now - self._last_renew >= settings.lease_renew_seconds:
            await self._renew_cycle()
        await self._execute_tasks()

    def _log_idle_once(self) -> None:
        """空转提示只打一次，避免刷日志。"""
        if self._idle_logged:
            return
        self._idle_logged = True
        self.log.warning(
            "Worker 空转中：只认领租约与发心跳，不建立 Telegram 连接（未配置 API ID/HASH）",
            extra={"worker_id": self.worker_id, "held": len(self.held)},
        )

    def _publish_metrics(self) -> None:
        """刷新 Gauge：在线号、租约数、心跳年龄。"""
        online = sum(1 for conn in self.connections.values() if conn.online)
        metrics.set_online_accounts(online)
        metrics.set_leased_accounts(len(self.held))
        if self._heartbeat_sent_at is not None:
            metrics.set_worker_heartbeat_age(time.monotonic() - self._heartbeat_sent_at)


__all__ = ["Worker"]
