"""会话（群聊 / 私信 / Bot 私信）：列表、消息、未读、同步历史、AI 草稿、发送。

发送严格分两条通道（契约第 5 节）：
- user_account：账号不在 healthy → 409；否则预写一条 status=pending 的 outgoing 消息，
  再写 send_message 任务，由持有租约的 Worker 真正发出并回填 tg_message_id；
- bot：API 直接用该 Bot 的 aiogram 实例发，立刻写 status=sent 的消息，task_id 为 null。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bots import manager
from app.api.deps import (
    assert_account_access,
    assert_dialog_access,
    get_current_user,
    get_session,
    visible_account_ids,
)
from app.api.routers import (
    dialog_out,
    enum_value,
    message_out,
    publish_safely,
    publish_task_safely,
    utcnow,
)
from app.config import settings
from app.core.audit import write_audit
from app.core.tasks import enqueue_task
from app.models import (
    ACCOUNT_STATUS_LABELS,
    Bot,
    Dialog,
    DialogChannel,
    DialogKind,
    DraftStatus,
    Message,
    MessageDirection,
    MessageStatus,
    ReplyDraft,
    TaskType,
    TgAccount,
    User,
)
from app.schemas import (
    DialogListResponse,
    DialogOut,
    DraftOut,
    MessageListResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from app.services import inbound, relay
from app.services.ai import AIUnavailable, ai_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dialogs", tags=["dialogs"])
#: /api/messages/send、/api/drafts/{id} 不挂在 /dialogs 下，单独两个小路由
messages_router = APIRouter(tags=["messages"])
drafts_router = APIRouter(tags=["drafts"])


class SyncMessagesBody(BaseModel):
    """拉某个会话的历史消息（条数由前端选）。"""

    limit: int = Field(default=50, ge=1, le=500)


class DraftBody(BaseModel):
    """AI 草稿的额外要求；会话 id 在路径里。"""

    instruction: str = Field(default="", max_length=500)


# ---------------- 内部工具 ----------------

async def _load_dialog(session: AsyncSession, dialog_id: uuid.UUID) -> Dialog:
    dialog = await session.scalar(select(Dialog).where(Dialog.id == dialog_id))
    if dialog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return dialog


def _dialog_conditions(ids: Optional[List[uuid.UUID]]):
    """会话可见范围：Bot 会话是全局的，用户号会话跟着账号分配走。"""
    if ids is None:
        return []
    return [(Dialog.channel == DialogChannel.bot) | (Dialog.account_id.in_(ids))]


async def _history(session: AsyncSession, dialog_id: uuid.UUID, limit: int) -> List[Message]:
    rows = await session.scalars(
        select(Message)
        .where(Message.dialog_id == dialog_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(reversed(list(rows.all())))


async def _mark_draft_sent(
    session: AsyncSession, draft: Optional[ReplyDraft], user: User, message: Message
) -> None:
    """发送成功后把草稿标成已发送，审计里能看出是谁点的发送。"""
    if draft is None:
        return
    draft.status = DraftStatus.sent
    draft.sent_by = user.id
    draft.sent_at = utcnow()
    draft.sent_message_id = message.id


async def _load_draft(session: AsyncSession, draft_id: uuid.UUID) -> ReplyDraft:
    draft = await session.scalar(select(ReplyDraft).where(ReplyDraft.id == draft_id))
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="草稿不存在")
    return draft


# ---------------- 会话列表 / 详情 ----------------

@router.get("", response_model=DialogListResponse, summary="会话列表")
async def list_dialogs(
    channel: Optional[DialogChannel] = Query(default=None),
    kind: Optional[DialogKind] = Query(default=None),
    account_id: Optional[uuid.UUID] = Query(default=None),
    bot_id: Optional[uuid.UUID] = Query(default=None),
    keyword: Optional[str] = Query(default=None),
    only_unread: bool = Query(default=False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DialogListResponse:
    """按最近消息时间倒序；operator 只能看到自己分配账号下的会话（Bot 会话人人可见）。"""
    ids = await visible_account_ids(session, user)
    conditions = _dialog_conditions(ids)
    if channel is not None:
        conditions.append(Dialog.channel == channel)
    if kind is not None:
        conditions.append(Dialog.kind == kind)
    if account_id is not None:
        await assert_account_access(session, user, account_id)
        conditions.append(Dialog.account_id == account_id)
    if bot_id is not None:
        conditions.append(Dialog.bot_id == bot_id)
    if only_unread:
        conditions.append(Dialog.unread_count > 0)
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                Dialog.title.ilike(pattern),
                Dialog.peer_display.ilike(pattern),
                Dialog.username.ilike(pattern),
                Dialog.last_message_preview.ilike(pattern),
                # 也按消息正文找：值班的人常记得「那句话在哪个会话里」。
                # 用 in_(子查询) 并加 limit，避免消息表很大时把整表扫穿。
                Dialog.id.in_(
                    select(Message.dialog_id).where(Message.body.ilike(pattern)).limit(500)
                ),
            )
        )

    total = await session.scalar(select(func.count()).select_from(Dialog).where(*conditions))
    dialogs = list(
        (
            await session.scalars(
                select(Dialog)
                .where(*conditions)
                .order_by(Dialog.last_message_at.desc().nullslast(), Dialog.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return DialogListResponse(
        items=[dialog_out(item) for item in dialogs],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.get("/{dialog_id}", response_model=DialogOut, summary="会话详情")
async def get_dialog(
    dialog_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DialogOut:
    """越权看别人号上的会话 → 403。"""
    dialog = await _load_dialog(session, dialog_id)
    await assert_dialog_access(session, user, dialog)
    return dialog_out(dialog)


@router.get("/{dialog_id}/messages", response_model=MessageListResponse, summary="会话消息（分页拉历史）")
async def list_messages(
    dialog_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=500),
    before: Optional[datetime] = Query(default=None, description="ISO8601，取这个时间之前的消息"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MessageListResponse:
    """返回按时间正序的 items；has_more 表示还有更早的消息，可继续用 before 翻。"""
    dialog = await _load_dialog(session, dialog_id)
    await assert_dialog_access(session, user, dialog)

    conditions = [Message.dialog_id == dialog.id]
    if before is not None:
        conditions.append(Message.created_at < before)
    total = await session.scalar(select(func.count()).select_from(Message).where(Message.dialog_id == dialog.id))
    rows = list(
        (
            await session.scalars(
                select(Message)
                .where(*conditions)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    page_rows = list(reversed(rows[:limit]))
    return MessageListResponse(
        items=[message_out(item) for item in page_rows],
        total=int(total or 0),
        dialog=dialog_out(dialog),
        has_more=has_more,
    )


@router.post("/{dialog_id}/read", summary="未读清零")
async def mark_read(
    dialog_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """打开会话时调用；只清 unread_count，不动消息。"""
    dialog = await _load_dialog(session, dialog_id)
    await assert_dialog_access(session, user, dialog)
    dialog.unread_count = 0
    await session.commit()
    return {"ok": True, "message": "未读已清零"}


@router.post("/{dialog_id}/sync", summary="拉取该会话历史消息")
async def sync_messages(
    dialog_id: uuid.UUID,
    payload: Optional[SyncMessagesBody] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """写一条 sync_messages 任务（Worker 用该号的会话拉历史）；Bot 通道没有历史接口，直接 400。"""
    dialog = await _load_dialog(session, dialog_id)
    await assert_dialog_access(session, user, dialog)
    if enum_value(dialog.channel) != DialogChannel.user_account.value or dialog.account_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bot 通道不支持补拉历史：Telegram Bot API 没有提供历史消息接口",
        )
    limit = payload.limit if payload else 50
    task = await enqueue_task(
        session,
        type=TaskType.sync_messages,
        account_id=dialog.account_id,
        dialog_id=dialog.id,
        payload={"dialog_id": str(dialog.id), "limit": limit},
        created_by=user.id,
        priority=60,
    )
    await write_audit(
        session,
        action="dialog.sync",
        user_id=user.id,
        account_id=dialog.account_id,
        target_type="dialog",
        target_id=str(dialog.id),
        detail={"task_id": str(task.id), "limit": limit},
    )
    await session.commit()
    return {"ok": True, "message": f"已排队拉取最近 {limit} 条消息", "task_id": task.id}


# ---------------- AI 草稿 ----------------

@router.get("/{dialog_id}/drafts", response_model=List[DraftOut], summary="该会话的待发草稿")
async def list_drafts(
    dialog_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[DraftOut]:
    """只回还没处理的草稿（pending）；已发送 / 已丢弃的不再展示。"""
    dialog = await _load_dialog(session, dialog_id)
    await assert_dialog_access(session, user, dialog)
    rows = await session.scalars(
        select(ReplyDraft)
        .where(ReplyDraft.dialog_id == dialog.id, ReplyDraft.status == DraftStatus.pending)
        .order_by(ReplyDraft.created_at.desc())
    )
    items = []
    for draft in rows.all():
        out = DraftOut.model_validate(draft)
        out.status = enum_value(draft.status)
        items.append(out)
    return items


@router.post("/{dialog_id}/draft", response_model=DraftOut, summary="生成 AI 草稿（停在输入框）")
async def create_draft(
    dialog_id: uuid.UUID,
    payload: Optional[DraftBody] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DraftOut:
    """按会话最近消息生成一段正文，落在 reply_drafts 里等员工点发送（不自动发出去）。"""
    dialog = await _load_dialog(session, dialog_id)
    await assert_dialog_access(session, user, dialog)
    history = await _history(session, dialog.id, settings.ai_max_history)
    instruction = payload.instruction if payload else ""
    try:
        text = await ai_service.draft_reply(dialog=dialog, history=history, instruction=instruction)
    except AIUnavailable as exc:
        # AI 通道没配好属于依赖不可用，回 503 并说清怎么修
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - 模型侧报错
        logger.warning("生成草稿失败 dialog_id=%s: %s", dialog.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"生成草稿失败：{type(exc).__name__}: {exc}"
        ) from exc

    draft = ReplyDraft(
        dialog_id=dialog.id,
        body=text,
        status=DraftStatus.pending,
        created_by=user.id,
        model=settings.ai_model,
    )
    session.add(draft)
    await session.flush()
    await write_audit(
        session,
        action="draft.create",
        user_id=user.id,
        account_id=dialog.account_id,
        bot_id=dialog.bot_id,
        target_type="dialog",
        target_id=str(dialog.id),
        detail={"draft_id": str(draft.id), "instruction": instruction},
    )
    await session.commit()
    out = DraftOut.model_validate(draft)
    out.status = enum_value(draft.status)
    return out


@drafts_router.delete("/drafts/{draft_id}", summary="丢弃草稿")
async def discard_draft(
    draft_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """草稿只标记 discarded，不物理删除，方便回溯 AI 到底写了什么。"""
    draft = await _load_draft(session, draft_id)
    dialog = await _load_dialog(session, draft.dialog_id)
    await assert_dialog_access(session, user, dialog)
    if enum_value(draft.status) != DraftStatus.pending.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该草稿已经发送或已丢弃")
    draft.status = DraftStatus.discarded
    await write_audit(
        session,
        action="draft.discard",
        user_id=user.id,
        account_id=dialog.account_id,
        bot_id=dialog.bot_id,
        target_type="draft",
        target_id=str(draft.id),
    )
    await session.commit()
    return {"ok": True, "message": "已丢弃草稿"}


# ---------------- 发送 ----------------

@messages_router.post("/messages/send", response_model=SendMessageResponse, summary="发送消息（用户号排队 / Bot 直发）")
async def send_message(
    payload: SendMessageRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SendMessageResponse:
    """两条通道分开处理：用户号必须 healthy 且由 Worker 发；Bot 由 API 直接发。"""
    dialog = await _load_dialog(session, payload.dialog_id)
    await assert_dialog_access(session, user, dialog)

    draft: Optional[ReplyDraft] = None
    if payload.draft_id is not None:
        draft = await _load_draft(session, payload.draft_id)
        if draft.dialog_id != dialog.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="草稿不属于这个会话")
        if enum_value(draft.status) != DraftStatus.pending.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该草稿已经发送或已丢弃")

    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息正文不能为空")

    if enum_value(dialog.channel) == DialogChannel.bot.value:
        return await _send_via_bot(session, user, dialog, text, draft)
    return await _queue_account_send(session, user, dialog, text, draft)


async def _send_via_bot(
    session: AsyncSession,
    user: User,
    dialog: Dialog,
    text: str,
    draft: Optional[ReplyDraft],
) -> SendMessageResponse:
    """Bot 通道：API 直接调 Bot API，成功即 status=sent，task_id 为 null。"""
    if dialog.bot_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该会话没有绑定 Bot，无法用 Bot 通道发送")
    bot_row = await session.scalar(select(Bot).where(Bot.id == dialog.bot_id))
    if bot_row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该会话对应的 Bot 已被删除")
    runtime = await manager.ensure_runtime(bot_row)
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bot 运行时不可用：Token 无法解密，请到 Bot 管理里重新保存 Token",
        )
    try:
        sent = await manager.send_text(runtime, dialog.tg_chat_id, text)
    except manager.BotSendError as exc:
        # 对方没和 Bot 说过话、Bot 不在群里、被拉黑等都属于「当前状态不允许」，用 409 更贴切
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

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
        created_by=user.id,
    )
    await _mark_draft_sent(session, draft, user, message)
    await write_audit(
        session,
        action="message.send",
        user_id=user.id,
        bot_id=bot_row.id,
        target_type="dialog",
        target_id=str(dialog.id),
        detail={"channel": "bot", "draft_id": str(draft.id) if draft else None, "preview": text[:80]},
    )
    await session.commit()
    await publish_safely(dialog, message)
    await publish_task_safely(
        {"task_id": None, "type": TaskType.send_message.value, "ok": True, "detail": "Bot 已直接发出"}
    )
    logger.info("Bot 直发成功 bot_id=%s dialog_id=%s", bot_row.id, dialog.id)
    return SendMessageResponse(
        ok=True,
        message=message_out(message),
        task_id=None,
        status=MessageStatus.sent,
        detail="已由 Bot 直接发出",
    )


async def _queue_account_send(
    session: AsyncSession,
    user: User,
    dialog: Dialog,
    text: str,
    draft: Optional[ReplyDraft],
) -> SendMessageResponse:
    """用户号通道：非 healthy 直接 409；否则预写 pending 消息 + send_message 任务。"""
    account = (
        await session.scalar(select(TgAccount).where(TgAccount.id == dialog.account_id))
        if dialog.account_id is not None
        else None
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该会话没有绑定用户号，无法排队发送")
    if not relay.account_can_send(account):
        label = ACCOUNT_STATUS_LABELS.get(enum_value(account.status), enum_value(account.status))
        reason = account.last_error or account.status_reason or "没有有效会话或租约"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"账号 {account.phone_masked} 当前状态「{label}」，不能发送：{reason}",
        )

    message = Message(
        dialog_id=dialog.id,
        channel=DialogChannel.user_account,
        direction=MessageDirection.outgoing,
        status=MessageStatus.pending,
        body=text,
        created_by=user.id,
    )
    session.add(message)
    await session.flush()
    # 页面立刻能看到这条「待发送」，真正的 tg_message_id 由 Worker 发完后回填
    dialog.last_message_at = message.created_at or utcnow()
    dialog.last_message_preview = inbound.preview_of(text)
    dialog.unread_count = 0

    task = await enqueue_task(
        session,
        type=TaskType.send_message,
        account_id=account.id,
        dialog_id=dialog.id,
        payload={
            "dialog_id": str(dialog.id),
            "text": text,
            "message_id": str(message.id),
            **({"draft_id": str(draft.id)} if draft is not None else {}),
        },
        created_by=user.id,
        priority=40,
    )
    await _mark_draft_sent(session, draft, user, message)
    await write_audit(
        session,
        action="message.send",
        user_id=user.id,
        account_id=account.id,
        target_type="dialog",
        target_id=str(dialog.id),
        detail={
            "channel": "user_account",
            "task_id": str(task.id),
            "message_id": str(message.id),
            "draft_id": str(draft.id) if draft else None,
            "preview": text[:80],
        },
    )
    await session.commit()
    await publish_safely(dialog, message)
    logger.info("发送任务已入队 account_id=%s dialog_id=%s task_id=%s", account.id, dialog.id, task.id)
    return SendMessageResponse(
        ok=True,
        message=message_out(message),
        task_id=task.id,
        status=MessageStatus.pending,
        detail="已排队，等持有租约的 Worker 发出后回填 Telegram 消息 ID",
    )
