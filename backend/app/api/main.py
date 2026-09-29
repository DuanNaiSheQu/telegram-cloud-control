"""FastAPI 应用装配：create_app() + lifespan。

启动顺序有讲究：
1. Redis 连接先建好（后面注册 webhook、推事件都要用）；
2. users 表为空时按 BOOTSTRAP_ADMIN_PASSWORD 建管理员，保证第一次就能登录；
3. 加载 Bot 运行时注册表（解密 Token → aiogram 实例）；
4. 起两个后台协程：Bot 任务轮询、Prometheus 指标刷新。

关停时反过来：先停协程，再关 Bot 会话 / Redis / 数据库连接池，避免请求打到半关闭的资源上。
Webhook 注册放在后台任务里做：没有外网时 getMe/setWebhook 会超时，不能把启动卡住。
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, List

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from app import __version__, db, security
from app.api import metrics, sampler
from app.api.bots import bot_tasks, manager
from app.api.bots import webhook as webhook_router
from app.api.routers import (
    browser,
    accounts,
    accounts_bulk,
    accounts_import,
    assignments,
    audit,
    auth,
    campaigns,
    dashboard,
    dialogs,
    exports,
    group_intel,
    groups,
    health,
    materials,
    network,
    notifications,
    relays,
    tasks,
    trends,
    users,
    ws,
)
from app.config import settings
from app.db import SessionFactory
from app.logging_conf import setup_logging
from app.models import Bot, User, UserRole
from app.redis_client import close_redis, get_redis
from app.services.ai import ai_service

logger = logging.getLogger(__name__)


async def ensure_bootstrap_admin() -> None:
    """users 表为空且配了初始口令时建一个 admin；已经有用户就什么都不做。"""
    password = settings.bootstrap_admin_password
    if not password:
        return
    async with SessionFactory() as session:
        count = await session.scalar(select(func.count()).select_from(User))
        if int(count or 0) > 0:
            return
        admin = User(
            username=settings.bootstrap_admin_username,
            display_name="管理员",
            password_hash=security.hash_password(password),
            role=UserRole.admin,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        logger.warning(
            "users 表为空，已按 BOOTSTRAP_ADMIN_PASSWORD 创建初始管理员 username=%s（请尽快改口令）",
            admin.username,
        )


async def register_bot_webhooks() -> None:
    """后台补注册 Webhook：逐个 Bot 调 Telegram，慢一点也不能挡住启动。"""
    try:
        async with SessionFactory() as session:
            bot_ids = list(
                (
                    await session.scalars(select(Bot.id).where(Bot.webhook_enabled.is_(True)))
                ).all()
            )
            for bot_id in bot_ids:
                # 每个 Bot 单独查一次：上一个失败 rollback 会把会话里所有对象标成过期，
                # 复用旧对象会在异步上下文里触发懒加载（MissingGreenlet）。
                bot_row = await session.scalar(select(Bot).where(Bot.id == bot_id))
                if bot_row is None:
                    continue
                ok, detail = await manager.apply_webhook(session, bot_row, enable=True)
                if ok:
                    await session.commit()
                else:
                    await session.rollback()
                    logger.warning("启动时注册 Webhook 失败 bot_id=%s：%s", bot_id, detail)
        if bot_ids:
            logger.info("启动时已尝试注册 %s 个 Bot 的 Webhook", len(bot_ids))
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.warning("启动时注册 Webhook 失败（不影响 API 提供 HTTP 服务）", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging("api", settings.log_level)
    logger.info("API 启动中 environment=%s version=%s", settings.environment, __version__)

    # 1) Redis：连不上也继续启动，/ready 会如实报 not_ready
    try:
        await get_redis().ping()
        logger.info("Redis 连接正常")
    except Exception:  # noqa: BLE001
        logger.error("Redis 连接失败：页面实时推送与 Webhook 去重会降级", exc_info=True)

    # 2) 初始管理员
    try:
        await ensure_bootstrap_admin()
    except Exception:  # noqa: BLE001
        logger.error("创建初始管理员失败", exc_info=True)

    # 3) Bot 运行时注册表（同步读库，快）
    try:
        async with SessionFactory() as session:
            await manager.load_all(session)
    except Exception:  # noqa: BLE001
        logger.error("加载 Bot 运行时注册表失败", exc_info=True)

    background: List[asyncio.Task] = [
        asyncio.create_task(bot_tasks.poll_loop(), name="bot-task-poll"),
        asyncio.create_task(metrics.refresh_loop(), name="metrics-refresh"),
        asyncio.create_task(sampler.sample_loop(), name="metrics-sampler"),
        asyncio.create_task(register_bot_webhooks(), name="bot-webhook-register"),
    ]
    logger.info("API 已启动，后台协程 %s 个", len(background))

    try:
        yield
    finally:
        logger.info("API 正在关停…")
        for task in background:
            task.cancel()
        for task in background:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                logger.warning("后台协程退出时带异常 name=%s", task.get_name(), exc_info=True)
        # 先停协程再关连接，避免请求打到半关闭的资源上
        await manager.shutdown()
        await ai_service.close()
        await close_redis()
        await db.dispose_engine()
        logger.info("API 已关停")


def create_app() -> FastAPI:
    """装配应用。业务路由统一挂 /api，探测类（/health、/ready、/metrics）不带前缀。"""
    setup_logging("api", settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Telegram 云控 API：HTTP + WebSocket + 官方 Bot Webhook",
        lifespan=lifespan,
    )

    origins = settings.cors_origin_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 探测类：不带前缀
    app.include_router(health.router)
    app.include_router(browser.router)
    app.include_router(metrics.router)

    # 业务路由：统一 /api 前缀
    api = APIRouter(prefix="/api")
    for router in (
        auth.router,
        dashboard.router,
        # ⚠️ /accounts/bulk/* 必须排在 /accounts/{account_id}/* 之前：
        # 否则 "bulk" 会被当成 account_id 去解析 UUID，直接 422。
        accounts_bulk.router,
        accounts_import.router,
        accounts.router,
        groups.router,
        group_intel.router,
        network.router,
        dialogs.router,
        dialogs.drafts_router,
        dialogs.messages_router,
        tasks.router,
        campaigns.router,
        materials.router,
        relays.bots_router,
        relays.router,
        assignments.router,
        users.router,
        audit.router,
        exports.router,
        notifications.router,
        trends.router,
        ws.router,
        webhook_router.router,
    ):
        api.include_router(router)
    app.include_router(api)

    logger.info(
        "路由已装配：CORS=%s public_base_url=%s",
        ",".join(origins),
        settings.public_base_url,
    )
    return app


#: uvicorn app.api.main:app 直接用这个实例
app = create_app()
