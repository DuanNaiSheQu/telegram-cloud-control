/**
 * 与 docs/API_CONTRACT.md（v1）逐字对齐的前端类型。
 * 字段名保持 snake_case；所有时间戳是带时区的 ISO8601；所有 ID 是 UUID 字符串。
 */

export type UUID = string;
export type ISODateTime = string;

/** 后端统一错误体 */
export interface ApiErrorBody {
  detail?: string | { msg?: string; loc?: (string | number)[] }[] | null;
}

// ---------------------------------------------------------------- 鉴权

export type UserRole = 'admin' | 'operator';

export interface UserOut {
  id: UUID;
  username: string;
  display_name: string;
  role: UserRole;
  is_active: boolean;
  last_login_at?: ISODateTime | null;
  created_at?: ISODateTime | null;
  account_count: number;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserOut;
}

export interface OkResponse {
  ok: boolean;
  message: string;
  detail?: Record<string, unknown> | null;
}

export interface TaskActionResponse {
  ok: boolean;
  task?: TaskOut | null;
  message: string;
}

// ---------------------------------------------------------------- 账号

export type AccountStatus =
  | 'pending'
  | 'healthy'
  | 'needs_code'
  | 'frozen'
  | 'invalid'
  | 'dead'
  | 'disabled';

export type CurrentTask = 'idle' | 'syncing' | 'awaiting_confirm' | 'relaying';

export interface AccountOut {
  id: UUID;
  phone_masked: string;
  username?: string | null;
  tg_user_id?: number | null;
  display_name: string;
  age_days?: number | null;
  group_count: number;
  group_id?: UUID | null;
  group_name?: string | null;
  proxy_id?: UUID | null;
  proxy_endpoint?: string | null;
  status: AccountStatus;
  status_label: string;
  status_reason: string;
  current_task: CurrentTask;
  current_task_label: string;
  last_heartbeat?: ISODateTime | null;
  last_checked_at?: ISODateTime | null;
  last_error: string;
  worker_id?: string | null;
  lease_until?: ISODateTime | null;
  remark: string;
  created_at?: ISODateTime | null;
}

export interface AccountSummary {
  total: number;
  healthy: number;
  abnormal: number;
  new_this_week: number;
  online: number;
  leased: number;
}

export interface AccountListResponse {
  items: AccountOut[];
  total: number;
  page: number;
  page_size: number;
  summary?: AccountSummary | null;
}

export interface AccountCreate {
  phone: string;
  group_id?: UUID | null;
  proxy_id?: UUID | null;
  remark?: string;
}

export interface AccountUpdate {
  group_id?: UUID | null;
  proxy_id?: UUID | null;
  remark?: string;
  display_name?: string;
  status?: AccountStatus;
}

export interface AccountListQuery {
  page?: number;
  page_size?: number;
  group_id?: UUID | null;
  status?: AccountStatus | '';
  current_task?: CurrentTask | '';
  phone?: string;
  keyword?: string;
}

// ---------------------------------------------------------------- 单号登录

export type LoginStep = 'code_required' | 'password_required' | 'done';

export interface LoginStepResponse {
  account_id: UUID;
  step: LoginStep;
  message: string;
  task_id?: UUID | null;
}

export interface LoginStartRequest {
  phone: string;
  group_id?: UUID | null;
  proxy_id?: UUID | null;
  /** 对已有账号「重新登录」时传 */
  account_id?: UUID | null;
}

// ---------------------------------------------------------------- 检测

export interface CheckRequest {
  account_ids?: UUID[] | null;
  /** selected | all | group:<group_id> */
  scope: string;
}

export interface CheckResultOut {
  account_id: UUID;
  phone_masked: string;
  reachable: boolean;
  status: AccountStatus;
  status_label: string;
  message: string;
  task_id?: UUID | null;
}

// ---------------------------------------------------------------- 分组 / 代理

export interface GroupOut {
  id: UUID;
  name: string;
  description: string;
  account_count: number;
  created_at?: ISODateTime | null;
}

export interface GroupCreate {
  name: string;
  description?: string;
}

export type ProxyScheme = 'socks5' | 'socks4' | 'http' | 'https' | 'mtproxy';

export interface ProxyOut {
  id: UUID;
  name: string;
  scheme: string;
  host: string;
  port: number;
  endpoint: string;
  has_auth: boolean;
  enabled: boolean;
  remark: string;
  account_count: number;
  created_at?: ISODateTime | null;
}

export interface ProxyCreate {
  name: string;
  scheme: ProxyScheme;
  host: string;
  port: number;
  username?: string | null;
  password?: string | null;
  enabled?: boolean;
  remark?: string;
}

export interface ProxyUpdate extends Partial<ProxyCreate> {}

// ---------------------------------------------------------------- 员工 / 分配

export interface UserCreate {
  username: string;
  password: string;
  display_name?: string;
  role?: UserRole;
}

export interface UserUpdate {
  display_name?: string;
  role?: UserRole;
  is_active?: boolean;
  password?: string;
}

export interface AssignmentOut {
  user_id: UUID;
  username: string;
  display_name: string;
  account_ids: UUID[];
  account_count: number;
}

// ---------------------------------------------------------------- 会话 / 消息

export type DialogChannel = 'user_account' | 'bot';
export type DialogKind = 'private' | 'group';

export interface DialogOut {
  id: UUID;
  channel: DialogChannel;
  channel_label: string;
  kind: DialogKind;
  kind_label: string;
  account_id?: UUID | null;
  account_label?: string | null;
  bot_id?: UUID | null;
  bot_label?: string | null;
  tg_chat_id: number;
  title: string;
  username?: string | null;
  member_count?: number | null;
  peer_display: string;
  unread_count: number;
  is_pinned: boolean;
  last_message_at?: ISODateTime | null;
  last_message_preview: string;
}

export interface DialogListQuery {
  channel?: DialogChannel | '';
  kind?: DialogKind | '';
  account_id?: UUID | null;
  bot_id?: UUID | null;
  keyword?: string;
  only_unread?: boolean;
  page?: number;
  page_size?: number;
}

export interface DialogListResponse {
  items: DialogOut[];
  total: number;
  page: number;
  page_size: number;
}

export type MessageDirection = 'incoming' | 'outgoing';
export type MessageStatus = 'received' | 'pending' | 'sent' | 'failed';

export interface MessageOut {
  id: UUID;
  dialog_id: UUID;
  channel: DialogChannel;
  direction: MessageDirection;
  direction_label: string;
  status: MessageStatus;
  status_label: string;
  body: string;
  tg_message_id?: number | null;
  sender_tg_id?: number | null;
  sender_name: string;
  has_media: boolean;
  media_type?: string | null;
  created_by?: UUID | null;
  created_at?: ISODateTime | null;
}

export interface MessageListResponse {
  items: MessageOut[];
  total: number;
  dialog: DialogOut;
  has_more: boolean;
}

export interface SendMessageRequest {
  dialog_id: UUID;
  text: string;
  draft_id?: UUID | null;
}

export interface SendMessageResponse {
  ok: boolean;
  message: MessageOut;
  task_id?: UUID | null;
  status: MessageStatus;
  detail: string;
}

export interface DraftOut {
  id: UUID;
  dialog_id: UUID;
  body: string;
  status: string;
  model: string;
  created_at?: ISODateTime | null;
}

// ---------------------------------------------------------------- 任务

export type TaskType =
  | 'sync_dialogs'
  | 'sync_messages'
  | 'send_message'
  | 'account_check'
  | 'update_profile'
  | 'login_start'
  | 'login_code'
  | 'login_password'
  | 'relay_to_staff'
  | 'bot_reply'
  | 'reply_to_origin';

export type TaskStatus =
  | 'pending'
  | 'pending_confirmation'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface TaskOut {
  id: UUID;
  type: TaskType;
  type_label: string;
  status: TaskStatus;
  status_label: string;
  account_id?: UUID | null;
  account_label?: string | null;
  bot_id?: UUID | null;
  bot_label?: string | null;
  dialog_id?: UUID | null;
  payload: Record<string, unknown>;
  result?: unknown;
  priority: number;
  attempts: number;
  max_attempts: number;
  error: string;
  worker_id?: string | null;
  created_by?: UUID | null;
  created_by_name?: string | null;
  next_run_at?: ISODateTime | null;
  started_at?: ISODateTime | null;
  completed_at?: ISODateTime | null;
  created_at?: ISODateTime | null;
}

export interface TaskListQuery {
  status?: TaskStatus | '';
  type?: TaskType | '';
  account_id?: UUID | null;
  bot_id?: UUID | null;
  only_failed?: boolean;
  page?: number;
  page_size?: number;
}

export interface TaskListResponse {
  items: TaskOut[];
  total: number;
  page: number;
  page_size: number;
  counts: Partial<Record<TaskStatus, number>>;
}

// ---------------------------------------------------------------- Bot / 转发

export type RelayTargetKind = 'group' | 'private';

export interface BotOut {
  id: UUID;
  name: string;
  bot_username?: string | null;
  bot_tg_id?: number | null;
  token_masked: string;
  webhook_enabled: boolean;
  webhook_url: string;
  webhook_set_at?: string | null;
  relay_enabled: boolean;
  relay_target_chat_id?: number | null;
  relay_target_kind: RelayTargetKind;
  auto_reply_enabled: boolean;
  persona_text: string;
  remark: string;
  created_at?: ISODateTime | null;
}

export interface BotCreate {
  name: string;
  token: string;
  relay_enabled?: boolean;
  relay_target_chat_id?: number | null;
  relay_target_kind?: RelayTargetKind;
  auto_reply_enabled?: boolean;
  persona_text?: string;
  remark?: string;
}

export interface BotUpdate extends Partial<Omit<BotCreate, 'token'>> {
  token?: string;
  webhook_enabled?: boolean;
}

export interface RelayRouteOut {
  id: UUID;
  name: string;
  bot_id: UUID;
  bot_name?: string | null;
  bot_username?: string | null;
  staff_chat_id: number;
  staff_chat_title: string;
  target_kind: RelayTargetKind;
  account_id?: UUID | null;
  account_label?: string | null;
  dialog_id?: UUID | null;
  dialog_title?: string | null;
  enabled: boolean;
  remark: string;
  relayed_count: number;
  created_at?: ISODateTime | null;
}

export interface RelayRouteCreate {
  name?: string;
  bot_id: UUID;
  staff_chat_id: number;
  staff_chat_title?: string;
  target_kind?: RelayTargetKind;
  account_id?: UUID | null;
  dialog_id?: UUID | null;
  enabled?: boolean;
  remark?: string;
}

export interface RelayRouteUpdate extends Partial<RelayRouteCreate> {}

export interface RelayLinkOut {
  id: UUID;
  route_id?: UUID | null;
  message_id: UUID;
  bot_id: UUID;
  staff_chat_id: number;
  staff_message_id: number;
  created_at?: ISODateTime | null;
}

// ---------------------------------------------------------------- 操作记录

export interface AuditOut {
  id: UUID;
  action: string;
  action_label: string;
  user_id?: UUID | null;
  user_name?: string | null;
  account_id?: UUID | null;
  account_label?: string | null;
  bot_id?: UUID | null;
  target_type: string;
  target_id: string;
  detail?: unknown;
  client_ip: string;
  created_at?: ISODateTime | null;
}

export interface AuditListQuery {
  action?: string;
  account_id?: UUID | null;
  user_id?: UUID | null;
  page?: number;
  page_size?: number;
}

export interface AuditListResponse {
  items: AuditOut[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------- 工作台

export interface WorkerStatus {
  worker_id: string;
  last_heartbeat?: ISODateTime | null;
  online_accounts: number;
  leased_accounts: number;
  stale: boolean;
  source: string;
}

export interface FailedTaskOut {
  id: UUID;
  type: string;
  type_label: string;
  account_id?: UUID | null;
  account_label?: string | null;
  error: string;
  attempts: number;
  max_attempts: number;
  created_at?: ISODateTime | null;
}

export interface DashboardOut {
  total_accounts: number;
  online_accounts: number;
  abnormal_accounts: number;
  leased_accounts: number;
  total_dialogs: number;
  unread_dialogs: number;
  total_bots: number;
  tasks_pending: number;
  tasks_running: number;
  tasks_failed: number;
  tasks_overdue: number;
  tasks_stuck: number;
  workers: WorkerStatus[];
  recent_failures: FailedTaskOut[];
  generated_at?: ISODateTime | null;
}

// ---------------------------------------------------------------- WebSocket

export type WsAccountEvent = {
  kind: 'account';
  account_id: UUID;
  status: AccountStatus;
  current_task: CurrentTask;
  last_heartbeat?: ISODateTime | null;
};

export type WsMessageEvent = {
  kind: 'message';
  dialog_id: UUID;
  message: MessageOut;
  dialog?: DialogOut | null;
};

export type WsTaskEvent = {
  kind: 'task';
  task_id: UUID;
  type: TaskType;
  ok: boolean;
  detail: string;
};

export type WsHelloEvent = { kind: 'hello'; dialogs: UUID[] };
export type WsPongEvent = { op: 'pong' };

export type WsServerEvent =
  | WsAccountEvent
  | WsMessageEvent
  | WsTaskEvent
  | WsHelloEvent
  | WsPongEvent;

export type WsStatus = 'connecting' | 'open' | 'closed';

// ---------------------------------------------------------------- 通用

export interface Paged<T> {
  items: T[];
  total: number;
  page?: number;
  page_size?: number;
}
