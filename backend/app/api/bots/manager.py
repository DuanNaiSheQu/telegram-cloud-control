"""Bot 运行时注册表：进程内保存 bot_id → (aiogram.Bot, Dispatcher)。

为什么要进程内注册表：Webhook 处理与 Bot 任务轮询都要复用同一个 aiogram 实例，
否则每次发消息都新建一个 aiohttp 会话，连接立刻被丢掉，也容易踩 Telegram 的连接数限制。
Token 换了 / Bot 删了都要重建或清理这个表。

所有 Telegram 调用都加了超时，并把 Telegram 的异常翻译成中文，方便直接回给值班的人看。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Union

from aiogram import Bot as AiogramBot
from aiogram import Dispatcher
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.types import Message as TgMessage
from aiogram.types import User as TgUser
from aiogram.utils.token import TokenValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.config import settings
from app.models import Bot as BotModel

logger = logging.getLogger(__name__)

#: 单次 Telegram 调用的超时：无网络时不要挂着请求等 60 秒
TELEGRAM_CALL_TIMEOUT = 15.0

#: Webhook 只关心这几类更新：普通消息、编辑过的消息、按钮回调、Bot 自己被拉进/踢出群
ALLOWED_UPDATES = ["message", "edited_message", "callback_query", "my_chat_member"]

#: Telegram 常见 bad request / forbidden 的中文说明（按小写子串匹配）
TELEGRAM_HINTS = (
    ("chat not found", "目标找不到（chat not found）：Bot 看不见这个会话——公开群/频道要填它的 @username，私有群要先拉 Bot 进群；转发和发送同样要求目标可达"),
    ("bot was blocked by the user", "对方已经把 Bot 拉黑"),
    ("user is deactivated", "对方账号已注销"),
    ("bot was kicked", "Bot 已被移出该群"),
    ("bot is not a member", "Bot 不在该群 / 会话中，请先把 Bot 拉进去"),
    ("not enough rights", "Bot 在该群没有发消息权限（需要设为管理员或关闭隐私模式）"),
    ("have no rights to send a message", "Bot 在该会话没有发消息权限"),
    ("chat_write_forbidden", "该会话是只读的，Bot 没有发言权限"),
    ("peer_id_invalid", "会话标识无效"),
    ("message text is empty", "消息正文为空"),
    ("message is too long", "消息太长，请拆短后再发"),
    ("too many requests", "被 Telegram 限速，请稍后重试"),
    ("chat admin required", "需要把 Bot 设为该群管理员才能执行这个操作"),
    ("button_user_privacy", "对方没和 Bot 发起过会话（需要对方先点 /start）"),
)


class BotTokenError(RuntimeError):
    """Token 不合法或 Telegram 连不上；路由层直接回 400 中文原因。"""


class BotSendError(RuntimeError):
    """发消息失败。retryable 决定任务回到队列还是直接判失败。"""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class BotRuntime:
    """一个 Bot 的进程内运行时。"""

    bot_id: uuid.UUID
    bot: AiogramBot
    dispatcher: Dispatcher = field(default_factory=Dispatcher)


_runtimes: Dict[uuid.UUID, BotRuntime] = {}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def translate_hint(text: str) -> Optional[str]:
    """把 Telegram 的英文报错翻译成人能看懂的说明。"""
    lowered = (text or "").lower()
    for needle, hint in TELEGRAM_HINTS:
        if needle in lowered:
            return hint
    return None


def describe_telegram_error(exc: BaseException) -> str:
    """统一的中文错误说明。"""
    text = str(exc)
    # 已经翻译过的自定义异常直接用它自己的话，别再套一层类名
    if isinstance(exc, (BotSendError, BotTokenError)):
        return text
    hint = translate_hint(text)
    if isinstance(exc, TokenValidationError):
        return "Token 格式不正确：应该形如 123456789:AA...（BotFather 给的完整字符串）"
    if isinstance(exc, TelegramUnauthorizedError):
        return "Telegram 拒绝了该 Token（401）：Token 无效或已被撤销，请到 BotFather 重新签发"
    if isinstance(exc, TelegramForbiddenError):
        return hint or f"Telegram 拒绝执行（403）：{text}"
    if isinstance(exc, TelegramRetryAfter):
        return f"被 Telegram 限速，请 {(getattr(exc, 'retry_after', 0) or 0)} 秒后重试"
    if isinstance(exc, TelegramBadRequest):
        return hint or f"Telegram 认为请求不合法（400）：{text}"
    if isinstance(exc, TelegramNetworkError):
        return "连不上 Telegram（网络或代理不可达），请检查服务器出网 / 代理配置"
    if isinstance(exc, TelegramServerError):
        return "Telegram 服务端错误（5xx），稍后会自动重试"
    if isinstance(exc, asyncio.TimeoutError):
        return "调用 Telegram 超时，请检查网络 / 代理"
    if isinstance(exc, TelegramAPIError):
        return hint or f"Telegram 接口报错：{text}"
    if isinstance(exc, (OSError, ConnectionError)):
        return "连不上 Telegram（网络不通），请检查服务器出网 / 代理配置"
    return f"操作失败：{type(exc).__name__}: {text}"


def _is_retryable(exc: BaseException) -> bool:
    """网络类 / 限速 / 5xx 值得重试；权限、参数类错误重试多少次都一样。"""
    return isinstance(
        exc,
        (TelegramNetworkError, TelegramRetryAfter, TelegramServerError, asyncio.TimeoutError),
    ) or isinstance(exc, (OSError, ConnectionError))


def build_bot(token: str) -> AiogramBot:
    """只做本地构造（会校验 Token 格式），不发网络请求。"""
    try:
        return AiogramBot(token=token)
    except TokenValidationError as exc:
        raise BotTokenError(describe_telegram_error(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - 其它构造失败也按 Token 问题处理
        raise BotTokenError(describe_telegram_error(exc)) from exc


async def fetch_me(token: str) -> tuple[AiogramBot, TgUser]:
    """调 getMe 校验 Token。失败时关掉临时会话，避免泄漏连接。"""
    bot = build_bot(token)
    try:
        me = await asyncio.wait_for(bot.get_me(), timeout=TELEGRAM_CALL_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        await close_bot(bot)
        raise BotTokenError(describe_telegram_error(exc)) from exc
    return bot, me


async def close_bot(bot: AiogramBot) -> None:
    try:
        await bot.session.close()
    except Exception:  # noqa: BLE001
        logger.debug("关闭 aiogram 会话失败", exc_info=True)


# ---------------- 注册表 ----------------

async def register(bot_id: uuid.UUID, *, aiogram_bot: AiogramBot) -> BotRuntime:
    """放进注册表；同一个 bot_id 重复注册会先关掉旧实例。"""
    old = _runtimes.pop(bot_id, None)
    if old is not None:
        await close_bot(old.bot)
    runtime = BotRuntime(bot_id=bot_id, bot=aiogram_bot)
    _runtimes[bot_id] = runtime
    return runtime


def get(bot_id: uuid.UUID) -> Optional[BotRuntime]:
    return _runtimes.get(bot_id)


async def unregister(bot_id: uuid.UUID, *, delete_webhook: bool = False) -> None:
    """清掉运行时；删 Bot 前先 delete_webhook，免得 Telegram 继续往不存在的地址打回调。"""
    runtime = _runtimes.pop(bot_id, None)
    if runtime is None:
        return
    if delete_webhook:
        try:
            await asyncio.wait_for(
                runtime.bot.delete_webhook(drop_pending_updates=False),
                timeout=TELEGRAM_CALL_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001 - 注销失败也要继续删库
            logger.warning("删除 Webhook 失败 bot_id=%s：%s", bot_id, describe_telegram_error(exc))
    await close_bot(runtime.bot)


async def ensure_runtime(bot_row: BotModel) -> Optional[BotRuntime]:
    """取运行时；没有就按库里的加密 Token 现场建一个（进程重启后第一次用到时走这里）。"""
    runtime = _runtimes.get(bot_row.id)
    if runtime is not None:
        return runtime
    try:
        token = security.decrypt_secret(bot_row.token_enc)
    except ValueError:
        logger.error("Bot Token 解密失败（SESSION_ENCRYPTION_KEY 可能变过）bot_id=%s", bot_row.id)
        return None
    try:
        aiogram_bot = build_bot(token)
    except BotTokenError as exc:
        logger.error("Bot Token 格式非法 bot_id=%s：%s", bot_row.id, exc)
        return None
    return await register(bot_row.id, aiogram_bot=aiogram_bot)


async def load_all(session: AsyncSession) -> int:
    """启动时把库里所有 Bot 装进注册表。"""
    bots = list((await session.scalars(select(BotModel))).all())
    loaded = 0
    for row in bots:
        if await ensure_runtime(row) is not None:
            loaded += 1
        else:
            logger.warning("跳过无法加载的 Bot bot_id=%s name=%s", row.id, row.name)
    logger.info("Bot 运行时注册表已加载 %s/%s 个", loaded, len(bots))
    return loaded


async def shutdown() -> None:
    """进程退出：关掉所有 aiogram 会话，别留在 aiohttp 的连接。"""
    bot_ids = list(_runtimes.keys())
    for bot_id in bot_ids:
        runtime = _runtimes.pop(bot_id, None)
        if runtime is not None:
            await close_bot(runtime.bot)
    if bot_ids:
        logger.info("已关闭 %s 个 Bot 运行时", len(bot_ids))


# ---------------- Webhook 注册 ----------------

async def apply_webhook(
    session: AsyncSession,
    bot_row: BotModel,
    *,
    enable: bool,
    runtime: Optional[BotRuntime] = None,
) -> tuple[bool, str]:
    """注册 / 删除 Telegram Webhook，并把 webhook_set_at 记在库里。返回 (是否成功, 中文说明)。"""
    runtime = runtime or await ensure_runtime(bot_row)
    if runtime is None:
        return False, "Bot 运行时不可用：Token 无法解密，请重新保存 Token"
    try:
        if enable:
            ok = await asyncio.wait_for(
                runtime.bot.set_webhook(
                    url=settings.webhook_url(bot_row.id),
                    allowed_updates=ALLOWED_UPDATES,
                    drop_pending_updates=False,
                ),
                timeout=TELEGRAM_CALL_TIMEOUT,
            )
            bot_row.webhook_enabled = True
            bot_row.webhook_secret = settings.webhook_secret
            bot_row.webhook_set_at = _now_iso()
            await session.flush()
            logger.info("Webhook 已注册 bot_id=%s ok=%s url=%s", bot_row.id, ok, settings.webhook_url(bot_row.id))
            return True, "Webhook 已注册"
        await asyncio.wait_for(
            runtime.bot.delete_webhook(drop_pending_updates=False),
            timeout=TELEGRAM_CALL_TIMEOUT,
        )
        bot_row.webhook_enabled = False
        bot_row.webhook_set_at = _now_iso()
        await session.flush()
        logger.info("Webhook 已删除 bot_id=%s", bot_row.id)
        return True, "Webhook 已删除"
    except Exception as exc:  # noqa: BLE001 - 网络 / Token 问题都翻译成中文回给前端
        detail = describe_telegram_error(exc)
        logger.warning("设置 Webhook 失败 bot_id=%s：%s", bot_row.id, detail)
        return False, detail


# ---------------- 发消息 ----------------

async def send_text(runtime: BotRuntime, chat_id: Union[int, str], text: str) -> TgMessage:
    """Bot 发一条文本。失败抛 BotSendError（中文原因 + 是否值得重试）。

    chat_id 允许 `@channel` 这类字符串：群发目标里两种写法都有。
    """
    try:
        return await asyncio.wait_for(
            runtime.bot.send_message(chat_id=chat_id, text=text),
            timeout=TELEGRAM_CALL_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        raise BotSendError(describe_telegram_error(exc), retryable=_is_retryable(exc)) from exc


async def forward_message(
    runtime: BotRuntime,
    chat_id: Union[int, str],
    from_chat_id: Union[int, str],
    message_id: int,
) -> TgMessage:
    """Bot 转发一条已有消息。与 send_text 同口径：统一超时 + 中文错误 + 可重试判定。"""
    try:
        return await asyncio.wait_for(
            runtime.bot.forward_message(
                chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id
            ),
            timeout=TELEGRAM_CALL_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        raise BotSendError(describe_telegram_error(exc), retryable=_is_retryable(exc)) from exc


__all__ = [
    "ALLOWED_UPDATES",
    "BotRuntime",
    "BotSendError",
    "BotTokenError",
    "TELEGRAM_CALL_TIMEOUT",
    "apply_webhook",
    "build_bot",
    "close_bot",
    "describe_telegram_error",
    "ensure_runtime",
    "fetch_me",
    "forward_message",
    "get",
    "load_all",
    "register",
    "send_text",
    "shutdown",
    "unregister",
]
