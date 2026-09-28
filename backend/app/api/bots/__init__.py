"""Bot 包：进程内运行时注册表 + Bot 任务轮询 + Telegram Webhook。

Bot 收发不进 Worker（规划：Bot 收发不进 Worker，Webhook 无状态，不跟某台 Worker 绑定）。
"""

from __future__ import annotations

from app.api.bots import manager

__all__ = ["manager"]
