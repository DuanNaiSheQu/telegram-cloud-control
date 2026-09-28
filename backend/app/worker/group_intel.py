"""群情报 Worker 侧：入群/退群事件的「无感」记录 + 群档案与成员名单的按需采集。

无感的三条纪律（代码里逐条落实）：
1. 事件回调**只写库**：不回复、不打招呼、不加表情、不做任何群内可见动作；
2. 采集只用读接口（`GetFullChannel` / `GetParticipants`），且分页之间有间隔、单任务有上限；
3. 成员数变化等群内动静全部来自事件的被动观察，不主动轮询群列表。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from telethon import functions
from telethon.tl import types as tl_types

from app.config import settings
from app.db import session_scope
from app.models import Dialog, DialogChannel, Task, TgAccount
from app.services.group_intel import (
    describe_chat_action,
    display_name_of,
    member_status_for_event,
    profile_fields_from_entity,
    record_event,
    upsert_member,
    upsert_profile,
)
from app.worker.telethon_account import TaskFailure, describe_exception, flood_wait_seconds

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _is_group_chat(chat: Any) -> bool:
    return isinstance(chat, (tl_types.Chat, tl_types.Channel, tl_types.ChatForbidden, tl_types.ChannelForbidden))


def make_chat_action_handler(
    *, worker_id: str, account_id: uuid.UUID, redis: Any
) -> Callable[[Any], Awaitable[None]]:
    """给一个号造 ChatAction 处理器：入群/退群/被拉进来，全程静默入库。

    注意这里**不做任何回应动作**——不发欢迎语、不点赞、不撤回，避免在群里留下痕迹。
    """

    async def _handler(event: Any) -> None:
        try:
            chat = await event.get_chat()
            if chat is None or not _is_group_chat(chat):
                return
            event_type = describe_chat_action(
                user_joined=bool(getattr(event, "user_joined", False)),
                user_added=bool(getattr(event, "user_added", False)),
                user_left=bool(getattr(event, "user_left", False)),
                user_kicked=bool(getattr(event, "user_kicked", False)),
            )
            if event_type is None:
                return

            user = None
            try:
                user = await event.get_user()
            except Exception:  # noqa: BLE001 - 拿不到用户实体不影响记事件
                user = None
            actor_id = getattr(event, "added_by_id", None)
            occurred = getattr(event, "date", None) or _now()

            async with session_scope() as session:
                fields = profile_fields_from_entity(chat)
                profile = await upsert_profile(
                    session,
                    account_id=account_id,
                    tg_chat_id=int(chat.id),
                    source="join_event",
                    touch_collected_at=False,
                    **fields,
                )
                await record_event(
                    session,
                    account_id=account_id,
                    tg_chat_id=int(chat.id),
                    event_type=event_type,
                    tg_user_id=getattr(user, "id", None),
                    actor_tg_id=actor_id,
                    user_display=display_name_of(user),
                    username=getattr(user, "username", None),
                    is_bot=bool(getattr(user, "bot", False)),
                    occurred_at=occurred,
                    raw={"event": event_type, "chat_kind": profile.kind},
                )
                if user is not None:
                    await upsert_member(
                        session,
                        profile=profile,
                        tg_user_id=int(user.id),
                        username=getattr(user, "username", None),
                        display_name=display_name_of(user),
                        is_bot=bool(getattr(user, "bot", False)),
                        is_premium=bool(getattr(user, "premium", False)),
                        status=member_status_for_event(event_type),
                        source="join_event",
                        raw={"event": event_type},
                    )
            logger.info(
                "群事件已记录（静默）",
                extra={
                    "worker_id": worker_id,
                    "account_id": str(account_id),
                    "tg_chat_id": int(chat.id),
                    "event_type": event_type,
                    "tg_user_id": getattr(user, "id", None),
                },
            )
        except Exception:  # noqa: BLE001 - 单个事件失败不能影响这个号的其它事件
            logger.exception(
                "处理群事件失败",
                extra={"worker_id": worker_id, "account_id": str(account_id)},
            )

    return _handler


class GroupIntelMixin:
    """两个只读采集任务：群档案（`collect_group`）与成员名单（`collect_members`）。"""

    async def _collect_group(self, session: Any, task: Task, account: Optional[TgAccount]) -> dict:
        """采集群档案：资料 + 成员数 + 邀请链接；可选顺带抽样前 N 个成员。"""
        assert account is not None
        payload = dict(task.payload or {})
        dialog = await self._resolve_group_dialog(session, task, payload)
        tg_chat_id = int(payload.get("tg_chat_id") or dialog.tg_chat_id)
        client = self._client(account.id)
        entity = await self._resolve_entity(client, dialog) if dialog is not None else await client.get_entity(tg_chat_id)

        try:
            full = await self._full_chat(client, entity)
        except Exception as exc:  # noqa: BLE001
            wait = flood_wait_seconds(exc)
            if wait:
                raise TaskFailure(
                    f"Telegram 限流，{wait} 秒后重试：{describe_exception(exc)}", retryable=True, requeue_after=wait + 1
                ) from exc
            raise TaskFailure(f"拉群资料失败：{describe_exception(exc)}", retryable=True) from exc

        fields = profile_fields_from_entity(entity, full)
        profile = await upsert_profile(
            session,
            account_id=account.id,
            tg_chat_id=tg_chat_id,
            dialog_id=dialog.id if dialog is not None else None,
            source="profile_sync",
            raw={"collect": "collect_group"},
            **fields,
        )
        # 顺手把群标题/成员数同步到 dialogs，页面列表口径一致
        if dialog is not None:
            if fields.get("title"):
                dialog.title = str(fields["title"])[:255]
            if fields.get("member_count") is not None:
                dialog.member_count = int(fields["member_count"])
            if fields.get("username") is not None:
                dialog.username = fields["username"]
            await session.flush()

        sampled = 0
        sample_limit = int(payload.get("sample_members") or 0)
        if sample_limit > 0:
            sampled = await self._fetch_members(
                session, account=account, client=client, profile=profile, entity=entity, limit=sample_limit
            )
            profile.member_sampled = int(profile.member_sampled or 0) + sampled
            profile.member_synced_at = _now()
            await session.flush()

        logger.info(
            "群档案采集完成",
            extra={
                "worker_id": self.worker.worker_id,
                "account_id": str(account.id),
                "task_id": str(task.id),
                "tg_chat_id": tg_chat_id,
                "member_count": profile.member_count,
                "sampled": sampled,
            },
        )
        return {
            "tg_chat_id": tg_chat_id,
            "title": profile.title,
            "kind": profile.kind,
            "member_count": profile.member_count,
            "sampled": sampled,
            "profile_id": str(profile.id),
        }

    async def _collect_members(self, session: Any, task: Task, account: Optional[TgAccount]) -> dict:
        """采集群成员名单：按页拉取，页间有间隔，单任务有上限（避免大批量拉取触发风控）。"""
        assert account is not None
        payload = dict(task.payload or {})
        profile_id = payload.get("profile_id")
        dialog = await self._resolve_group_dialog(session, task, payload)
        limit = min(
            int(payload.get("limit") or settings.group_intel_max_members_per_task),
            settings.group_intel_max_members_per_task,
        )
        client = self._client(account.id)

        from app.models import GroupProfile

        profile = None
        if profile_id:
            profile = await session.get(GroupProfile, uuid.UUID(str(profile_id)))
        if profile is None:
            tg_chat_id = int(payload.get("tg_chat_id") or (dialog.tg_chat_id if dialog is not None else 0))
            if not tg_chat_id:
                raise TaskFailure("采集成员任务缺少 profile_id 或 tg_chat_id", retryable=False)
            entity = await client.get_entity(tg_chat_id)
            profile = await upsert_profile(
                session,
                account_id=account.id,
                tg_chat_id=tg_chat_id,
                dialog_id=dialog.id if dialog is not None else None,
                source="profile_sync",
                touch_collected_at=False,
                **profile_fields_from_entity(entity),
            )
            profile_entity = entity
        else:
            profile_entity = (
                await self._resolve_entity(client, dialog) if dialog is not None else await client.get_entity(profile.tg_chat_id)
            )

        fetched = await self._fetch_members(
            session, account=account, client=client, profile=profile, entity=profile_entity, limit=limit
        )
        profile.member_synced_at = _now()
        profile.member_sampled = int(profile.member_sampled or 0) + fetched
        await session.flush()
        logger.info(
            "群成员采集完成",
            extra={
                "worker_id": self.worker.worker_id,
                "account_id": str(account.id),
                "task_id": str(task.id),
                "tg_chat_id": profile.tg_chat_id,
                "fetched": fetched,
            },
        )
        return {"profile_id": str(profile.id), "fetched": fetched, "limit": limit}

    # ---------------- 公共：Telegram 调用 ----------------

    async def _resolve_group_dialog(self, session: Any, task: Task, payload: dict) -> Optional[Dialog]:
        """任务里的 dialog_id（可选）→ dialogs 行。"""
        raw = payload.get("dialog_id") or (str(task.dialog_id) if task.dialog_id else "")
        if not raw:
            return None
        try:
            dialog_id = uuid.UUID(str(raw))
        except ValueError:
            return None
        return await session.get(Dialog, dialog_id)

    async def _full_chat(self, client: Any, entity: Any) -> Any:
        """读群全量资料：超级群/频道走 GetFullChannel，普通群走 GetFullChat。"""
        if isinstance(entity, (tl_types.Channel, tl_types.ChannelForbidden)):
            return await client(functions.channels.GetFullChannelRequest(channel=entity))
        if isinstance(entity, tl_types.Chat):
            return await client(functions.messages.GetFullChatRequest(chat_id=entity.id))
        return None

    async def _fetch_members(
        self,
        session: Any,
        *,
        account: TgAccount,
        client: Any,
        profile: Any,
        entity: Any,
        limit: int,
    ) -> int:
        """分页拉成员并写库。页与页之间 sleep `GROUP_INTEL_PAGE_INTERVAL_SECONDS`。"""
        if limit <= 0:
            return 0
        page_size = max(1, min(settings.group_intel_page_size, limit))
        fetched = 0
        offset = 0
        is_channel = isinstance(entity, (tl_types.Channel, tl_types.ChannelForbidden))
        while fetched < limit:
            want = min(page_size, limit - fetched)
            try:
                if is_channel:
                    resp = await client(
                        functions.channels.GetParticipantsRequest(
                            channel=entity,
                            filter=tl_types.ChannelParticipantsRecent(),
                            offset=offset,
                            limit=want,
                            hash=0,
                        )
                    )
                    users = list(getattr(resp, "users", []) or [])
                    participants = {int(getattr(p, "user_id", 0) or 0): p for p in getattr(resp, "participants", []) or []}
                else:
                    full = await client(functions.messages.GetFullChatRequest(chat_id=entity.id))
                    users = list(getattr(full, "users", []) or [])
                    participants = {}
            except Exception as exc:  # noqa: BLE001 - 单页失败不再无限重试
                wait = flood_wait_seconds(exc)
                if wait:
                    raise TaskFailure(
                        f"拉成员被限流，{wait} 秒后重试：{describe_exception(exc)}",
                        retryable=True,
                        requeue_after=wait + 1,
                    ) from exc
                logger.warning("拉群成员失败（已采 %s 个）：%s", fetched, describe_exception(exc))
                break

            if not users:
                break
            for user in users:
                try:
                    participant = participants.get(int(getattr(user, "id", 0) or 0))
                    await upsert_member(
                        session,
                        profile=profile,
                        tg_user_id=int(user.id),
                        username=getattr(user, "username", None),
                        display_name=display_name_of(user),
                        is_bot=bool(getattr(user, "bot", False)),
                        is_premium=bool(getattr(user, "premium", False)),
                        is_admin=bool(getattr(participant, "admin_rights", None)),
                        status="member",
                        source="participant_sync",
                    )
                    fetched += 1
                except Exception:  # noqa: BLE001 - 单个成员失败不中断整页
                    continue
            offset += len(users)
            if len(users) < want:
                break
            if fetched < limit:
                await asyncio.sleep(max(0.5, float(settings.group_intel_page_interval_seconds)))
        return fetched


__all__ = ["GroupIntelMixin", "make_chat_action_handler"]
