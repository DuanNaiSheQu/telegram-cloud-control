"""Prometheus 指标（API 侧）。

为什么用后台协程刷新 Gauge：/metrics 可能被 Prometheus 每 15 秒抓一次，如果在请求里查库，
抓取频率一高就把连接池占满；这里改成每 10 秒刷一次内存里的 Gauge，抓取时零查询。

任务积压相关的口径直接复用 `core.tasks.due_task_metrics`，与告警规则保持一致。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from sqlalchemy import func, select

from app.core.tasks import due_task_metrics
from app.db import SessionFactory
from app.models import ACCOUNT_STATUS_LABELS, Bot, Dialog, Task, TgAccount
from app.api.routers import enum_value

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ops"])

#: 刷新间隔：抓取周期（15s）的 2/3，够新也不至于频繁查库
REFRESH_INTERVAL_SECONDS = 10.0

TGCC_TASKS = Gauge("tgcc_tasks", "任务数（按状态 / 到期 / 卡住）", ["status"])
TGCC_ACCOUNTS = Gauge("tgcc_accounts", "账号数（按状态）", ["status"])
TGCC_DIALOGS_UNREAD = Gauge("tgcc_dialogs_unread", "有未读消息的会话数")
TGCC_BOTS = Gauge("tgcc_bots", "已配置的官方 Bot 数量")
TGCC_API_UP = Gauge("tgcc_api_up", "API 进程存活（1=存活）")


async def refresh_once() -> None:
    """查一次库，把当前值写进 Gauge。"""
    async with SessionFactory() as session:
        # 1) 任务：due_task_metrics 给的是告警口径（含 overdue / stuck）
        metrics = await due_task_metrics(session)
        for key in ("pending", "running", "failed", "overdue", "stuck"):
            TGCC_TASKS.labels(status=key).set(int(metrics.get(key, 0) or 0))

        # 2) 任务：按状态全量分一遍，补齐 completed / cancelled / pending_confirmation
        rows = await session.execute(select(Task.status, func.count()).group_by(Task.status))
        for status_value, count in rows.all():
            TGCC_TASKS.labels(status=enum_value(status_value)).set(int(count or 0))

        # 3) 账号：所有状态都要有一行，值归零也要暴露，否则 Grafana 曲线会断
        account_rows = await session.execute(
            select(TgAccount.status, func.count()).group_by(TgAccount.status)
        )
        seen = set()
        for status_value, count in account_rows.all():
            label = enum_value(status_value)
            seen.add(label)
            TGCC_ACCOUNTS.labels(status=label).set(int(count or 0))
        for label in ACCOUNT_STATUS_LABELS:
            if label not in seen:
                TGCC_ACCOUNTS.labels(status=label).set(0)

        # 4) 未读会话数 / Bot 数
        unread = await session.scalar(
            select(func.count()).select_from(Dialog).where(Dialog.unread_count > 0)
        )
        TGCC_DIALOGS_UNREAD.set(int(unread or 0))
        bots = await session.scalar(select(func.count()).select_from(Bot))
        TGCC_BOTS.set(int(bots or 0))

    TGCC_API_UP.set(1)


async def refresh_loop() -> None:
    """lifespan 起的后台协程；任何一次失败都不能把循环打断。"""
    logger.info("指标刷新协程启动，间隔 %ss", REFRESH_INTERVAL_SECONDS)
    while True:
        try:
            await refresh_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 指标坏掉不能影响 API
            logger.warning("刷新 Prometheus 指标失败", exc_info=True)
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus 文本；只读内存里的 Gauge，不在请求里查库。"""
    return Response(content=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})
