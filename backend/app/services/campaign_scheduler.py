"""群发定时计划调度：到点把计划里的批量动作排进任务队列。

与 bot 任务轮询同一套路，常驻在 API 进程里：每 20 秒扫一次「到点且启用」的计划，
按计划里存的 payload **复用对应端点的提交逻辑**（校验、解析账号范围、一号一任务、
错峰入队全都不重写一遍），跑完把计划顺延到下一次。

时间窗（send_window）交给任务侧的 `_gate_send_window` 继续兜底：
计划照常提交，不在窗口内的任务会自己顺延到窗口开始，不会白挨一次 PeerFlood。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import session_scope
from app.models import CampaignSchedule, User

logger = logging.getLogger("app.scheduler")

#: 扫描间隔（秒）：计划的颗粒度是分钟级，20 秒足够跟手
POLL_SECONDS = 20
#: 一轮最多处理多少条到期计划，避免一次涌进来几百条把库压住
BATCH = 20


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _dispatch(session, schedule: CampaignSchedule) -> int:
    """按计划 payload 调对应端点的提交函数，返回入队任务数。"""
    # 延迟导入：routers 那边会 import services，顶层 import 会成环
    from app.api.routers.campaigns import (
        BulkPmRequest,
        GroupBroadcastRequest,
        MaterialSendRequest,
        bulk_pm,
        group_broadcast,
        material_send,
    )

    builders = {
        "bulk_pm": (BulkPmRequest, bulk_pm),
        "group_broadcast": (GroupBroadcastRequest, group_broadcast),
        "material_send": (MaterialSendRequest, material_send),
    }
    entry = builders.get(schedule.action)
    if entry is None:
        raise ValueError(f"不支持定时的动作：{schedule.action}")
    request_cls, endpoint = entry

    if schedule.created_by is None:
        raise ValueError("计划没有记录创建人，无法解析账号范围")
    user = await session.get(User, schedule.created_by)
    if user is None:
        raise ValueError("计划的创建人已被删除，请重建计划")

    # 每次提交现生成 batch_id / account_index，计划里存的那份作废
    raw = {
        key: value
        for key, value in dict(schedule.payload or {}).items()
        if key not in {"batch_id", "account_index", "account_count"}
    }
    request = request_cls(**raw)
    result = await endpoint(request, session=session, user=user)
    return len(result.task_ids or [])


async def fire_schedule(session, schedule: CampaignSchedule) -> None:
    """跑一条计划，并把它顺延到下一次（提交无论成败都顺延，免得卡在原地空转）。

    页面上的「立即执行」也走这个入口：跑一次、计数 +1、按间隔顺延。
    """
    now = _now()
    try:
        count = await _dispatch(session, schedule)
        schedule.last_error = ""
        logger.info(
            "定时计划已提交 schedule=%s action=%s 入队=%s",
            schedule.id,
            schedule.action,
            count,
        )
    except Exception as exc:  # noqa: BLE001 - 单条计划失败不影响其它计划
        schedule.last_error = f"{type(exc).__name__}: {exc}"[:255]
        logger.warning("定时计划提交失败 schedule=%s: %s", schedule.id, exc)
    finally:
        schedule.last_run_at = now
        schedule.run_count = (schedule.run_count or 0) + 1
        schedule.next_run_at = now + timedelta(minutes=max(1, int(schedule.interval_minutes or 30)))
        await session.commit()


async def run_due() -> int:
    """跑一轮到期计划，返回处理条数。异常在这里收口，不让调度循环停摆。"""
    fired = 0
    try:
        async with session_scope() as session:
            rows = list(
                await session.scalars(
                    select(CampaignSchedule)
                    .where(
                        CampaignSchedule.enabled.is_(True),
                        CampaignSchedule.next_run_at <= _now(),
                    )
                    .order_by(CampaignSchedule.next_run_at)
                    .limit(BATCH)
                )
            )
            for schedule in rows:
                await fire_schedule(session, schedule)
                fired += 1
    except Exception:  # noqa: BLE001
        logger.exception("定时计划扫描失败")
    return fired


async def schedule_loop() -> None:
    """常驻循环：API 进程启动时挂上（见 app/api/main.py）。"""
    logger.info("定时群发调度已启动：每 %s 秒扫描一次到期计划", POLL_SECONDS)
    while True:
        await asyncio.sleep(POLL_SECONDS)
        await run_due()
