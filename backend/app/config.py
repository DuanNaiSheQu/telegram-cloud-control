"""全局配置。所有可变项走环境变量，密钥不进镜像。"""

from __future__ import annotations

import base64
import hashlib
import os
import socket
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- 基础 ----------
    app_name: str = "Telegram 云控"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    component: str = "api"

    # ---------- 数据库 / Redis ----------
    database_url: str = "postgresql+asyncpg://cloudctl:cloudctl@localhost:5432/cloudctl"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    # ---------- 安全 ----------
    secret_key: str = "dev-insecure-secret-change-me"
    # Fernet key（44 字符 urlsafe base64）。为空时由 secret_key 派生，仅限开发环境。
    session_encryption_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""

    # ---------- Telegram ----------
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_device_model: str = "Cloud Control"
    telegram_system_version: str = "Linux"
    telegram_app_version: str = "1.0"
    login_session_ttl_seconds: int = 900

    # ---------- 租约 / 任务 ----------
    worker_id: str = ""
    lease_ttl_seconds: int = 30
    lease_renew_seconds: int = 10
    accounts_per_replica: int = 100
    task_batch: int = 10
    task_poll_interval: float = 2.0
    task_max_attempts: int = 5
    task_retry_base_seconds: int = 10
    task_retry_max_seconds: int = 600
    worker_metrics_port: int = 9101
    api_metrics_port: int = 9100
    account_reconnect_backoff_seconds: int = 15
    account_reconnect_backoff_max_seconds: int = 300

    # ---------- API / Bot ----------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Telegram 回调用，必须是公网可达地址
    public_base_url: str = "http://localhost:8000"
    webhook_secret: str = "change-me-webhook-secret"
    cors_origins: str = "*"
    bot_task_poll_interval: float = 1.0

    # ---------- AI ----------
    ai_enabled: bool = False
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: int = 30
    ai_max_history: int = 20

    # ---------- 转发 ----------
    relay_include_source_header: bool = True

    # ---------- 属性 ----------
    @property
    def cors_origin_list(self) -> List[str]:
        raw = (self.cors_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def fernet_key(self) -> bytes:
        """会话 / Bot Token 的对称加密密钥。"""
        if self.session_encryption_key:
            key = self.session_encryption_key.encode()
            try:
                base64.urlsafe_b64decode(key)
                if len(base64.urlsafe_b64decode(key)) == 32:
                    return key
            except Exception:  # noqa: BLE001 - 非法 key 走派生逻辑
                pass
            digest = hashlib.sha256(self.session_encryption_key.encode()).digest()
            return base64.urlsafe_b64encode(digest)
        digest = hashlib.sha256(self.secret_key.encode()).digest()
        return base64.urlsafe_b64encode(digest)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    def resolve_worker_id(self) -> str:
        if self.worker_id:
            return self.worker_id
        return f"{socket.gethostname()}-{os.getpid()}"

    def webhook_url(self, bot_id: str) -> str:
        base = self.public_base_url.rstrip("/")
        return f"{base}/api/webhook/{bot_id}/{self.webhook_secret}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
