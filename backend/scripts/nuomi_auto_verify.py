"""NuoMi 类验证（Cloudflare Turnstile）全自动通过 —— 系统真 Chrome，全程不碰自动化协议。

实测结论（这是本方案的全部依据）：

1. **Turnstile 会识破 Playwright/CDP**
   同一个页面、同一条网络：Playwright 打开的浏览器一律报 `Widget error`，
   而系统真 Chrome 完全正常。Cloudflare 识别的是自动化协议通道，不是浏览器指纹本身。
   所以这里**不用 Playwright**：拿链接靠 telethon，打开靠 `open -a`。

2. **Turnstile 是非交互式的**
   页面上没有需要点的复选框，widget 自己会算出 token 并回调提交，
   **不需要任何鼠标/键盘动作**（我试过 Tab+Space 也没影响，纯粹是白费时间）。

3. **唯一真正的约束是速度**
   验证链接只有 60 秒寿命。把等待全部压掉后，实测 **14.5 秒**完成全套：
   3.2s 拿到链接 → 5.5s 打开并激活 → 14.5s 回查已进群。

4. **验证成功的判据**
   不靠读页面（那需要截图权限），而是**回查群成员身份**：
   `ChannelParticipantSelf` = 正式成员；`ChannelParticipantBanned` = 被限制；
   抛 `UserNotParticipantError` = 还没进去。

用法：
    cd backend
    .venv/bin/python -m scripts.nuomi_auto_verify --group devqun --uid 8645074324 --bot NuoMiBot
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import time
from typing import Any, Optional

from sqlalchemy import select
from telethon import TelegramClient, functions
from telethon.sessions import StringSession

from app.config import settings
from app.db import SessionFactory
from app.models import TgAccount
from app.security import decrypt_secret


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


def osascript(script: str) -> str:
    """macOS 系统级调用：用来把 Chrome 激活，不经过任何自动化协议。"""
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
        return (result.stdout or result.stderr).strip()[:160]
    except BaseException as exc:  # noqa: BLE001
        return f"osascript 失败: {type(exc).__name__}"


async def verify_link(client: TelegramClient, bot: Any, previous: set[str], timeout: float = 15.0) -> str:
    """轮询等 NuoMi 发新链接（要排除上一轮留下的旧链接，否则会拿着过期 token 白跑）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await asyncio.sleep(1.2)
        for message in list(await client.get_messages(bot, limit=6)):
            for row in getattr(message, "buttons", None) or []:
                for button in row:
                    url = deep_url(button)
                    if "okapp.uk" in url and url not in previous:
                        return url
    return ""


async def collect_links(client: TelegramClient, bot: Any) -> set[str]:
    found: set[str] = set()
    for message in list(await client.get_messages(bot, limit=6)):
        for row in getattr(message, "buttons", None) or []:
            for button in row:
                url = deep_url(button)
                if "okapp.uk" in url:
                    found.add(url)
    return found


async def member_state(client: TelegramClient, chat: Any) -> Optional[str]:
    """回查自己在群里的身份 —— 这是判断验证是否成功的可靠依据。"""
    try:
        part = await client(functions.channels.GetParticipantRequest(channel=chat, participant="me"))
        participant = getattr(part, "participant", None)
        return type(participant).__name__ if participant is not None else "Unknown"
    except BaseException as exc:  # noqa: BLE001
        return type(exc).__name__


async def main() -> None:
    parser = argparse.ArgumentParser(description="NuoMi(Turnstile) 验证全自动")
    parser.add_argument("--group", required=True, help="目标群用户名")
    parser.add_argument("--uid", type=int, required=True, help="用哪个号（tg_user_id）")
    parser.add_argument("--bot", default="NuoMiBot", help="发验证链接的管理机器人用户名")
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
        connection_retries=1,
        request_retries=1,
        timeout=20,
    )
    await client.connect()
    started = time.monotonic()
    try:
        chat = (await client(functions.contacts.ResolveUsernameRequest(username=args.group))).chats[0]
        bot = (await client(functions.contacts.ResolveUsernameRequest(username=args.bot))).users[0]
        previous = await collect_links(client, bot)

        # 触发：申请入群会立刻收到新的验证链接
        try:
            await client(functions.channels.JoinChannelRequest(channel=chat))
        except BaseException:  # noqa: BLE001 - 已在群里或已申请过，都不影响拿链接
            pass

        url = await verify_link(client, bot, previous)
        if not url:
            print(f"✗ 没拿到新的验证链接（{time.monotonic() - started:.1f}s）")
            return
        print(f"① {time.monotonic() - started:.1f}s 拿到链接")

        # 交给系统真 Chrome —— 关键：不经 CDP，Turnstile 才不会报 Widget error
        subprocess.run(["open", "-a", "Google Chrome", url], check=False)
        osascript('tell application "Google Chrome" to activate')
        print(f"② {time.monotonic() - started:.1f}s 已用系统 Chrome 打开并激活")

        # Turnstile 非交互式，等待它自己完成并提交即可
        for attempt in range(8):
            await asyncio.sleep(2.5)
            state = await member_state(client, chat)
            if state and "NotParticipant" not in state:
                print(f"③ {time.monotonic() - started:.1f}s ✅ 验证通过，成员身份：{state}")
                return
        print(f"③ {time.monotonic() - started:.1f}s ❌ 未通过（成员身份：{await member_state(client, chat)}）")
        print("   排查提示：链接是否在 60 秒内打开？系统 Chrome 是否可用？")
    finally:
        await client.disconnect()


asyncio.run(main())
