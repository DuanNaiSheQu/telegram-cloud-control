"""AI 服务层验证：未配置时报错明确；配置后用假 HTTP 通道验证草稿与 Bot 自动回复。

    cd backend && .venv/bin/python -m tests.smoke_ai
不起真实模型，用 httpx.MockTransport 拦请求，验证请求形状与返回值处理。
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict, List

import httpx

from app.config import settings
from app.models import Bot, Dialog, DialogChannel, DialogKind, Message, MessageDirection
from app.services.ai import AIUnavailable, ai_service

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    print(f"  {'✅' if ok else '❌'} {name}{(' — ' + str(detail)) if detail else ''}")


def make_dialog() -> Dialog:
    return Dialog(
        channel=DialogChannel.bot,
        kind=DialogKind.private,
        tg_chat_id=12345,
        title="张三",
        peer_display="张三",
    )


def make_messages() -> List[Message]:
    incoming = Message(dialog_id=None, channel=DialogChannel.bot, direction=MessageDirection.incoming, body="你们几点上班？")  # type: ignore[arg-type]
    outgoing = Message(dialog_id=None, channel=DialogChannel.bot, direction=MessageDirection.outgoing, body="你好，请问有什么可以帮您？")  # type: ignore[arg-type]
    return [incoming, outgoing]


async def main() -> int:
    print("== AI 服务层冒烟 ==")
    original = {
        "ai_enabled": settings.ai_enabled,
        "ai_api_key": settings.ai_api_key,
        "ai_base_url": settings.ai_base_url,
        "ai_model": settings.ai_model,
    }
    captured: Dict[str, Any] = {}

    # ---------- 1. 未配置 ----------
    print("1) 未配置 AI 时的行为")
    settings.ai_enabled = False
    settings.ai_api_key = ""
    check("available 为 False", ai_service.available is False)
    try:
        await ai_service.draft_reply(dialog=make_dialog(), history=make_messages())
        check("未配置时抛 AIUnavailable", False, "居然成功了")
    except AIUnavailable as exc:
        check("未配置时抛 AIUnavailable", True, str(exc)[:60])

    # ---------- 2. 配置后（假通道） ----------
    print("2) 配置后用假 HTTP 通道验证请求与解析")
    settings.ai_enabled = True
    settings.ai_api_key = "sk-test"
    settings.ai_base_url = "https://ai.example.com/v1"
    settings.ai_model = "test-model"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "我们 9:30 上班。"}}]},
        )

    # 用真实构造逻辑（含 Authorization / base_url），只把底层 transport 换成假通道，
    # 这样验证的就是生产路径上的请求形状，而不是测试自己拼出来的客户端。
    ai_service._client = None
    real_client = ai_service.client()
    check("真实客户端带上 Bearer 密钥", real_client.headers.get("authorization") == "Bearer sk-test")
    real_client._transport = httpx.MockTransport(handler)
    ai_service._client = real_client

    text = await ai_service.draft_reply(dialog=make_dialog(), history=make_messages(), instruction="客气一点")
    check("草稿返回模型正文", text == "我们 9:30 上班。", text)
    check("请求打到 /chat/completions", captured["url"].endswith("/v1/chat/completions"), captured["url"])
    check("带上 Bearer 密钥", captured["auth"] == "Bearer sk-test")
    check("使用配置的模型", captured["body"]["model"] == "test-model", captured["body"].get("model"))
    system_prompt = captured["body"]["messages"][0]["content"]
    check("system 里带会话上下文与额外要求", "张三" in system_prompt and "客气一点" in system_prompt)
    check(
        "历史消息按 incoming=user / outgoing=assistant 映射",
        [m["role"] for m in captured["body"]["messages"][1:]] == ["user", "assistant"],
        str([m["role"] for m in captured["body"]["messages"][1:]]),
    )

    bot = Bot(name="冒烟Bot", token_enc="x", persona_text="我们是内部客服，工作时间 9:30-18:30。")
    text = await ai_service.bot_auto_reply(bot=bot, dialog=make_dialog(), history=make_messages())
    check("Bot 自动回复返回正文", text == "我们 9:30 上班。", text)
    bot_system = captured["body"]["messages"][0]["content"]
    check("Bot 回复把资料放进 system（身份是 Bot）", "9:30-18:30" in bot_system and "Bot" in bot_system)

    # ---------- 3. 上游报错 ----------
    print("3) 上游报错要能冒泡")
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    ai_service._client = httpx.AsyncClient(
        base_url=settings.ai_base_url, transport=httpx.MockTransport(failing)
    )
    try:
        await ai_service.draft_reply(dialog=make_dialog(), history=make_messages())
        check("上游 500 会抛错（不静默返回空串）", False, "居然成功了")
    except httpx.HTTPStatusError as exc:
        check("上游 500 会抛错（不静默返回空串）", exc.response.status_code == 500)

    await ai_service.close()
    for key, value in original.items():
        setattr(settings, key, value)

    print()
    print(f"== 结果：{len(PASSED)} 通过 / {len(FAILED)} 失败 ==")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
