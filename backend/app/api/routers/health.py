"""运维探测：/health 看进程活着，/ready 看数据库与 Redis 都通。

这两个路径按契约不带 /api 前缀，给容器探针和负载均衡用。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import __version__, db, redis_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ops"])


@router.get("/health", summary="进程存活探测")
async def health() -> dict:
    """只要进程还能回包就算活着；不查库、不查 Redis，避免依赖抖动导致容器被重启。"""
    return {"status": "ok", "service": "api", "version": __version__}


@router.get("/ready", summary="依赖就绪探测")
async def ready():
    """数据库或 Redis 任一不通就 503，让编排系统先把流量摘掉。"""
    database_ok = await db.ping_database()
    redis_ok = await redis_client.ping_redis()
    healthy = database_ok and redis_ok
    body = {
        "status": "ready" if healthy else "not_ready",
        "database": bool(database_ok),
        "redis": bool(redis_ok),
    }
    if not healthy:
        logger.warning("就绪探测失败 database=%s redis=%s", database_ok, redis_ok)
        return JSONResponse(status_code=503, content=body)
    return body
