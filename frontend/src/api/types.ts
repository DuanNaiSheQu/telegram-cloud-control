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
  /** 服务端排序字段（非法字段后端回 400） */
  sort?: string;
  order?: SortOrder;
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

export type ProxyUpdate = Partial<ProxyCreate>;

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
  sort?: string;
  order?: SortOrder;
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
  | 'bulk_pm'
  | 'group_broadcast'
  | 'material_send'
  | 'join_group'
  | 'leave_group'
  | 'force_add_member'
  | 'storm_chat'
  | 'persona_chat'
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
  sort?: string;
  order?: SortOrder;
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

export type RelayRouteUpdate = Partial<RelayRouteCreate>;

export interface RelayLinkOut {
  id: UUID;
  route_id?: UUID | null;
  message_id: UUID;
  bot_id: UUID;
  staff_chat_id: number;
  staff_message_id: number;
  created_at?: ISODateTime | null;
  // ---- 以下由路由回填，用于「已转发记录」列表与详情抽屉 ----
  /** 原消息正文（截断 500 字） */
  origin_body?: string | null;
  origin_sender_name?: string | null;
  origin_dialog_title?: string | null;
  /** 原会话 id：详情抽屉「跳原会话」深链 /dialogs?dialog_id= 用 */
  origin_dialog_id?: UUID | null;
  /** 脱敏手机号；Bot 会话为 null */
  account_label?: string | null;
  origin_created_at?: ISODateTime | null;
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
  bot_id?: UUID | null;
  /** ISO8601（可带时区，不带按 UTC）；作用在 created_at 上，闭区间；from > to → 400 */
  from?: string;
  to?: string;
  page?: number;
  page_size?: number;
  sort?: string;
  order?: SortOrder;
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

/** 服务端会推的业务事件（pong 在客户端内部消化，不派发给页面） */
export type WsServerEvent = WsAccountEvent | WsMessageEvent | WsTaskEvent | WsHelloEvent;

/** 原始帧：业务事件 + pong */
export type WsRawEvent = WsServerEvent | WsPongEvent;

export type WsStatus = 'connecting' | 'open' | 'closed';

// ---------------------------------------------------------------- 通用

export interface Paged<T> {
  items: T[];
  total: number;
  page?: number;
  page_size?: number;
}

// ================================================================
// 新增端点（与 docs/API_CONTRACT.md 待补章节对齐；
// 形状由后端负责人 api-completeness 于 2026-09-28 确认）
// ================================================================

/** 列表接口统一排序方向；null = 用后端默认排序 */
export type SortOrder = 'asc' | 'desc' | null;

// ---------------------------------------------------------------- 批量账号操作

/** 批量动作（都是「对已有的号做一次已有操作」，不含批量发送/群发/加群） */
export type BulkAction =
  | 'check'
  | 'sync-dialogs'
  | 'assign'
  | 'group'
  | 'proxy'
  | 'status'
  | 'disable'
  | 'enable'
  | 'release-lease';

/**
 * 响应体 `action` 的取值：比请求多一个 `unassign`
 * （请求是 `assign` + `mode='unassign'`，后端回填短名时归一化成 unassign）。
 * 页面做「动作 → 中文名」映射表时按 BulkAction 写即可，把 unassign 当 assign 的取消分支处理。
 */
export type BulkActionName = BulkAction | 'unassign';

/**
 * 批量请求体。
 * scope：`selected`（用 account_ids）/ `all` / `group:<uuid>`；
 * operator 传 all 时后端自动收敛为自己的号；assign 仅 admin 可用。
 */
export interface BulkAccountRequest {
  account_ids?: UUID[] | null;
  scope?: 'selected' | 'all' | `group:${string}`;
  /** 本次最多处理多少个号，1..500，默认 200；超出只处理前 N 个并回 truncated=true */
  limit?: number;
  /** bulk/assign（必填 user_id；仅 admin） */
  user_id?: UUID;
  mode?: 'assign' | 'unassign';
  /** bulk/group：null = 移出分组 */
  group_id?: UUID | null;
  /** bulk/proxy：null = 改直连 */
  proxy_id?: UUID | null;
  /** bulk/status */
  enabled?: boolean;
}

export interface BulkItemResult {
  account_id: UUID;
  /** 脱敏手机号 */
  account_label: string;
  ok: boolean;
  message: string;
  task_id?: UUID | null;
  /** 仅 bulk/check 返回，与单号检测同口径 */
  status?: AccountStatus | null;
  status_label?: string | null;
  reachable?: boolean | null;
}

export interface BulkResultOut {
  ok: boolean;
  /** 动作短名（账号批量操作） */
  action: BulkActionName | string;
  requested: number;
  succeeded: number;
  failed: number;
  skipped: number;
  /** true 表示命中上限被截断，页面要提示用户缩小范围 */
  truncated: boolean;
  message: string;
  task_ids: UUID[];
  items: BulkItemResult[];
}

// ---------------------------------------------------------------- 账号详情概览

export interface AccountLeaseOut {
  worker_id?: string | null;
  lease_until?: ISODateTime | null;
  last_heartbeat?: ISODateTime | null;
  active: boolean;
}

export interface AccountDialogStats {
  total: number;
  group: number;
  private: number;
  unread: number;
}

export interface AccountTaskStats {
  pending: number;
  running: number;
  failed: number;
  completed: number;
  pending_confirmation: number;
  cancelled: number;
}

/** GET /api/accounts/{id}/overview：详情抽屉一次拿全 */
export interface AccountOverviewOut {
  account: AccountOut;
  group?: GroupOut | null;
  proxy?: ProxyOut | null;
  lease?: AccountLeaseOut | null;
  dialog_stats: AccountDialogStats;
  task_stats: AccountTaskStats;
  recent_dialogs: DialogOut[];
  recent_messages: MessageOut[];
  recent_tasks: TaskOut[];
  recent_audit: AuditOut[];
  generated_at?: ISODateTime | null;
}

// ---------------------------------------------------------------- 指标趋势

export type MetricsWindow = '24h' | '7d' | '30d';

export interface MetricsTrendPoint {
  t: ISODateTime;
  v: number;
}

export interface MetricsTrendSeries {
  /** online_accounts / abnormal_accounts / tasks_succeeded / tasks_failed */
  key: string;
  label: string;
  unit: string;
  points: MetricsTrendPoint[];
}

/** 扁平版：给表格视图 */
export interface MetricsTrendBucket {
  bucket: ISODateTime;
  online_accounts: number;
  abnormal_accounts: number;
  tasks_succeeded: number;
  tasks_failed: number;
}

export interface MetricsTrendsOut {
  window: MetricsWindow;
  range: MetricsWindow;
  granularity: 'hour' | 'day';
  from: ISODateTime;
  to: ISODateTime;
  /** null = 后端还没开始采样，此时 series[].points 为空数组 */
  latest_sample_at?: ISODateTime | null;
  generated_at?: ISODateTime | null;
  series: MetricsTrendSeries[];
  points: MetricsTrendBucket[];
}

// ---------------------------------------------------------------- 通知

export type NotificationKind = 'task_failed' | 'worker_lost' | 'account_abnormal' | 'backup_failed';
export type NotificationLevel = 'info' | 'warning' | 'error' | 'success';

export interface NotificationOut {
  id: UUID;
  kind: NotificationKind | string;
  kind_label: string;
  level: NotificationLevel;
  title: string;
  body: string;
  account_id?: UUID | null;
  account_label?: string | null;
  bot_id?: UUID | null;
  task_id?: UUID | null;
  worker_id?: string | null;
  /**
   * 前端可直接跳转的站内路径（后端给，不要在前端拼）：
   * task_failed → /tasks?status=failed；worker_lost / backup_failed → /；
   * account_abnormal → /accounts/<account_id>
   */
  link: string;
  /** 结构化补充信息（任务类型、错误、尝试次数等），列表可不展示 */
  detail?: Record<string, unknown> | null;
  read: boolean;
  read_at?: ISODateTime | null;
  created_at?: ISODateTime | null;
}

export interface NotificationListQuery {
  unread_only?: boolean;
  kind?: NotificationKind | '';
  level?: NotificationLevel | '';
  page?: number;
  page_size?: number;
  sort?: string;
  order?: SortOrder;
}

export interface NotificationListResponse {
  items: NotificationOut[];
  total: number;
  unread: number;
  page: number;
  page_size: number;
  counts_by_kind: Partial<Record<NotificationKind, number>>;
}

// ---------------------------------------------------------------- 消息检索 / 导出

export interface MessageListQuery {
  /** 正文关键词 */
  q?: string;
  channel?: DialogChannel | '';
  kind?: DialogKind | '';
  account_id?: UUID | null;
  dialog_id?: UUID | null;
  direction?: MessageDirection | '';
  status?: MessageStatus | '';
  page?: number;
  page_size?: number;
  sort?: string;
  order?: SortOrder;
}

export type MessageSearchResponse = Paged<MessageOut>;

/** 可导出的资源（服务端流式 CSV） */
export type ExportResource = 'accounts' | 'dialogs' | 'messages' | 'tasks' | 'audit';

export interface ExportResult {
  blob: Blob;
  filename: string;
  /** X-Export-Total：命中行数（后端给不出时为 null） */
  total: number | null;
  /** X-Export-Truncated：超过 5 万行被截断 */
  truncated: boolean;
}

// ---------------------------------------------------------------- 任务批量重试

/** POST /api/tasks/bulk/retry：队列运维动作（不是批量发送），最多 200 条，逐条给结果 */
export interface TaskBulkRetryRequest {
  task_ids: UUID[];
}

export interface TaskBulkRetryItem {
  task_id: UUID;
  ok: boolean;
  /** 失败原因中文：任务不存在 / 当前状态「completed」不能重试 / 账号未分配给你 */
  message: string;
}

export interface TaskBulkRetryResponse {
  ok: boolean;
  requested: number;
  succeeded: number;
  failed: number;
  results: TaskBulkRetryItem[];
}

// ---------------------------------------------------------------- 转发测试

/** POST /api/relays/test（仅 admin）：保存规则前先试通，只发一条，不碰用户号 */
export interface RelayTestRequest {
  bot_id: UUID;
  chat_id: number;
  /** 不传用默认文案，最长 4096 */
  text?: string;
}

export interface RelayTestResponse {
  ok: boolean;
  message: string;
  detail: string;
  staff_message_id?: number | null;
}

// ================================================================
// 营销中心（批量私信 / 群发 / 素材 / 加群退群 / 强拉 / 改资料 / 吵群 / 拟人）
// ================================================================

export interface CampaignScopeRequest {
  account_ids?: UUID[] | null;
  scope?: 'selected' | 'all' | `group:${string}`;
  limit?: number;
}

export interface BulkPmRequest extends CampaignScopeRequest {
  targets: string[];
  text?: string | null;
  texts?: string[] | null;
  naturalize?: boolean;
  min_interval?: number;
  max_interval?: number;
}

export interface GroupBroadcastRequest extends CampaignScopeRequest {
  target_group: string;
  text?: string | null;
  texts?: string[] | null;
  naturalize?: boolean;
}

export interface MaterialSendRequest extends CampaignScopeRequest {
  material_id: UUID;
  target_group?: string | null;
  targets?: string[] | null;
  min_interval?: number;
  max_interval?: number;
}

export interface JoinGroupRequest extends CampaignScopeRequest {
  target: string;
}

export interface LeaveGroupRequest extends CampaignScopeRequest {
  target: string;
  delete_history?: boolean;
}

export interface ForceAddRequest extends CampaignScopeRequest {
  group: string;
  members: string[];
}

export interface ProfileFields {
  first_name?: string | null;
  last_name?: string | null;
  bio?: string | null;
  username?: string | null;
  photo_url?: string | null;
}

export interface ProfileBulkRequest extends CampaignScopeRequest {
  profile: ProfileFields;
  per_account?: Record<UUID, ProfileFields> | null;
}

export interface StormRequest extends CampaignScopeRequest {
  dialog_id?: UUID | null;
  group?: string | null;
  rounds?: number;
  min_interval?: number;
  max_interval?: number;
  texts: string[];
  reply_probability?: number;
}

export interface PersonaRequest extends CampaignScopeRequest {
  dialog_id?: UUID | null;
  group?: string | null;
  persona: string;
  topic?: string | null;
  use_ai?: boolean;
  texts?: string[] | null;
  rounds?: number;
  min_interval?: number;
  max_interval?: number;
}

export type MaterialKind = 'text' | 'photo' | 'video' | 'document';

export interface MaterialOut {
  id: UUID;
  name: string;
  kind: MaterialKind;
  kind_label: string;
  text: string;
  file_name?: string | null;
  original_name?: string | null;
  size_bytes: number;
  mime_type?: string | null;
  created_by?: UUID | null;
  created_at?: ISODateTime | null;
}

export interface MaterialListResponse {
  items: MaterialOut[];
  total: number;
  page: number;
  page_size: number;
}

export interface CampaignBatchItem {
  account_id?: UUID | null;
  account_label: string;
  task_id: UUID;
  type: string;
  type_label: string;
  status: TaskStatus;
  status_label: string;
  attempts: number;
  error: string;
  started_at?: ISODateTime | null;
  completed_at?: ISODateTime | null;
}

export interface CampaignBatchOut {
  batch_id: UUID;
  created_at?: ISODateTime | null;
  created_by_name?: string | null;
  total: number;
  counts: Record<string, number>;
  items: CampaignBatchItem[];
}

export interface CampaignBatchListResponse {
  items: CampaignBatchOut[];
  total: number;
  page: number;
  page_size: number;
}
