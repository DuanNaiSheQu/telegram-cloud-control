/**
 * 下拉选项与兜底中文标签。
 * 优先使用后端返回的 *_label 字段；这里的映射用于筛选下拉和后端没回 label 的场景，
 * 取值与 backend/app/models/enums.py、backend/app/core/audit.py 保持一致。
 */
import type {
  AccountStatus,
  CurrentTask,
  DialogChannel,
  DialogKind,
  MessageStatus,
  NotificationLevel,
  ProxyScheme,
  RelayTargetKind,
  TaskStatus,
  TaskType,
  UserRole,
} from './api/types';

export interface SelectOption<T extends string = string> {
  value: T;
  label: string;
}

export const ACCOUNT_STATUS_LABELS: Record<AccountStatus, string> = {
  pending: '待登录',
  healthy: '正常',
  needs_code: '要验证码',
  frozen: '冻结',
  invalid: '失效',
  dead: '永久双向',
  disabled: '停用',
};

export const ACCOUNT_STATUS_COLORS: Record<AccountStatus, string> = {
  pending: 'gold',
  healthy: 'green',
  needs_code: 'orange',
  frozen: 'red',
  invalid: 'volcano',
  dead: 'default',
  disabled: 'default',
};

export const ACCOUNT_STATUS_OPTIONS: SelectOption<AccountStatus>[] = (
  Object.keys(ACCOUNT_STATUS_LABELS) as AccountStatus[]
).map((value) => ({ value, label: ACCOUNT_STATUS_LABELS[value] }));

export const CURRENT_TASK_LABELS: Record<CurrentTask, string> = {
  idle: '空闲',
  syncing: '同步会话',
  awaiting_confirm: '等待确认发送',
  relaying: '转发到员工群',
};

export const CURRENT_TASK_OPTIONS: SelectOption<CurrentTask>[] = (
  Object.keys(CURRENT_TASK_LABELS) as CurrentTask[]
).map((value) => ({ value, label: CURRENT_TASK_LABELS[value] }));

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  pending: '待执行',
  pending_confirmation: '等待确认',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

export const TASK_STATUS_COLORS: Record<TaskStatus, string> = {
  pending: 'blue',
  pending_confirmation: 'gold',
  running: 'processing',
  completed: 'green',
  failed: 'red',
  cancelled: 'default',
};

export const TASK_STATUS_OPTIONS: SelectOption<TaskStatus>[] = (
  Object.keys(TASK_STATUS_LABELS) as TaskStatus[]
).map((value) => ({ value, label: TASK_STATUS_LABELS[value] }));

export const TASK_TYPE_LABELS: Record<TaskType, string> = {
  sync_dialogs: '同步会话',
  sync_messages: '拉取历史消息',
  send_message: '单条发送',
  account_check: '账号检测',
  update_profile: '修改资料',
  login_start: '登录-发送验证码',
  login_code: '登录-提交验证码',
  login_password: '登录-提交两步密码',
  relay_to_staff: '转发到员工群',
  bot_reply: 'Bot 自动回复',
  reply_to_origin: '回复送回原会话',
};

export const TASK_TYPE_OPTIONS: SelectOption<TaskType>[] = (
  Object.keys(TASK_TYPE_LABELS) as TaskType[]
).map((value) => ({ value, label: TASK_TYPE_LABELS[value] }));

/** 消息状态（与 backend/app/models/enums.py 对齐；后端有 status_label 时优先用后端的） */
export const MESSAGE_STATUS_LABELS: Record<MessageStatus, string> = {
  received: '已接收',
  pending: '待发送',
  sent: '已发送',
  failed: '发送失败',
};

export const MESSAGE_STATUS_OPTIONS: SelectOption<MessageStatus>[] = (
  Object.keys(MESSAGE_STATUS_LABELS) as MessageStatus[]
).map((value) => ({ value, label: MESSAGE_STATUS_LABELS[value] }));

export const DIALOG_CHANNEL_LABELS: Record<DialogChannel, string> = {
  user_account: '用户号',
  bot: 'Bot',
};

export const DIALOG_CHANNEL_OPTIONS: SelectOption<DialogChannel>[] = [
  { value: 'user_account', label: '用户号' },
  { value: 'bot', label: 'Bot' },
];

export const DIALOG_KIND_LABELS: Record<DialogKind, string> = {
  private: '私信',
  group: '群聊',
};

export const DIALOG_KIND_OPTIONS: SelectOption<DialogKind>[] = [
  { value: 'private', label: '私信' },
  { value: 'group', label: '群聊' },
];

export const PROXY_SCHEME_OPTIONS: SelectOption<ProxyScheme>[] = [
  { value: 'socks5', label: 'SOCKS5' },
  { value: 'socks4', label: 'SOCKS4' },
  { value: 'http', label: 'HTTP' },
  { value: 'https', label: 'HTTPS' },
  { value: 'mtproxy', label: 'MTProto' },
];

export const RELAY_TARGET_KIND_OPTIONS: SelectOption<RelayTargetKind>[] = [
  { value: 'group', label: '群聊' },
  { value: 'private', label: '私聊' },
];

export const USER_ROLE_LABELS: Record<UserRole, string> = {
  admin: '管理员',
  operator: '操作员',
};

export const USER_ROLE_OPTIONS: SelectOption<UserRole>[] = [
  { value: 'admin', label: '管理员' },
  { value: 'operator', label: '操作员' },
];

/** backend/app/core/audit.py::ACTION_LABELS */
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  login: '登录控制台',
  'account.create': '新建账号',
  'account.login_start': '发起登录',
  'account.login_code': '提交验证码',
  'account.login_password': '提交两步密码',
  'account.check': '账号检测',
  'account.update': '修改账号',
  'account.disable': '停用账号',
  'account.enable': '启用账号',
  'account.release_lease': '清除租约',
  'account.profile_update': '修改本号资料',
  'account.assign': '分配账号',
  'account.unassign': '取消分配',
  'group.create': '新建分组',
  'group.update': '修改分组',
  'group.delete': '删除分组',
  'proxy.create': '新建代理',
  'proxy.update': '修改代理',
  'proxy.delete': '删除代理',
  'dialog.sync': '同步会话',
  'message.send_request': '发起发送',
  'message.send': '确认发送',
  'message.receive': '接收到消息',
  'draft.create': '生成 AI 草稿',
  'draft.discard': '丢弃草稿',
  'task.retry': '重试任务',
  'task.cancel': '取消任务',
  'relay.create': '新建转发规则',
  'relay.update': '修改转发规则',
  'relay.delete': '删除转发规则',
  'relay.forward': '转发到员工群',
  'relay.reply': '员工群回复送回',
  'bot.create': '新建 Bot',
  'bot.update': '修改 Bot',
  'bot.delete': '删除 Bot',
  'bot.webhook_set': '注册 Webhook',
  'bot.auto_reply': 'Bot 自动回复',
  'user.create': '新建员工',
  'user.update': '修改员工',
  'user.delete': '删除员工',
};

export const AUDIT_ACTION_OPTIONS: SelectOption[] = Object.entries(AUDIT_ACTION_LABELS).map(
  ([value, label]) => ({ value, label: `${label}（${value}）` }),
);

export function optionLabel(
  map: Record<string, string>,
  value?: string | null,
  fallback = '—',
): string {
  if (!value) return fallback;
  return map[value] ?? value;
}

/** 账号「异常」口径：非 healthy 且非 pending（待登录单独算，不算异常） */
export function isAbnormalStatus(status: AccountStatus): boolean {
  return status !== 'healthy' && status !== 'pending';
}

// ---------------------------------------------------------------- 语义色调
// 组件里不要写死颜色：状态 → Tone → CSS 变量（--tg-color-*），换皮只改 tokens.ts。

export type Tone = 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'neutral';

/** 账号 7 态 → 语义色调（配色细节在 tokens.ts 的 color.account） */
export const ACCOUNT_STATUS_TONE: Record<AccountStatus, Tone> = {
  healthy: 'success',
  pending: 'warning',
  needs_code: 'warning',
  frozen: 'danger',
  invalid: 'danger',
  dead: 'neutral',
  disabled: 'neutral',
};

export const TASK_STATUS_TONE: Record<TaskStatus, Tone> = {
  pending: 'info',
  pending_confirmation: 'warning',
  running: 'primary',
  completed: 'success',
  failed: 'danger',
  cancelled: 'neutral',
};

export const MESSAGE_STATUS_TONE: Record<MessageStatus, Tone> = {
  received: 'neutral',
  pending: 'warning',
  sent: 'success',
  failed: 'danger',
};

export const NOTIFICATION_LEVEL_TONE: Record<NotificationLevel, Tone> = {
  info: 'info',
  success: 'success',
  warning: 'warning',
  error: 'danger',
};

/** 账号状态分组：用于「异常」筛选与看板口径（与后端 abnormal 一致） */
export const ABNORMAL_STATUSES: AccountStatus[] = ['needs_code', 'frozen', 'invalid', 'dead', 'disabled'];

/** 任务状态分组：失败/待处理，任务中心与看板共用 */
export const FAILED_TASK_STATUSES: TaskStatus[] = ['failed'];
export const ACTIVE_TASK_STATUSES: TaskStatus[] = ['pending', 'pending_confirmation', 'running'];
