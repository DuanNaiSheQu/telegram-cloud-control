"""Worker 包：认领租约、维持 Telethon 长连接、执行用户号任务、暴露 Prometheus 指标。

入口是 `python -m app.worker.main`；Bot 收发不在这里，走 API 的 Webhook。
"""

from __future__ import annotations

__all__ = ["main"]
