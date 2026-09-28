"""批量运营任务执行（营销中心）：8 类任务类型的 handler，以 Mixin 形式挂进 `TaskRunner`。

为什么单独成文件：这些 handler 只依赖 `TaskRunner` 上已有的公共件
（`self.worker` / `self.log` / `self._client` / `self._load_dialog` / `self._resolve_entity`
/ `self._apply_status` / `self._failure` / `self._publish_task_event`），
独立出来能让 `task_runner.py` 只保留「分派 + 公共件」，批量运营的改动面收敛在一个文件里。

任务类型与 payload 约定见 docs/API_CONTRACT.md 第 10 / 18 节。
"""

from __future__ import annotations

import asyncio
import pathlib
import uuid
from typing import Any, Optional

from telethon import functions, utils
from telethon.errors import (
    ChatAdminRequiredError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    UserAlreadyParticipantError,
    UserNotMutualContactError,
)
from telethon.tl import types as tl_types

from app.config import settings
from app.models import (
    ACCOUNT_STATUS_LABELS,
    AccountStatus,
    DialogKind,
    MATERIAL_KIND_LABELS,
    Material,
    MaterialKind,
    MessageDirection,
    MessageStatus,
    Task,
    TaskStatus,
    TgAccount,
)
from app.services.ai import ai_service
from app.services.inbound import publish_message
from app.worker.handlers import MessageData, persist_message
from app.worker.humanize import (
    naturalize,
    persona_messages,
    pick_for_index,
    pick_random,
    rng_for,
    sleep_human,
)
from app.worker.telethon_account import (
    TaskFailure,
    describe_exception,
    flood_wait_seconds,
    is_network_error,
    map_exception_to_status,
)


def _status_value(status: Any) -> str:
    """枚举 / 字符串统一成库里的取值（与 task_runner 同口径）。"""
    return status.value if hasattr(status, "value") else str(status)


class CampaignTasksMixin:
    """批量私信 / 群发 / 素材群发 / 加群 / 退群 / 强拉 / 吵群 / 拟人发言。

    宿主类（TaskRunner）需提供：`worker`（含 `worker_id` / `redis` / `get_connection`）、
    `log`、`_client`、`_load_dialog`、`_resolve_entity`、`_apply_status`、`_failure`、
    `_publish_task_event`。
    """

    # ---------------- 公共件 ----------------

    def _ensure_sendable(self, account: TgAccount) -> None:
        """发送类动作的前置检查：只有 healthy 的号才替它对外发消息。"""
        status_value = _status_value(account.status)
        if status_value != AccountStatus.healthy.value:
            label = ACCOUNT_STATUS_LABELS.get(status_value, status_value)
            raise TaskFailure(f"账号不是正常状态（当前：{label}），不替它发送", retryable=False)

    def _campaign_rng(self, task: Task, payload: dict, salt: int = 0) -> Any:
        index = int(payload.get("account_index") or 0)
        return rng_for(task.id, index, salt)

    def _campaign_text(self, payload: dict, rng: Any) -> str:
        """按账号序号从文本池取一句，可选做口语化。"""
        texts = [str(item).strip() for item in (payload.get("texts") or []) if str(item).strip()]
        if texts:
            text = pick_for_index(texts, int(payload.get("account_index") or 0))
        else:
            text = str(payload.get("text") or "").strip()
        if not text:
            raise TaskFailure("任务没有可发送的文本", retryable=False)
        return naturalize(text, rng) if payload.get("naturalize") else text

    async def _resolve_group_entity(self, session: Any, task: Task, payload: dict, client: Any) -> Any:
        """目标群 → Telethon 实体：优先 dialog_id，其次 @username / 数字 chat_id。"""
        if payload.get("dialog_id"):
            dialog = await self._load_dialog(session, task, payload)
            return await self._resolve_entity(client, dialog)
        raw = str(payload.get("group") or payload.get("target_group") or payload.get("target") or "").strip()
        if not raw:
            raise TaskFailure("任务缺少目标群", retryable=False)
        try:
            return await client.get_entity(raw)
        except ValueError as exc:
            raise TaskFailure(f"找不到目标群：{raw}", retryable=False) from exc
        except Exception as exc:  # noqa: BLE001
            network = is_network_error(exc)
            raise TaskFailure(
                f"目标群打不开（{raw}）：{describe_exception(exc)}", retryable=network
            ) from exc

    async def _resolve_member_entity(self, client: Any, raw: str) -> Any:
        """成员目标（@username / 手机号 / 数字 user_id）→ 实体。"""
        try:
            return await client.get_entity(str(raw).strip())
        except ValueError as exc:
            raise TaskFailure(f"找不到成员：{raw}", retryable=False) from exc
        except Exception as exc:  # noqa: BLE001
            raise TaskFailure(
                f"成员打不开（{raw}）：{describe_exception(exc)}", retryable=is_network_error(exc)
            ) from exc

    async def _record_campaign_sent(
        self, session: Any, task: Task, account: TgAccount, entity: Any, text: str, sent: Any
    ) -> None:
        """批量运营的发出消息回填 messages 表（与单条发送同口径，页面能立刻看到）。"""
        is_group = isinstance(entity, (tl_types.Chat, tl_types.Channel))
        data = MessageData(
            tg_chat_id=int(getattr(entity, "id", 0)),
            kind=DialogKind.group if is_group else DialogKind.private,
            title=str(getattr(entity, "title", None) or ""),
            username=getattr(entity, "username", None),
            peer_display=str(getattr(entity, "title", None) or ""),
            body=text,
            tg_message_id=getattr(sent, "id", None),
            direction=MessageDirection.outgoing,
            status=MessageStatus.sent,
            sender_name=account.display_name or "",
            raw={"source": "campaign"},
        )
        if not data.tg_chat_id:
            return
        try:
            dialog, row, _ = await persist_message(session, account_id=account.id, data=data)
            await publish_message(self.worker.redis, dialog, row)
        except Exception:  # noqa: BLE001 - 回填失败不影响任务本身
            self.log.warning(
                "批量运营消息回填失败",
                extra={"worker_id": self.worker.worker_id, "account_id": str(account.id), "task_id": str(task.id)},
            )

    async def _campaign_send_one(
        self,
        session: Any,
        task: Task,
        account: TgAccount,
        client: Any,
        entity: Any,
        text: str,
        *,
        reply_to: Any = None,
    ) -> Any:
        """发一条并回填；FloodWait 交给调用方决定重试策略。"""
        sent = await client.send_message(entity, text, reply_to=reply_to)
        await self._record_campaign_sent(session, task, account, entity, text, sent)
        self.log.info(
            "批量运营消息已发出",
            extra={
                "worker_id": self.worker.worker_id,
                "account_id": str(account.id),
                "task_id": str(task.id),
                "tg_chat_id": getattr(entity, "id", None),
                "tg_message_id": getattr(sent, "id", None),
            },
        )
        return sent

    @staticmethod
    def _interval_of(payload: dict, key: str, default: float) -> float:
        try:
            return max(0.0, float(payload.get(key, default)))
        except (TypeError, ValueError):
            return default

    # ---------------- 批量私信 ----------------

    async def _bulk_pm(self, session: Any, task: Task, account: Optional[TgAccount]) -> dict:
        """批量私信：向 payload.targets 逐个发消息，目标之间随机间隔。"""
        assert account is not None
        self._ensure_sendable(account)
        payload = dict(task.payload or {})
        targets = [str(item).strip() for item in (payload.get("targets") or []) if str(item).strip()]
        if not targets:
            raise TaskFailure("批量私信任务缺少目标", retryable=False)
        client = self._client(account.id)
        rng = self._campaign_rng(task, payload)
        text = self._campaign_text(payload, rng)
        min_interval = self._interval_of(payload, "min_interval", 3.0)
        max_interval = self._interval_of(payload, "max_interval", 8.0)

        sent = failed = 0
        failures: list[dict] = []
        for index, raw in enumerate(targets):
            try:
                entity = await self._resolve_member_entity(client, raw)
                await self._campaign_send_one(session, task, account, client, entity, text)
                sent += 1
            except TaskFailure as exc:
                failed += 1
                failures.append({"target": raw, "error": exc.error})
            except Exception as exc:  # noqa: BLE001 - 单个目标失败不中断整批
                failed += 1
                failures.append({"target": raw, "error": describe_exception(exc)})
            if index < len(targets) - 1:
                await sleep_human(min_interval, max_interval, rng)

        if sent == 0 and failed:
            raise TaskFailure(f"批量私信全部失败（{failed} 个目标），首错：{failures[0]['error']}", retryable=False)
        return {"sent": sent, "failed": failed, "targets": len(targets), "failures": failures[:20]}

    # ---------------- 群发 ----------------

    async def _group_broadcast(self, session: Any, task: Task, account: Optional[TgAccount]) -> dict:
        """群发：向指定群发一条（文本池按号分配）。"""
        assert account is not None
        self._ensure_sendable(account)
        payload = dict(task.payload or {})
        client = self._client(account.id)
        entity = await self._resolve_group_entity(session, task, payload, client)
        rng = self._campaign_rng(task, payload)
        text = self._campaign_text(payload, rng)
        try:
            await self._campaign_send_one(session, task, account, client, entity, text)
        except Exception as exc:  # noqa: BLE001
            await self._apply_status(session, account, exc)
            raise self._failure(exc, "群发失败") from exc
        return {"tg_chat_id": getattr(entity, "id", None)}

    # ---------------- 素材群发 ----------------

    async def _material_send(self, session: Any, task: Task, account: Optional[TgAccount]) -> dict:
        """素材群发：按素材库内容发给指定群或逐个私信目标。"""
        assert account is not None
        self._ensure_sendable(account)
        payload = dict(task.payload or {})
        material_id = payload.get("material_id")
        if not material_id:
            raise TaskFailure("素材群发任务缺少 material_id", retryable=False)
        material = await session.get(Material, uuid.UUID(str(material_id)))
        if material is None:
            raise TaskFailure("素材不存在（可能已被删除）", retryable=False)
        client = self._client(account.id)
        rng = self._campaign_rng(task, payload)

        if payload.get("target_group"):
            targets = [await self._resolve_group_entity(session, task, payload, client)]
        else:
            raw_targets = [str(item).strip() for item in (payload.get("targets") or []) if str(item).strip()]
            if not raw_targets:
                raise TaskFailure("素材群发任务缺少目标", retryable=False)
            targets = [await self._resolve_member_entity(client, raw) for raw in raw_targets]

        min_interval = self._interval_of(payload, "min_interval", 3.0)
        max_interval = self._interval_of(payload, "max_interval", 8.0)
        caption = naturalize(material.text, rng) if (material.text and payload.get("naturalize")) else (material.text or "")
        sent = failed = 0
        failures: list[dict] = []
        for index, entity in enumerate(targets):
            try:
                if material.kind == MaterialKind.text:
                    body = str(material.text or "").strip()
                    if not body:
                        raise TaskFailure("文字素材内容为空", retryable=False)
                    await self._campaign_send_one(session, task, account, client, entity, body)
                else:
                    path = self._material_path(material)
                    kwargs = {"caption": caption or None}
                    if material.kind == MaterialKind.document:
                        kwargs["force_document"] = True
                    sent_msg = await client.send_file(entity, path, **kwargs)
                    await self._record_campaign_sent(
                        session,
                        task,
                        account,
                        entity,
                        caption or f"[{MATERIAL_KIND_LABELS.get(material.kind.value, material.kind.value)}]",
                        sent_msg,
                    )
                sent += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                failures.append({"target": str(getattr(entity, "id", "")), "error": describe_exception(exc)})
            if index < len(targets) - 1:
                await sleep_human(min_interval, max_interval, rng)

        if sent == 0 and failed:
            raise TaskFailure(f"素材群发全部失败，首错：{failures[0]['error']}", retryable=False)
        return {
            "material_id": str(material.id),
            "kind": material.kind.value,
            "sent": sent,
            "failed": failed,
            "failures": failures[:20],
        }

    def _material_path(self, material: Material) -> str:
        """素材 → 本地文件绝对路径。"""
        base = pathlib.Path(settings.materials_dir)
        if not base.is_absolute():
            base = pathlib.Path.cwd() / base
        path = base / (material.file_name or "")
        if not material.file_name or not path.is_file():
            raise TaskFailure(
                f"素材「{material.name}」的媒体文件不存在（{material.file_name or '未记录'}），请重新上传",
                retryable=False,
            )
        return str(path)

    # ---------------- 加群 / 退群 / 强拉 ----------------

    @staticmethod
    def _invite_hash(raw: str) -> str:
        """邀请链接 → hash：支持 https://t.me/+HASH / t.me/+HASH / +HASH / 纯 HASH。"""
        value = str(raw).strip()
        if "+" in value:
            value = value.rsplit("+", 1)[1]
        return value.split("?")[0].strip()

    async def _join_group(self, session: Any, task: Task, account: Optional[TgAccount]) -> dict:
        """加群：邀请链接（ImportChatInvite）或公开群 @username（JoinChannel）。"""
        assert account is not None
        payload = dict(task.payload or {})
        target = str(payload.get("target") or "").strip()
        if not target:
            raise TaskFailure("加群任务缺少目标", retryable=False)
        client = self._client(account.id)
        try:
            if "+" in target:
                await client(functions.messages.ImportChatInviteRequest(hash=self._invite_hash(target)))
                return {"joined": True, "via": "invite"}
            username = target.lstrip("@").split("/")[-1].strip()
            entity = await client.get_input_entity(username)
            await client(functions.channels.JoinChannelRequest(channel=entity))
            return {"joined": True, "via": "username"}
        except (UserAlreadyParticipantError, InviteHashExpiredError) as exc:
            return {"joined": False, "already": True, "detail": describe_exception(exc)}
        except (InviteHashInvalidError, ValueError) as exc:
            raise TaskFailure(f"邀请无效或找不到目标（{target}）：{describe_exception(exc)}", retryable=False) from exc
        except Exception as exc:  # noqa: BLE001
            await self._apply_status(session, account, exc)
            raise self._failure(exc, "加群失败") from exc

    async def _leave_group(self, session: Any, task: Task, account: Optional[TgAccount]) -> dict:
        """退群：频道用 LeaveChannel，普通群用 DeleteChatUser；可选删除本地会话。"""
        assert account is not None
        payload = dict(task.payload or {})
        target = str(payload.get("target") or "").strip()
        if not target:
            raise TaskFailure("退群任务缺少目标", retryable=False)
        client = self._client(account.id)
        try:
            entity = await client.get_entity(target)
        except ValueError as exc:
            raise TaskFailure(f"找不到要退的群：{target}", retryable=False) from exc
        except Exception as exc:  # noqa: BLE001
            raise TaskFailure(f"群打不开（{target}）：{describe_exception(exc)}", retryable=is_network_error(exc)) from exc
        try:
            if isinstance(entity, (tl_types.Channel, tl_types.ChannelForbidden)):
                await client(functions.channels.LeaveChannelRequest(channel=entity))
            else:
                await client(functions.messages.DeleteChatUserRequest(chat_id=int(entity.id), user_id="me"))
            if payload.get("delete_history", True):
                try:
                    await client.delete_dialog(entity)
                except Exception:  # noqa: BLE001 - 删本地会话失败不影响退群结果
                    self.log.debug(
                        "删除会话记录失败",
                        extra={"account_id": str(account.id), "tg_chat_id": getattr(entity, "id", None)},
                    )
        except Exception as exc:  # noqa: BLE001
            await self._apply_status(session, account, exc)
            raise self._failure(exc, "退群失败") from exc
        return {"left": True, "tg_chat_id": getattr(entity, "id", None)}

    async def _force_add_member(self, session: Any, task: Task, account: Optional[TgAccount]) -> dict:
        """强拉进群：把 members 拉进 group（执行号须为该群管理员）。"""
        assert account is not None
        payload = dict(task.payload or {})
        group_raw = str(payload.get("group") or "").strip()
        members = [str(item).strip() for item in (payload.get("members") or []) if str(item).strip()]
        if not group_raw or not members:
            raise TaskFailure("强拉任务缺少群或成员", retryable=False)
        client = self._client(account.id)
        try:
            group = await client.get_entity(group_raw)
        except ValueError as exc:
            raise TaskFailure(f"找不到目标群：{group_raw}", retryable=False) from exc
        except Exception as exc:  # noqa: BLE001
            raise TaskFailure(f"群打不开（{group_raw}）：{describe_exception(exc)}", retryable=is_network_error(exc)) from exc

        added = already = 0
        failures: list[dict] = []
        is_channel = isinstance(group, (tl_types.Channel, tl_types.ChannelForbidden))
        for raw in members:
            try:
                user = await client.get_entity(raw)
                input_user = utils.get_input_user(user)
                if input_user is None:
                    failures.append({"member": raw, "error": "无法解析成员身份"})
                    continue
                if is_channel:
                    await client(functions.channels.InviteToChannelRequest(channel=group, users=[input_user]))
                else:
                    await client(functions.messages.AddChatUserRequest(
                        chat_id=int(group.id), user_id=input_user, fwd_limit=0
                    ))
                added += 1
            except UserAlreadyParticipantError:
                already += 1
            except (UserNotMutualContactError, ChatAdminRequiredError) as exc:
                failures.append({"member": raw, "error": describe_exception(exc)})
            except Exception as exc:  # noqa: BLE001
                failures.append({"member": raw, "error": describe_exception(exc)})
        if added == 0 and failures and not already:
            raise TaskFailure(f"强拉全部失败，首错：{failures[0]['error']}", retryable=False)
        return {"added": added, "already_in_group": already, "failed": len(failures), "failures": failures[:20]}

    # ---------------- 吵群 / 拟人发言 ----------------

    async def _task_still_running(self, session: Any, task_id: uuid.UUID) -> bool:
        """循环任务每轮检查：被页面取消（或其它状态变化）就收手。"""
        from sqlalchemy import select

        status_value = await session.scalar(select(Task.status).where(Task.id == task_id))
        return status_value == TaskStatus.running

    async def _chat_loop(
        self,
        *,
        session: Any,
        task: Task,
        account: TgAccount,
        client: Any,
        entity: Any,
        payload: dict,
        make_text: Any,
    ) -> dict:
        """吵群 / 拟人共用的循环：每轮取文本 → （可选）回复群内最近消息 → 发送 → 随机间隔。"""
        rounds = max(1, min(int(payload.get("rounds") or 5), settings.campaign_max_rounds))
        min_interval = self._interval_of(payload, "min_interval", 8.0)
        max_interval = self._interval_of(payload, "max_interval", 30.0)
        reply_probability = min(1.0, max(0.0, float(payload.get("reply_probability") or 0.0)))
        rng = self._campaign_rng(task, payload)
        sent = cancelled = 0
        for round_no in range(1, rounds + 1):
            if not await self._task_still_running(session, task.id):
                cancelled = rounds - round_no + 1
                break
            try:
                produced = make_text(round_no, rng)
                text = await produced if asyncio.iscoroutine(produced) else produced
                if not text or not str(text).strip():
                    raise TaskFailure("本轮没有可用文本", retryable=False)
                reply_to = None
                if reply_probability and rng.random() < reply_probability:
                    try:
                        recent = await client.get_messages(entity, limit=1)
                        if recent and getattr(recent[0], "id", None):
                            reply_to = recent[0].id
                    except Exception:  # noqa: BLE001 - 拿不到最近消息就不回复
                        reply_to = None
                await self._campaign_send_one(session, task, account, client, entity, text, reply_to=reply_to)
                sent += 1
                await self._publish_task_event(task, ok=True, detail=f"第 {round_no}/{rounds} 轮已发出")
            except Exception as exc:  # noqa: BLE001
                wait = flood_wait_seconds(exc)
                if wait:
                    self.log.warning(
                        "循环发言被限流，等待后继续",
                        extra={
                            "worker_id": self.worker.worker_id,
                            "account_id": str(account.id),
                            "task_id": str(task.id),
                            "wait": wait,
                        },
                    )
                    await asyncio.sleep(wait + 1)
                else:
                    status = map_exception_to_status(exc)
                    await self._apply_status(session, account, exc, status)
                    raise self._failure(exc, "循环发言失败", retryable=status is None) from exc
            if round_no < rounds and await self._task_still_running(session, task.id):
                await sleep_human(min_interval, max_interval, rng)
        return {"rounds": rounds, "sent": sent, "cancelled": cancelled}

    async def _storm_chat(self, session: Any, task: Task, account: Optional[TgAccount]) -> dict:
        """吵群：按文本池随机挑句、随机间隔连续发言。"""
        assert account is not None
        self._ensure_sendable(account)
        payload = dict(task.payload or {})
        texts = [str(item).strip() for item in (payload.get("texts") or []) if str(item).strip()]
        if not texts:
            raise TaskFailure("吵群任务没有文本池", retryable=False)
        client = self._client(account.id)
        entity = await self._resolve_group_entity(session, task, payload, client)

        def make_text(_round_no: int, rng: Any) -> str:
            text = pick_random(texts, rng)
            return naturalize(text, rng) if payload.get("naturalize") else text

        result = await self._chat_loop(
            session=session, task=task, account=account, client=client,
            entity=entity, payload=payload, make_text=make_text,
        )
        result["tg_chat_id"] = getattr(entity, "id", None)
        return result

    async def _persona_chat(self, session: Any, task: Task, account: Optional[TgAccount]) -> dict:
        """拟人发言：按人设用 AI 生成话术；AI 不可用时退回文本池。"""
        assert account is not None
        self._ensure_sendable(account)
        payload = dict(task.payload or {})
        persona = str(payload.get("persona") or "").strip()
        if not persona:
            raise TaskFailure("拟人发言任务缺少人设", retryable=False)
        fallback = [str(item).strip() for item in (payload.get("texts") or []) if str(item).strip()]
        client = self._client(account.id)
        entity = await self._resolve_group_entity(session, task, payload, client)
        topic = payload.get("topic")
        use_ai = bool(payload.get("use_ai", True)) and ai_service.available

        async def make_text(round_no: int, rng: Any) -> str:
            if use_ai:
                try:
                    recent = list(await client.get_messages(entity, limit=settings.campaign_persona_context_messages))
                    context = [
                        str(getattr(msg, "message", "") or "").strip()
                        for msg in recent
                        if str(getattr(msg, "message", "") or "").strip()
                    ]
                    messages = persona_messages(persona=persona, topic=topic, context=context)
                    reply = await ai_service.chat(messages, temperature=0.9)
                    if reply:
                        return naturalize(reply, rng) if payload.get("naturalize") else reply
                except Exception:  # noqa: BLE001 - AI 抖动退回文本池，循环继续
                    self.log.warning(
                        "拟人发言 AI 生成失败，本轮退回文本池",
                        extra={
                            "worker_id": self.worker.worker_id,
                            "account_id": str(account.id),
                            "task_id": str(task.id),
                        },
                    )
            if fallback:
                return naturalize(pick_random(fallback, rng), rng)
            raise TaskFailure("AI 生成失败且没有备用文本池", retryable=False)

        result = await self._chat_loop(
            session=session, task=task, account=account, client=client,
            entity=entity, payload=payload, make_text=make_text,
        )
        result["tg_chat_id"] = getattr(entity, "id", None)
        result["used_ai"] = use_ai
        return result


__all__ = ["CampaignTasksMixin"]
