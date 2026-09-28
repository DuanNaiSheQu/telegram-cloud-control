"""口令哈希、JWT、会话与 Bot Token 的对称加密、脱敏工具。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.fernet_key)
    return _fernet


# ---------------- 口令 ----------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------- JWT ----------------

def create_access_token(subject: str, extra: Optional[Dict[str, Any]] = None) -> str:
    now = datetime.now(tz=timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None


# ---------------- 对称加密（会话串 / Bot Token） ----------------

def encrypt_secret(plaintext: str) -> str:
    if plaintext is None:
        raise ValueError("plaintext is required")
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:  # 密钥轮换或数据损坏
        raise ValueError("无法解密：请检查 SESSION_ENCRYPTION_KEY 是否与写入时一致") from exc


# ---------------- 脱敏 ----------------

def mask_phone(phone: Optional[str]) -> str:
    """138****8888 形式。未知则返回占位。"""
    if not phone:
        return "未知"
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 7:
        return phone[:2] + "***"
    return f"{digits[:3]}****{digits[-4:]}"


def mask_token(token: Optional[str]) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return "****"
    return f"{token[:6]}...{token[-4:]}"


def new_webhook_secret() -> str:
    return secrets.token_urlsafe(24)


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")
