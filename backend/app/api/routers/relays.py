"""Bot 管理 + Bot 转发规则。

- Bot：Token 只用 `security.encrypt_secret` 加密保存，出参只给 `token_masked`；
  新建 / 换 Token 都先调 Telegram `getMe()` 校验，连不上或 Token 无效回 400（不是 500）。
- 转发规则：某个 Bot 把哪些来源的消息发到哪个员工聊天（relay_routes）。
  真正的转发动作在 `app/api/bots/bot_tasks.py` 的轮询协程里做。
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.api.bots import manager
from app.api.deps import get_current_user, get_session, require_admin
from app.api.routers import account_label, bot_out
from app.config import settings
from app.core.audit import write_audit
from app.models import Bot, Dialog, Message, RelayLink, RelayRoute, TgAccount, User
from app.schemas import (
    BotCreate,
    BotOut,
    BotUpdate,
    RelayLinkOut,
    RelayRouteCreate,
    RelayRouteOut,
    RelayRouteUpdate,
)

logger = logging.getLogger(__name__)

bots_router = APIRouter(prefix="/bots", tags=["bots"])
router = APIRouter(prefix="/relays", tags=["relays"])


class WebhookToggleRequest(BaseModel):
    """注册 / 删除 Telegram Webhook。"""

    enable: bool = True


class RelayTestRequest(BaseModel):
    """用某个 Bot 往指定员工聊天发一条测试消息（保存规则之前也能先试）。"""

    bot_id: uuid.UUID
    chat_id: int
    text: Optional[str] = None


#: 测试消息默认文案
RELAY_TEST_TEXT = "这是一条测试消息（Telegram 云控）"


class RelayLinkListResponse(BaseModel):
    """转发记录分页；单独定义是为了让 OpenAPI 里有完整 schema（前端直接生成类型）。"""

    items: List[RelayLinkOut] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


# ---------------- 出参拼装 ----------------

def route_out(
    route: RelayRoute,
    *,
    bot: Optional[Bot] = None,
    account: Optional[TgAccount] = None,
    dialog: Optional[Dialog] = None,
    relayed_count: int = 0,
) -> RelayRouteOut:
    out = RelayRouteOut.model_validate(route)
    if bot is not None:
        out.bot_name = bot.name
        out.bot_username = bot.bot_username
    out.account_label = account_label(account)
    out.dialog_title = dialog.title if dialog is not None else None
    out.relayed_count = relayed_count
    return out


async def _route_context(session: AsyncSession, routes: List[RelayRoute]) -> List[RelayRouteOut]:
    """批量补 Bot / 账号 / 会话 / 已转发条数，避免 N+1。"""
    bot_ids = {item.bot_id for item in routes if item.bot_id}
    account_ids = {item.account_id for item in routes if item.account_id}
    dialog_ids = {item.dialog_id for item in routes if item.dialog_id}
    bots = {
        row.id: row for row in (await session.scalars(select(Bot).where(Bot.id.in_(bot_ids)))).all()
    } if bot_ids else {}
    accounts = {
        row.id: row
        for row in (await session.scalars(select(TgAccount).where(TgAccount.id.in_(account_ids)))).all()
    } if account_ids else {}
    dialogs = {
        row.id: row for row in (await session.scalars(select(Dialog).where(Dialog.id.in_(dialog_ids)))).all()
    } if dialog_ids else {}

    counts: dict = {}
    if routes:
        rows = await session.execute(
            select(RelayLink.route_id, func.count())
            .where(RelayLink.route_id.in_([item.id for item in routes]))
            .group_by(RelayLink.route_id)
        )
        counts = {row[0]: int(row[1] or 0) for row in rows.all()}

    return [
        route_out(
            item,
            bot=bots.get(item.bot_id),
            account=accounts.get(item.account_id),
            dialog=dialogs.get(item.dialog_id),
            relayed_count=counts.get(item.id, 0),
        )
        for item in routes
    ]


async def _get_bot(session: AsyncSession, bot_id: uuid.UUID) -> Bot:
    bot = await session.scalar(select(Bot).where(Bot.id == bot_id))
    if bot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot 不存在")
    return bot


# ---------------- Bot CRUD ----------------

@bots_router.get("", response_model=List[BotOut], summary="Bot 列表")
async def list_bots(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[BotOut]:
    """只回脱敏 Token；webhook_url 里带 settings.webhook_secret，方便直接贴到别处核对。"""
    bots = list((await session.scalars(select(Bot).order_by(Bot.created_at))).all())
    return [bot_out(item) for item in bots]


@bots_router.post("", response_model=BotOut, status_code=status.HTTP_201_CREATED, summary="新建 Bot")
async def create_bot(
    payload: BotCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> BotOut:
    """先 getMe 校验 Token（无效 / 连不上 Telegram 都是 400 中文原因），成功后再注册 Webhook。"""
    exists = await session.scalar(select(Bot.id).where(Bot.name == payload.name))
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已存在同名 Bot")

    try:
        aiogram_bot, me = await manager.fetch_me(payload.token)
    except manager.BotTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    bot = Bot(
        name=payload.name,
        bot_username=me.username,
        bot_tg_id=me.id,
        token_enc=security.encrypt_secret(payload.token),
        webhook_secret=settings.webhook_secret,
        webhook_enabled=True,
        relay_enabled=payload.relay_enabled,
        relay_target_chat_id=payload.relay_target_chat_id,
        relay_target_kind=payload.relay_target_kind,
        auto_reply_enabled=payload.auto_reply_enabled,
        persona_text=payload.persona_text or "",
        remark=payload.remark or "",
    )
    session.add(bot)
    await session.flush()

    runtime = await manager.register(bot.id, aiogram_bot=aiogram_bot)
    ok, detail = await manager.apply_webhook(session, bot, enable=True, runtime=runtime)

    await write_audit(
        session,
        action="bot.create",
        user_id=admin.id,
        bot_id=bot.id,
        target_type="bot",
        target_id=str(bot.id),
        detail={"name": bot.name, "username": me.username, "webhook_ok": ok, "webhook_detail": detail},
    )
    await session.commit()
    logger.info("新建 Bot name=%s username=%s webhook_ok=%s", bot.name, me.username, ok)
    out = bot_out(bot)
    if not ok:
        # 不因为 Webhook 没注册成功就回滚建档：Token 已验证，规则可以稍后重试
        logger.warning("Bot 已建档但 Webhook 注册失败 bot_id=%s detail=%s", bot.id, detail)
    return out


@bots_router.patch("/{bot_id}", response_model=BotOut, summary="修改 Bot")
async def update_bot(
    bot_id: uuid.UUID,
    payload: BotUpdate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> BotOut:
    """换 Token 会重新校验并重建运行时；关掉 webhook_enabled 会去 Telegram 注销。"""
    bot = await _get_bot(session, bot_id)
    changes: dict = {}

    if payload.name is not None and payload.name != bot.name:
        exists = await session.scalar(select(Bot.id).where(Bot.name == payload.name))
        if exists is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已存在同名 Bot")
        bot.name = payload.name
        changes["name"] = payload.name

    token_changed = False
    if payload.token is not None and payload.token != "":
        try:
            aiogram_bot, me = await manager.fetch_me(payload.token)
        except manager.BotTokenError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        bot.token_enc = security.encrypt_secret(payload.token)
        bot.bot_username = me.username
        bot.bot_tg_id = me.id
        # Token 换了，旧实例连同它的 aiohttp 会话一起丢掉
        await manager.unregister(bot.id)
        await manager.register(bot.id, aiogram_bot=aiogram_bot)
        token_changed = True
        changes["token"] = "updated"

    for field in (
        "relay_enabled",
        "relay_target_chat_id",
        "relay_target_kind",
        "auto_reply_enabled",
        "persona_text",
        "remark",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(bot, field, value)
            changes[field] = str(value)

    webhook_detail = ""
    if payload.webhook_enabled is not None and payload.webhook_enabled != bot.webhook_enabled:
        ok, webhook_detail = await manager.apply_webhook(
            session, bot, enable=payload.webhook_enabled
        )
        changes["webhook_enabled"] = payload.webhook_enabled
        changes["webhook_detail"] = webhook_detail
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Webhook 操作失败：{webhook_detail}",
            )
    elif token_changed and bot.webhook_enabled:
        # URL 里的 bot_id 没变，但新实例需要重新注册一次，保证 Telegram 侧指向同一个地址
        ok, webhook_detail = await manager.apply_webhook(session, bot, enable=True)
        changes["webhook_detail"] = webhook_detail

    await write_audit(
        session,
        action="bot.update",
        user_id=admin.id,
        bot_id=bot.id,
        target_type="bot",
        target_id=str(bot.id),
        detail=changes,
    )
    await session.commit()
    return bot_out(bot)


@bots_router.delete("/{bot_id}", summary="删除 Bot")
async def delete_bot(
    bot_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict:
    """先 delete_webhook 再删库，避免 Telegram 一直往一个已经没有的 bot_id 打回调。"""
    bot = await _get_bot(session, bot_id)
    await manager.unregister(bot.id, delete_webhook=True)
    name = bot.name
    await write_audit(
        session,
        action="bot.delete",
        user_id=admin.id,
        target_type="bot",
        target_id=str(bot_id),
        detail={"name": name},
    )
    await session.delete(bot)
    await session.commit()
    logger.info("Bot 已删除 bot_id=%s name=%s", bot_id, name)
    return {"ok": True, "message": f"已删除 Bot「{name}」，其 Webhook 已注销"}


@bots_router.post("/{bot_id}/webhook", summary="注册 / 删除 Telegram Webhook")
async def set_webhook(
    bot_id: uuid.UUID,
    payload: WebhookToggleRequest,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict:
    """公网地址由 settings.public_base_url 决定；失败回 400 并带上 Telegram 的原始原因。"""
    bot = await _get_bot(session, bot_id)
    ok, detail = await manager.apply_webhook(session, bot, enable=payload.enable)
    if not ok:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Webhook 操作失败：{detail}")
    await write_audit(
        session,
        action="bot.webhook_set",
        user_id=admin.id,
        bot_id=bot.id,
        target_type="bot",
        target_id=str(bot.id),
        detail={"enable": payload.enable, "url": settings.webhook_url(bot.id) if payload.enable else ""},
    )
    await session.commit()
    return {
        "ok": True,
        "message": f"Webhook 已注册：{settings.webhook_url(bot.id)}" if payload.enable else "Webhook 已删除",
    }


@bots_router.get("/{bot_id}/check", response_model=BotOut, summary="重新 getMe 校验 Bot")
async def check_bot(
    bot_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> BotOut:
    """重新拉一次 getMe，把 username / tg id 回填（换过 Token 或改过用户名时用）。"""
    bot = await _get_bot(session, bot_id)
    try:
        token = security.decrypt_secret(bot.token_enc)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    try:
        aiogram_bot, me = await manager.fetch_me(token)
    except manager.BotTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    bot.bot_username = me.username
    bot.bot_tg_id = me.id
    await manager.unregister(bot.id)
    await manager.register(bot.id, aiogram_bot=aiogram_bot)
    await session.commit()
    logger.info("Bot 校验通过 bot_id=%s username=%s", bot.id, me.username)
    return bot_out(bot)


# ---------------- 转发规则 ----------------

@router.get("", response_model=List[RelayRouteOut], summary="转发规则列表")
async def list_relays(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[RelayRouteOut]:
    """带 Bot 名、来源账号脱敏号、目标会话名和已转发条数，页面一屏看全。"""
    routes = list((await session.scalars(select(RelayRoute).order_by(RelayRoute.created_at))).all())
    return await _route_context(session, routes)


@router.post("", response_model=RelayRouteOut, status_code=status.HTTP_201_CREATED, summary="新建转发规则")
async def create_relay(
    payload: RelayRouteCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> RelayRouteOut:
    """规则命中条件：账号 / 会话两个过滤器为空表示不过滤（所有来源都转发）。"""
    bot = await session.scalar(select(Bot).where(Bot.id == payload.bot_id))
    if bot is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bot 不存在，请先创建 Bot")
    if payload.account_id is not None:
        exists = await session.scalar(select(TgAccount.id).where(TgAccount.id == payload.account_id))
        if exists is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="来源账号不存在")
    if payload.dialog_id is not None:
        exists = await session.scalar(select(Dialog.id).where(Dialog.id == payload.dialog_id))
        if exists is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="来源会话不存在")

    route = RelayRoute(
        name=payload.name or "",
        bot_id=payload.bot_id,
        staff_chat_id=payload.staff_chat_id,
        staff_chat_title=payload.staff_chat_title or "",
        target_kind=payload.target_kind,
        account_id=payload.account_id,
        dialog_id=payload.dialog_id,
        enabled=payload.enabled,
        created_by=admin.id,
        remark=payload.remark or "",
    )
    session.add(route)
    await session.flush()
    await write_audit(
        session,
        action="relay.create",
        user_id=admin.id,
        bot_id=bot.id,
        account_id=route.account_id,
        target_type="relay_route",
        target_id=str(route.id),
        detail={"staff_chat_id": route.staff_chat_id, "name": route.name},
    )
    await session.commit()
    return (await _route_context(session, [route]))[0]


@router.patch("/{route_id}", response_model=RelayRouteOut, summary="修改转发规则")
async def update_relay(
    route_id: uuid.UUID,
    payload: RelayRouteUpdate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> RelayRouteOut:
    """停用规则用 enabled=false，不删数据，历史 relay_links 仍能回溯。"""
    route = await session.scalar(select(RelayRoute).where(RelayRoute.id == route_id))
    if route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="转发规则不存在")
    if payload.bot_id is not None:
        exists = await session.scalar(select(Bot.id).where(Bot.id == payload.bot_id))
        if exists is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bot 不存在")
    for field in (
        "name",
        "bot_id",
        "staff_chat_id",
        "staff_chat_title",
        "target_kind",
        "account_id",
        "dialog_id",
        "enabled",
        "remark",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(route, field, value)
    await write_audit(
        session,
        action="relay.update",
        user_id=admin.id,
        bot_id=route.bot_id,
        account_id=route.account_id,
        target_type="relay_route",
        target_id=str(route.id),
        detail=payload.model_dump(exclude_none=True, mode="json"),
    )
    await session.commit()
    return (await _route_context(session, [route]))[0]


@router.delete("/{route_id}", summary="删除转发规则")
async def delete_relay(
    route_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict:
    """删规则不会删已转发记录：relay_links.route_id 外键是 ON DELETE SET NULL。"""
    route = await session.scalar(select(RelayRoute).where(RelayRoute.id == route_id))
    if route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="转发规则不存在")
    name = route.name or str(route.id)[:8]
    # AsyncSession.delete 是协程：忘了 await 会静默不删（照样回 200、照样写审计），必须 await
    await session.delete(route)
    await write_audit(
        session,
        action="relay.delete",
        user_id=admin.id,
        target_type="relay_route",
        target_id=str(route_id),
        detail={"name": name},
    )
    await session.commit()
    return {"ok": True, "message": f"已删除转发规则「{name}」"}


@router.post("/test", summary="用指定 Bot 发一条测试消息到员工聊天")
async def test_relay(
    payload: RelayTestRequest,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict:
    """转发规则「测试」按钮：不依赖已保存的规则，保存前也能先试通。

    只发**一条**测试消息到指定的员工聊天（不会碰任何用户号、也不会群发），
    失败一律给人能看懂的中文：Bot 不存在 / Token 解不开 → 400，Telegram 拒绝（不在群里、
    没和 Bot 说过话、被拉黑等）→ 409。
    """
    bot_row = await session.scalar(select(Bot).where(Bot.id == payload.bot_id))
    if bot_row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bot 不存在，请刷新 Bot 列表后重试")

    text = (payload.text or "").strip() or RELAY_TEST_TEXT
    if len(text) > 4096:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="测试消息太长了：最多 4096 个字符")

    runtime = await manager.ensure_runtime(bot_row)
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bot 运行时不可用：Token 无法解密，请到 Bot 管理里重新保存 Token",
        )
    try:
        sent = await manager.send_text(runtime, payload.chat_id, text)
    except manager.BotSendError as exc:
        # Telegram 侧的「当前状态不允许」：用 409 更贴切（员工看到中文原因知道怎么办）
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - 网络/上游异常也要给中文，不抛 500
        logger.warning("测试消息发送失败 bot_id=%s chat_id=%s: %s", bot_row.id, payload.chat_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"测试消息发送失败：{type(exc).__name__}: {exc}",
        ) from exc

    await write_audit(
        session,
        action="relay.test",
        user_id=admin.id,
        bot_id=bot_row.id,
        target_type="relay_test",
        target_id=str(payload.chat_id),
        detail={"chat_id": payload.chat_id, "staff_message_id": sent.message_id, "preview": text[:80]},
    )
    await session.commit()
    logger.info("测试消息已发出 bot_id=%s chat_id=%s message_id=%s", bot_row.id, payload.chat_id, sent.message_id)
    return {
        "ok": True,
        "message": f"测试消息已发到 {payload.chat_id}",
        "detail": "如果员工群没收到，确认 Bot 在群里、且群里发过 /start 或已被设为管理员",
        "staff_message_id": sent.message_id,
    }


@router.get("/links", response_model=RelayLinkListResponse, summary="转发记录（原消息 ↔ 员工群那条）")
async def list_relay_links(
    route_id: Optional[uuid.UUID] = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RelayLinkListResponse:
    """按时间倒序；员工在群里回复时就是靠这张表找回原会话的。

    顺带把原消息正文 / 会话名 / 归属号拼进返回，列表页不必再逐条查。
    """
    conditions = []
    if route_id is not None:
        conditions.append(RelayLink.route_id == route_id)
    total = await session.scalar(select(func.count()).select_from(RelayLink).where(*conditions))
    rows = list(
        (
            await session.execute(
                select(RelayLink, Message, Dialog, TgAccount)
                .join(Message, Message.id == RelayLink.message_id)
                .join(Dialog, Dialog.id == Message.dialog_id)
                .outerjoin(TgAccount, TgAccount.id == Dialog.account_id)
                .where(*conditions)
                .order_by(RelayLink.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )

    items: List[RelayLinkOut] = []
    for link, message, dialog, account in rows:
        item = RelayLinkOut.model_validate(link)
        item.origin_body = (message.body or "")[:500] or None
        item.origin_sender_name = message.sender_name or None
        item.origin_dialog_title = dialog.title or None
        item.origin_dialog_id = dialog.id
        item.account_label = account_label(account) if account is not None else None
        item.origin_created_at = message.created_at
        items.append(item)

    return RelayLinkListResponse(
        items=items,
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )
