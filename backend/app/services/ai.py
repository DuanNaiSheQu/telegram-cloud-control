"""AI：只做两件事 —— 控制台草稿，以及官方 Bot 按自己资料自动回复。

调用记录与资料分开存放：资料在 bots.persona_text，调用记录在 audit_logs / reply_drafts。
未配置 AI_API_KEY 时明确报错，不静默假装成功。
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import httpx

from app.config import settings
from app.models import Bot, Dialog, Message, MessageDirection


class AIUnavailable(RuntimeError):
    """没有配置可用的模型通道。"""


DRAFT_SYSTEM_PROMPT = (
    "你是 Telegram 会话助理，为运营人员生成一段可直接发送的回复草稿。"
    "要求：语气自然、简短、与上下文语言一致；不要编造未提供的事实；"
    "不要寒暄解释，只输出要发送的正文。"
)

BOT_SYSTEM_PROMPT = (
    "你在以官方 Bot 的身份回复 Telegram 用户。只依据下面提供的资料作答，"
    "资料里没有的信息要坦率说明并给出下一步；语气友好、简短，不要暴露自己是模型。"
)


class AIService:
    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def available(self) -> bool:
        return bool(settings.ai_enabled and settings.ai_api_key and settings.ai_base_url)

    def _ensure(self) -> None:
        if not self.available:
            raise AIUnavailable("AI 未启用：请配置 AI_ENABLED、AI_API_KEY、AI_BASE_URL、AI_MODEL")

    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.ai_base_url.rstrip("/"),
                timeout=settings.ai_timeout_seconds,
                headers={
                    "Authorization": f"Bearer {settings.ai_api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def chat(self, messages: List[dict], *, temperature: float = 0.6) -> str:
        self._ensure()
        payload = {
            "model": settings.ai_model,
            "messages": messages,
            "temperature": temperature,
        }
        response = await self.client().post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise AIUnavailable("模型返回为空")
        content = (choices[0].get("message") or {}).get("content") or ""
        return content.strip()

    @staticmethod
    def to_history(messages: Sequence[Message], *, limit: Optional[int] = None) -> List[dict]:
        max_items = limit or settings.ai_max_history
        history: List[dict] = []
        for message in list(messages)[-max_items:]:
            role = "user" if message.direction == MessageDirection.incoming else "assistant"
            body = message.body or ""
            if not body.strip():
                continue
            history.append({"role": role, "content": body})
        return history

    async def draft_reply(
        self,
        *,
        dialog: Dialog,
        history: Sequence[Message],
        instruction: str = "",
    ) -> str:
        """按资料库生成一段回复草稿，交给运营人员确认。"""
        self._ensure()
        context_lines = [
            f"会话类型：{'群聊' if str(getattr(dialog.kind, 'value', dialog.kind)) == 'group' else '私信'}",
            f"会话名称：{dialog.title}",
            f"对方：{dialog.peer_display or dialog.username or dialog.tg_chat_id}",
        ]
        system = DRAFT_SYSTEM_PROMPT + "\n" + "\n".join(context_lines)
        if instruction:
            system += f"\n额外要求：{instruction}"
        messages = [{"role": "system", "content": system}]
        messages.extend(self.to_history(history))
        if not messages[1:]:
            messages.append({"role": "user", "content": "（对方还没有消息，请给出一句合适的开场）"})
        return await self.chat(messages)

    async def bot_auto_reply(
        self, *, bot: Bot, dialog: Dialog, history: Sequence[Message]
    ) -> str:
        """官方 Bot 用自己的资料自动回复，身份是 Bot。"""
        self._ensure()
        persona = (bot.persona_text or "").strip() or "这是一个自动应答的服务号，请礼貌地说明你无法回答该问题。"
        system = (
            f"{BOT_SYSTEM_PROMPT}\n\n=== 本 Bot 资料 ===\n{persona}\n=== 资料结束 ===\n"
            f"会话：{dialog.title}；对方：{dialog.peer_display or dialog.tg_chat_id}"
        )
        messages = [{"role": "system", "content": system}]
        messages.extend(self.to_history(history))
        return await self.chat(messages)


ai_service = AIService()
