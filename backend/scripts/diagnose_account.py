"""账号体检：直接连上 Telegram，逐个探测方法可用性，判断号到底是被冻结、限制还是正常。

用途：页面报 `FrozenMethodInvalidError` 这类错误时，用来确认「是号的问题，还是操作的问题」。

    cd backend
    .venv/bin/python -m scripts.diagnose_account                # 检查全部账号
    .venv/bin/python -m scripts.diagnose_account --phone 9597   # 只检查手机号/标识含该串的号

探测项（从只读到轻微写，逐步加压）：

1. `get_me()`            纯读，确认会话能不能用；
2. `account.updateStatus` 切换在线状态（无痕，官方客户端本来就会做）；
3. `account.updateProfile` 传**当前值**（例如当前的 first_name），如果号没法改资料，
   这一步就会像页面上那样抛 `FrozenMethodInvalidError`，但因为是原值，不会改动任何东西；
4. `messages.getDialogs(1)` 读会话列表，确认读权限正常。

结论怎么读：

- 1 失败 → 会话本身无效（需重新登录）；
- 1 通过、2 或 3 失败且报 Frozen → **账号被冻结**，需要申诉；
- 3 报 PeerFlood → 只是发送频率限制，等等就好；
- 全通过 → 号是好的，之前失败的操作可能是目标（群/人）的问题。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any, Optional

from sqlalchemy import select
from telethon import functions
from telethon.sessions import StringSession

from app.config import settings
from app.db import SessionFactory
from app.models import TgAccount
from app.security import decrypt_secret
from app.worker.telethon_account import describe_exception

PROBES = ("get_me", "update_status", "update_profile", "read_dialogs")


def _client(session_string: str, device: dict[str, str]):
    from telethon import TelegramClient

    kwargs: dict[str, Any] = {
        "connection_retries": 2,
        "request_retries": 2,
        "timeout": 20,
        "flood_sleep_threshold": 0,
    }
    if device.get("device_model"):
        kwargs["device_model"] = device["device_model"]
    if device.get("system_version"):
        kwargs["system_version"] = device["system_version"]
    if device.get("app_version"):
        kwargs["app_version"] = device["app_version"]
    if device.get("lang_code"):
        kwargs["lang_code"] = device["lang_code"]
    return TelegramClient(
        StringSession(session_string),
        int(settings.telegram_api_id),
        settings.telegram_api_hash,
        **kwargs,
    )


async def probe_account(account: TgAccount) -> dict[str, str]:
    """逐个探测，返回 {探测项: 结果描述}。"""
    results: dict[str, str] = {}
    if not account.session_enc:
        return {"会话": "该号没有会话（需要先登录）"}
    try:
        session_string = decrypt_secret(account.session_enc)
    except ValueError:
        return {"会话": "会话解密失败（SESSION_ENCRYPTION_KEY 变了？）"}

    device = {
        "device_model": account.device_model or "",
        "system_version": account.system_version or "",
        "app_version": account.app_version or "",
        "lang_code": account.lang_code or "en",
    }
    client = _client(session_string, device)
    try:
        await client.connect()
    except BaseException as exc:  # noqa: BLE001 - 连接失败也算结论
        return {"连接": f"失败：{describe_exception(exc)}"}

    try:
        # 1) 读：能不能拿到自己
        me = None
        try:
            me = await client.get_me()
            results["get_me"] = f"通过（{getattr(me, 'id', '?')} @{getattr(me, 'username', None) or '无用户名'}）"
        except BaseException as exc:  # noqa: BLE001
            results["get_me"] = f"失败：{describe_exception(exc)}"

        # 2) 轻写：切换在线状态
        try:
            await client(functions.account.UpdateStatusRequest(offline=False))
            results["update_status"] = "通过（可写）"
        except BaseException as exc:  # noqa: BLE001
            results["update_status"] = f"失败：{describe_exception(exc)}"

        # 3) 用户实际失败的那个方法：传当前值，不改动任何东西
        if me is not None:
            try:
                await client(
                    functions.account.UpdateProfileRequest(
                        first_name=getattr(me, "first_name", None) or "",
                        last_name=getattr(me, "last_name", None) or "",
                    )
                )
                results["update_profile"] = "通过（可改资料）"
            except BaseException as exc:  # noqa: BLE001
                results["update_profile"] = f"失败：{describe_exception(exc)}"
        else:
            results["update_profile"] = "跳过（上一步没拿到自己）"

        # 4) 读会话列表
        try:
            dialogs = await client.get_dialogs(limit=1)
            results["read_dialogs"] = f"通过（可读，样例 {len(dialogs)} 条）"
        except BaseException as exc:  # noqa: BLE001
            results["read_dialogs"] = f"失败：{describe_exception(exc)}"

        # 收尾：把在线状态切回来，不在服务器上留痕
        try:
            await client(functions.account.UpdateStatusRequest(offline=True))
        except BaseException:  # noqa: BLE001
            pass
    finally:
        try:
            await client.disconnect()
        except BaseException:  # noqa: BLE001
            pass
    return results


def verdict(results: dict[str, str]) -> str:
    """根据探测结果给一句结论。"""
    joined = " ".join(results.values())
    if "Frozen" in joined:
        return "结论：账号被 Telegram 冻结（写操作被拒），需要找 @SpamBot 申诉"
    if "PeerFlood" in joined:
        return "结论：触发发送频率限制（PeerFlood），不是冻结，降速等待即可"
    if results.get("get_me", "").startswith("失败"):
        return "结论：会话无效或号已注销，需要重新登录"
    if results.get("update_status", "").startswith("通过") and results.get("update_profile", "").startswith("通过"):
        return "结论：账号正常，可读可写（之前失败的那次可能是目标或权限问题）"
    return "结论：部分能力受限，见上面逐项结果"


async def main() -> int:
    parser = argparse.ArgumentParser(description="账号体检：探测方法可用性")
    parser.add_argument("--phone", default="", help="只看标识/手机号包含该串的账号")
    args = parser.parse_args()

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        print("未配置 TELEGRAM_API_ID/HASH，无法连接 Telegram")
        return 1

    async with SessionFactory() as session:
        rows = list((await session.scalars(select(TgAccount).order_by(TgAccount.created_at))).all())
    if args.phone:
        rows = [r for r in rows if args.phone in (r.phone_masked or "") or args.phone in (r.remark or "")]
    if not rows:
        print("没有匹配的账号")
        return 1

    for account in rows:
        print(f"\n=== {account.phone_masked}（ID {account.tg_user_id or '—'}）===")
        results = await probe_account(account)
        for key in PROBES:
            if key in results:
                print(f"  {key:<16} {results[key][:120]}")
        for key, value in results.items():
            if key not in PROBES:
                print(f"  {key:<16} {value[:120]}")
        print("  " + verdict(results))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
