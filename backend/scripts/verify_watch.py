"""NuoMi 类验证的实时监听器：群内一出现验证按钮，立刻抓 URL 交给内置浏览器完成。

为什么必须实时：
    @devqun 的验证机器人只给 **60 秒**（比佩奇的 300 秒紧得多）。事后翻消息来不及，
    必须挂着事件监听，命中就立刻解题。

适用对象：
    任何在群里发「点击下方按钮完成验证」+ webview/URL 按钮的机器人（NuoMi、佩奇等）。
    命中条件不看机器人名字，而是看消息形态——换机器人也不用改代码。

用法：
    cd backend
    .venv/bin/python -m scripts.verify_watch --group devqun --uid 8645074324 --seconds 1800
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from sqlalchemy import select
from telethon import TelegramClient, events, functions
from telethon.sessions import StringSession

from app.config import settings
from app.db import SessionFactory
from app.models import TgAccount
from app.security import decrypt_secret
from app.services.browser import browser_service


def deep_url(button: Any) -> str:
    """webview 按钮的 url 藏在 btn.button.type.url 这一层。"""
    for obj in (button, getattr(button, "button", None)):
        if obj is None:
            continue
        url = getattr(obj, "url", None)
        if url:
            return str(url)
    inner = getattr(button, "button", None)
    inner_type = getattr(inner, "type", None) if inner is not None else None
    if inner_type is not None and getattr(inner_type, "url", None):
        return str(inner_type.url)
    return ""


def extract_verify_url(message: Any) -> str:
    """从消息里挑出验证入口：优先 captcha/verify 类链接，其次任何按钮链接。"""
    candidates: list[str] = []
    for row in getattr(message, "buttons", None) or []:
        for button in row:
            url = deep_url(button)
            if url:
                candidates.append(url)
    for url in candidates:
        if any(key in url for key in ("captcha", "verify", "check", "challenge")):
            return url
    return candidates[0] if candidates else ""


async def main() -> None:
    parser = argparse.ArgumentParser(description="验证按钮实时监听器")
    parser.add_argument("--group", required=True, help="要监听的群用户名")
    parser.add_argument("--uid", type=int, required=True, help="用哪个号监听（tg_user_id）")
    parser.add_argument("--seconds", type=int, default=1800, help="监听时长（秒）")
    args = parser.parse_args()

    async with SessionFactory() as session:
        account = await session.scalar(select(TgAccount).where(TgAccount.tg_user_id == args.uid))
    if account is None:
        print(f"找不到 tg_user_id={args.uid}")
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
    handled: set[int] = set()

    @client.on(events.NewMessage)
    async def on_message(event: Any) -> None:
        try:
            message = event.message
            message_id = getattr(message, "id", None)
            if message_id in handled:
                return
            text = (message.message or "").lower()
            url = extract_verify_url(message)
            looks_like_verify = bool(url) and any(
                key in text for key in ("verify", "验证", "welcome", "欢迎", "seconds", "秒")
            )
            if not looks_like_verify:
                return
            handled.add(message_id)
            print(f"\n★ 命中验证消息 [{message_id}] {(message.message or '')[:120]!r}", flush=True)
            print(f"   验证入口: {url}", flush=True)

            result = await browser_service.solve(url)
            print("   结果:", json.dumps({
                "ok": result.get("ok"),
                "browser": result.get("browser"),
                "window": result.get("window"),
                "elapsed": result.get("elapsed"),
                "verify": result.get("verify_response"),
            }, ensure_ascii=False), flush=True)
            print("   " + ("✅ 验证通过" if result.get("ok") else f"❌ {result.get('error')}"), flush=True)
        except BaseException as exc:  # noqa: BLE001
            print("   处理异常:", type(exc).__name__, str(exc)[:150], flush=True)

    try:
        chat = (await client(functions.contacts.ResolveUsernameRequest(username=args.group))).chats[0]
        print(f"监听中：{getattr(chat, 'title', None)} | 号 {account.phone_masked} | {args.seconds}s", flush=True)
        try:
            participant = await client(functions.channels.GetParticipantRequest(channel=chat, participant="me")
                                       )
            print(f"   当前成员状态：{type(getattr(participant, 'participant', None)).__name__}", flush=True)
        except BaseException:
            print("   当前不在群里（等管理员批准，批准后进群即触发）", flush=True)
        await asyncio.sleep(args.seconds)
    finally:
        await client.disconnect()
        print("监听结束", flush=True)


asyncio.run(main())
