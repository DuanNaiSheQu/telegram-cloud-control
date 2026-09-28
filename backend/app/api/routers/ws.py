"""WebSocket：只推「当前打开的会话」的新消息，账号 / 任务事件原样转发。

为什么用 Redis pub/sub 而不是在 API 里存订阅表：API 是无状态的，可以随时重启 / 多副本，
页面订阅丢了只是这一条实时推送没了，数据事实在 Postgres 里，重连后拉一次列表即可。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional, Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.deps import load_user_by_token
from app.core import events
from app.db import SessionFactory
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

#: 自定义关闭码：4401 = 令牌无效（与 HTTP 401 对应，前端看到它就去重新登录）
WS_CLOSE_UNAUTHORIZED = 4401


async def _pump(websocket: WebSocket, subscribed: Set[str]) -> None:
    """把 Redis 上的推送转发给这个客户端，只放行它订阅了的会话。"""
    redis = get_redis()
    pubsub = redis.pubsub(ignore_subscribe_messages=True)
    try:
        await pubsub.subscribe(events.CHANNEL_INBOX_ALL)
        await pubsub.subscribe(events.CHANNEL_ACCOUNTS)
        await pubsub.subscribe(events.CHANNEL_TASKS)
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if not message:
                continue
            raw = message.get("data")
            if raw is None:
                continue
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if payload.get("kind") == "message":
                # 只推当前打开的会话；没订阅的直接丢掉（数据在库里，不靠推送补）
                if payload.get("dialog_id") not in subscribed:
                    continue
            await websocket.send_json(payload)
    except asyncio.CancelledError:
        raise
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001 - 推送通道坏了不能影响其它请求
        logger.warning("WebSocket 推送协程结束", exc_info=True)
        try:
            await websocket.close(code=1011)
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            await pubsub.unsubscribe()
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            logger.debug("关闭 pubsub 失败", exc_info=True)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None, description="登录拿到的 JWT"),
) -> None:
    """连接流程：先 accept（这样才能用 4401 关闭码告诉前端去登录）→ 校验令牌 → 发 hello。"""
    await websocket.accept()

    # 单独开一个短会话做鉴权：不要在长连接期间占着连接池里的连接
    user = None
    if token:
        try:
            async with SessionFactory() as session:
                user = await load_user_by_token(session, token)
        except Exception:  # noqa: BLE001 - 数据库抖动时按未授权处理，前端会重连
            logger.warning("WebSocket 鉴权查询失败", exc_info=True)
    if user is None:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return

    subscribed: Set[str] = set()
    await websocket.send_json({"kind": "hello", "dialogs": sorted(subscribed)})

    pump = asyncio.create_task(_pump(websocket, subscribed))
    logger.info("WebSocket 已连接 user=%s", user.username)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            op = payload.get("op")
            if op == "ping":
                await websocket.send_json({"op": "pong"})
            elif op == "subscribe":
                for dialog_id in payload.get("dialog_ids") or []:
                    subscribed.add(str(dialog_id))
            elif op == "unsubscribe":
                for dialog_id in payload.get("dialog_ids") or []:
                    subscribed.discard(str(dialog_id))
            else:
                logger.debug("忽略未知 WebSocket 指令 user=%s op=%s", user.username, op)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.warning("WebSocket 读循环异常结束 user=%s", user.username, exc_info=True)
    finally:
        # 收尾：停推送协程、清订阅集合
        pump.cancel()
        try:
            await pump
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            logger.debug("推送协程退出时带异常", exc_info=True)
        subscribed.clear()
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
        logger.info("WebSocket 已断开 user=%s", user.username)
