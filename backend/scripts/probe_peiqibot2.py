"""抓佩奇验证消息的原始按钮结构。

上一个脚本用 isinstance 引用了不存在的类型（KeyboardButtonWebView），异常打断了按钮解析，
于是最关键的数据没拿到。这里改成纯反射读取（不引用具体类），并且专门筛「带按钮或经机器人转发」
的消息——验证入口就在那里。

判读标准：
- 按钮带 data        → 回调按钮，点一下就过（可直接自动化）
- 按钮带 url         → 跳网页（Turnstile / Cap 在这里）
- 按钮 inner 是 webview → 打开 Telegram 内置网页（要 WebView，Telethon 没有）

顺带检查当前号在这个群的发言权限（验证没过会被禁言）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy import select
from telethon import TelegramClient, functions
from telethon.sessions import StringSession

from app.config import settings
from app.db import SessionFactory
from app.models import TgAccount
from app.security import decrypt_secret

GROUP_ID = 1555693413  # 电报技术俱乐部（@devqun）


def describe_button(btn: Any) -> dict:
    """纯反射读按钮——不引用具体类型，避免 telethon 版本差异把解析打断。"""
    item: dict[str, Any] = {"text": getattr(btn, "text", None), "cls": type(btn).__name__}
    for attr in ("url", "data", "query", "text"):
        value = getattr(btn, attr, None)
        if value in (None, ""):
            continue
        if isinstance(value, bytes):
            item[attr] = value.hex()[:400]
            try:
                item[attr + "_utf8"] = value.decode("utf-8", "replace")[:200]
            except Exception:  # noqa: BLE001
                pass
        else:
            item[attr] = str(value)[:400]
    inner = getattr(btn, "button", None)
    if inner is not None:
        item["inner_cls"] = type(inner).__name__
        for attr in ("url", "query", "text", "data", "hash"):
            value = getattr(inner, attr, None)
            if value in (None, ""):
                continue
            item["inner_" + attr] = (
                value.hex()[:200] if isinstance(value, bytes) else str(value)[:400]
            )
    return item


def describe_message(message: Any) -> dict:
    urls = []
    for ent in getattr(message, "entities", None) or []:
        url = getattr(ent, "url", None)
        if url:
            urls.append(url)
    return {
        "id": getattr(message, "id", None),
        "date": str(getattr(message, "date", None)),
        "sender_id": getattr(message, "sender_id", None),
        "via_bot_id": getattr(message, "via_bot_id", None),
        "text": (getattr(message, "message", None) or "")[:500],
        "entity_urls": urls,
        "buttons": [
            [describe_button(b) for b in row] for row in (getattr(message, "buttons", None) or [])
        ],
    }


async def main() -> None:
    async with SessionFactory() as session:
        rows = list((await session.scalars(select(TgAccount).order_by(TgAccount.created_at))).all())
    account = next((r for r in rows if r.tg_user_id == 8966880282), None)
    if account is None:
        print("没找到目标账号")
        return

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
        print("账号:", getattr(me, "id", None), getattr(me, "first_name", None))

        print("\n=== ① 当前在群里的状态与发言权限 ===")
        # 按 id 解析依赖本地实体缓存——新入群的号缓存里没有这个群，必然失败；
        # 用公开用户名解析不受缓存影响，再把会话列表拉一遍填缓存。
        entity = None
        try:
            resolved = await client(functions.contacts.ResolveUsernameRequest(username="devqun"))
            entity = resolved.chats[0] if resolved.chats else None
            print("按用户名解析:", type(entity).__name__, getattr(entity, "title", None))
        except BaseException as exc:  # noqa: BLE001
            print("按用户名解析失败:", type(exc).__name__, str(exc)[:140])
        if entity is None:
            raise SystemExit("拿不到群实体，无法继续")
        try:
            await client.get_dialogs(limit=200)
            print("已拉取会话列表（填充实体缓存）")
        except BaseException as exc:  # noqa: BLE001
            print("拉会话列表失败:", type(exc).__name__, str(exc)[:100])
        try:
            part = await client(functions.channels.GetParticipantRequest(channel=entity, participant="me"))
            participant = getattr(part, "participant", None)
            print("我的成员记录:", type(participant).__name__)
            banned = getattr(participant, "banned_rights", None)
            print("被禁权限 banned_rights:", banned is not None and bool(banned))
            if banned is not None:
                print("  能否发消息:", not bool(getattr(banned, "send_messages", False)))
                print("  完整 banned_rights:", str(banned)[:300])
        except BaseException as exc:  # noqa: BLE001
            print("查成员记录失败:", type(exc).__name__, str(exc)[:150])

        print("\n=== ② 群里带按钮 / 经机器人转发的消息（验证入口） ===")
        hit = 0
        for message in await client.get_messages(entity, limit=200):
            buttons = getattr(message, "buttons", None)
            if not buttons and not getattr(message, "via_bot_id", None):
                continue
            info = describe_message(message)
            text = info["text"] or ""
            if buttons or "验证" in text or "欢迎" in text or info["via_bot_id"]:
                hit += 1
                print(json.dumps(info, ensure_ascii=False, indent=2))
                if hit >= 8:
                    break
        if hit == 0:
            print("（最近 200 条里没有按钮消息——验证消息可能已被删除，或需要更早的历史）")

        print("\n=== ③ 私信里的验证机器人 ===")
        for dialog in (await client.get_dialogs(limit=30))[:30]:
            ent = dialog.entity
            name = (getattr(ent, "first_name", None) or "") + (getattr(ent, "username", None) or "")
            if getattr(ent, "bot", False) or "bot" in name.lower() or "PeiQi" in name or "佩奇" in name:
                print(f"-- {getattr(ent, 'first_name', None)} @{getattr(ent, 'username', None)} id={getattr(ent, 'id', None)}")
                try:
                    for message in list(await client.get_messages(ent, limit=5)):
                        print(json.dumps(describe_message(message), ensure_ascii=False)[:600])
                except BaseException as exc:  # noqa: BLE001
                    print("   读私信失败:", type(exc).__name__, str(exc)[:120])
    finally:
        await client.disconnect()


asyncio.run(main())
