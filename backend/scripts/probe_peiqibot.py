"""佩奇群验证探测：入群 @devqun，把验证消息的原始结构抓下来。

关心的是「验证长什么样」——是普通 URL、web_app 按钮、还是 inline 回调按钮，
这决定了后面走 Cap（纯计算可自动化）还是 Turnstile（要真浏览器）。

分阶段输出：只读探测 → 群详情 → 入群 → 抓新消息（含按钮/URL 原始字段）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy import select
from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from telethon.tl import types as tl_types

from app.config import settings
from app.db import SessionFactory
from app.models import TgAccount
from app.security import decrypt_secret

GROUP = "devqun"


def dump_buttons(message: Any) -> list[dict]:
    """把按钮的原始结构打出来——佩奇的验证入口就在这里。"""
    rows = getattr(message, "buttons", None) or []
    out: list[dict] = []
    for row in rows:
        for btn in row:
            item = {
                "text": getattr(btn, "text", None),
                "type": type(btn).__name__,
            }
            for attr in ("url", "data", "button"):
                value = getattr(btn, attr, None)
                if value is not None:
                    item[attr] = str(value)[:300] if not isinstance(value, bytes) else value.hex()[:300]
            inner = getattr(btn, "button", None)
            if inner is not None:
                item["inner_type"] = type(inner).__name__
                if isinstance(inner, tl_types.KeyboardButtonWebView):
                    item["webview_url"] = getattr(inner, "url", None)
                if isinstance(inner, tl_types.KeyboardButtonUrl):
                    item["url"] = getattr(inner, "url", None)
            out.append(item)
    return out


def dump_urls(message: Any) -> list[str]:
    """正文里的所有 URL（含隐藏锚文本的 TextUrl）。"""
    urls: list[str] = []
    for ent in getattr(message, "entities", None) or []:
        if isinstance(ent, tl_types.MessageEntityTextUrl):
            urls.append(ent.url)
        elif isinstance(ent, tl_types.MessageEntityUrl):
            raw = message.message or ""
            urls.append(raw[ent.offset : ent.offset + ent.length])
    return urls


def dump_message(message: Any, tag: str = "") -> None:
    line = {
        "id": getattr(message, "id", None),
        "sender_id": getattr(message, "sender_id", None),
        "date": str(getattr(message, "date", None)),
        "text": (getattr(message, "message", None) or "")[:400],
        "urls": dump_urls(message),
        "via_bot_id": getattr(message, "via_bot_id", None),
        "buttons": dump_buttons(message),
        "has_media": getattr(message, "media", None) is not None,
    }
    print(f"[{tag}] " + json.dumps(line, ensure_ascii=False))


async def main() -> None:
    async with SessionFactory() as session:
        rows = list((await session.scalars(select(TgAccount).order_by(TgAccount.created_at))).all())

    # 优先用那个能正常登录的号（@wwwwwdhjewgd / 8966880282）
    account = next((r for r in rows if r.tg_user_id == 8966880282), None) or next(
        (r for r in rows if r.session_enc), None
    )
    if account is None:
        print("没有可用账号")
        return
    print(f"使用账号: {account.phone_masked} ({account.tg_user_id})")

    client = TelegramClient(
        StringSession(decrypt_secret(account.session_enc)),
        int(settings.telegram_api_id),
        settings.telegram_api_hash,
        device_model=account.device_model or None,
        system_version=account.system_version or None,
        app_version=account.app_version or None,
        connection_retries=2,
        request_retries=2,
        timeout=40,
    )
    await client.connect()
    try:
        me = await client.get_me()
        print("已连接:", getattr(me, "id", None), "@" + (getattr(me, "username", None) or "无"))

        # ---------- 1. 只读探测 ----------
        print("\n=== ① 解析 @devqun ===")
        resolved = await client(functions.contacts.ResolveUsernameRequest(username=GROUP))
        for item in list(resolved.chats) + list(resolved.users):
            print("  ", type(item).__name__, getattr(item, "id", None),
                  getattr(item, "title", None) or getattr(item, "username", None))
        if not resolved.chats:
            print("这不是群/频道，停止")
            return
        chat = resolved.chats[0]

        # ---------- 2. 群详情 ----------
        print("\n=== ② 群详情 ===")
        full = await client(functions.channels.GetFullChannelRequest(channel=chat))
        fc = full.full_chat
        print(json.dumps({
            "title": getattr(chat, "title", None),
            "id": getattr(chat, "id", None),
            "username": getattr(chat, "username", None),
            "megagroup": getattr(chat, "megagroup", None),
            "broadcast": getattr(chat, "broadcast", None),
            "participants_count": getattr(fc, "participants_count", None),
            "participants_hidden": getattr(fc, "participants_hidden", None),
            "join_request": getattr(fc, "join_request", None),
            "about": (getattr(fc, "about", "") or "")[:300],
        }, ensure_ascii=False, indent=2))

        # ---------- 3. 入群前的可见消息（暴露群里的机器人） ----------
        before_max = 0
        print("\n=== ③ 入群前可见消息 ===")
        try:
            for message in reversed(list(await client.get_messages(chat, limit=15))):
                before_max = max(before_max, getattr(message, "id", 0))
                dump_message(message, "pre")
        except BaseException as exc:  # noqa: BLE001
            print("  读不到（还没入群的常见结果）:", type(exc).__name__, str(exc)[:120])

        # ---------- 4. 入群 ----------
        print("\n=== ④ 入群 ===")
        try:
            await client(functions.channels.JoinChannelRequest(channel=chat))
            print("  ✅ JoinChannel 成功")
        except BaseException as exc:  # noqa: BLE001
            print("  入群结果:", type(exc).__name__, str(exc)[:200])

        # ---------- 5. 抓入群后的新消息（验证可能私信也可能在群里） ----------
        print("\n=== ⑤ 等待并抓取验证消息（60 秒） ===")
        for round_index in range(6):
            await asyncio.sleep(10)
            try:
                batch = await client.get_messages(chat, limit=20)
                fresh = [m for m in batch if getattr(m, "id", 0) > before_max]
                print(f"-- 第 {round_index + 1} 轮：群内新消息 {len(fresh)} 条")
                for message in reversed(fresh):
                    dump_message(message, "post")
                    before_max = max(before_max, message.id)
            except BaseException as exc:  # noqa: BLE001
                print("  读群消息失败:", type(exc).__name__, str(exc)[:100])

            # 私信通道（很多验证机器人走私信）
            try:
                dialogs = await client.get_dialogs(limit=15)
                for dialog in dialogs[:15]:
                    entity = dialog.entity
                    if getattr(entity, "bot", False) or "Bot" in (getattr(entity, "first_name", "") or ""):
                        print(f"-- 私信机器人: {getattr(entity, 'first_name', None)} @{getattr(entity, 'username', None)}")
                        for message in list(await client.get_messages(entity, limit=3)):
                            dump_message(message, "pm")
            except BaseException as exc:  # noqa: BLE001
                print("  读私信失败:", type(exc).__name__, str(exc)[:100])
    finally:
        await client.disconnect()


asyncio.run(main())
