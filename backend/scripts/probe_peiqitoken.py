"""盯佩奇：入群 @TokenPayGroup，实时抓验证消息的原始按钮结构。

关键设计：**监听在入群之前注册**——佩奇的验证消息常在入群后几十秒内到达，
而且 60 秒后可能被它自己删掉；用轮询 get_messages 会漏，必须挂 NewMessage 事件。

捕获范围：佩奇发的（sender 或 via_bot 指向它）、正文含「验证/欢迎」的、带按钮的消息。
拿到结构后：
- 按钮带 data  → 用 GetBotCallbackAnswerRequest 直接触发（这就是「过验证」的动作）；
- 按钮带 url   → 验证在网页里，记下 URL 交浏览器层。
"""

from __future__ import annotations

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

PEIQI_ID = 8590651516  # @PeiQiBot
GROUP = "TokenPayGroup"
LISTEN_SECONDS = 150
OUT_FILE = "/tmp/peiqicap.json"

captured: list[dict] = []


def describe_button(btn: Any) -> dict:
    item: dict[str, Any] = {"text": getattr(btn, "text", None), "cls": type(btn).__name__}
    for attr in ("url", "data", "query"):
        value = getattr(btn, attr, None)
        if value in (None, ""):
            continue
        if isinstance(value, bytes):
            item[attr] = value.hex()[:400]
            item[attr + "_utf8"] = value.decode("utf-8", "replace")[:200]
        else:
            item[attr] = str(value)[:400]
    inner = getattr(btn, "button", None)
    if inner is not None:
        item["inner_cls"] = type(inner).__name__
        for attr in ("url", "query", "text"):
            value = getattr(inner, attr, None)
            if value:
                item["inner_" + attr] = str(value)[:400]
    return item


def describe(message: Any, *, chat_title: str = "", is_private: bool = False) -> dict:
    return {
        "where": ("私信" if is_private else f"群:{chat_title}"),
        "id": getattr(message, "id", None),
        "date": str(getattr(message, "date", None)),
        "sender_id": getattr(message, "sender_id", None),
        "via_bot_id": getattr(message, "via_bot_id", None),
        "text": (getattr(message, "message", None) or "")[:600],
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

    @client.on(events.NewMessage)
    async def on_message(event: Any) -> None:
        try:
            message = event.message
            text = message.message or ""
            is_bot_msg = getattr(message, "via_bot_id", None) == PEIQI_ID
            try:
                sender_id = event.sender_id
            except BaseException:  # noqa: BLE001
                sender_id = None
            from_peqi = sender_id == PEIQI_ID or is_bot_msg
            interesting = from_peqi or "验证" in text or "欢迎" in text or bool(getattr(message, "buttons", None))
            if not interesting:
                return
            is_private = bool(getattr(event, "is_private", False))
            title = ""
            try:
                chat = await event.get_chat()
                title = getattr(chat, "title", None) or getattr(chat, "first_name", "") or ""
            except BaseException:  # noqa: BLE001
                pass
            info = describe(message, chat_title=title, is_private=is_private)
            info["from_peqi"] = from_peqi
            captured.append(info)
            print("★ 捕获:", json.dumps(info, ensure_ascii=False)[:1200], flush=True)
        except BaseException as exc:  # noqa: BLE001
            print("handler 异常:", type(exc).__name__, str(exc)[:120], flush=True)

    try:
        # ---------- 只读探测 ----------
        print("=== ① 探测群 ===", flush=True)
        resolved = await client(functions.contacts.ResolveUsernameRequest(username=GROUP))
        if not resolved.chats:
            print("这不是群/频道", flush=True)
            return
        chat = resolved.chats[0]
        print(f"群: {getattr(chat, 'title', None)} id={getattr(chat, 'id', None)} "
              f"megagroup={getattr(chat, 'megagroup', None)}", flush=True)
        full = await client(functions.channels.GetFullChannelRequest(channel=chat))
        fc = full.full_chat
        print(json.dumps({
            "participants_count": getattr(fc, "participants_count", None),
            "join_request": bool(getattr(fc, "join_request", False)),
            "participants_hidden": bool(getattr(fc, "participants_hidden", False)),
            "about": (getattr(fc, "about", "") or "")[:200],
        }, ensure_ascii=False), flush=True)

        # ---------- 入群 ----------
        print("=== ② 入群 ===", flush=True)
        try:
            await client(functions.channels.JoinChannelRequest(channel=chat))
            print("✅ JoinChannel 成功（已是成员或在成员列表）", flush=True)
        except BaseException as exc:  # noqa: BLE001
            print("入群结果:", type(exc).__name__, str(exc)[:200], flush=True)

        # ---------- 实时监听 ----------
        print(f"=== ③ 实时监听 {LISTEN_SECONDS} 秒（等佩奇的验证消息） ===", flush=True)
        await asyncio.sleep(LISTEN_SECONDS)

        # ---------- 尝试一次点击（仅回调按钮） ----------
        print("=== ④ 尝试过验证 ===", flush=True)
        done = False
        for info in captured:
            if done or not info.get("from_peqi"):
                continue
            for row in info.get("buttons") or []:
                for btn in row:
                    if btn.get("data"):
                        peer = chat
                        try:
                            answer = await client(functions.messages.GetBotCallbackAnswerRequest(
                                peer=peer,
                                msg_id=info["id"],
                                data=bytes.fromhex(btn["data"]),
                            ))
                            print("回调结果:", json.dumps({
                                "button": btn.get("text"),
                                "message": getattr(answer, "message", None),
                                "url": getattr(answer, "url", None),
                                "alert": getattr(answer, "alert", False),
                            }, ensure_ascii=False), flush=True)
                            done = True
                        except BaseException as exc:  # noqa: BLE001
                            print("回调失败:", type(exc).__name__, str(exc)[:200], flush=True)
                        break
        if not done:
            print("（没有可点的回调按钮——说明佩奇给的是 URL / 网页验证）", flush=True)
    finally:
        try:
            with open(OUT_FILE, "w", encoding="utf-8") as handle:
                json.dump(captured, handle, ensure_ascii=False, indent=2)
            print(f"\n共捕获 {len(captured)} 条 → {OUT_FILE}", flush=True)
        except BaseException as exc:  # noqa: BLE001
            print("写文件失败:", exc, flush=True)
        await client.disconnect()


asyncio.run(main())
