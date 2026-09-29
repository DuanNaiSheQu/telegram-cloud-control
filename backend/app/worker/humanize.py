"""真人化辅助：随机间隔、文本池分配、轻度口语化、AI 人设话术。

不引入全局随机状态：每个任务用自己的 `random.Random`（种子取自 task id + 账号），
这样重试时序列可复现，不同号之间又不雷同。
"""

from __future__ import annotations

import asyncio
import random
import uuid
from typing import List, Optional, Sequence

from app.config import settings

#: 句尾标点集合（判断要不要补标点）
_ENDINGS = "。！？.!?~～…"


def rng_for(task_id: uuid.UUID, account_index: int = 0, round_no: int = 0) -> random.Random:
    """按任务 / 账号 / 轮次生成可复现的随机源。"""
    seed = int(str(task_id).replace("-", ""), 16) ^ (account_index * 7919) ^ (round_no * 104729)
    return random.Random(seed)


def pick_for_index(texts: Sequence[str], index: int) -> str:
    """文本池按账号序号取模分配：不同号说不同的话，池子短了自动循环。"""
    if not texts:
        return ""
    return str(texts[index % len(texts)])


def pick_random(texts: Sequence[str], rng: random.Random) -> str:
    if not texts:
        return ""
    return str(rng.choice(texts))


def human_delay(min_seconds: float, max_seconds: float, rng: random.Random) -> float:
    """两句话之间的随机间隔（秒），带一点浮点抖动。"""
    lo = max(0.0, float(min_seconds))
    hi = max(lo, float(max_seconds))
    return round(rng.uniform(lo, hi), 2)


async def sleep_human(min_seconds: float, max_seconds: float, rng: random.Random) -> None:
    await asyncio.sleep(human_delay(min_seconds, max_seconds, rng))


#: 不可见字符：零宽空格 / 零宽非连接符 / BOM / 词连接符。
#: 它们不影响阅读，但会改变消息的**字节序列**——同一句文案发多次，
#: 每次的指纹都不同，绕开「完全相同内容重复发送」这一类内容级判定。
_INVISIBLE_CHARS = ("\u200b", "\u200c", "\u2060", "\ufeff")


def inject_invisible(text: str, rng: random.Random, chance: float = 0.6) -> str:
    """给文案注入不可见字符变体（每条都不一样，肉眼与复制粘贴都看不出）。

    对手（彩虹）这一手是通过第三方机器人 `@postbot` 完成的：让机器人返回一串编码，
    发送时替换成文案。**原理并不神秘**——就是给文本做不可见的字节级扰动，
    让每条消息的内容指纹不同。既然如此，没必要依赖别人的机器人：
    我们在发送前本地做掉，可控、无外部依赖、随时能关。

    注意：这只影响「内容重复」这一类判定。风控主要还是看**行为**（频率、目标数、
    举报率、账号年龄），所以它是节流/配额的补充，不是替代。
    """
    if not text:
        return text
    rng_local = rng
    out: list[str] = []
    for ch in text:
        out.append(ch)
        # 在字与字之间按概率插一个不可见字符；不插在末尾，避免被某些客户端裁掉
        if ch.strip() and rng_local.random() < chance * 0.12:
            out.append(rng_local.choice(_INVISIBLE_CHARS))
    return "".join(out)


def naturalize(text: str, rng: random.Random) -> str:
    """轻度口语化：补句尾标点、偶尔换成波浪号、小概率统一半角问叹号。

    刻意保守：不改词、不加错别字、不动语义，只做「像随手打出来」的标点层微调。
    """
    value = (text or "").strip()
    if not value:
        return value
    if value[-1] not in _ENDINGS:
        value += rng.choice(["~", "。", "～"])
    elif rng.random() < 0.12:
        value = value.rstrip("。.!?…") + "～"
    if rng.random() < 0.10:
        value = value.replace("！", "!").replace("？", "?")
    return inject_invisible(value, rng)


#: 拟人发言的系统提示（AI 生成话术用）
PERSONA_SYSTEM_PROMPT = (
    "你是一名普通 Telegram 用户，正在群里聊天。你的人设如下，请完全按人设说话。\n"
    "要求：一句话到三句话，口语化、自然、像真人随手打出来的；\n"
    "禁止 AI 腔（不要说“大家好”“很高兴认识你”“总结一下”），禁止输出引号、解释或多余标点；\n"
    "直接给出要发出去的那句话。"
)


def persona_messages(
    *,
    persona: str,
    topic: Optional[str],
    context: Sequence[str],
) -> List[dict]:
    """构造给 AI 的 messages：人设 + 话题 + 最近群聊上下文。"""
    system = PERSONA_SYSTEM_PROMPT + "\n\n=== 你的人设 ===\n" + persona + "\n=== 人设结束 ==="
    if topic:
        system += f"\n发言围绕这个话题：{topic}"
    messages: List[dict] = [{"role": "system", "content": system}]
    for line in context[-settings.campaign_persona_context_messages:]:
        messages.append({"role": "user", "content": line})
    if not context:
        messages.append({"role": "user", "content": "（群里还没人说话）按人设起个头"})
    return messages
