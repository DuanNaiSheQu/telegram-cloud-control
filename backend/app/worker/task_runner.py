"""账号任务执行：按 `TaskType` 分派，统一收口成败，保证任务不会卡在 running。

约定：handler 成功返回 result（由本模块写 `complete_task`）；预期失败抛 `TaskFailure`
（带是否可重试 / 多久后重试 / 要不要清租约），未预期异常按可重试失败处理。
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import functions
from telethon.errors import UsernameInvalidError, UsernameOccupiedError

from app.config import settings
from app.core import audit as audit_core
from app.core import events as core_events
from app.core import leases as lease_core
from app.core.tasks import complete_task, fail_task
from app.db import session_scope
from app.models import (
    ACCOUNT_STATUS_LABELS,
    AccountStatus,
    Dialog,
    DialogChannel,
    DialogKind,
    DraftStatus,
    Message,
    MessageDirection,
    MessageStatus,
    ReplyDraft,
    Task,
    TaskStatus,
    TaskType,
    TgAccount,
)
from app.services.inbound import preview_of, publish_message, upsert_dialog
from app.services.throttle import note_flood
from app.worker import login as login_flow
from app.worker import metrics
from app.worker.campaign_tasks import CampaignTasksMixin
from app.worker.group_intel import GroupIntelMixin
from app.worker.handlers import MessageData, message_data_from_telethon, persist_message
from app.worker.telethon_account import (
    AccountConnection,
    AccountUnavailable,
    TaskFailure,
    describe_exception,
    flood_wait_seconds,
    is_network_error,
    map_exception_to_status,
    persist_identity,
)

logger = logging.getLogger(__name__)

#: 登录类任务成功后要换掉连接（新会话串刚写回库里）
LOGIN_TYPES = (TaskType.login_start.value, TaskType.login_code.value, TaskType.login_password.value)

TaskHandler = Callable[[AsyncSession, Task, Optional[TgAccount]], Awaitable[Any]]


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _status_value(status: Any) -> str:
    """枚举 / 字符串统一成库里的取值。"""
    return status.value if hasattr(status, "value") else str(status)


@dataclass(slots=True)
class ClaimedTask:
    """已领取任务的纯数据副本，避免 ORM 对象跨会话失效。"""

    id: uuid.UUID
    type: str
    account_id: Optional[uuid.UUID]
    dialog_id: Optional[uuid.UUID]
    payload: dict
    attempts: int = 0
    max_attempts: int = 5

    @classmethod
    def from_orm(cls, task: Task) -> "ClaimedTask":
        """从领取到的 ORM 行拷一份纯数据。"""
        return cls(
            id=task.id,
            type=_status_value(task.type),
            account_id=task.account_id,
            dialog_id=task.dialog_id,
            payload=dict(task.payload or {}),
            attempts=int(task.attempts or 0),
            max_attempts=int(task.max_attempts or settings.task_max_attempts),
        )


class TaskRunner(CampaignTasksMixin, GroupIntelMixin):
    """任务分派器：Worker 领到任务后交给它执行。

    批量运营的 8 类 handler 在 `app.worker.campaign_tasks.CampaignTasksMixin` 里。
    """

    def __init__(self, worker: Any) -> None:
        self.worker = worker
        self.log = logging.getLogger("app.worker.task_runner")
        self._handlers: dict[str, TaskHandler] = {
            TaskType.sync_dialogs.value: self._sync_dialogs,
            TaskType.sync_messages.value: self._sync_messages,
            TaskType.send_message.value: self._send_message,
            TaskType.account_check.value: self._account_check,
            TaskType.update_profile.value: self._update_profile,
            TaskType.login_start.value: self._login_start,
            TaskType.login_code.value: self._login_code,
            TaskType.login_password.value: self._login_password,
            TaskType.bulk_pm.value: self._bulk_pm,
            TaskType.group_broadcast.value: self._group_broadcast,
            TaskType.material_send.value: self._material_send,
            TaskType.join_group.value: self._join_group,
            TaskType.leave_group.value: self._leave_group,
            TaskType.force_add_member.value: self._force_add_member,
            TaskType.storm_chat.value: self._storm_chat,
            TaskType.persona_chat.value: self._persona_chat,
            TaskType.collect_group.value: self._collect_group,
            TaskType.collect_members.value: self._collect_members,
        }

    # ---------------- 执行入口 ----------------

    async def run(self, claim: ClaimedTask) -> bool:
        """执行一条任务，返回是否成功；任何异常都在这里收口。"""
        started = time.perf_counter()
        outcome = "failed"
        failure: Optional[TaskFailure] = None
        drop_account_id: Optional[uuid.UUID] = None
        extra = {
            "worker_id": self.worker.worker_id,
            "account_id": str(claim.account_id) if claim.account_id else "",
            "task_id": str(claim.id),
            "task_type": claim.type,
        }
        try:
            handler = self._handlers.get(claim.type)
            if handler is None:
                raise TaskFailure(f"Worker 不执行该任务类型：{claim.type}", retryable=False)
            async with session_scope() as session:
                task = await session.get(Task, claim.id)
                if task is None:
                    self.log.info("任务已不存在，跳过", extra=extra)
                    metrics.record_task_skipped(claim.type)
                    return False
                if task.status != TaskStatus.running:
                    self.log.info("任务状态已变化，跳过", extra={**extra, "status": _status_value(task.status)})
                    metrics.record_task_skipped(claim.type)
                    return False
                if task.account_id is None:
                    raise TaskFailure("用户号任务缺少 account_id", retryable=False)
                account = await session.get(TgAccount, task.account_id)
                if account is None:
                    raise TaskFailure("任务对应的账号不存在", retryable=False)
                try:
                    result = await handler(session, task, account)
                except TaskFailure as exc:
                    # 在同一个事务里收尾：handler 已经写好的账号状态（冻结 / 要验证码）不能丢
                    failure = exc
                    outcome = await self._fail_in_session(session, task, exc)
                    drop_account_id = task.account_id if exc.release_lease else None
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - 未预期异常也要落库，不能卡 running
                    self.log.exception("任务执行出现未预期异常", extra=extra)
                    failure = TaskFailure(f"任务执行异常：{type(exc).__name__}: {exc}", retryable=True)
                    outcome = await self._fail_in_session(session, task, failure)
                else:
                    await complete_task(session, task, result)
                    await self._publish_task_event(task, ok=True, detail="")
                    outcome = "ok"
            # 事务已提交，副作用放这里
            if drop_account_id is not None:
                await self.worker.invalidate_connection(drop_account_id, drop=True)
            if outcome == "ok":
                if claim.type in LOGIN_TYPES and claim.account_id is not None:
                    await self.worker.invalidate_connection(claim.account_id)
                self.log.info(
                    "任务执行成功",
                    extra={**extra, "result": result if isinstance(result, dict) else str(result)},
                )
                return True
            if failure is not None:
                log = self.log.warning if outcome == "retried" else self.log.error
                log(
                    "任务失败，已回队列重试" if outcome == "retried" else "任务失败",
                    extra={**extra, "error": failure.error, "retry_in": failure.requeue_after},
                )
            return False
        except asyncio.CancelledError:
            raise
        except TaskFailure as exc:
            # 走到这里说明事务本身没起来（比如任务行已被删），用新会话收尾
            outcome = await self._record_failure(claim, exc)
            return False
        except Exception as exc:  # noqa: BLE001 - 兜底，任务不能卡在 running
            self.log.exception("任务执行出现未预期异常", extra=extra)
            outcome = await self._record_failure(
                claim, TaskFailure(f"任务执行异常：{type(exc).__name__}: {exc}", retryable=True)
            )
            return False
        finally:
            metrics.record_task(claim.type, outcome == "ok", time.perf_counter() - started, outcome=outcome)

    async def _fail_in_session(self, session: AsyncSession, task: Task, failure: TaskFailure) -> str:
        """在任务自己的事务里写失败/重试，必要时清租约；返回 outcome。"""
        status = await fail_task(
            session,
            task,
            failure.error,
            retryable=failure.retryable,
            requeue_after=failure.requeue_after,
        )
        await self._publish_task_event(task, ok=False, detail=failure.error)
        if failure.release_lease and task.account_id is not None:
            await lease_core.release_account(
                session, account_id=task.account_id, worker_id=self.worker.worker_id
            )
            self.log.warning(
                "已清掉该号租约",
                extra={"worker_id": self.worker.worker_id, "account_id": str(task.account_id), "task_id": str(task.id)},
            )
        return "retried" if status == TaskStatus.pending else "failed"

    async def _record_failure(self, claim: ClaimedTask, failure: TaskFailure) -> str:
        """写失败 / 重试，必要时清租约；返回 outcome。"""
        extra = {
            "worker_id": self.worker.worker_id,
            "account_id": str(claim.account_id) if claim.account_id else "",
            "task_id": str(claim.id),
            "task_type": claim.type,
            "error": failure.error,
        }
        try:
            async with session_scope() as session:
                task = await session.get(Task, claim.id)
                if task is None:
                    return "failed"
                status = await fail_task(
                    session,
                    task,
                    failure.error,
                    retryable=failure.retryable,
                    requeue_after=failure.requeue_after,
                )
                await self._publish_task_event(task, ok=False, detail=failure.error)
                if failure.release_lease and task.account_id is not None:
                    await lease_core.release_account(
                        session, account_id=task.account_id, worker_id=self.worker.worker_id
                    )
                    self.log.warning("已清掉该号租约", extra=extra)
                    drop_account_id = task.account_id
                else:
                    drop_account_id = None
            if drop_account_id is not None:
                await self.worker.invalidate_connection(drop_account_id, drop=True)
            if status == TaskStatus.pending:
                self.log.warning("任务失败，已回队列重试", extra={**extra, "retry_in": failure.requeue_after})
                return "retried"
            self.log.error("任务失败", extra=extra)
            return "failed"
        except Exception:  # noqa: BLE001 - 收尾也失败时只记日志
            self.log.exception("任务失败收尾时出错", extra=extra)
            return "failed"

    async def _publish_task_event(self, task: Task, *, ok: bool, detail: str) -> None:
        """把任务结果推给页面（Redis 挂了不影响事实）。"""
        try:
            await core_events.publish_task_event(
                self.worker.redis,
                {
                    "task_id": str(task.id),
                    "type": _status_value(task.type),
                    "ok": ok,
                    "detail": detail,
                    "status": _status_value(task.status),
                },
            )
        except Exception:  # noqa: BLE001
            logger.debug("推送任务事件失败", extra={"task_id": str(task.id)})

    # ---------------- 公共辅助 ----------------

    def _connection(self, account_id: Optional[uuid.UUID]) -> AccountConnection:
        """取本进程持有的连接对象。"""
        if account_id is None:
            raise TaskFailure("任务缺少 account_id", retryable=False)
        if not self.worker.telegram_ready:
            # 空转模式没有连接，任务不该假装失败：配置好 API ID/HASH 重启后自动继续
            raise TaskFailure(
                "未配置 TELEGRAM_API_ID/TELEGRAM_API_HASH，Worker 空转中，无法执行该任务",
                retryable=True,
                requeue_after=60,
            )
        conn = self.worker.get_connection(account_id)
        if conn is None:
            raise TaskFailure("该号尚未建立连接（可能刚认领或正在重连），稍后重试", retryable=True, requeue_after=5)
        return conn

    def _client(self, account_id: Optional[uuid.UUID]) -> Any:
        """取在线客户端；没连上就是可重试失败。"""
        conn = self._connection(account_id)
        try:
            return conn.require_client()
        except AccountUnavailable as exc:
            raise TaskFailure(
                f"该号当前未连接（{exc}），稍后重试",
                retryable=True,
                requeue_after=max(5, settings.account_reconnect_backoff_seconds // 3),
            ) from exc

    async def _resolve_entity(self, client: Any, dialog: Dialog) -> Any:
        """tg_chat_id → Telethon 实体；打不开按约定清该号租约。"""
        try:
            return await client.get_entity(dialog.tg_chat_id)
        except Exception as exc:  # noqa: BLE001
            network = is_network_error(exc)
            raise TaskFailure(
                f"会话打不开（tg_chat_id={dialog.tg_chat_id}）：{describe_exception(exc)}",
                retryable=network,
                release_lease=not network,
            ) from exc

    async def _load_dialog(self, session: AsyncSession, task: Task, payload: dict) -> Dialog:
        """任务里的 dialog_id → dialogs 行。"""
        raw = payload.get("dialog_id") or (str(task.dialog_id) if task.dialog_id else "")
        if not raw:
            raise TaskFailure("任务缺少 dialog_id", retryable=False)
        try:
            dialog_id = uuid.UUID(str(raw))
        except ValueError as exc:
            raise TaskFailure(f"dialog_id 不是合法的 UUID：{raw}", retryable=False) from exc
        dialog = await session.get(Dialog, dialog_id)
        if dialog is None:
            raise TaskFailure("会话不存在（可能已被删除）", retryable=False)
        return dialog

    async def _apply_status(
        self, session: AsyncSession, account: TgAccount, exc: BaseException, status: Optional[AccountStatus] = None
    ) -> Optional[AccountStatus]:
        """按异常映射写回账号状态（返回写了什么，没映射就返回 None）。"""
        resolved = status or map_exception_to_status(exc)
        if resolved is None:
            account.last_error = describe_exception(exc)[:512]
            await session.flush()
            return None
        account.status = resolved
        account.status_reason = describe_exception(exc)[:255]
        account.last_error = describe_exception(exc)[:512]
        account.last_checked_at = _now()
        await session.flush()
        if resolved is AccountStatus.dead:
            # 永久双向：立刻清租约，不必等别的副本
            await lease_core.release_account(
                session, account_id=account.id, worker_id=self.worker.worker_id
            )
        return resolved

    @staticmethod
    def _failure(exc: BaseException, prefix: str, *, retryable: Optional[bool] = None) -> TaskFailure:
        """业务异常 → TaskFailure；网络类默认可重试，其它默认不可重试。"""
        wait = flood_wait_seconds(exc)
        if wait:
            return TaskFailure(f"{prefix}：{describe_exception(exc)}", retryable=True, requeue_after=wait + 1)
        if retryable is None:
            retryable = is_network_error(exc)
        return TaskFailure(f"{prefix}：{describe_exception(exc)}", retryable=retryable)

    @staticmethod
    def _clamp_limit(raw: Any, *, default: int, maximum: int) -> int:
        """payload.limit 收敛到 1..maximum。"""
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        if value <= 0:
            return default
        return min(value, maximum)

    # ---------------- 各类任务 ----------------

    async def _sync_dialogs(self, session: AsyncSession, task: Task, account: Optional[TgAccount]) -> dict:
        """同步会话列表：群聊与私信 upsert 到 dialogs，并更新群数量。"""
        assert account is not None
        client = self._client(account.id)
        try:
            dialogs = await client.get_dialogs()
        except Exception as exc:  # noqa: BLE001
            await self._apply_status(session, account, exc)
            raise self._failure(exc, "拉取会话列表失败") from exc

        groups = privates = failed = 0
        for item in dialogs:
            try:
                kind = DialogKind.group if (item.is_group or item.is_channel) else DialogKind.private
                entity = getattr(item, "entity", None)
                title = getattr(item, "title", None) or getattr(item, "name", "") or ""
                async with session.begin_nested():
                    dialog = await upsert_dialog(
                        session,
                        channel=DialogChannel.user_account,
                        kind=kind,
                        tg_chat_id=int(item.id),
                        account_id=account.id,
                        title=title,
                        username=getattr(entity, "username", None),
                        peer_display=title,
                        member_count=getattr(entity, "participants_count", None),
                    )
                    dialog.unread_count = int(getattr(item, "unread_count", 0) or 0)
                    dialog.is_pinned = bool(getattr(item, "pinned", False))
                    date = getattr(item, "date", None)
                    if date is not None:
                        dialog.last_message_at = date
                    last = getattr(item, "message", None)
                    if last is not None:
                        dialog.last_message_preview = preview_of(getattr(last, "message", "") or "")
                if kind == DialogKind.group:
                    groups += 1
                else:
                    privates += 1
            except Exception:  # noqa: BLE001 - 单个会话失败不影响整批
                failed += 1
                self.log.warning(
                    "单个会话同步失败",
                    extra={
                        "worker_id": self.worker.worker_id,
                        "account_id": str(account.id),
                        "task_id": str(task.id),
                        "tg_chat_id": getattr(item, "id", None),
                    },
                )
        account.group_count = groups
        account.last_error = f"{failed} 个会话同步失败"[:512] if failed else ""
        account.last_checked_at = _now()
        await session.flush()
        self.log.info(
            "会话同步完成",
            extra={
                "worker_id": self.worker.worker_id,
                "account_id": str(account.id),
                "task_id": str(task.id),
                "dialogs": len(dialogs),
                "groups": groups,
            },
        )
        return {"dialogs": len(dialogs), "groups": groups, "private": privates, "failed": failed}

    async def _sync_messages(self, session: AsyncSession, task: Task, account: Optional[TgAccount]) -> dict:
        """拉某个会话最近 N 条历史消息入库（靠 tg_message_id 去重，不重复转发）。"""
        assert account is not None
        payload = dict(task.payload or {})
        dialog = await self._load_dialog(session, task, payload)
        limit = self._clamp_limit(payload.get("limit"), default=50, maximum=500)
        client = self._client(account.id)
        entity = await self._resolve_entity(client, dialog)
        try:
            messages = list(await client.get_messages(entity, limit=limit))
        except Exception as exc:  # noqa: BLE001
            await self._apply_status(session, account, exc)
            raise self._failure(exc, "拉取历史消息失败") from exc

        created = failed = 0
        for msg in reversed(messages):  # 从旧到新，会话预览才是最新那条
            try:
                data = message_data_from_telethon(
                    message=msg,
                    chat=entity,
                    tg_chat_id=dialog.tg_chat_id,
                    kind=dialog.kind,
                    title=dialog.title,
                    username=dialog.username,
                    peer_display=dialog.peer_display,
                    member_count=dialog.member_count,
                )
                async with session.begin_nested():
                    # 补历史不算未读：这些是老消息，不该点亮未读角标
                    dialog_row, row, is_new = await persist_message(
                        session, account_id=account.id, data=data, count_unread=False
                    )
                    if is_new:
                        await publish_message(self.worker.redis, dialog_row, row)
                if is_new:
                    created += 1
            except Exception:  # noqa: BLE001 - 单条失败不影响整批
                failed += 1
                self.log.warning(
                    "单条历史消息入库失败",
                    extra={
                        "worker_id": self.worker.worker_id,
                        "account_id": str(account.id),
                        "task_id": str(task.id),
                        "tg_message_id": getattr(msg, "id", None),
                    },
                )
        await session.flush()
        return {
            "dialog_id": str(dialog.id),
            "fetched": len(messages),
            "created": created,
            "failed": failed,
        }

    async def _send_message(self, session: AsyncSession, task: Task, account: Optional[TgAccount]) -> dict:
        """员工确认后替用户号发出（只有 healthy 的号才发）。"""
        assert account is not None
        payload = dict(task.payload or {})
        text = str(payload.get("text") or "").strip()
        if not text:
            raise TaskFailure("发送任务缺少正文", retryable=False)
        status_value = _status_value(account.status)
        if status_value != AccountStatus.healthy.value:
            label = ACCOUNT_STATUS_LABELS.get(status_value, status_value)
            raise TaskFailure(f"账号不是正常状态（当前：{label}），不替它发送", retryable=False)

        dialog = await self._load_dialog(session, task, payload)
        client = self._client(account.id)
        entity = await self._resolve_entity(client, dialog)
        try:
            sent = await client.send_message(entity, text)
        except Exception as exc:  # noqa: BLE001
            wait = flood_wait_seconds(exc)
            if wait:
                # 限流是临时的：写熔断冷却（期间别的发送类任务也会被闸门挡住），只记 last_error，不动状态
                await note_flood(account, wait)
                account.last_error = describe_exception(exc)[:512]
                await session.flush()
                self.log.warning(
                    "发送被限流，稍后重试",
                    extra={
                        "worker_id": self.worker.worker_id,
                        "account_id": str(account.id),
                        "task_id": str(task.id),
                        "wait": wait,
                    },
                )
                raise TaskFailure(
                    f"Telegram 限流，{wait} 秒后重试：{describe_exception(exc)}",
                    retryable=True,
                    requeue_after=wait + 1,
                ) from exc
            status = map_exception_to_status(exc)
            await self._apply_status(session, account, exc, status)
            raise self._failure(exc, "发送失败", retryable=status is None) from exc

        row = await self._mark_message_sent(session, task=task, dialog=dialog, account=account, text=text, sent=sent)
        await self._throttle_record(account, task, cost=1)
        self.log.info(
            "消息已发出",
            extra={
                "worker_id": self.worker.worker_id,
                "account_id": str(account.id),
                "task_id": str(task.id),
                "dialog_id": str(dialog.id),
                "tg_message_id": getattr(sent, "id", None),
            },
        )
        return {
            "tg_message_id": getattr(sent, "id", None),
            "dialog_id": str(dialog.id),
            "message_id": str(row.id) if row is not None else None,
        }

    async def _mark_message_sent(
        self,
        session: AsyncSession,
        *,
        task: Task,
        dialog: Dialog,
        account: TgAccount,
        text: str,
        sent: Any,
    ) -> Optional[Message]:
        """回填 messages 行：status=sent、tg_message_id、direction=outgoing，并推页面。"""
        payload = dict(task.payload or {})
        row: Optional[Message] = None
        raw_message_id = payload.get("message_id")
        if raw_message_id:
            try:
                row = await session.get(Message, uuid.UUID(str(raw_message_id)))
            except (ValueError, AttributeError):
                row = None
        if row is None and getattr(sent, "id", None) is not None:
            row = await session.scalar(
                select(Message).where(Message.dialog_id == dialog.id, Message.tg_message_id == sent.id)
            )
        if row is None:
            data = MessageData(
                tg_chat_id=dialog.tg_chat_id,
                kind=dialog.kind,
                title=dialog.title,
                username=dialog.username,
                peer_display=dialog.peer_display,
                member_count=dialog.member_count,
                body=text,
                tg_message_id=getattr(sent, "id", None),
                direction=MessageDirection.outgoing,
                status=MessageStatus.sent,
                sender_name=account.display_name or "",
                raw={"source": "worker_send"},
            )
            _, row, _ = await persist_message(session, account_id=account.id, data=data)
        else:
            row.status = MessageStatus.sent
            row.direction = MessageDirection.outgoing
            row.tg_message_id = getattr(sent, "id", None) or row.tg_message_id
            row.body = row.body or text
            row.sender_name = row.sender_name or account.display_name or ""
            row.raw = {**(row.raw or {}), "sent_by_worker": self.worker.worker_id}

        dialog.last_message_at = getattr(sent, "date", None) or _now()
        dialog.last_message_preview = preview_of(text)
        dialog.unread_count = 0
        await session.flush()
        await publish_message(self.worker.redis, dialog, row)
        await self._close_draft(session, payload=payload, task=task, row=row)
        return row

    async def _close_draft(self, session: AsyncSession, *, payload: dict, task: Task, row: Message) -> None:
        """带 draft_id 时把 AI 草稿标成已发送。"""
        draft_id = payload.get("draft_id")
        if not draft_id:
            return
        try:
            draft = await session.get(ReplyDraft, uuid.UUID(str(draft_id)))
        except (ValueError, AttributeError):
            return
        if draft is None:
            return
        draft.status = DraftStatus.sent
        draft.sent_at = _now()
        draft.sent_message_id = row.id
        if draft.sent_by is None:
            draft.sent_by = task.created_by
        await session.flush()

    async def _account_check(self, session: AsyncSession, task: Task, account: Optional[TgAccount]) -> dict:
        """单号检测：连得上 / 要验证码 / 会话失效。"""
        assert account is not None
        if not self.worker.telegram_ready:
            raise TaskFailure(
                "未配置 TELEGRAM_API_ID/TELEGRAM_API_HASH，Worker 空转中，无法连接 Telegram",
                retryable=True,
                requeue_after=60,
            )
        if not account.session_enc:
            account.status = AccountStatus.needs_code
            account.status_reason = "该号还没有会话，需要验证码登录"
            account.last_error = "没有可用会话，请先用验证码登录"
            account.last_checked_at = _now()
            await session.flush()
            raise TaskFailure("该号还没有会话，请先用验证码登录", retryable=False)

        conn = self.worker.get_connection(account.id)
        if conn is None:
            raise TaskFailure("该号不在本进程的租约里，稍后由持有它的 Worker 检测", retryable=True, requeue_after=10)
        try:
            me = await conn.ensure_and_get_me()
        except AccountUnavailable as exc:
            account.last_checked_at = _now()
            account.last_error = str(exc)[:512]
            await session.flush()
            raise TaskFailure(f"该号当前连不上（{exc}），稍后重试", retryable=True, requeue_after=30) from exc
        except Exception as exc:  # noqa: BLE001
            await self._apply_status(session, account, exc)
            raise TaskFailure(f"账号检测失败：{describe_exception(exc)}", retryable=False) from exc

        await persist_identity(session, account, me)
        status_value = _status_value(account.status)
        payload = dict(task.payload or {})
        health: Optional[dict] = None
        if payload.get("deep"):
            health = await self._deep_probe(
                session, task, account, conn, write_probe=bool(payload.get("write_probe"))
            )
        result = {
            "reachable": True,
            "status": status_value,
            "status_label": ACCOUNT_STATUS_LABELS.get(status_value, status_value),
            "tg_user_id": account.tg_user_id,
            "username": account.username,
            "display_name": account.display_name,
        }
        if health is not None:
            result["health"] = health
            result["health_score"] = account.health_score
        return result

    async def _deep_probe(
        self,
        session: AsyncSession,
        task: Task,
        account: TgAccount,
        conn: AccountConnection,
        *,
        write_probe: bool,
    ) -> dict:
        """深度验活：读权限 / 授权会话数 / 可选写权限探测，复算 health_score 与风险标记。

        轻检（普通检测）只回答「连得上」；深度验活要回答「这个号还能不能用来干活」：
        - 读权限：能不能列会话（被限制的号常常读得到但发不出，所以读通过不代表健康）；
        - 授权会话数：突然变多说明可能被异地登录；
        - 写探测（可选）：往自己的收藏夹发一条，确认写权限与限流状态；
        - 结合账号状态与历史限流次数折算 0-100 的健康分。
        """
        detail: dict[str, Any] = {"checked_at": _now().isoformat(), "deep": True}
        score = 100
        try:
            client = conn.require_client()
        except AccountUnavailable as exc:
            raise TaskFailure(f"该号当前未连接（{exc}）", retryable=True, requeue_after=15) from exc

        try:
            await client.get_dialogs(limit=1)
            detail["read_ok"] = True
        except Exception as exc:  # noqa: BLE001 - 读失败也要把原因记下来
            detail["read_ok"] = False
            detail["read_error"] = describe_exception(exc)
            score -= 30

        try:
            auths = await client(functions.account.GetAuthorizationsRequest())
            detail["auth_count"] = len(getattr(auths, "authorizations", []) or [])
        except Exception:  # noqa: BLE001 - 拿不到不算失败
            detail["auth_count"] = None

        if write_probe:
            try:
                await client.send_message("me", "云控验活探测（可自行删除）")
                detail["write_ok"] = True
                await self._throttle_record(account, task, cost=1)
            except Exception as exc:  # noqa: BLE001
                detail["write_ok"] = False
                wait = flood_wait_seconds(exc)
                if wait:
                    await note_flood(account, wait)
                    detail["flood_wait"] = wait
                    score -= 25
                else:
                    detail["write_error"] = describe_exception(exc)
                    score -= 45

        status_value = _status_value(account.status)
        if status_value != AccountStatus.healthy.value:
            score -= 25
        if int(getattr(account, "flood_strikes", 0) or 0) >= 3:
            score -= 15
        account.health_score = max(0, min(100, score))
        account.health_checked_at = _now()
        account.health_detail = detail
        flags = dict(account.risk_flags or {})
        flags["restricted"] = detail.get("write_ok") is False or status_value in (
            AccountStatus.frozen.value,
            AccountStatus.invalid.value,
            AccountStatus.dead.value,
        )
        flags["last_probe_at"] = detail["checked_at"]
        account.risk_flags = flags
        await session.flush()
        self.log.info(
            "深度验活完成",
            extra={
                "worker_id": self.worker.worker_id,
                "account_id": str(account.id),
                "task_id": str(task.id),
                "health_score": account.health_score,
                "read_ok": detail.get("read_ok"),
                "write_ok": detail.get("write_ok"),
            },
        )
        return {"score": account.health_score, **detail}

    async def _update_profile(self, session: AsyncSession, task: Task, account: Optional[TgAccount]) -> dict:
        """改本号名称 / 简介 / 用户名 / 头像。"""
        assert account is not None
        payload = {key: value for key, value in dict(task.payload or {}).items() if value not in (None, "")}
        if not payload:
            raise TaskFailure("修改资料任务没有可执行字段", retryable=False)
        client = self._client(account.id)
        changed: list[str] = []
        try:
            profile: dict[str, Any] = {}
            if "first_name" in payload:
                profile["first_name"] = str(payload["first_name"])
            if "last_name" in payload:
                profile["last_name"] = str(payload["last_name"])
            bio = payload.get("bio") or payload.get("about")
            if bio:
                profile["about"] = str(bio)
            if profile:
                await client(functions.account.UpdateProfileRequest(**profile))
                changed.extend(sorted(profile))
            if payload.get("username"):
                await client(functions.account.UpdateUsernameRequest(username=str(payload["username"])))
                changed.append("username")
            if payload.get("photo_url"):
                await self._upload_profile_photo(client, str(payload["photo_url"]))
                changed.append("photo")
        except UsernameOccupiedError as exc:
            raise TaskFailure(f"用户名已被占用：{payload.get('username')}", retryable=False) from exc
        except UsernameInvalidError as exc:
            raise TaskFailure(f"用户名不合法：{payload.get('username')}", retryable=False) from exc
        except Exception as exc:  # noqa: BLE001
            await self._apply_status(session, account, exc)
            raise self._failure(exc, "修改资料失败", retryable=False) from exc

        me = await client.get_me()
        await persist_identity(session, account, me)
        await audit_core.write_audit(
            session,
            action="account.profile_update",
            account_id=account.id,
            target_type="tg_account",
            target_id=str(account.id),
            detail={"updated": changed},
        )
        return {"updated": changed, "display_name": account.display_name, "username": account.username}

    async def _upload_profile_photo(self, client: Any, photo_url: str) -> None:
        """下载图片并设为头像（只需要 httpx，已在 requirements 里）。"""
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - 依赖缺失时才走到
            raise TaskFailure("服务端缺少 httpx，无法下载头像", retryable=False) from exc
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http:
                resp = await http.get(photo_url)
                resp.raise_for_status()
                content = resp.content
        except Exception as exc:  # noqa: BLE001 - 外部图片地址不可控
            raise TaskFailure(f"头像下载失败：{type(exc).__name__}: {exc}", retryable=True, requeue_after=30) from exc
        if not content:
            raise TaskFailure("头像下载为空", retryable=False)
        uploaded = await client.upload_file(io.BytesIO(content), file_name="avatar.jpg")
        await client(functions.photos.UploadProfilePhotoRequest(file=uploaded))

    async def _login_start(self, session: AsyncSession, task: Task, account: Optional[TgAccount]) -> dict:
        """登录第一步：发送验证码。"""
        assert account is not None
        return await login_flow.login_start(session, task=task, account=account, worker=self.worker)

    async def _login_code(self, session: AsyncSession, task: Task, account: Optional[TgAccount]) -> dict:
        """登录第二步：提交验证码。"""
        assert account is not None
        return await login_flow.login_code(session, task=task, account=account, worker=self.worker)

    async def _login_password(self, session: AsyncSession, task: Task, account: Optional[TgAccount]) -> dict:
        """登录第三步：提交两步验证密码。"""
        assert account is not None
        return await login_flow.login_password(session, task=task, account=account, worker=self.worker)


__all__ = ["ClaimedTask", "LOGIN_TYPES", "TaskFailure", "TaskRunner"]
