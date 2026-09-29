"""Bot 任务轮询：API 自己领取带 bot_id 的任务并执行（relay_to_staff / bot_reply / reply_to_origin）。

为什么是 API 而不是 Worker：Bot 收发走 Webhook + Bot API，与某台 Worker 上挂的用户号无关，
Webhook 无状态，谁接到都可以处理。领取用 `core.tasks.claim_tasks(kind="bot")`，
与 Worker 侧 `kind="worker"` 互不干扰。
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aiogram.exceptions import TelegramAPIError

from app.api.bots import manager
from app.api.routers import publish_safely, publish_task_safely
from app.config import settings
from app.core.audit import write_audit
from app.core.tasks import claim_tasks, complete_task, enqueue_task, fail_task
from app.db import SessionFactory
from app.models import (
    Bot,
    Dialog,
    DialogChannel,
    Message,
    MessageDirection,
    MessageStatus,
    Task,
    TaskStatus,
    TaskType,
    TgAccount,
)
from app.services import inbound, relay
from app.services.ai import AIUnavailable, ai_service

logger = logging.getLogger(__name__)

#: 启动时把「上一个 API 进程留下、还卡在 running」的 Bot 任务放回队列
STALE_RUNNING_SECONDS = 300

#: 轮询里多久顺带回收一次卡住的 Bot 任务
RECLAIM_INTERVAL_SECONDS = 60.0


class TaskPayloadError(RuntimeError):
    """任务载荷缺字段或指向的对象已经没了，重试也没用。"""


def _uuid_field(task: Task, key: str) -> uuid.UUID:
    raw = (task.payload or {}).get(key)
    if not raw:
        raise TaskPayloadError(f"任务载荷缺少字段 {key}")
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError) as exc:
        raise TaskPayloadError(f"任务载荷字段 {key} 不是合法 UUID：{raw}") from exc


async def _load_bot(session: AsyncSession, bot_id: Optional[uuid.UUID]) -> Bot:
    if bot_id is None:
        raise TaskPayloadError("任务没有绑定 Bot")
    bot = await session.scalar(select(Bot).where(Bot.id == bot_id))
    if bot is None:
        raise TaskPayloadError("Bot 已被删除，无法执行该任务")
    return bot


async def _load_message(session: AsyncSession, message_id: uuid.UUID) -> Message:
    message = await session.scalar(select(Message).where(Message.id == message_id))
    if message is None:
        raise TaskPayloadError("原消息已被删除")
    return message


async def _load_dialog(session: AsyncSession, dialog_id: uuid.UUID) -> Dialog:
    dialog = await session.scalar(select(Dialog).where(Dialog.id == dialog_id))
    if dialog is None:
        raise TaskPayloadError("会话已被删除")
    return dialog


async def _history(session: AsyncSession, dialog_id: uuid.UUID, limit: int) -> list[Message]:
    rows = await session.scalars(
        select(Message)
        .where(Message.dialog_id == dialog_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(reversed(list(rows.all())))


# ---------------- 三个执行器 ----------------

async def _handle_relay_to_staff(session: AsyncSession, task: Task) -> None:
    """把一条收到的消息转发到员工群，并记下（员工群消息 → 原消息）的对应关系。"""
    message_id = _uuid_field(task, "message_id")
    dialog_id = _uuid_field(task, "dialog_id")
    staff_chat_id = (task.payload or {}).get("staff_chat_id")
    if staff_chat_id is None:
        raise TaskPayloadError("任务载荷缺少字段 staff_chat_id")
    route_id: Optional[uuid.UUID] = None
    if (task.payload or {}).get("route_id"):
        try:
            route_id = uuid.UUID(str(task.payload["route_id"]))
        except (ValueError, TypeError):
            route_id = None

    message = await _load_message(session, message_id)
    dialog = await _load_dialog(session, dialog_id)
    sender_bot = await _load_bot(session, task.bot_id)

    # 来源标注用「收到这条消息的那个号 / 那个 Bot」，不是转发用的 Bot
    account, source_bot = await relay.context_for_message(session, dialog=dialog)
    text = relay.format_relay_text(
        dialog=dialog,
        message=message,
        account=account,
        bot=source_bot,
        sender_name=message.sender_name,
    )

    runtime = await manager.ensure_runtime(sender_bot)
    if runtime is None:
        raise TaskPayloadError("Bot 运行时不可用：Token 无法解密，请重新保存 Token")

    sent = await manager.send_text(runtime, int(staff_chat_id), text)
    link = await relay.record_relay_link(
        session,
        route_id=route_id,
        bot_id=sender_bot.id,
        message_id=message.id,
        staff_chat_id=int(staff_chat_id),
        staff_message_id=sent.message_id,
    )
    await write_audit(
        session,
        action="relay.forward",
        account_id=dialog.account_id,
        bot_id=sender_bot.id,
        target_type="message",
        target_id=str(message.id),
        detail={
            "staff_chat_id": int(staff_chat_id),
            "staff_message_id": sent.message_id,
            "relay_link_id": str(link.id),
        },
    )
    await complete_task(
        session,
        task,
        result={
            "staff_chat_id": int(staff_chat_id),
            "staff_message_id": sent.message_id,
            "message_id": str(message.id),
        },
    )
    logger.info(
        "已转发到员工群 task_id=%s staff_chat_id=%s staff_message_id=%s",
        task.id,
        staff_chat_id,
        sent.message_id,
        extra={"task_id": str(task.id), "bot_id": str(sender_bot.id), "dialog_id": str(dialog.id)},
    )


async def _handle_bot_reply(session: AsyncSession, task: Task) -> None:
    """官方 Bot 按自己的资料自动回复，身份是 Bot。AI 不可用就明确失败，不静默。"""
    dialog_id = _uuid_field(task, "dialog_id")
    dialog = await _load_dialog(session, dialog_id)
    bot_row = await _load_bot(session, task.bot_id or dialog.bot_id)

    history = await _history(session, dialog.id, settings.ai_max_history)
    try:
        text = await ai_service.bot_auto_reply(bot=bot_row, dialog=dialog, history=history)
    except AIUnavailable as exc:
        # 没配模型通道是配置问题，重试多少次都一样
        await fail_task(session, task, f"AI 不可用，无法自动回复：{exc}", retryable=False)
        logger.warning("Bot 自动回复跳过（AI 不可用）task_id=%s dialog_id=%s", task.id, dialog.id)
        return

    runtime = await manager.ensure_runtime(bot_row)
    if runtime is None:
        raise TaskPayloadError("Bot 运行时不可用：Token 无法解密，请重新保存 Token")
    sent = await manager.send_text(runtime, dialog.tg_chat_id, text)

    dialog, message, _created = await inbound.ingest_message(
        session,
        channel=DialogChannel.bot,
        direction=MessageDirection.outgoing,
        tg_chat_id=dialog.tg_chat_id,
        kind=dialog.kind,
        bot_id=bot_row.id,
        title=dialog.title,
        peer_display=dialog.peer_display,
        body=text,
        tg_message_id=sent.message_id,
        sender_name=bot_row.bot_username or bot_row.name,
        status=MessageStatus.sent,
    )
    await write_audit(
        session,
        action="bot.auto_reply",
        bot_id=bot_row.id,
        target_type="dialog",
        target_id=str(dialog.id),
        detail={"message_id": str(message.id), "model": settings.ai_model, "preview": text[:80]},
    )
    await complete_task(
        session, task, result={"message_id": str(message.id), "tg_message_id": sent.message_id}
    )
    await publish_safely(dialog, message)
    logger.info(
        "Bot 自动回复已发出 task_id=%s dialog_id=%s",
        task.id,
        dialog.id,
        extra={"task_id": str(task.id), "bot_id": str(bot_row.id), "dialog_id": str(dialog.id)},
    )


async def _handle_reply_to_origin(session: AsyncSession, task: Task) -> None:
    """员工在员工群里回复那条转发：Bot 会话直接发回原会话；用户号会话写成待发送任务。"""
    dialog_id = _uuid_field(task, "dialog_id")
    dialog = await _load_dialog(session, dialog_id)
    text = str((task.payload or {}).get("text") or "").strip()
    if not text:
        raise TaskPayloadError("回复内容为空")

    if str(getattr(dialog.channel, "value", dialog.channel)) == DialogChannel.bot.value:
        bot_row = await _load_bot(session, task.bot_id or dialog.bot_id)
        runtime = await manager.ensure_runtime(bot_row)
        if runtime is None:
            raise TaskPayloadError("Bot 运行时不可用：Token 无法解密，请重新保存 Token")
        sent = await manager.send_text(runtime, dialog.tg_chat_id, text)
        dialog, message, _created = await inbound.ingest_message(
            session,
            channel=DialogChannel.bot,
            direction=MessageDirection.outgoing,
            tg_chat_id=dialog.tg_chat_id,
            kind=dialog.kind,
            bot_id=bot_row.id,
            title=dialog.title,
            peer_display=dialog.peer_display,
            body=text,
            tg_message_id=sent.message_id,
            sender_name=bot_row.bot_username or bot_row.name,
            status=MessageStatus.sent,
        )
        await write_audit(
            session,
            action="relay.reply",
            bot_id=bot_row.id,
            target_type="dialog",
            target_id=str(dialog.id),
            detail={"message_id": str(message.id), "staff_message_id": (task.payload or {}).get("staff_message_id")},
        )
        await complete_task(
            session, task, result={"message_id": str(message.id), "tg_message_id": sent.message_id}
        )
        await publish_safely(dialog, message)
        return

    # 用户号通道：仍然遵守「先预写 pending 消息，再交给持有租约的 Worker 发」
    if dialog.account_id is None:
        raise TaskPayloadError("会话没有绑定用户号")
    account = await session.scalar(select(TgAccount).where(TgAccount.id == dialog.account_id))
    if account is None:
        raise TaskPayloadError("会话对应的账号已被删除")
    if not relay.account_can_send(account):
        label = getattr(account.status, "value", account.status)
        await fail_task(
            session,
            task,
            f"账号 {account.phone_masked} 当前状态「{label}」，不能发送，等号恢复后在任务中心重试",
            retryable=False,
        )
        return

    message = Message(
        dialog_id=dialog.id,
        channel=DialogChannel.user_account,
        direction=MessageDirection.outgoing,
        status=MessageStatus.pending,
        body=text,
        sender_name="员工群回复",
    )
    session.add(message)
    await session.flush()
    dialog.last_message_at = message.created_at or message.updated_at
    dialog.last_message_preview = inbound.preview_of(text)
    dialog.unread_count = 0

    send_task = await enqueue_task(
        session,
        type=TaskType.send_message,
        account_id=account.id,
        dialog_id=dialog.id,
        payload={"dialog_id": str(dialog.id), "text": text, "message_id": str(message.id)},
        priority=40,
    )
    await write_audit(
        session,
        action="relay.reply",
        account_id=account.id,
        target_type="dialog",
        target_id=str(dialog.id),
        detail={
            "message_id": str(message.id),
            "send_task_id": str(send_task.id),
            "staff_message_id": (task.payload or {}).get("staff_message_id"),
        },
    )
    await complete_task(
        session, task, result={"message_id": str(message.id), "send_task_id": str(send_task.id)}
    )
    await publish_safely(dialog, message)
    logger.info(
        "员工群回复已转成发送任务 task_id=%s send_task_id=%s",
        task.id,
        send_task.id,
        extra={"task_id": str(task.id), "account_id": str(account.id), "dialog_id": str(dialog.id)},
    )


async def _handle_bot_broadcast(session: AsyncSession, task: Task) -> None:
    """Bot 群发/转发：用 Bot 把消息发到指定群。

    两种用法（payload）：
    - `text`：直接发这段文字；
    - `forward_from_chat_id` + `forward_from_message_id`：把某条已有消息**转发**过去
      （群发转发场景：原消息在某个群/频道，用 Bot 原样转到多个目标群）。

    支持 `targets`（多个群）批量，以及 `send_window` / `daily_quota` 的门禁思路——
    Bot 侧没有账号的节流与冻结概念，所以这里只做间隔，不做配额（配额是防号被限流用的）。
    """
    payload = dict(task.payload or {})
    targets = [str(item).strip() for item in (payload.get("targets") or []) if str(item).strip()]
    single = str(payload.get("target") or "").strip()
    if single and single not in targets:
        targets.insert(0, single)
    if not targets:
        raise TaskPayloadError("Bot 群发任务缺少目标（targets / target）")

    text = str(payload.get("text") or "")
    forward_chat_id = payload.get("forward_from_chat_id")
    forward_message_id = payload.get("forward_from_message_id")
    if not text and forward_chat_id is None:
        raise TaskPayloadError("Bot 群发需要 text（直接发文字）或 forward_from_*（转发已有消息）")

    sender_bot = await _load_bot(session, task.bot_id)
    runtime = await manager.ensure_runtime(sender_bot)
    if runtime is None:
        raise TaskPayloadError("Bot 运行时不可用：Token 无法解密，请重新保存 Token")

    sent = failed = 0
    results: list[dict] = []
    for target in targets:
        try:
            if forward_chat_id is not None and forward_message_id is not None:
                # 走 manager 的统一封装：属性是 runtime.bot（不是 .client），
                # 且带 15 秒超时 + 中文错误翻译 + 可重试判定
                await manager.forward_message(
                    runtime, target, int(forward_chat_id), int(forward_message_id)
                )
                via = "forward"
            else:
                await manager.send_text(runtime, target, text)
                via = "text"
            sent += 1
            results.append({"target": target, "ok": True, "via": via})
        except BaseException as exc:  # noqa: BLE001 - 单个群失败继续下一个
            failed += 1
            results.append({"target": target, "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:120]}"})

    task.result = {"sent": sent, "failed": failed, "total": len(targets), "results": results[:50]}
    if sent == 0 and failed:
        raise TaskPayloadError(f"Bot 群发全部失败，首错：{results[0].get('error')}")


_HANDLERS = {
    TaskType.relay_to_staff.value: _handle_relay_to_staff,
    TaskType.bot_reply.value: _handle_bot_reply,
    TaskType.reply_to_origin.value: _handle_reply_to_origin,
    TaskType.bot_broadcast.value: _handle_bot_broadcast,
}


async def handle_task(session: AsyncSession, task: Task) -> None:
    """按类型分派。抛出的异常由 _run_one 统一记失败。"""
    task_type = task.type.value if hasattr(task.type, "value") else str(task.type)
    handler = _HANDLERS.get(task_type)
    if handler is None:
        await fail_task(session, task, f"API 不支持这个 Bot 任务类型：{task_type}", retryable=False)
        return
    await handler(session, task)


async def _requeue_cancelled(*, task_id: uuid.UUID, task_type: str) -> None:
    """关停时把没做完的任务放回 pending（用全新会话，避免用到已被取消的事务）。"""
    from datetime import datetime, timedelta, timezone

    try:
        async with SessionFactory() as fresh_session:
            row = await fresh_session.scalar(select(Task).where(Task.id == task_id))
            if row is None or row.status != TaskStatus.running:
                return
            row.status = TaskStatus.pending
            row.worker_id = None
            row.error = "API 进程关停，任务已放回队列"
            row.next_run_at = datetime.now(tz=timezone.utc) + timedelta(seconds=5)
            await fresh_session.commit()
        logger.warning("API 关停，任务已放回队列 task_id=%s type=%s", task_id, task_type)
    except Exception:  # noqa: BLE001 - 关停路径尽力而为，放不回去还有 reclaim 兜底
        logger.warning("关停时放回任务失败 task_id=%s（下次启动 reclaim 会处理）", task_id, exc_info=True)


async def _run_one(session: AsyncSession, task: Task, claimer_id: str) -> None:
    """执行一条任务：成功提交、失败记原因并退回队列（值得重试时）。"""
    task_id = task.id
    bot_id = task.bot_id
    task_type = task.type.value if hasattr(task.type, "value") else str(task.type)
    try:
        await handle_task(session, task)
        await session.commit()
        await publish_task_safely({"task_id": str(task_id), "type": task_type, "ok": True, "detail": ""})
    except asyncio.CancelledError:
        # 进程要退出了（部署滚动 / kill）：这一条已经认领但还没做完，
        # 用一个新的会话把它放回队列 —— 重新发一次消息，好过让这条转发彻底丢掉。
        await session.rollback()
        await _requeue_cancelled(task_id=task_id, task_type=task_type)
        raise
    except Exception as exc:  # noqa: BLE001 - 单条任务失败不能拖垮轮询
        await session.rollback()
        detail = (
            manager.describe_telegram_error(exc)
            if isinstance(exc, (manager.BotSendError, manager.BotTokenError, TelegramAPIError))
            else (str(exc) or type(exc).__name__)
        )
        retryable = getattr(exc, "retryable", not isinstance(exc, TaskPayloadError))
        fresh = await session.scalar(select(Task).where(Task.id == task_id))
        if fresh is None:
            logger.error("任务行已消失，无法记录失败 task_id=%s", task_id)
            return
        await fail_task(session, fresh, detail, retryable=retryable)
        await session.commit()
        logger.error(
            "Bot 任务失败 task_id=%s type=%s retryable=%s：%s",
            task_id,
            task_type,
            retryable,
            detail,
            extra={"task_id": str(task_id), "bot_id": str(bot_id) if bot_id else None},
        )
        await publish_task_safely(
            {"task_id": str(task_id), "type": task_type, "ok": False, "detail": detail}
        )


async def reclaim_stale_api_tasks(session: AsyncSession, *, older_than_seconds: int = STALE_RUNNING_SECONDS) -> int:
    """把上一个 API 进程留下的 running Bot 任务放回队列（进程被 kill 时来不及收尾）。"""
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=older_than_seconds)
    result = await session.execute(
        update(Task)
        .where(
            Task.status == TaskStatus.running,
            Task.bot_id.is_not(None),
            Task.account_id.is_(None),
            Task.worker_id.like("api-%"),
            (Task.started_at.is_(None)) | (Task.started_at < cutoff),
        )
        .values(status=TaskStatus.pending, worker_id=None, next_run_at=datetime.now(tz=timezone.utc))
    )
    await session.commit()
    count = int(result.rowcount or 0)
    if count:
        logger.warning("已把 %s 条卡住的 Bot 任务放回队列", count)
    return count


async def poll_loop() -> None:
    """lifespan 起的轮询协程：认领 → 执行 → 提交，间隔 settings.bot_task_poll_interval。

    每隔 RECLAIM_INTERVAL_SECONDS 顺带回收一次卡在 running 的 Bot 任务：
    只在启动时回收不够 —— 进程如果很快重启（滚动发布），上次留下的任务
    因为没到 STALE_RUNNING_SECONDS 不会被回收，就会一直挂着。
    """
    claimer_id = f"api-{os.getpid()}"
    interval = max(0.2, float(settings.bot_task_poll_interval))
    logger.info("Bot 任务轮询启动 claimer=%s interval=%ss", claimer_id, interval)
    next_reclaim_at = 0.0  # 0 = 立刻先回收一次
    while True:
        try:
            task_ids: list[tuple[uuid.UUID, str]] = []
            async with SessionFactory() as session:
                now = asyncio.get_running_loop().time()
                if now >= next_reclaim_at:
                    next_reclaim_at = now + RECLAIM_INTERVAL_SECONDS
                    await reclaim_stale_api_tasks(session)
                claimed = await claim_tasks(session, claimer_id=claimer_id, kind="bot")
                # 先把 id 取出来：回滚会让 ORM 对象过期，后面不能再用这些对象
                task_ids = [
                    (item.id, item.type.value if hasattr(item.type, "value") else str(item.type))
                    for item in claimed
                ]
            for index, (task_id, task_type) in enumerate(task_ids):
                try:
                    # 每条任务单独一个会话：一条失败回滚不会把同批其它任务的对象搞过期
                    async with SessionFactory() as session:
                        task = await session.scalar(select(Task).where(Task.id == task_id))
                        if task is None or task.status != TaskStatus.running or task.worker_id != claimer_id:
                            continue
                        await _run_one(session, task, claimer_id)
                except asyncio.CancelledError:
                    # 关停：本条任务（_run_one 已尽力放回）和本批还没轮到的都放回 pending，
                    # 否则它们要等 reclaim（默认 5 分钟）才被重新捡起来。
                    await _requeue_cancelled(task_id=task_id, task_type=task_type)
                    for rest_id, rest_type in task_ids[index + 1 :]:
                        await _requeue_cancelled(task_id=rest_id, task_type=rest_type)
                    raise
        except asyncio.CancelledError:
            logger.info("Bot 任务轮询收到停止信号，退出")
            raise
        except Exception:  # noqa: BLE001 - 数据库抖动也要继续轮询
            logger.error("Bot 任务轮询出错", exc_info=True)
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise


__all__ = ["handle_task", "poll_loop", "reclaim_stale_api_tasks"]
