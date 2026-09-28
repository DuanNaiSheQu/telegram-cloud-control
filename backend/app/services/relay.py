"""Bot 转发：新消息入库后写一条任务，用指定 Bot 发到员工群；员工群回复按 relay_links 送回。"""

from __future__ import annotations

import uuid
from typing import Optional, Sequence, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import events
from app.core.tasks import enqueue_task
from app.models import (
    AccountStatus,
    Bot,
    Dialog,
    DialogChannel,
    DialogKind,
    Message,
    MessageDirection,
    RelayLink,
    RelayRoute,
    TgAccount,
    Task,
    TaskType,
)


def _label_account(account: Optional[TgAccount]) -> str:
    if account is None:
        return "未知号"
    if account.phone_masked and account.phone_masked != "未知":
        return account.phone_masked
    if account.username:
        return f"@{account.username}"
    return str(account.id)[:8]


def source_header(
    *, dialog: Dialog, account: Optional[TgAccount] = None, bot: Optional[Bot] = None
) -> str:
    """带上来源：哪个号 / 哪个 Bot、群还是私信、对方是谁。"""
    if dialog.channel == DialogChannel.user_account:
        owner = f"用户号 {_label_account(account)}"
    else:
        owner = f"Bot @{bot.bot_username}" if bot and bot.bot_username else "官方 Bot"
    kind = "群聊" if dialog.kind == DialogKind.group else "私信"
    peer = dialog.peer_display or dialog.title or str(dialog.tg_chat_id)
    return f"来源：{owner} · {kind} · 对方：{peer}"


def format_relay_text(
    *, dialog: Dialog, message: Message, account: Optional[TgAccount] = None, bot: Optional[Bot] = None,
    sender_name: str = "",
) -> str:
    lines = []
    if settings.relay_include_source_header:
        lines.append(source_header(dialog=dialog, account=account, bot=bot))
        lines.append(f"会话：{dialog.title}（chat_id={dialog.tg_chat_id}）")
    who = sender_name or message.sender_name or "对方"
    lines.append(f"{who}：{message.body or '（空消息）'}")
    return "\n".join(lines)


async def matching_routes(session: AsyncSession, *, dialog: Dialog) -> Sequence[RelayRoute]:
    """命中的转发规则：未过滤，或正好过滤到这个号 / 这个会话。"""
    stmt = select(RelayRoute).where(
        RelayRoute.enabled.is_(True),
        or_(RelayRoute.account_id.is_(None), RelayRoute.account_id == dialog.account_id),
        or_(RelayRoute.dialog_id.is_(None), RelayRoute.dialog_id == dialog.id),
    )
    return list((await session.scalars(stmt)).all())


async def enqueue_relays(
    session: AsyncSession, *, dialog: Dialog, message: Message
) -> list[Task]:
    """给每条命中的规则写一条转发任务。只转发收到的消息。"""
    if message.direction != MessageDirection.incoming:
        return []
    tasks: list[Task] = []
    for route in await matching_routes(session, dialog=dialog):
        task = await enqueue_task(
            session,
            type=TaskType.relay_to_staff,
            bot_id=route.bot_id,
            dialog_id=dialog.id,
            payload={
                "route_id": str(route.id),
                "message_id": str(message.id),
                "dialog_id": str(dialog.id),
                "staff_chat_id": route.staff_chat_id,
            },
            priority=50,
            dedupe_key=f"relay:{message.id}:{route.id}",
        )
        tasks.append(task)
    if tasks:
        dialog_task_note = None  # 账号当前任务由 Worker 侧维护
        del dialog_task_note
        await session.flush()
    return tasks


async def record_relay_link(
    session: AsyncSession,
    *,
    route_id: Optional[uuid.UUID],
    bot_id: uuid.UUID,
    message_id: uuid.UUID,
    staff_chat_id: int,
    staff_message_id: int,
) -> RelayLink:
    link = RelayLink(
        route_id=route_id,
        bot_id=bot_id,
        message_id=message_id,
        staff_chat_id=staff_chat_id,
        staff_message_id=staff_message_id,
    )
    session.add(link)
    await session.flush()
    return link


async def find_origin_by_staff_reply(
    session: AsyncSession, *, staff_chat_id: int, staff_message_id: int
) -> Optional[Tuple[RelayLink, Message, Dialog]]:
    """员工在员工群里回复某条转发，找到原消息和原会话。"""
    link = await session.scalar(
        select(RelayLink).where(
            RelayLink.staff_chat_id == staff_chat_id,
            RelayLink.staff_message_id == staff_message_id,
        )
    )
    if link is None:
        return None
    message = await session.scalar(select(Message).where(Message.id == link.message_id))
    if message is None:
        return None
    dialog = await session.scalar(select(Dialog).where(Dialog.id == message.dialog_id))
    if dialog is None:
        return None
    return link, message, dialog


async def staff_chat_ids(session: AsyncSession) -> set[int]:
    """所有员工群 chat_id，用于识别员工群里的回复。"""
    ids = set(
        (await session.scalars(select(RelayRoute.staff_chat_id).where(RelayRoute.enabled.is_(True)))).all()
    )
    ids.update(
        (
            await session.scalars(
                select(Bot.relay_target_chat_id).where(
                    Bot.relay_enabled.is_(True), Bot.relay_target_chat_id.is_not(None)
                )
            )
        ).all()
    )
    return {int(item) for item in ids if item is not None}


def account_can_send(account: Optional[TgAccount]) -> bool:
    if account is None:
        return False
    status = account.status.value if hasattr(account.status, "value") else str(account.status)
    return status == AccountStatus.healthy.value


async def context_for_message(
    session: AsyncSession, *, dialog: Dialog
) -> Tuple[Optional[TgAccount], Optional[Bot]]:
    account = None
    bot = None
    if dialog.account_id is not None:
        account = await session.scalar(select(TgAccount).where(TgAccount.id == dialog.account_id))
    if dialog.bot_id is not None:
        bot = await session.scalar(select(Bot).where(Bot.id == dialog.bot_id))
    return account, bot


async def publish_relay_event(redis, *, task: Task, ok: bool, detail: str = "") -> None:
    if redis is None:
        return
    await events.publish_task_event(
        redis,
        {
            "task_id": str(task.id),
            "type": task.type.value if hasattr(task.type, "value") else str(task.type),
            "ok": ok,
            "detail": detail,
        },
    )
