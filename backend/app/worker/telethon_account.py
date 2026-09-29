"""单个用户号的 Telethon 连接封装：建连、身份回填、错误映射、指数退避。

一个号一个 `AccountConnection`，由 Worker 持有。连接失败不抛给主循环：
按 `map_exception_to_status()` 写回账号状态，或者只记 `last_error` 后重连。
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import update
from telethon import TelegramClient, events
from telethon import connection as tg_connection
from telethon.errors import (
    AuthKeyDuplicatedError,
    AuthKeyUnregisteredError,
    ChatWriteForbiddenError,
    FloodWaitError,
    PeerFloodError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberInvalidError,
    PhoneNumberUnoccupiedError,
    SessionExpiredError,
    SessionPasswordNeededError,
    SessionRevokedError,
    UserBannedInChannelError,
    UserDeactivatedBanError,
    UserDeactivatedError,
    UserRestrictedError,
)
from telethon.sessions import StringSession

from app.config import settings
from app.db import session_scope
from app.models import AccountStatus, TgAccount
from app.security import decrypt_secret
from app.worker import metrics
from app.worker.handlers import make_new_message_handler

logger = logging.getLogger(__name__)

#: 网络类错误：不改账号状态，只记 last_error 并重连
NETWORK_ERRORS = (ConnectionError, TimeoutError, OSError, asyncio.TimeoutError)


class SessionNotAuthorized(RuntimeError):
    """会话存在但 Telegram 不认（需要重新验证码）。"""


class CredentialsMissing(RuntimeError):
    """没配 TELEGRAM_API_ID / TELEGRAM_API_HASH，Worker 空转。"""


class AccountUnavailable(RuntimeError):
    """本进程暂时用不了这个号（未连接 / 退避中 / 没有会话）。"""


class ProxyUnavailable(RuntimeError):
    """配了代理但这套环境没有可用的 socks 后端。"""


class TaskFailure(RuntimeError):
    """任务失败：是否可重试、多久后重试、要不要顺手清掉这个号的租约。

    放在这里是因为登录流程与任务执行都要用，避免 task_runner ↔ login 循环导入。
    """

    def __init__(
        self,
        error: str,
        *,
        retryable: bool = True,
        requeue_after: Optional[int] = None,
        release_lease: bool = False,
    ) -> None:
        super().__init__(error)
        self.error = error
        self.retryable = retryable
        self.requeue_after = requeue_after
        self.release_lease = release_lease


# ---------------- 错误映射（纯函数，便于测试） ----------------


def map_exception_to_status(exc: BaseException) -> Optional[AccountStatus]:
    """把 Telethon 异常映射成账号状态；返回 None 表示不改状态（网络抖动）。"""
    if isinstance(exc, AuthKeyDuplicatedError):
        return AccountStatus.dead  # 永久双向：同一会话被两个地方使用
    if isinstance(exc, UserDeactivatedBanError):
        return AccountStatus.dead  # 已被封号，重登也没用
    if isinstance(exc, (AuthKeyUnregisteredError, SessionRevokedError, SessionExpiredError)):
        return AccountStatus.invalid  # 会话打不开
    if isinstance(exc, UserDeactivatedError):
        return AccountStatus.invalid  # 号已注销
    if isinstance(exc, (PhoneCodeInvalidError, PhoneCodeExpiredError, SessionPasswordNeededError)):
        return AccountStatus.needs_code
    if isinstance(exc, (PhoneNumberInvalidError, PhoneNumberUnoccupiedError)):
        return AccountStatus.needs_code
    if isinstance(exc, SessionNotAuthorized):
        return AccountStatus.needs_code
    if isinstance(exc, PhoneNumberBannedError):
        return AccountStatus.frozen  # 号被限制，不再替它发送
    if isinstance(exc, (FloodWaitError, PeerFloodError, UserBannedInChannelError, UserRestrictedError, ChatWriteForbiddenError)):
        return AccountStatus.frozen
    return None


def is_network_error(exc: BaseException) -> bool:
    """网络类错误：连接被断、超时、DNS 之类，不改账号状态。"""
    return isinstance(exc, NETWORK_ERRORS)


def flood_wait_seconds(exc: BaseException) -> Optional[int]:
    """FloodWait 还要等多少秒；不是限流则返回 None。"""
    if isinstance(exc, FloodWaitError):
        return int(getattr(exc, "seconds", 0) or 0)
    return None


def describe_exception(exc: BaseException) -> str:
    """给 last_error / 任务 error 用的中文说明，附异常类名方便排查。"""
    if isinstance(exc, AuthKeyUnregisteredError):
        text = "会话未被 Telegram 认可（AuthKey 未注册），需要重新登录"
    elif isinstance(exc, (SessionRevokedError, SessionExpiredError)):
        text = "会话已被吊销或过期，需要重新登录"
    elif isinstance(exc, AuthKeyDuplicatedError):
        text = "同一会话在别处被使用，Telegram 已永久停用该会话（永久双向）"
    elif isinstance(exc, SessionPasswordNeededError):
        text = "该号开启了两步验证，需要提交密码"
    elif isinstance(exc, (PhoneCodeInvalidError, PhoneCodeExpiredError)):
        text = "验证码不正确或已过期"
    elif isinstance(exc, PhoneNumberBannedError):
        text = "该手机号已被 Telegram 封禁"
    elif isinstance(exc, (PhoneNumberInvalidError, PhoneNumberUnoccupiedError)):
        text = "手机号无效或未注册 Telegram"
    elif isinstance(exc, FloodWaitError):
        text = f"Telegram 限流，需要等待 {flood_wait_seconds(exc)} 秒"
    elif isinstance(exc, PeerFloodError):
        text = "该号被 Telegram 限制发送（PeerFlood），已冻结"
    elif isinstance(exc, UserBannedInChannelError):
        text = "该号在目标会话里被禁言"
    elif isinstance(exc, UserRestrictedError):
        text = "该号被 Telegram 限制"
    elif isinstance(exc, ChatWriteForbiddenError):
        text = "没有在该会话发言的权限"
    elif isinstance(exc, UserDeactivatedBanError):
        text = "该号已被 Telegram 封禁"
    elif isinstance(exc, UserDeactivatedError):
        text = "该号已注销"
    elif is_network_error(exc):
        text = "网络连接异常"
    elif isinstance(exc, ProxyUnavailable):
        text = str(exc)
    elif isinstance(exc, SessionNotAuthorized):
        text = str(exc)
    else:
        text = "Telegram 调用失败"
    return f"{text}（{type(exc).__name__}: {exc}）"[:512]


# ---------------- 代理 ----------------


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    """账号固定出站地址（用户名 / 密码已解密）。"""

    scheme: str
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None

    @property
    def secret(self) -> str:
        """MTProxy 的 secret：库里没有单独字段，用密码或用户名承载。"""
        return (self.password or self.username or "").strip()

    @property
    def endpoint(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    @property
    def is_mtproxy(self) -> bool:
        return self.scheme.lower() in {"mtproxy", "mtproto"}


def build_proxy_config(proxy_row: Any) -> Optional[ProxyConfig]:
    """把 proxies 行转成 ProxyConfig，账号名 / 密码从密文解出。"""
    if proxy_row is None or not getattr(proxy_row, "enabled", True):
        return None
    username = None
    password = None
    if getattr(proxy_row, "username_enc", None):
        try:
            username = decrypt_secret(proxy_row.username_enc)
        except ValueError as exc:
            raise ProxyUnavailable(f"代理用户名解密失败：{exc}") from exc
    if getattr(proxy_row, "password_enc", None):
        try:
            password = decrypt_secret(proxy_row.password_enc)
        except ValueError as exc:
            raise ProxyUnavailable(f"代理密码解密失败：{exc}") from exc
    return ProxyConfig(
        scheme=(proxy_row.scheme or "socks5").lower(),
        host=proxy_row.host,
        port=int(proxy_row.port),
        username=username or None,
        password=password or None,
    )


def proxy_backend_available() -> bool:
    """Telethon 走 socks/http 代理需要 python-socks（或 PySocks）。"""
    try:
        import python_socks  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import socks  # noqa: F401
        return True
    except ImportError:
        return False


def telethon_proxy_argument(proxy: ProxyConfig) -> tuple:
    """Telethon 的 proxy 参数：socks/http 用六元组，MTProxy 用 (host, port, secret)。"""
    if proxy.is_mtproxy:
        if not proxy.secret:
            raise ProxyUnavailable("MTProxy 缺少 secret（填写在代理密码或用户名里）")
        return (proxy.host, proxy.port, proxy.secret)
    scheme = "http" if proxy.scheme in {"https", "http"} else proxy.scheme
    if scheme not in {"socks5", "socks4", "http"}:
        raise ProxyUnavailable(f"不支持的代理类型：{proxy.scheme}（支持 socks5/socks4/http/mtproxy）")
    if not proxy_backend_available():
        raise ProxyUnavailable(
            "该号配了代理，但环境里没有 python-socks / PySocks，无法通过代理建连；"
            "请安装 python-socks（telethon 的 socks 依赖）或清空该号代理"
        )
    # Telethon 的元组顺序：类型 / 地址 / 端口 / rdns / 用户名 / 密码
    return (scheme, proxy.host, proxy.port, True, proxy.username, proxy.password)


def connection_class_for(proxy: Optional[ProxyConfig]) -> Any:
    """MTProxy 用 RandomizedIntermediate，其它走默认 TcpFull。"""
    if proxy is not None and proxy.is_mtproxy:
        return tg_connection.ConnectionTcpMTProxyRandomizedIntermediate
    return tg_connection.ConnectionTcpFull


# ---------------- 账号快照 ----------------


@dataclass(slots=True)
class AccountSnapshot:
    """从 tg_accounts 行取出的连接所需字段（会话串已解密）。"""

    id: uuid.UUID
    phone_masked: str = "未知"
    status: str = AccountStatus.pending.value
    session_string: Optional[str] = None
    proxy: Optional[ProxyConfig] = None
    proxy_error: str = ""
    # 设备指纹：每个号一套（导入时随机写入），空值表示回退到全局默认
    device_model: str = ""
    system_version: str = ""
    app_version: str = ""
    lang_code: str = ""
    lang_pack: str = ""
    # 对齐的官方客户端平台（android / ios / tdesktop）
    client_kind: str = ""


def snapshot_from_row(row: TgAccount) -> AccountSnapshot:
    """把 ORM 行转成快照；会话串解密失败不抛异常，交给连接流程记 last_error。"""
    session_string: Optional[str] = None
    if row.session_enc:
        try:
            session_string = decrypt_secret(row.session_enc).strip() or None
        except ValueError as exc:
            logger.error(
                "会话解密失败，请检查 SESSION_ENCRYPTION_KEY",
                extra={"account_id": str(row.id), "error": str(exc)},
            )
            session_string = None
    proxy: Optional[ProxyConfig] = None
    proxy_error = ""
    try:
        proxy = build_proxy_config(row.proxy)
    except ProxyUnavailable as exc:
        proxy_error = str(exc)
    status = row.status.value if hasattr(row.status, "value") else str(row.status)
    return AccountSnapshot(
        id=row.id,
        phone_masked=row.phone_masked or "未知",
        status=status,
        session_string=session_string,
        device_model=(getattr(row, "device_model", "") or "").strip(),
        system_version=(getattr(row, "system_version", "") or "").strip(),
        app_version=(getattr(row, "app_version", "") or "").strip(),
        lang_code=(getattr(row, "lang_code", "") or "").strip(),
        lang_pack=(getattr(row, "lang_pack", "") or "").strip(),
        client_kind=(getattr(row, "client_kind", "") or "").strip(),
        proxy=proxy,
        proxy_error=proxy_error,
    )


# ---------------- 身份回填 ----------------


def display_name_of_user(user: Any) -> str:
    """Telegram 用户对象 → 展示名。"""
    if user is None:
        return ""
    parts = [getattr(user, "first_name", None), getattr(user, "last_name", None)]
    name = " ".join(part for part in parts if part).strip()
    if name:
        return name
    return getattr(user, "username", None) or getattr(user, "phone", None) or ""


async def persist_identity(
    session: Any,
    account: TgAccount,
    user: Any,
    *,
    session_string: Optional[str] = None,
    reset_authorized_at: bool = False,
    client_kind: Optional[str] = None,
) -> None:
    """连接成功 / 登录成功后回填身份：用户 ID、用户名、展示名、状态、号龄、对齐的客户端平台。"""
    now = datetime.now(tz=timezone.utc)
    if client_kind and not account.client_kind:
        # 连上以后把实际使用的官方客户端平台写回，页面就不再显示「未对齐」
        account.client_kind = client_kind
    if user is not None:
        account.tg_user_id = getattr(user, "id", None) or account.tg_user_id
        account.username = getattr(user, "username", None) or account.username
        name = display_name_of_user(user)
        if name:
            account.display_name = name
    if session_string:
        from app.security import encrypt_secret

        account.session_enc = encrypt_secret(session_string)
    if reset_authorized_at or account.authorized_at is None:
        account.authorized_at = now
    account.age_days = max(0, (now - account.authorized_at).days) if account.authorized_at else None
    account.status = AccountStatus.healthy
    account.status_reason = ""
    account.last_error = ""
    account.last_checked_at = now
    account.last_heartbeat = now
    await session.flush()


# ---------------- 单号连接 ----------------


class AccountConnection:
    """一个用户号的连接：惰性建连、失败退避、事件处理器注册、身份回填。"""

    def __init__(
        self,
        snapshot: AccountSnapshot,
        *,
        worker_id: str,
        redis: Any,
        handler_enabled: bool = True,
    ) -> None:
        self.snapshot = snapshot
        self.worker_id = worker_id
        self.redis = redis
        self.handler_enabled = handler_enabled
        self.client: Optional[TelegramClient] = None
        self.online = False
        self.ever_connected = False
        self.attempts = 0
        self.next_attempt_at = 0.0
        self.last_error = ""
        self.fatal_status: Optional[AccountStatus] = None
        self.connected_at: Optional[float] = None

    # ---------- 基本信息 ----------

    @property
    def account_id(self) -> uuid.UUID:
        """本连接的账号 ID。"""
        return self.snapshot.id

    @property
    def phone_masked(self) -> str:
        """脱敏手机号，日志用。"""
        return self.snapshot.phone_masked

    @property
    def has_session(self) -> bool:
        """库里有没有可用会话串。"""
        return bool(self.snapshot.session_string)

    def log_extra(self, **extra: Any) -> dict:
        """日志统一附带的上下文字段。"""
        return {"worker_id": self.worker_id, "account_id": str(self.account_id), **extra}

    def update_snapshot(self, snapshot: AccountSnapshot) -> bool:
        """用最新的库里状态刷新快照；会话变了要断开重连。返回是否要重连。"""
        session_changed = snapshot.session_string != self.snapshot.session_string
        proxy_changed = snapshot.proxy != self.snapshot.proxy
        self.snapshot = snapshot
        if session_changed or proxy_changed:
            self.attempts = 0
            self.next_attempt_at = 0.0
            return True
        return False

    def backoff_delay(self) -> float:
        """指数退避：base * 2^n，封顶 max，加一点抖动避免同时重连。"""
        base = max(1, settings.account_reconnect_backoff_seconds)
        ceiling = max(base, settings.account_reconnect_backoff_max_seconds)
        delay = min(base * (2 ** max(0, self.attempts - 1)), ceiling)
        return float(min(ceiling, delay * (0.85 + random.random() * 0.3)))

    # ---------- 建连 ----------

    def build_client(self, session_string: Optional[str] = None) -> TelegramClient:
        """按配置构造 TelegramClient（会话串 / 设备参数 / 代理）。"""
        if not settings.telegram_api_id or not settings.telegram_api_hash:
            raise CredentialsMissing("未配置 TELEGRAM_API_ID/TELEGRAM_API_HASH")
        proxy = self.snapshot.proxy
        proxy_arg = telethon_proxy_argument(proxy) if proxy is not None else None
        # 身份对齐：号自己没指纹时，从官方发布版本表里按平台挑一个（而不是用全局默认的假设备名）
        identity = self._identity()
        return TelegramClient(
            StringSession(session_string if session_string is not None else self.snapshot.session_string),
            settings.telegram_api_id,
            settings.telegram_api_hash,
            connection=connection_class_for(proxy),
            proxy=proxy_arg,
            # 设备指纹走这个号自己的（导入时随机生成），没有才退回全局默认：
            # 一批号用同型号同客户端版本是最容易被关联的特征之一
            device_model=identity["device_model"] or settings.telegram_device_model,
            system_version=identity["system_version"] or settings.telegram_system_version,
            app_version=identity["app_version"] or settings.telegram_app_version,
            lang_code=identity["lang_code"] or "en",
            # 注意：telethon 1.45 起不再接受 lang_pack（旧版本要求传），这里按支持情况动态组装，
            # 免得升级后又因为一个参数直接连不上（账号会一直「未上线」）
            **({"system_lang_code": identity["lang_pack"]} if identity.get("lang_pack") else {}),
            timeout=15,
            request_retries=3,
            connection_retries=3,
            retry_delay=1,
            auto_reconnect=True,
            receive_updates=self.handler_enabled,
            catch_up=False,
            # 限流直接抛 FloodWaitError，交给任务重试，别在事件循环里睡
            flood_sleep_threshold=0,
        )

    def _identity(self) -> dict[str, str]:
        """这个号对外呈现的客户端身份：优先用库里存的对齐值，缺失则按 client_kind 从官方表取。"""
        snapshot = self.snapshot
        if snapshot.device_model and snapshot.app_version:
            return {
                "device_model": snapshot.device_model,
                "system_version": snapshot.system_version,
                "app_version": snapshot.app_version,
                "lang_code": snapshot.lang_code or "en",
                "lang_pack": snapshot.lang_pack,
            }
        try:
            from app.services.official import pick_official_client

            client = pick_official_client(prefer=snapshot.client_kind or None)
            return {
                "device_model": client.device_model,
                "system_version": client.system_version,
                "app_version": client.app_version,
                "lang_code": client.system_lang_code.split("-")[0].lower() or "en",
                "lang_pack": client.lang_pack,
            }
        except Exception:  # noqa: BLE001 - 身份表不可用就退回配置默认值
            return {"device_model": "", "system_version": "", "app_version": "", "lang_code": "", "lang_pack": ""}

    def register_handlers(self, client: TelegramClient) -> None:
        """注册事件处理器：新消息入库 + 群入退群事件静默记录。"""
        if not self.handler_enabled:
            return
        handler = make_new_message_handler(
            worker_id=self.worker_id, account_id=self.account_id, redis=self.redis
        )
        client.add_event_handler(handler, events.NewMessage(incoming=True, outgoing=True))

        # 群情报：入群/退群/被拉进来——只写库，不在群里留下任何痕迹
        if settings.group_intel_watch_enabled:
            from app.worker.group_intel import make_chat_action_handler

            client.add_event_handler(
                make_chat_action_handler(
                    worker_id=self.worker_id, account_id=self.account_id, redis=self.redis
                ),
                events.ChatAction(),
            )

    async def ensure_connected(self) -> bool:
        """保证连接可用；连不上按退避重试并写回账号状态，绝不抛给主循环。"""
        if self.online and self.client is not None and self.client.is_connected():
            return True
        now = time.monotonic()
        if now < self.next_attempt_at:
            return False
        if not settings.telegram_api_id or not settings.telegram_api_hash:
            self.last_error = "未配置 TELEGRAM_API_ID/TELEGRAM_API_HASH"
            return False
        if not self.has_session:
            self.last_error = "该号还没有会话，需要先登录"
            return False
        if self.snapshot.proxy_error:
            self.last_error = self.snapshot.proxy_error
            self.attempts += 1
            self.next_attempt_at = now + self.backoff_delay()
            await self._write_last_error(self.last_error)
            logger.warning("代理不可用，跳过建连", extra=self.log_extra(error=self.last_error))
            return False

        client: Optional[TelegramClient] = None
        try:
            client = self.build_client()
            if self.ever_connected:
                metrics.record_reconnect()
            await client.connect()
            if not await client.is_user_authorized():
                raise SessionNotAuthorized("会话存在但 Telegram 不认，需要重新用验证码登录")
            me = await client.get_me()
            if me is None:
                raise SessionNotAuthorized("get_me 返回空，会话不可用，需要重新登录")
            async with session_scope() as session:
                account = await session.get(TgAccount, self.account_id)
                if account is None:
                    raise AccountUnavailable("账号已被删除")
                await persist_identity(session, account, me, client_kind=self._identity().get("lang_pack") or None)
        except Exception as exc:  # noqa: BLE001 - 连接失败都在这里收口
            if client is not None:
                await self._safe_disconnect(client)
            await self._handle_failure(exc)
            return False

        self.client = client
        self.online = True
        self.ever_connected = True
        self.attempts = 0
        self.next_attempt_at = 0.0
        self.last_error = ""
        self.connected_at = time.monotonic()
        self.register_handlers(client)
        logger.info(
            "用户号已连接",
            extra=self.log_extra(phone_masked=self.phone_masked, proxy=self.snapshot.proxy.endpoint if self.snapshot.proxy else ""),
        )
        return True

    async def disconnect(self) -> None:
        """断开连接（重连前 / 进程退出时调用）。"""
        client, self.client = self.client, None
        self.online = False
        self.connected_at = None
        if client is not None:
            await self._safe_disconnect(client)

    async def _safe_disconnect(self, client: TelegramClient) -> None:
        """断开且不抛异常。"""
        try:
            await client.disconnect()
        except Exception as exc:  # noqa: BLE001 - 退出路径不让异常扩散
            logger.debug("断开连接时出错", extra=self.log_extra(error=str(exc)))

    async def _handle_failure(self, exc: BaseException) -> None:
        """连接失败后的收口：映射状态 / 记 last_error / 排下一次重试。"""
        self.online = False
        self.attempts += 1
        self.next_attempt_at = time.monotonic() + self.backoff_delay()
        self.last_error = describe_exception(exc)[:512]
        status = map_exception_to_status(exc)

        if isinstance(exc, AccountUnavailable):
            logger.warning("账号不可用，稍后重试", extra=self.log_extra(error=self.last_error))
            return

        if status is not None:
            self.fatal_status = status if status in (AccountStatus.dead, AccountStatus.disabled) else None
            await self._write_status(status, reason=self.last_error)
            logger.warning(
                "用户号状态已更新",
                extra=self.log_extra(status=status.value, error=self.last_error, retry_in=round(self.backoff_delay(), 1)),
            )
            return

        # 网络类 / 未知异常：只记 last_error，状态不动
        await self._write_last_error(self.last_error)
        logger.warning(
            "用户号连接失败，稍后重连",
            extra=self.log_extra(error=self.last_error, attempts=self.attempts, retry_in=round(self.backoff_delay(), 1)),
        )

    async def _write_status(self, status: AccountStatus, *, reason: str = "") -> None:
        """写账号状态（连接层只改这三列）。"""
        try:
            async with session_scope() as session:
                await session.execute(
                    update(TgAccount)
                    .where(TgAccount.id == self.account_id)
                    .values(
                        status=status,
                        status_reason=reason[:255],
                        last_error=reason[:512],
                        last_checked_at=datetime.now(tz=timezone.utc),
                    )
                )
        except Exception:  # noqa: BLE001 - 写库失败不能打挂主循环
            logger.exception("写账号状态失败", extra=self.log_extra(status=status.value))

    async def _write_last_error(self, error: str) -> None:
        """只更新 last_error（网络抖动不改状态）。"""
        try:
            async with session_scope() as session:
                await session.execute(
                    update(TgAccount)
                    .where(TgAccount.id == self.account_id)
                    .values(last_error=error[:512])
                )
        except Exception:  # noqa: BLE001
            logger.exception("写 last_error 失败", extra=self.log_extra())

    # ---------- 调用辅助 ----------

    def require_client(self) -> TelegramClient:
        """取在线客户端；不在线直接抛 AccountUnavailable。"""
        if self.client is None or not self.online or not self.client.is_connected():
            raise AccountUnavailable(self.last_error or "该号当前未连接")
        return self.client

    async def ensure_and_get_me(self) -> Any:
        """检测用：确保连上并读一次 get_me。"""
        if not self.online or self.client is None or not self.client.is_connected():
            ok = await self.ensure_connected()
            if not ok:
                raise AccountUnavailable(self.last_error or "该号当前未连接")
        me = await self.require_client().get_me()
        if me is None:
            raise SessionNotAuthorized("get_me 返回空，会话不可用")
        async with session_scope() as session:
            account = await session.get(TgAccount, self.account_id)
            if account is not None:
                await persist_identity(session, account, me, client_kind=self._identity().get("lang_pack") or None)
        return me

    async def refresh_identity(self) -> bool:
        """读一次 get_me 回填身份，成功返回 True；失败只记日志。"""
        try:
            await self.ensure_and_get_me()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("刷新账号身份失败", extra=self.log_extra(error=describe_exception(exc)))
            return False



__all__ = [
    "AccountConnection",
    "AccountSnapshot",
    "AccountUnavailable",
    "CredentialsMissing",
    "ProxyConfig",
    "ProxyUnavailable",
    "SessionNotAuthorized",
    "TaskFailure",
    "build_proxy_config",
    "connection_class_for",
    "describe_exception",
    "display_name_of_user",
    "flood_wait_seconds",
    "is_network_error",
    "map_exception_to_status",
    "persist_identity",
    "proxy_backend_available",
    "snapshot_from_row",
    "telethon_proxy_argument",
]
