"""佩奇私聊验证：读私聊历史 → 触发 /start → 抓验证按钮原始结构 → 能点就点。

从群里的公告看，流程是「点开始验证按钮 → 跳私聊 → 在私聊里完成验证」，
所以真正要处理的是**私聊那一侧**：
- 读历史：看它是否已经发过验证（加入群时它可能已经推过）；
- 触发：给 bot 发 `/start`（带 payload 的更好，payload 从群里按钮 URL 提取）；
- 抓结构：按钮带 data → 直接回调触发；带 url → 记下 URL 交浏览器层；
- 私有网页验证（Cap / Turnstile）通常由按钮 URL 或 webview 承载，URL 本身也是证据。
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from sqlalchemy import select
from telethon import TelegramClient, events, functions
from telethon.sessions import StringSession

from app.config import settings
from app.db import SessionFactory
from app.models import TgAccount
from app.security import decrypt_secret

PEIQI = "PeiQiBot"
GROUP = "TokenPayGroup"
OUT_FILE = "/tmp/peiqicap.json"
captured: list[dict] = []


def describe_button(btn: Any) -> dict:
    item: dict[str, Any] = {"text": getattr(btn, "text", None), "cls": type(btn).__name__}
    for attr in ("url", "data", "query"):
        value = getattr(btn, attr, None)
        if value in (None, ""):
            continue
        if isinstance(value, bytes):
            item[attr] = value.hex()[:500]
            item[attr + "_utf8"] = value.decode("utf-8", "replace")[:300]
        else:
            item[attr] = str(value)[:500]
    inner = getattr(btn, "button", None)
    if inner is not None:
        item["inner_cls"] = type(inner).__name__
        for attr in ("url", "query", "text", "hash"):
            value = getattr(inner, attr, None)
            if value:
                item["inner_" + attr] = str(value)[:500]
    return item


def describe(message: Any) -> dict:
    urls = [getattr(e, "url", None) for e in (getattr(message, "entities", None) or []) if getattr(e, "url", None)]
    return {
        "id": getattr(message, "id", None),
        "date": str(getattr(message, "date", None)),
        "out": bool(getattr(message, "out", False)),
        "sender_id": getattr(message, "sender_id", None),
        "via_bot_id": getattr(message, "via_bot_id", None),
        "text": (getattr(message, "message", None) or "")[:700],
        "entity_urls": urls,
        "buttons": [
            [describe_button(b) for b in row] for row in (getattr(message, "buttons", None) or [])
        ],
    }


def remember(info: dict, tag: str) -> None:
    info["tag"] = tag
    captured.append(info)
    print(f"★ [{tag}]", json.dumps(info, ensure_ascii=False)[:1500], flush=True)


async def main() -> None:
    async with SessionFactory() as session:
        rows = list((await session.scalars(select(TgAccount).order_by(TgAccount.created_at))).all())
    account = next((r for r in rows if r.tg_user_id == 8966880282), None) or next(
        (r for r in rows if r.session_enc), None
    )
    if account is None:
        print("没有可用账号")
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
            if getattr(event, "is_private", False):
                remember(describe(message), "私信(实时)")
        except BaseException as exc:  # noqa: BLE001
            print("handler err:", type(exc).__name__, flush=True)

    try:
        # ---------- ① 群里的按钮（拿 payload） ----------
        print("=== ① 群内佩奇消息 + 按钮 ===", flush=True)
        group_payload = ""
        try:
            resolved = await client(functions.contacts.ResolveUsernameRequest(username=GROUP))
            chat = resolved.chats[0] if resolved.chats else None
            if chat is not None:
                for message in await client.get_messages(chat, limit=50):
                    buttons = getattr(message, "buttons", None)
                    text = message.message or ""
                    if not buttons and "验证" not in text and "欢迎" not in text:
                        continue
                    info = describe(message)
                    remember(info, "群内")
                    for row in info["buttons"]:
                        for btn in row:
                            for key in ("url", "inner_url"):
                                link = btn.get(key) or ""
                                match = re.search(r"[?&]start=([A-Za-z0-9_\-\.]+)", link)
                                if match and not group_payload:
                                    group_payload = match.group(1)
                                    print("  提取到 start payload:", group_payload, flush=True)
        except BaseException as exc:  # noqa: BLE001
            print("读群消息失败:", type(exc).__name__, str(exc)[:150], flush=True)

        # ---------- ② 佩奇私聊历史 ----------
        print("=== ② 佩奇私聊历史 ===", flush=True)
        peiqi = None
        try:
            resolved_bot = await client(functions.contacts.ResolveUsernameRequest(username=PEIQI))
            peiqi = resolved_bot.users[0] if resolved_bot.users else None
            if peiqi is not None:
                print(f"佩奇 id={peiqi.id}", flush=True)
                for message in list(await client.get_messages(peiqi, limit=15)):
                    remember(describe(message), "私聊历史")
        except BaseException as exc:  # noqa: BLE001
            print("读佩奇私聊失败:", type(exc).__name__, str(exc)[:200], flush=True)

        # ---------- ③ 触发验证：发 /start（带 payload） ----------
        if peiqi is not None:
            command = f"/start {group_payload}".strip()
            print(f"=== ③ 给佩奇发 {command!r} ===", flush=True)
            try:
                await client.send_message(peiqi, command)
                print("  已发送，等 25 秒看回复", flush=True)
                await asyncio.sleep(25)
                for message in list(await client.get_messages(peiqi, limit=8)):
                    info = describe(message)
                    if info["id"] not in {c.get("id") for c in captured}:
                        remember(info, "私聊回复")
            except BaseException as exc:  # noqa: BLE001
                print("  发送失败:", type(exc).__name__, str(exc)[:200], flush=True)

        # ---------- ④ 尝试回调按钮（能点就点） ----------
        print("=== ④ 尝试过验证（仅回调按钮） ===", flush=True)
        clicked = False
        for info in captured:
            if clicked:
                break
            for row in info.get("buttons") or []:
                for btn in row:
                    data_hex = btn.get("data")
                    if not data_hex:
                        continue
                    try:
                        answer = await client(functions.messages.GetBotCallbackAnswerRequest(
                            peer=peiqi,
                            msg_id=info["id"],
                            data=bytes.fromhex(data_hex),
                        ))
                        print("  回调结果:", json.dumps({
                            "button": btn.get("text"),
                            "message": getattr(answer, "message", None),
                            "url": getattr(answer, "url", None),
                            "alert": getattr(answer, "alert", False),
                        }, ensure_ascii=False), flush=True)
                        clicked = True
                    except BaseException as exc:  # noqa: BLE001
                        print("  回调失败:", type(exc).__name__, str(exc)[:200], flush=True)
                    break
        if not clicked:
            print("  （佩奇给的是 URL / 网页验证，Telegram 这一层点不出来）", flush=True)
    finally:
        try:
            with open(OUT_FILE, "w", encoding="utf-8") as handle:
                json.dump(captured, handle, ensure_ascii=False, indent=2)
            print(f"\n共记录 {len(captured)} 条 → {OUT_FILE}", flush=True)
        except BaseException as exc:  # noqa: BLE001
            print("写文件失败:", exc, flush=True)
        await client.disconnect()


asyncio.run(main())
