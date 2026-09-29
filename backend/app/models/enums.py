"""业务枚举。值直接落库，改动需同步迁移与前端。"""

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    operator = "operator"


class AccountStatus(str, enum.Enum):
    """账号状态，和值班时要扫的四类对齐，另加登录前后的中间态。"""

    pending = "pending"        # 待登录：已建档，未拿到会话
    healthy = "healthy"        # 正常：租约有效、心跳在
    needs_code = "needs_code"  # 要验证码：会话存在但需重新验证
    frozen = "frozen"          # 冻结：被 Telegram 限制，不再替它发送
    invalid = "invalid"        # 失效：会话打不开
    dead = "dead"              # 永久双向：只留记录，不再认领
    disabled = "disabled"      # 人工停用：手动下线


#: 可被 Worker 认领的状态（dead 与 disabled 不再认领）
CLAIMABLE_STATUSES = (
    AccountStatus.pending.value,
    AccountStatus.healthy.value,
    AccountStatus.needs_code.value,
    AccountStatus.frozen.value,
    AccountStatus.invalid.value,
)

#: 允许替它执行发送的状态
SENDABLE_STATUSES = (AccountStatus.healthy.value,)

#: 展示用中文名
ACCOUNT_STATUS_LABELS = {
    "pending": "待登录",
    "healthy": "正常",
    "needs_code": "要验证码",
    "frozen": "冻结",
    "invalid": "失效",
    "dead": "永久双向",
    "disabled": "停用",
}


class CurrentTask(str, enum.Enum):
    """账号当前任务，页面直接显示。"""

    idle = "idle"                        # 空闲
    syncing = "syncing"                  # 同步会话
    awaiting_confirm = "awaiting_confirm"  # 等待确认发送
    relaying = "relaying"                # 转发到员工群


CURRENT_TASK_LABELS = {
    "idle": "空闲",
    "syncing": "同步会话",
    "awaiting_confirm": "等待确认发送",
    "relaying": "转发到员工群",
}


class DialogChannel(str, enum.Enum):
    user_account = "user_account"
    bot = "bot"


class DialogKind(str, enum.Enum):
    private = "private"
    group = "group"


class MessageDirection(str, enum.Enum):
    incoming = "incoming"
    outgoing = "outgoing"


class MessageStatus(str, enum.Enum):
    received = "received"
    pending = "pending"
    sent = "sent"
    failed = "failed"


class TaskType(str, enum.Enum):
    # 用户号（Worker 执行）
    sync_dialogs = "sync_dialogs"        # 同步会话列表
    sync_messages = "sync_messages"      # 拉某个会话的历史消息
    send_message = "send_message"        # 员工确认后发出
    account_check = "account_check"      # 单号检测
    update_profile = "update_profile"    # 改本号名称 / 头像
    login_start = "login_start"          # 发送验证码
    login_code = "login_code"            # 提交验证码
    login_password = "login_password"    # 提交两步验证密码
    # 批量运营（Worker 执行，每号一条任务，payload.batch_id 聚合）
    bulk_pm = "bulk_pm"                  # 批量私信：向目标逐个发消息
    group_broadcast = "group_broadcast"  # 群发：向指定群发消息
    material_send = "material_send"      # 素材群发：按素材库内容发送
    join_group = "join_group"            # 加群：邀请链接 / 公开群
    leave_group = "leave_group"          # 退群
    force_add_member = "force_add_member"  # 强拉进群：把成员拉进群（需管理员）
    storm_chat = "storm_chat"            # 吵群：按文本池和随机间隔连续发言
    persona_chat = "persona_chat"        # 拟人发言：按人设生成话术连续发言
    # 群情报（无感采集：只读，不发言）
    collect_group = "collect_group"      # 采集群档案（资料 + 成员数 + 邀请链接）
    collect_members = "collect_members"  # 采集群成员名单（分页拉取，带节流）
    collect_link = "collect_link"        # 按群链接采集：解析链接 → 可选入群 → 档案 + 成员
    # 官方机制：养号与限制参数同步
    sync_official = "sync_official"      # 同步服务端下发的官方限制参数（help.GetAppConfig）
    warmup_activity = "warmup_activity"  # 官方节奏养号：上线→翻会话→（可选）已读/打字→下线，不发消息
    appeal_spam = "appeal_spam"          # 模拟真人向 @SpamBot 申诉：/start → 看状态 → 点「这是误判」
    collect_messages = "collect_messages"  # 采集群内对话：按时间范围扫消息，把发言者落成成员档案
    # Bot（API 执行）
    relay_to_staff = "relay_to_staff"    # 转发到员工群
    bot_reply = "bot_reply"              # 官方 Bot 自动回复
    bot_broadcast = "bot_broadcast"      # Bot 群发/转发：用 Bot 把消息发到指定群（可转发某条来源消息）
    reply_to_origin = "reply_to_origin"  # 员工群回复送回原会话（Bot 侧）


class TaskStatus(str, enum.Enum):
    pending = "pending"
    pending_confirmation = "pending_confirmation"  # 等待员工确认
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


TASK_TYPE_LABELS = {
    "sync_dialogs": "同步会话",
    "sync_messages": "拉取历史消息",
    "send_message": "单条发送",
    "account_check": "账号检测",
    "update_profile": "修改资料",
    "login_start": "登录-发送验证码",
    "login_code": "登录-提交验证码",
    "login_password": "登录-提交两步密码",
    "bulk_pm": "批量私信",
    "group_broadcast": "群发",
    "material_send": "素材群发",
    "join_group": "加群",
    "leave_group": "退群",
    "force_add_member": "强拉进群",
    "storm_chat": "吵群",
    "persona_chat": "拟人发言",
    "collect_group": "采集群档案",
    "collect_members": "采集群成员",
    "collect_link": "按链接采集群员",
    "sync_official": "同步官方限制参数",
    "warmup_activity": "官方养号活动",
    "appeal_spam": "申诉解封",
    "collect_messages": "采集群内对话",
    "relay_to_staff": "转发到员工群",
    "bot_reply": "Bot 自动回复",
    "bot_broadcast": "Bot 群发/转发",
    "reply_to_origin": "回复送回原会话",
}

TASK_STATUS_LABELS = {
    "pending": "待执行",
    "pending_confirmation": "等待确认",
    "running": "执行中",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
}


class DraftStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    discarded = "discarded"


class RelayTargetKind(str, enum.Enum):
    group = "group"
    private = "private"
