"""趋势采样协程：每个 API 副本只跑一个采样。

多副本时用 Redis 的 leader 键（`SET NX EX` + 自己续期）选出一个采样者：
`metrics_samples` 里任务成败是**区间累加**，两个副本同时写会把数字翻倍，
所以这里必须先抢到 leader 才写库（DB 侧 UPSERT 只是并发兜底）。

Redis 不可用时**允许采样**（记一条警告）：此时本来就没有协调能力，
单副本部署不能因为 Redis 抖动就没有趋势数据；双写风险只在「Redis 挂 + 多副本」同时出现。
采样失败一律不打断循环，下一次间隔再试。
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from typing import Optional

from app.core import samples
from app.db import SessionFactory
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

#: leader 键：值是本进程标识；TTL 取 1.5 个采样间隔——
#: 活着的 leader 每 60s 续期不会被抢，挂掉后最多 90s 就有别的副本接手（不会 3 分钟没有趋势点）
LEADER_KEY = "tgcc:metrics:sampler-leader"
LEADER_TTL_SECONDS = int(samples.SAMPLE_INTERVAL_SECONDS * 1.5)

#: 进程标识（多副本区分用）
INSTANCE_ID = f"{socket.gethostname()}:{os.getpid()}"

#: 上次看到的 leader（只用来避免"别的副本在采样"这行日志刷屏）
_last_seen_owner: Optional[str] = None


async def try_become_sampler() -> bool:
    """抢 / 续 leader。Redis 抛异常时返回 True（降级为「都来采」）。"""
    global _last_seen_owner

    redis = get_redis()
    try:
        current = await redis.get(LEADER_KEY)
        if current is None:
            acquired = await redis.set(LEADER_KEY, INSTANCE_ID, nx=True, ex=LEADER_TTL_SECONDS)
            if acquired:
                _last_seen_owner = INSTANCE_ID
                logger.info("本副本成为趋势采样者 instance=%s", INSTANCE_ID)
            return bool(acquired)
        owner = current.decode("utf-8", "ignore") if isinstance(current, bytes) else str(current)
        if owner == INSTANCE_ID:
            await redis.expire(LEADER_KEY, LEADER_TTL_SECONDS)
            return True
        if _last_seen_owner != owner:
            _last_seen_owner = owner
            logger.info(
                "另一个副本正在采样（owner=%s），本副本跳过；它挂掉后最多 %ss 接手",
                owner,
                LEADER_TTL_SECONDS,
            )
        return False
    except Exception:  # noqa: BLE001 - Redis 抖动不能把采样彻底停掉
        logger.warning("Redis 不可用，趋势采样降级为本副本直接写（多副本可能重复计数）", exc_info=True)
        return True


async def sample_once() -> Optional[dict]:
    """采一次样；不是 leader 时返回 None。"""
    if not await try_become_sampler():
        return None
    async with SessionFactory() as session:
        return await samples.record_sample(session)


async def sample_loop() -> None:
    """lifespan 起的后台协程：启动先采一次，之后每 SAMPLE_INTERVAL_SECONDS 一次。"""
    logger.info("趋势采样协程启动 instance=%s 间隔=%ss", INSTANCE_ID, samples.SAMPLE_INTERVAL_SECONDS)
    while True:
        try:
            result = await sample_once()
            if result is not None:
                logger.debug(
                    "趋势采样 bucket=%s 在线=%s 异常=%s 成功=%s 失败=%s",
                    result["bucket"], result["online_accounts"], result["abnormal_accounts"],
                    result["tasks_succeeded"], result["tasks_failed"],
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 采样坏掉不能影响 API
            logger.warning("趋势采样失败", exc_info=True)
        await asyncio.sleep(samples.SAMPLE_INTERVAL_SECONDS)


__all__ = ["LEADER_KEY", "LEADER_TTL_SECONDS", "INSTANCE_ID", "try_become_sampler", "sample_once", "sample_loop"]
