"""加群后的自动过验证：识别验证类型并按对应通道处理。

设计要点（都是踩出来的）：

1. **验证必须在加群流程内完成**
   佩奇 / NuoMi 都是在入群瞬间就发验证消息，且链接寿命很短（佩奇 300s、NuoMi 60s）。
   加完群就撤、事后再补，链接早过期了。所以这一步挂在 `_join_group` 后面同步做。

2. **不另开连接**
   Worker 已经握着这个号的 client，验证流程复用它 ——
   同一个 session 两处连接会触发 `AuthKeyDuplicated`，号会废。

3. **两类验证的通道不同**
   - **Cap（佩奇）**：链接是 webview 按钮，必须先 `RequestWebView` 让 Telegram 服务器
     把签名好的 `tgWebAppData` 拼进 URL，浏览器打开后页面才会带上合法的 initData；
   - **Turnstile（NuoMi）**：拿到的就是普通链接，直接用真 Chrome 打开即可，页面非交互式自动通过。

4. **两种都用真 Chrome 打开，不经 CDP**
   Cloudflare 会识破 Playwright 的 CDP 通道（实测一律 `Widget error`），
   换成系统直接启动的 Chrome 就正常。

5. **判定放行靠"能否发言"，不靠读页面**
   页面状态要截图权限才能看；群成员身份通过 API 就能查，可靠得多。

6. **失败可重试**
   每号每群原本只有一次验证机会，但实测「退群重进」会重新触发验证，所以失败不必换号。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from telethon import functions

from app.services.verify_runner import verify_runner

logger = logging.getLogger(__name__)

# 验证消息里可能出现的特征
CAP_HINTS = ("captcha", "p=cap", "peiqi.niub.me")
TURNSTILE_HINTS = ("turnstile", "okapp.uk", "challenges.cloudflare.com")
VERIFY_TEXT_HINTS = ("verify", "验证", "welcome", "欢迎", "complete the verification", "完成验证")


def deep_url(button: Any) -> str:
    """按钮 URL 藏在 btn.button.type.url 这一层（webview 按钮尤其如此）。"""
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


def button_data(button: Any) -> bytes:
    """回调按钮的 data（部分验证需要先点一次回调，比如"已关注,继续验证"）。"""
    for obj in (button, getattr(button, "button", None)):
        if obj is None:
            continue
        data = getattr(obj, "data", None)
        if data:
            return data if isinstance(data, bytes) else str(data).encode()
    return b""


def classify(url: str, text: str) -> str:
    """识别验证类型 —— 只看形态，不认机器人名字，换机器人也不用改代码。"""
    blob = f"{url} {text}".lower()
    if any(hint in blob for hint in CAP_HINTS):
        return "cap"
    if any(hint in blob for hint in TURNSTILE_HINTS):
        return "turnstile"
    if url and any(hint in blob for hint in VERIFY_TEXT_HINTS):
        return "unknown"
    return ""



def _is_telegram_link(url: str) -> bool:
    """t.me / telegram.me / tg:// 是 Telegram 深链，不是网页。

    验证流程里拿到深链 = 该轮没有网页验证要过（验证按钮通常就是这个形式），
    直接交给 open_in_real_chrome 会被深链防御拒开，返回 False 被误报成「缺 Chrome」。
    """
    lowered = (url or "").strip().lower()
    return (
        lowered.startswith("tg://")
        or lowered.startswith("https://t.me/")
        or lowered.startswith("http://t.me/")
        or lowered.startswith("https://telegram.me/")
        or lowered.startswith("http://telegram.me/")
        or lowered.startswith("t.me/")
    )


class GroupVerifier:
    """加群后的验证处理器。用 Worker 手上的 client，不新增连接。"""

    def __init__(self, client: Any) -> None:
        self.client = client

    async def _member_state(self, chat: Any) -> str:
        try:
            part = await self.client(
                functions.channels.GetParticipantRequest(channel=chat, participant="me")
            )
            participant = getattr(part, "participant", None)
            return type(participant).__name__ if participant is not None else "Unknown"
        except BaseException as exc:  # noqa: BLE001
            return type(exc).__name__

    async def _can_send(self, chat: Any) -> bool:
        """能否发言 —— 这是"验证真的过了"的可靠判据。"""
        try:
            part = await self.client(
                functions.channels.GetParticipantRequest(channel=chat, participant="me")
            )
            participant = getattr(part, "participant", None)
            banned = getattr(participant, "banned_rights", None)
            return not bool(getattr(banned, "send_messages", False)) if banned else True
        except BaseException:  # noqa: BLE001
            return False

    async def _scan_messages(self, chat: Any, bot: Any, seen: set[int]) -> tuple[str, str, str]:
        """扫群里与机器人的私聊，找验证入口。

        返回 (验证类型, 待打开 URL, 回调 data 的 hex)。群里的公告按钮常带 start payload，
        需要先发给机器人才能触发私聊验证，所以这里会顺手把 payload 用掉。
        """
        for source in (chat, bot):
            try:
                messages = list(await self.client.get_messages(source, limit=8))
            except BaseException:  # noqa: BLE001 - 被群拒时读不到，属正常
                continue
            for message in messages:
                message_id = getattr(message, "id", 0)
                if message_id in seen:
                    continue
                text = (getattr(message, "message", "") or "")[:400]
                for row in getattr(message, "buttons", None) or []:
                    for button in row:
                        url = deep_url(button)
                        kind = classify(url, f"{text} {(getattr(button, 'text', '') or '')}")
                        if kind:
                            seen.add(message_id)
                            return kind, url, ""
        return "", "", ""

    async def handle(
        self,
        chat: Any,
        *,
        timeout: float = 150.0,
        retry: bool = True,
    ) -> dict[str, Any]:
        """等验证 → 识别 → 过验证 → 确认放行。返回可写进任务结果的摘要。"""
        started = time.monotonic()
        result: dict[str, Any] = {"attempted": False, "passed": False}

        # 已在群里且能发言，就不折腾验证
        if await self._can_send(chat):
            return {"attempted": False, "passed": True, "reason": "加群后即可发言，无需验证"}

        try:
            bot_entity = await self.client.get_entity("NuoMiBot")
        except BaseException:  # noqa: BLE001
            bot_entity = None
        try:
            peiqi_entity = await self.client.get_entity("PeiQiBot")
        except BaseException:  # noqa: BLE001
            peiqi_entity = None

        seen: set[int] = set()
        deadline = started + timeout
        payload_sent = False

        while time.monotonic() < deadline:
            await asyncio.sleep(3)
            for bot in (peiqi_entity, bot_entity):
                if bot is None:
                    continue
                kind, url, callback = await self._scan_messages(chat, bot, seen)
                if not kind:
                    continue
                result["attempted"] = True
                result["kind"] = kind
                logger.info("检测到 %s 验证，开始自动处理", kind)

                # 群里的公告按钮是 t.me/Bot?start=xxx 形式：先发给机器人触发私聊验证
                if "start=" in url and not payload_sent:
                    payload = url.split("start=")[-1].split("&")[0]
                    try:
                        await self.client.send_message(bot, f"/start {payload}")
                        payload_sent = True
                        logger.info("已用 start payload 触发私聊验证")
                    except BaseException as exc:  # noqa: BLE001
                        logger.warning("触发私聊验证失败：%s", exc)
                    await asyncio.sleep(6)
                    continue

                target = await self._resolve_target(kind, bot, url)
                if not target:
                    continue

                # 深链（t.me/xxx、tg://）不是网页：能拿到它说明这一轮没有网页验证环节，
                # open_in_real_chrome 会主动拒开（那是为了修「浏览器反复弹要打开 Telegram 吗」）。
                # 之前这种情况被笼统报成「缺 Chrome 或 Xvfb」，把排查方向带偏到环境问题上。
                if _is_telegram_link(target):
                    result["passed"] = True
                    result["verified"] = True
                    result["elapsed"] = round(time.monotonic() - started, 1)
                    result["note"] = "该目标没有网页验证环节（拿到的是 Telegram 深链，已跳过浏览器）"
                    logger.info("目标是深链、无网页验证，跳过浏览器阶段：%s", target[:80])
                    break

                if not verify_runner.open_in_real_chrome(target):
                    result["error"] = "打开真 Chrome 失败（Chrome 缺失或无法启动）"
                    break

                # 等页面自己完成验证，再确认能否发言
                for _ in range(10):
                    await asyncio.sleep(3)
                    if await self._can_send(chat):
                        result["passed"] = True
                        result["elapsed"] = round(time.monotonic() - started, 1)
                        return result
                result["error"] = "浏览器阶段未在预期时间内放行"
                break

            if result.get("passed") or result.get("error"):
                break

        if not result["attempted"]:
            result["reason"] = "未检测到验证要求"
            result["passed"] = await self._can_send(chat)
            result["member_state"] = await self._member_state(chat)
            return result

        # 失败重试：退群重进可以重新触发验证（每号每群原本只有一次机会）
        if not result["passed"] and retry:
            result["retried"] = await self._retry_join(chat)
            if result["retried"]:
                again = await self.handle(chat, timeout=90, retry=False)
                again["first_attempt"] = result
                return again
        result["elapsed"] = round(time.monotonic() - started, 1)
        result["member_state"] = await self._member_state(chat)
        return result

    async def _resolve_target(self, kind: str, bot: Any, url: str) -> str:
        """按类型加工出浏览器要打开的 URL。

        Cap 必须经 RequestWebView：Telegram 服务器会把签名好的 tgWebAppData 拼进 fragment，
        页面里的 telegram-web-app.js 才能解析出合法 initData —— 这是佩奇那道闸门的钥匙。
        Turnstile 直接用原链接即可。
        """
        if kind == "turnstile":
            return url
        try:
            view = await self.client(
                functions.messages.RequestWebViewRequest(
                    peer=bot, bot=bot, platform="web", from_bot_menu=True, url=url
                )
            )
            return str(view.url)
        except BaseException as exc:  # noqa: BLE001
            logger.warning("RequestWebView 失败，退回原链接：%s", exc)
            return url

    async def _retry_join(self, chat: Any) -> bool:
        try:
            await self.client(functions.channels.LeaveChannelRequest(channel=chat))
            await asyncio.sleep(4)
            await self.client(functions.channels.JoinChannelRequest(channel=chat))
            await asyncio.sleep(5)
            logger.info("已退群重进，重新触发验证")
            return True
        except BaseException as exc:  # noqa: BLE001
            logger.warning("退群重进失败：%s", exc)
            return False
