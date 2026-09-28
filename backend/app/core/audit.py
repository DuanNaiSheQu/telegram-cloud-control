"""审计写入。所有会改状态的动作都要留一条。"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def write_audit(
    session: AsyncSession,
    *,
    action: str,
    user_id: Optional[uuid.UUID] = None,
    account_id: Optional[uuid.UUID] = None,
    bot_id: Optional[uuid.UUID] = None,
    target_type: str = "",
    target_id: str = "",
    detail: Optional[Any] = None,
    client_ip: str = "",
) -> AuditLog:
    log = AuditLog(
        action=action,
        user_id=user_id,
        account_id=account_id,
        bot_id=bot_id,
        target_type=target_type,
        target_id=str(target_id or ""),
        detail=detail,
        client_ip=client_ip,
    )
    session.add(log)
    await session.flush()
    return log


ACTION_LABELS = {
    "login": "登录控制台",
    "account.create": "新建账号",
    "account.login_start": "发起登录",
    "account.login_code": "提交验证码",
    "account.login_password": "提交两步密码",
    "account.check": "账号检测",
    "account.update": "修改账号",
    "account.disable": "停用账号",
    "account.enable": "启用账号",
    "account.release_lease": "清除租约",
    "account.profile_update": "修改本号资料",
    "account.assign": "分配账号",
    "account.unassign": "取消分配",
    "group.create": "新建分组",
    "group.update": "修改分组",
    "group.delete": "删除分组",
    "proxy.create": "新建代理",
    "proxy.update": "修改代理",
    "proxy.delete": "删除代理",
    "dialog.sync": "同步会话",
    "message.send_request": "发起发送",
    "message.send": "确认发送",
    "message.receive": "接收到消息",
    "draft.create": "生成 AI 草稿",
    "draft.discard": "丢弃草稿",
    "task.retry": "重试任务",
    "task.cancel": "取消任务",
    "relay.create": "新建转发规则",
    "relay.update": "修改转发规则",
    "relay.delete": "删除转发规则",
    "relay.forward": "转发到员工群",
    "relay.reply": "员工群回复送回",
    "bot.create": "新建 Bot",
    "bot.update": "修改 Bot",
    "bot.delete": "删除 Bot",
    "bot.webhook_set": "注册 Webhook",
    "bot.auto_reply": "Bot 自动回复",
    "user.create": "新建员工",
    "user.update": "修改员工",
    "user.delete": "删除员工",
}
