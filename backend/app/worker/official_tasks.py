"""官方机制养号：同步服务端下发的官方限制参数 + 按官方客户端节奏做养号活动。

两个任务，都只做「官方客户端本来就会做的事」：

- `sync_official`：读 `help.GetAppConfig`（服务端下发给所有客户端的限制参数）与 `help.GetConfig`
  （DC 与连接参数），把 flood/上限类参数落库。之后节流会**只收紧不放松**地参考它们，
  所以服务端一收紧我们立刻跟上，服务端放宽时也不会让我们放飞。
- `warmup_activity`：模仿官方客户端的日常节奏——上线、翻会话列表、可选地标记已读或显示打字状态、
  下线。**不发任何消息**，也不加入任何群；在服务端看来就是「一个正常刷消息的用户」。

为什么这样能防封：风控看的是行为分布。一个从不产生读行为、永远不上下线、只在特定时刻精准发消息的
会话，本身就是异常；而官方客户端的读/在线/输入节奏是最不异常的模板。
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from telethon import functions

from app.models import Task, TgAccount
from app.services.official import extract_dc_options, extract_official_limits
from app.worker.humanize import human_delay
from app.worker.telethon_account import TaskFailure, describe_exception, flood_wait_seconds

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class OfficialTasksMixin:
    """官方机制相关的两个任务。"""

    async def _sync_official(self, session: Any, task: Task, account: Optional[TgAccount]) -> dict:
        """同步服务端下发的官方限制参数（并顺带记录 DC / 连接配置）。"""
        assert account is not None
        client = self._client(account.id)
        try:
            app_config = await client(functions.help.GetAppConfigRequest(hash=0))
        except Exception as exc:  # noqa: BLE001
            wait = flood_wait_seconds(exc)
            if wait:
                raise TaskFailure(
                    f"读取官方参数被限流，{wait} 秒后重试：{describe_exception(exc)}",
                    retryable=True,
                    requeue_after=wait + 1,
                ) from exc
            raise TaskFailure(f"读取官方参数失败：{describe_exception(exc)}", retryable=True) from exc

        limits = extract_official_limits(app_config)
        account.official_limits = limits
        account.official_synced_at = _now()
        # 客户端身份：库里没写过就按官方表补一个，后续所有连接都用它
        if not account.device_model or not account.app_version:
            from app.services.official import pick_official_client

            identity = pick_official_client()
            account.device_model = identity.device_model
            account.system_version = identity.system_version
            account.app_version = identity.app_version
            account.lang_pack = identity.lang_pack
            account.client_kind = identity.lang_pack
        await session.flush()

        dc_info: dict[str, Any] = {}
        try:
            server_config = await client(functions.help.GetConfigRequest())
            dc_info = extract_dc_options(server_config)
        except Exception:  # noqa: BLE001 - DC 信息只是附加观测，拿不到不算失败
            logger.debug("读取 help.GetConfig 失败，跳过 DC 信息")

        logger.info(
            "官方限制参数已同步",
            extra={
                "worker_id": self.worker.worker_id,
                "account_id": str(account.id),
                "task_id": str(task.id),
                "limit_keys": len(limits),
                "dc": dc_info.get("dc_count"),
            },
        )
        return {
            "limit_keys": len(limits),
            "limits": limits,
            "dc": dc_info,
            "identity": {
                "device_model": account.device_model,
                "app_version": account.app_version,
                "client_kind": account.client_kind,
            },
        }

    async def _warmup_activity(self, session: Any, task: Task, account: Optional[TgAccount]) -> dict:
        """官方节奏养号：上线 → 翻会话 → （可选）已读/打字 → 下线。全程不发消息、不加群。

        payload：
        - `rounds`：做几轮（1-5，默认 1）
        - `online_min_seconds` / `online_max_seconds`：单轮在线时长（默认 60-300 秒）
        - `read_inbox`：是否标记已读一次（默认 false；开了对方会看到「已读」）
        - `typing`：是否显示「正在输入」（默认 false；开了对方会看到，慎用）
        - `typing_seconds`：打字状态持续多久（默认 3-8 秒随机）
        """
        assert account is not None
        payload = dict(task.payload or {})
        rounds = max(1, min(int(payload.get("rounds") or 1), 5))
        online_min = max(10, int(payload.get("online_min_seconds") or 60))
        online_max = max(online_min, int(payload.get("online_max_seconds") or 300))
        read_inbox = bool(payload.get("read_inbox"))
        typing = bool(payload.get("typing"))
        rng = random.Random(f"{account.id}:{task.id}")

        client = self._client(account.id)
        results: list[dict[str, Any]] = []

        for index in range(rounds):
            online_seconds = rng.randint(online_min, online_max)
            detail: dict[str, Any] = {"round": index + 1, "online_seconds": online_seconds}
            try:
                # 1) 上线（官方客户端每次打开都会做的事）
                await client(functions.account.UpdateStatusRequest(offline=False))
                await self._report_progress(
                    session, task, stage="online", detail=f"第 {index + 1}/{rounds} 轮：已上线，模拟 {online_seconds} 秒在线"
                )

                # 2) 翻会话：只读列表，不点进具体聊天（不产生已读回执）
                dialogs_seen = 0
                try:
                    limit = rng.randint(5, 15)
                    async for _ in client.iter_dialogs(limit=limit):
                        dialogs_seen += 1
                    detail["dialogs_seen"] = dialogs_seen
                except Exception as exc:  # noqa: BLE001 - 翻会话失败不影响在线状态
                    logger.debug("养号翻会话失败：%s", describe_exception(exc))
                    detail["dialogs_error"] = describe_exception(exc)

                # 3) 可选：标记已读（对方会看到已读，默认关闭）
                if read_inbox:
                    try:
                        peers = [d.entity for d in await client.get_dialogs(limit=3) if not d.is_user or d.unread_count]
                        for peer in peers[:2]:
                            await client(functions.messages.ReadHistoryRequest(peer=peer, max_id=0))
                            await asyncio.sleep(rng.uniform(1.5, 4.0))
                        detail["read_inbox"] = len(peers[:2])
                    except Exception as exc:  # noqa: BLE001
                        detail["read_error"] = describe_exception(exc)

                # 4) 可选：打字状态（对方能看到「正在输入」，默认关闭）
                if typing:
                    try:
                        dialogs = await client.get_dialogs(limit=5)
                        if dialogs:
                            pick = rng.choice(dialogs)
                            seconds = float(payload.get("typing_seconds") or rng.uniform(3.0, 8.0))
                            async with client.action(pick.entity, "typing"):
                                await asyncio.sleep(seconds)
                            detail["typing_seconds"] = round(seconds, 1)
                    except Exception as exc:  # noqa: BLE001
                        detail["typing_error"] = describe_exception(exc)

                # 5) 在线停留：模拟「人在刷手机」，中途随机做几次无关的轻请求
                started = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - started < online_seconds:
                    await asyncio.sleep(min(30.0, max(5.0, human_delay(rng, 5.0, 30.0))))
                    try:
                        await client(functions.updates.GetStateRequest())
                    except Exception:  # noqa: BLE001 - 心跳失败无所谓，继续待着
                        pass
            finally:
                try:
                    await client(functions.account.UpdateStatusRequest(offline=True))
                    detail["offline"] = True
                except Exception:  # noqa: BLE001
                    logger.debug("养号下线失败 account_id=%s", account.id)

            results.append(detail)
            await self._report_progress(
                session,
                task,
                stage="done" if index == rounds - 1 else "online",
                detail=f"第 {index + 1}/{rounds} 轮完成（翻会话 {detail.get('dialogs_seen', 0)} 个）",
                rounds_done=index + 1,
                rounds_total=rounds,
            )
            if index < rounds - 1:
                await asyncio.sleep(rng.uniform(20.0, 90.0))

        account.warmup_active_at = _now()
        await session.flush()
        logger.info(
            "养号活动完成",
            extra={
                "worker_id": self.worker.worker_id,
                "account_id": str(account.id),
                "task_id": str(task.id),
                "rounds": rounds,
                "read_inbox": read_inbox,
                "typing": typing,
            },
        )
        return {"rounds": rounds, "read_inbox": read_inbox, "typing": typing, "details": results}


__all__ = ["OfficialTasksMixin"]
