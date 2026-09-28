"""验证码登录三步：`login_start` 发码 → `login_code` 提交 → `login_password` 两步密码。

只用这个号自己的验证码，不导入别人的会话文件。发码用的临时会话串加密后放 Redis
（`settings.login_session_ttl_seconds` 秒），提交成功后 `tg_accounts.session_enc` 才落库。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from telethon import TelegramClient
from telethon.errors import PhoneCodeExpiredError, SessionPasswordNeededError
from telethon.sessions import StringSession

from app.config import settings
from app.core import audit as audit_core
from app.core import events as core_events
from app.core.tasks import enqueue_task
from app.models import AccountStatus, Task, TaskType, TgAccount
from app.security import decrypt_secret, encrypt_secret, mask_phone
from app.worker.telethon_account import (
    TaskFailure,
    build_proxy_config,
    connection_class_for,
    describe_exception,
    flood_wait_seconds,
    is_network_error,
    map_exception_to_status,
    persist_identity,
    telethon_proxy_argument,
)

logger = logging.getLogger(__name__)

STEP_CODE = "code_required"
STEP_PASSWORD = "password_required"
STEP_DONE = "done"

_DELIVERY_LABELS = {
    "SentCodeTypeApp": "Telegram App",
    "SentCodeTypeSms": "短信",
    "SentCodeTypeCall": "语音电话",
    "SentCodeTypeFlashCall": "闪信",
    "SentCodeTypeMissedCall": "未接来电",
    "SentCodeTypeEmailCode": "邮件",
    "SentCodeTypeSetUpEmailRequired": "需要先设置邮箱",
    "SentCodeTypeFragmentSms": "Fragment 短信",
}


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def delivery_label(sent: Any) -> str:
    """验证码发送方式，回给页面提示用户去哪儿看。"""
    code_type = getattr(sent, "type", None)
    name = type(code_type).__name__ if code_type is not None else ""
    return _DELIVERY_LABELS.get(name, name or "未知方式")


def build_login_client(*, account: TgAccount, session_string: str = "") -> TelegramClient:
    """登录用临时客户端：套用该号的代理与设备参数，会话串可来自 Redis 临时态。"""
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise TaskFailure(
            "未配置 TELEGRAM_API_ID/TELEGRAM_API_HASH，无法登录", retryable=True, requeue_after=60
        )
    proxy = build_proxy_config(account.proxy)
    proxy_arg = telethon_proxy_argument(proxy) if proxy is not None else None
    return TelegramClient(
        StringSession(session_string or ""),
        settings.telegram_api_id,
        settings.telegram_api_hash,
        connection=connection_class_for(proxy),
        proxy=proxy_arg,
        device_model=settings.telegram_device_model,
        system_version=settings.telegram_system_version,
        app_version=settings.telegram_app_version,
        timeout=15,
        request_retries=3,
        connection_retries=3,
        retry_delay=1,
        auto_reconnect=False,
        receive_updates=False,
        catch_up=False,
        flood_sleep_threshold=0,
    )


async def safe_disconnect(client: Optional[TelegramClient]) -> None:
    """断开临时客户端且不抛异常。"""
    if client is None:
        return
    try:
        await client.disconnect()
    except Exception as exc:  # noqa: BLE001 - 退出路径不让异常扩散
        logger.debug("断开登录临时客户端出错", extra={"error": str(exc)})


async def _client_from_state(state: dict, account: TgAccount) -> TelegramClient:
    """按 Redis 里的临时态重建客户端（同一个 auth key 才能接着 sign_in）。"""
    raw = state.get("session") or ""
    session_string = ""
    if raw:
        try:
            session_string = decrypt_secret(raw)
        except ValueError as exc:
            raise TaskFailure(f"登录临时会话解密失败：{exc}", retryable=False) from exc
    return build_login_client(account=account, session_string=session_string)


def _failure(
    account: TgAccount,
    exc: BaseException,
    *,
    prefix: str,
    retryable: bool = False,
    retry_after: Optional[int] = None,
) -> TaskFailure:
    """把登录异常写回账号行并转成 TaskFailure。"""
    status = map_exception_to_status(exc)
    account.last_checked_at = _now()
    account.last_error = describe_exception(exc)[:512]
    if status is AccountStatus.dead:
        account.status = AccountStatus.dead
        account.status_reason = "会话永久不可用"
    elif status is AccountStatus.frozen:
        account.status = AccountStatus.frozen
        account.status_reason = "被 Telegram 限制，不再替它执行"
    elif status is AccountStatus.invalid:
        account.status = AccountStatus.invalid
        account.status_reason = "会话不可用，需要重新登录"
    elif status is AccountStatus.needs_code:
        account.status = AccountStatus.needs_code
    wait = flood_wait_seconds(exc)
    if wait:
        return TaskFailure(f"{prefix}：{describe_exception(exc)}", retryable=True, requeue_after=wait + 1)
    if is_network_error(exc):
        return TaskFailure(
            f"{prefix}：{describe_exception(exc)}", retryable=True, requeue_after=retry_after or 15
        )
    return TaskFailure(f"{prefix}：{describe_exception(exc)}", retryable=retryable, requeue_after=retry_after)


async def _publish_account(worker: Any, account: TgAccount) -> None:
    """把账号状态变化推给页面。"""
    try:
        await core_events.publish_account_event(
            worker.redis,
            {
                "account_id": str(account.id),
                "status": account.status.value if hasattr(account.status, "value") else str(account.status),
                "current_task": account.current_task.value
                if hasattr(account.current_task, "value")
                else str(account.current_task),
                "last_heartbeat": _now().isoformat(),
            },
        )
    except Exception:  # noqa: BLE001 - 推送失败不影响登录
        logger.debug("推送账号事件失败", extra={"account_id": str(account.id)})


# ---------------- 三步 ----------------


async def login_start(session: Any, *, task: Task, account: TgAccount, worker: Any) -> dict:
    """第一步：发验证码，把临时会话串加密后放 Redis。"""
    payload = dict(task.payload or {})
    phone = str(payload.get("phone") or "").strip()
    if not phone and account.phone_enc:
        try:
            phone = decrypt_secret(account.phone_enc)
        except ValueError:
            phone = ""
    if not phone:
        raise TaskFailure("登录任务缺少手机号", retryable=False)
    if not worker.telegram_ready:
        raise TaskFailure(
            "未配置 TELEGRAM_API_ID/TELEGRAM_API_HASH，Worker 空转，无法发起登录",
            retryable=True,
            requeue_after=60,
        )

    client = build_login_client(account=account)
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        session_string = client.session.save()
        delivery = delivery_label(sent)
        code_hash = getattr(sent, "phone_code_hash", "") or ""
    except TaskFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - 统一转成任务失败
        raise _failure(account, exc, prefix="发送验证码失败", retryable=True) from exc
    finally:
        await safe_disconnect(client)

    state = {
        "step": STEP_CODE,
        "phone": phone,
        "phone_code_hash": code_hash,
        "session": encrypt_secret(session_string),
        "delivery": delivery,
        "created_at": _now().isoformat(),
    }
    await core_events.save_login_session(
        worker.redis, account.id, state, ttl=settings.login_session_ttl_seconds
    )
    account.phone_enc = encrypt_secret(phone)
    account.phone_masked = mask_phone(phone)
    account.status = AccountStatus.needs_code
    account.status_reason = f"已发送验证码（{delivery}），等待提交"
    account.last_error = ""
    account.last_checked_at = _now()
    await session.flush()
    await audit_core.write_audit(
        session,
        action="account.login_start",
        account_id=account.id,
        target_type="tg_account",
        target_id=str(account.id),
        detail={"phone_masked": account.phone_masked, "delivery": delivery},
    )
    await _publish_account(worker, account)
    logger.info(
        "已发送登录验证码",
        extra={"worker_id": worker.worker_id, "account_id": str(account.id), "task_id": str(task.id), "delivery": delivery},
    )
    return {"step": STEP_CODE, "phone_masked": account.phone_masked, "delivery": delivery}


async def login_code(session: Any, *, task: Task, account: TgAccount, worker: Any) -> dict:
    """第二步：提交验证码；开了两步验证就转 `login_password`。"""
    payload = dict(task.payload or {})
    code = str(payload.get("code") or "").strip()
    if not code:
        raise TaskFailure("登录任务缺少验证码", retryable=False)
    state = await core_events.load_login_session(worker.redis, account.id)
    if not state:
        raise TaskFailure(
            f"登录会话已过期（{settings.login_session_ttl_seconds} 秒内没提交），请重新获取验证码",
            retryable=False,
        )

    client = await _client_from_state(state, account)
    try:
        await client.connect()
        try:
            user = await client.sign_in(
                phone=state.get("phone"),
                code=code,
                phone_code_hash=state.get("phone_code_hash"),
            )
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, SessionPasswordNeededError):
                state["step"] = STEP_PASSWORD
                await core_events.save_login_session(
                    worker.redis, account.id, state, ttl=settings.login_session_ttl_seconds
                )
                account.status = AccountStatus.needs_code
                account.status_reason = "验证码已通过，等待两步验证密码"
                account.last_error = ""
                account.last_checked_at = _now()
                await session.flush()
                logger.info(
                    "该号开启了两步验证，等待密码",
                    extra={"worker_id": worker.worker_id, "account_id": str(account.id), "task_id": str(task.id)},
                )
                return {"step": STEP_PASSWORD}
            retryable = task.attempts < 2  # 验证码错允许重试一次，不无限重试
            if isinstance(exc, PhoneCodeExpiredError):
                await core_events.clear_login_session(worker.redis, account.id)
                retryable = False
            raise _failure(account, exc, prefix="提交验证码失败", retryable=retryable) from exc
        return await finalize(
            session, client=client, account=account, worker=worker, task=task,
            action="account.login_code", user=user,
        )
    finally:
        await safe_disconnect(client)


async def login_password(session: Any, *, task: Task, account: TgAccount, worker: Any) -> dict:
    """第三步：提交两步验证密码并落会话。"""
    payload = dict(task.payload or {})
    password = str(payload.get("password") or "")
    if not password:
        raise TaskFailure("登录任务缺少两步验证密码", retryable=False)
    state = await core_events.load_login_session(worker.redis, account.id)
    if not state:
        raise TaskFailure("登录会话已过期，请重新获取验证码", retryable=False)
    if state.get("step") != STEP_PASSWORD:
        raise TaskFailure("当前登录还没有走到两步验证，请先提交验证码", retryable=False)

    client = await _client_from_state(state, account)
    try:
        await client.connect()
        try:
            user = await client.sign_in(password=password)
        except Exception as exc:  # noqa: BLE001
            retryable = task.attempts < 2  # 密码错允许重试一次
            raise _failure(account, exc, prefix="提交两步验证密码失败", retryable=retryable) from exc
        return await finalize(
            session, client=client, account=account, worker=worker, task=task,
            action="account.login_password", user=user,
        )
    finally:
        await safe_disconnect(client)


async def finalize(
    session: Any,
    *,
    client: TelegramClient,
    account: TgAccount,
    worker: Any,
    task: Task,
    action: str,
    user: Any = None,
) -> dict:
    """登录成功收尾：加密存会话、状态转正常、回填身份、清 Redis 临时态、写审计。"""
    me = user if user is not None else await client.get_me()
    session_string = client.session.save()
    if not session_string:
        raise TaskFailure("登录成功但会话串为空，请重试", retryable=True, requeue_after=5)
    await persist_identity(
        session, account, me, session_string=session_string, reset_authorized_at=True
    )
    await core_events.clear_login_session(worker.redis, account.id)
    await audit_core.write_audit(
        session,
        action=action,
        account_id=account.id,
        target_type="tg_account",
        target_id=str(account.id),
        detail={
            "phone_masked": account.phone_masked,
            "tg_user_id": account.tg_user_id,
            "username": account.username,
        },
    )
    await _publish_account(worker, account)
    # 登录成功后自动补一条「同步会话」任务：规划的第一步就是登录后拉出已有群和私信。
    # 用登录任务 id 做去重键，重试同一次登录不会重复入队；这条号此刻正被本 Worker 持有租约。
    await enqueue_task(
        session,
        type=TaskType.sync_dialogs,
        account_id=account.id,
        payload={"reason": "login_finalize"},
        priority=60,
        dedupe_key=f"login-sync:{account.id}:{task.id}",
    )
    logger.info(
        "用户号登录完成",
        extra={
            "worker_id": worker.worker_id,
            "account_id": str(account.id),
            "task_id": str(task.id),
            "tg_user_id": account.tg_user_id,
            "username": account.username,
        },
    )
    return {
        "step": STEP_DONE,
        "tg_user_id": account.tg_user_id,
        "username": account.username,
        "display_name": account.display_name,
    }


__all__ = [
    "STEP_CODE",
    "STEP_DONE",
    "STEP_PASSWORD",
    "build_login_client",
    "delivery_label",
    "finalize",
    "login_code",
    "login_password",
    "login_start",
    "safe_disconnect",
]
