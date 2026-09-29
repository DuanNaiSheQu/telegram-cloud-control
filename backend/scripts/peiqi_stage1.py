"""佩奇验证全流程（第一阶段）：入群 → 拿 webview 验证 URL。

第二阶段立刻由 Playwright 打开这个 URL，让页面里的 cap-widget 自己完成 PoW，
再把 /gk/captcha/verify 的响应抓回来——这样只需验证「佩奇是否接受空 init_data」，
不必手写 PoW 求解器。

时间预算：佩奇给 300 秒，本阶段控制在 120 秒内，留给浏览器阶段。
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from sqlalchemy import select
from telethon import TelegramClient, functions
from telethon.sessions import StringSession

from app.config import settings
from app.db import SessionFactory
from app.models import TgAccount
from app.security import decrypt_secret

PEIQI_ID = 8590651516
GROUP = "dujiaonext_official"
URL_FILE = "/tmp/peiqi_verify_url.txt"
INFO_FILE = "/tmp/peiqi_stage1.json"
WAIT_GROUP = 60   # 等群内公告
WAIT_PM = 45      # 等私聊验证消息


def button_url(btn: Any) -> str:
    """从按钮各种嵌套里挖出 URL。"""
    for target in (btn, getattr(btn, "button", None)):
        if target is None:
            continue
        url = getattr(target, "url", None)
        if url:
            return str(url)
        inner_type = getattr(target, "type", None)
        if inner_type is not None:
            url = getattr(inner_type, "url", None)
            if url:
                return str(url)
    return ""


def all_buttons(message: Any) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for row in (getattr(message, "buttons", None) or []):
        for btn in row:
            out.append((getattr(btn, "text", "") or "", button_url(btn)))
    return out


async def main() -> None:
    result: dict[str, Any] = {}
    async with SessionFactory() as session:
        rows = list((await session.scalars(select(TgAccount).order_by(TgAccount.created_at))).all())
    # 用较干净的那个号（上轮 @wwwwwdhjewgd 在另一个群已被临时禁言）
    # 8232186463 的会话已被 Telegram 撤销（AuthKeyUnregistered），改用实测可用的号
    account = next((r for r in rows if r.tg_user_id == 8966880282), None) or next(
        (r for r in rows if r.session_enc), None
    )
    if account is None:
        print("没有可用账号")
        return
    print(f"使用账号: {account.phone_masked} ({account.tg_user_id})", flush=True)

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
        # ---------- ① 群详情 ----------
        print("=== ① 解析目标群 ===", flush=True)
        resolved = await client(functions.contacts.ResolveUsernameRequest(username=GROUP))
        if not resolved.chats:
            print("这个用户名不是群/频道", flush=True)
            return
        chat = resolved.chats[0]
        result["group"] = {"id": getattr(chat, "id", None), "title": getattr(chat, "title", None)}
        print(json.dumps(result["group"], ensure_ascii=False), flush=True)
        try:
            full = await client(functions.channels.GetFullChannelRequest(channel=chat))
            fc = full.full_chat
            result["group_detail"] = {
                "participants_count": getattr(fc, "participants_count", None),
                "join_request": bool(getattr(fc, "join_request", False)),
                "participants_hidden": bool(getattr(fc, "participants_hidden", False)),
            }
            print(json.dumps(result["group_detail"], ensure_ascii=False), flush=True)
        except BaseException as exc:  # noqa: BLE001
            print("读群详情失败:", type(exc).__name__, flush=True)

        # 记录入群前最大消息 id，便于只挑新消息
        before_max = 0
        try:
            for message in await client.get_messages(chat, limit=5):
                before_max = max(before_max, getattr(message, "id", 0))
        except BaseException:  # noqa: BLE001
            pass

        # ---------- ② 入群 ----------
        print("=== ② 入群 ===", flush=True)
        try:
            await client(functions.channels.JoinChannelRequest(channel=chat))
            print("  ✅ JoinChannel 返回成功", flush=True)
        except BaseException as exc:  # noqa: BLE001
            print(f"  入群结果: {type(exc).__name__}: {str(exc)[:160]}", flush=True)
            result["join"] = f"{type(exc).__name__}: {str(exc)[:160]}"

        # ---------- ③ 等群内公告，取 start payload ----------
        print(f"=== ③ 等群内佩奇公告（最多 {WAIT_GROUP}s） ===", flush=True)
        payload = ""
        for _ in range(WAIT_GROUP // 5):
            await asyncio.sleep(5)
            try:
                for message in await client.get_messages(chat, limit=10):
                    if getattr(message, "id", 0) <= before_max:
                        continue
                    if getattr(message, "sender_id", None) != PEIQI_ID:
                        continue
                    for text, url in all_buttons(message):
                        match = re.search(r"[?&]start=([A-Za-z0-9_\-\.]+)", url)
                        if match:
                            payload = match.group(1)
                            result["payload"] = payload
                            result["group_announce_text"] = (message.message or "")[:400]
                            result["group_announce_button"] = {"text": text, "url": url}
                            print("  ★ 拿到 payload:", payload, "| 按钮:", url, flush=True)
                            break
                    if payload:
                        break
            except BaseException as exc:  # noqa: BLE001
                print("  读群消息失败:", type(exc).__name__, flush=True)
            if payload:
                break
        if not payload:
            print("  没等到群内公告按钮（可能入群需审核，或公告发出较慢）", flush=True)

        # ---------- ④ 触发私聊验证 ----------
        print("=== ④ 触发私聊验证 ===", flush=True)
        peiqi = None
        try:
            resolved_bot = await client(functions.contacts.ResolveUsernameRequest(username="PeiQiBot"))
            peiqi = resolved_bot.users[0] if resolved_bot.users else None
        except BaseException as exc:  # noqa: BLE001
            print("  解析佩奇失败:", type(exc).__name__, flush=True)
        if peiqi is not None:
            command = f"/start {payload}".strip()
            try:
                await client.send_message(peiqi, command)
                print(f"  已发 {command!r}，等私聊验证消息（{WAIT_PM}s）", flush=True)
            except BaseException as exc:  # noqa: BLE001
                print("  发送失败:", type(exc).__name__, str(exc)[:160], flush=True)

            verify_url = ""
            for _ in range(WAIT_PM // 5):
                await asyncio.sleep(5)
                try:
                    for message in list(await client.get_messages(peiqi, limit=6)):
                        if getattr(message, "sender_id", None) != PEIQI_ID:
                            continue
                        text = message.message or ""
                        for label, url in all_buttons(message):
                            if not url:
                                continue
                            verify_url = url
                            result["pm_text"] = text[:400]
                            result["pm_button"] = {"text": label, "url": url}
                            print("  ★ 私聊验证按钮:", label, "→", url, flush=True)
                            break
                        if verify_url:
                            break
                except BaseException as exc:  # noqa: BLE001
                    print("  读私聊失败:", type(exc).__name__, flush=True)
                if verify_url:
                    break

            if verify_url:
                with open(URL_FILE, "w", encoding="utf-8") as handle:
                    handle.write(verify_url)
                print(f"\n验证 URL 已写入 {URL_FILE}", flush=True)
            else:
                print("  没拿到 webview URL", flush=True)
    finally:
        with open(INFO_FILE, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        await client.disconnect()


asyncio.run(main())
