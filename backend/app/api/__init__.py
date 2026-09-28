"""HTTP / WebSocket / 官方 Bot Webhook 层。

这一层只做协议转换与权限判断：查库、写任务、推 Redis；真正的业务规则在
`app/core`（任务 / 租约 / 事件 / 审计）和 `app/services`（入库 / 转发 / AI）里，
API 重启不应该影响 Worker 上已经连着的号。
"""

from __future__ import annotations

__all__ = ["create_app"]


def __getattr__(name: str):
    """延迟导入 create_app：避免 `import app.api` 时就把整棵路由树拉起来（循环导入风险）。"""
    if name == "create_app":
        from app.api.main import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
