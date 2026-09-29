"""佩奇验证全自动（无人值守版）。

链路（全部自动，不弹窗、不点任何东西）：
  1. 入群 → 读佩奇群内公告按钮 → 提取 start payload
  2. /start <payload> → 佩奇私聊
  3. 若要求先关注频道 → 自动 JoinChannel
  4. 点「已关注,继续验证」回调按钮（bot callback）
  5. 读 webview 按钮 → 提取 captcha URL（...&p=cap）
  6. RequestWebView(platform='web', from_bot_menu=True) → 服务器签发 tgWebAppData（合法 initData）
  7. 调 Node 脚本：屏幕外 Chrome 打开 URL → cap-widget 自动解 PoW → POST verify

用法：
    cd backend
    .venv/bin/python -m scripts.peiqi_auto_verify --uid 8802064479 --group dujiaonext_official
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import platform
import shutil
import subprocess
import time
from typing import Any

from sqlalchemy import select
from telethon import TelegramClient, functions
from telethon.sessions import StringSession

from app.config import settings
from app.db import SessionFactory
from app.models import TgAccount
from app.security import decrypt_secret

def ensure_display() -> dict:
    """给浏览器阶段准备一块"屏幕"。

    Cap 会检测浏览器环境，纯无头模式直接被拦；所以必须跑真实窗口。
    服务器没有桌面时用 Xvfb 造虚拟显示——Chrome 以为自己在正常显示器上，
    实际没有任何物理输出。macOS/Windows 本身有显示，无需处理。
    """
    env = dict(os.environ)
    if platform.system() != "Linux" or env.get("DISPLAY"):
        return env
    if shutil.which("Xvfb") is None:
        print("   ⚠ 未装 Xvfb，浏览器阶段会失败：先跑 bash scripts/install_browser.sh", flush=True)
        return env
    display = ":99"
    subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "1280x800x24"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)
    env["DISPLAY"] = display
    print(f"   已启动虚拟显示 {display}（无桌面环境也能跑真窗口）", flush=True)
    return env


PEIQI_ID = 8590651516
PEIQI_USERNAME = "PeiQiBot"
ROOT = pathlib.Path(__file__).resolve().parents[2]
NODE_SCRIPT = ROOT / "frontend" / "scripts" / "peiqi_web_solve.mjs"
URL_FILE = "/tmp/peiqi_auto_url.txt"


def deep_url(button: Any) -> str:
    """逐层挖按钮 URL：btn.url → btn.button.url → btn.button.type.url（webview 的藏在最后一层）。"""
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


def button_data(button: Any) -> str:
    for obj in (button, getattr(button, "button", None)):
        if obj is None:
            continue
        data = getattr(obj, "data", None)
        if data:
            return data.hex() if isinstance(data, bytes) else str(data)
    return ""


def scan_buttons(message: Any) -> dict:
    """从一条消息里收集：所有 url、带 data 的回调、captcha 链接。"""
    out: dict[str, Any] = {
        "msg_id": getattr(message, "id", None),
        "urls": [], "callbacks": [], "captcha": "",
        "text": (getattr(message, "message", "") or "")[:200],
    }
    for row in getattr(message, "buttons", None) or []:
        for button in row:
            label = (getattr(button, "text", "") or "").strip()
            url = deep_url(button)
            data = button_data(button)
            if url:
                out["urls"].append({"label": label, "url": url})
            if data:
                out["callbacks"].append({"label": label, "data": data})
            if "captcha" in url:
                out["captcha"] = url
    return out


async def main() -> None:
    parser = argparse.ArgumentParser(description="佩奇验证全自动")
    parser.add_argument("--uid", type=int, required=True, help="用哪个号的 tg_user_id")
    parser.add_argument("--group", required=True, help="目标群用户名")
    parser.add_argument("--visible", action="store_true", help="调试用：让浏览器窗口显示出来")
    args = parser.parse_args()

    async with SessionFactory() as session:
        account = await session.scalar(select(TgAccount).where(TgAccount.tg_user_id == args.uid))
    if account is None:
        print(f"找不到 tg_user_id={args.uid} 的号")
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
        print(f"① 账号 {account.phone_masked}（{args.uid}）已连接", flush=True)
        chat = (await client(functions.contacts.ResolveUsernameRequest(username=args.group))).chats[0]
        before_max = 0
        try:
            for message in await client.get_messages(chat, limit=3):
                before_max = max(before_max, getattr(message, "id", 0))
        except BaseException:  # noqa: BLE001
            pass

        print("② 提交入群申请 …", flush=True)
        try:
            await client(functions.channels.JoinChannelRequest(channel=chat))
        except BaseException as exc:  # noqa: BLE001 - 需审核的群会抛 InviteRequestSent，属正常
            print(f"   {type(exc).__name__}", flush=True)

        print("③ 等佩奇群内公告 …", flush=True)
        payload = ""
        for _ in range(20):
            await asyncio.sleep(1.5)
            for message in await client.get_messages(chat, limit=8):
                if getattr(message, "id", 0) <= before_max or getattr(message, "sender_id", None) != PEIQI_ID:
                    continue
                for entry in scan_buttons(message)["urls"]:
                    if "start=" in entry["url"]:
                        payload = entry["url"].split("start=")[-1].split("&")[0]
                if payload:
                    break
            if payload:
                break
        print(f"   payload={payload or '未拿到'}", flush=True)
        if not payload:
            return

        peiqi = (await client(functions.contacts.ResolveUsernameRequest(username=PEIQI_USERNAME))).users[0]
        await client.send_message(peiqi, f"/start {payload}")

        print("④ 处理佩奇私聊（关注频道 / 点回调 / 取 captcha）…", flush=True)
        captcha = ""
        channel_joined = False
        for round_index in range(20):
            await asyncio.sleep(1.5)
            scans = [scan_buttons(m) for m in await client.get_messages(peiqi, limit=10)]
            for scan in scans:
                if scan["captcha"]:
                    captcha = scan["captcha"]
            if captcha:
                break
            # 需要先关注频道
            for scan in scans:
                for entry in scan["urls"]:
                    if entry["url"].startswith("https://t.me/") and "频道" in entry["label"] and not channel_joined:
                        name = entry["url"].rstrip("/").split("/")[-1]
                        print(f"   → 关注频道 @{name}", flush=True)
                        try:
                            target = (await client(functions.contacts.ResolveUsernameRequest(username=name))).chats[0]
                            await client(functions.channels.JoinChannelRequest(channel=target))
                            channel_joined = True
                        except BaseException as exc:  # noqa: BLE001
                            print(f"     关注失败 {type(exc).__name__}", flush=True)
                for entry in scan["callbacks"]:
                    if "继续验证" in entry["label"]:
                        print(f"   → 点回调「{entry['label']}」", flush=True)
                        try:
                            answer = await client(
                                functions.messages.GetBotCallbackAnswerRequest(
                                    peer=peiqi, msg_id=scan.get("msg_id"), data=bytes.fromhex(entry["data"])
                                )
                            )
                            print(f"     回调：{(getattr(answer, 'message', None) or '')[:80]}", flush=True)
                        except BaseException as exc:  # noqa: BLE001
                            print(f"     回调失败 {type(exc).__name__}", flush=True)
                        await client.send_message(peiqi, f"/start {payload}")
        print(f"⑤ captcha：{'已拿到' if captcha else '未拿到'}", flush=True)
        if not captcha:
            return

        result = await client(
            functions.messages.RequestWebViewRequest(
                peer=peiqi, bot=peiqi, platform="web", from_bot_menu=True, url=captcha
            )
        )
        pathlib.Path(URL_FILE).write_text(result.url, encoding="utf-8")
        print(f"⑥ 签名 URL 已生成（含 initData），长度 {len(result.url)}", flush=True)
    finally:
        await client.disconnect()

    # ---------- ⑦ 浏览器阶段（屏幕外运行，全程自动点击） ----------
    print("⑦ 交给浏览器完成 Cap 与提交 …", flush=True)
    browser_env = ensure_display()
    command = ["node", str(NODE_SCRIPT), URL_FILE] + (["--visible"] if args.visible else [])
    completed = subprocess.run(
        command, cwd=str(ROOT / "frontend"), capture_output=True, text=True,
        timeout=240, env=browser_env,
    )
    for line in (completed.stdout or "").splitlines():
        print("   " + line, flush=True)
    if completed.returncode != 0:
        print("   浏览器阶段退出码", completed.returncode, (completed.stderr or "")[:300], flush=True)


asyncio.run(main())
