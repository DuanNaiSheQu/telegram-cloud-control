/**
 * 接口封装。路径与 docs/API_CONTRACT.md（v1）逐条对应。
 * 所有函数只做「拼路径 + 传参 + 解析」，不做业务判断。
 */
import { ApiError, api, type QueryValue, type RequestOptions } from './client';
import { buildQuery } from './client';
import type {
  AccountCreate,
  AccountListQuery,
  AccountListResponse,
  AccountOut,
  AccountOverviewOut,
  AccountSummary,
  AccountUpdate,
  AccountMatrixState,
  BulkAccountRequest,
  BulkAction,
  CollectJobsResponse,
  CollectLinkRequest,
  GroupCollectRequest,
  GroupEventListResponse,
  GroupIntelStats,
  GroupMemberListResponse,
  GroupProfileListResponse,
  GroupProfileOut,
  BulkPmRequest,
  BulkProbeRequest,
  BulkWarmupRequest,
  BulkThrottleRequest,
  ImportBatchOut,
  ImportFormatsResponse,
  ImportParseResponse,
  ImportResponse,
  BulkResultOut,
  CampaignBatchListResponse,
  CampaignBatchOut,
  AssignmentOut,
  AuditListQuery,
  AuditListResponse,
  BotCreate,
  BotOut,
  BotUpdate,
  CheckRequest,
  CheckResultOut,
  DashboardOut,
  DialogListQuery,
  DialogListResponse,
  DialogOut,
  DraftOut,
  ForceAddRequest,
  GroupBroadcastRequest,
  GroupCreate,
  GroupOut,
  JoinGroupRequest,
  LeaveGroupRequest,
  LoginStartRequest,
  MaterialKind,
  MaterialListResponse,
  MaterialOut,
  MaterialSendRequest,
  LoginStepResponse,
  MessageListQuery,
  MessageListResponse,
  MessageSearchResponse,
  MetricsTrendsOut,
  MetricsWindow,
  NotificationListQuery,
  NotificationListResponse,
  NotificationOut,
  OkResponse,
  Paged,
  PersonaRequest,
  ProfileBulkRequest,
  ProxyCreate,
  ProxyOut,
  ProxyUpdate,
  RelayLinkOut,
  RelayRouteCreate,
  RelayRouteOut,
  RelayRouteUpdate,
  SendMessageResponse,
  StormRequest,
  TaskActionResponse,
  TaskBulkRetryResponse,
  TaskListQuery,
  TaskListResponse,
  TaskOut,
  TokenResponse,
  RelayTestRequest,
  RelayTestResponse,
  ExportResource,
  ExportResult,
  UserCreate,
  UserOut,
  UserUpdate,
  KeywordHitOut,
  KeywordWatchOut,
  ReplyRuleOut,
  UUID,
} from './types';

/** 后端多数集合接口回数组，个别回 {items,total}；这里两种都接住 */
export function asList<T>(payload: Paged<T> | T[] | null | undefined): T[] {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  return Array.isArray(payload.items) ? payload.items : [];
}

// ---------------------------------------------------------------- 鉴权

export const authApi = {
  login: (username: string, password: string) =>
    api.post<TokenResponse>(
      '/api/auth/login',
      { username, password },
      // 口令错误也是 401，这里不能让封装当成「登录过期」处理
      { silent: true, authRedirect: false },
    ),
  me: () => api.get<UserOut>('/api/auth/me', undefined, { silent: true }),
  logout: () => api.post<OkResponse>('/api/auth/logout', {}, { silent: true, authRedirect: false }),
};

// ---------------------------------------------------------------- 工作台

export const dashboardApi = {
  get: () => api.get<DashboardOut>('/api/dashboard'),
};

// ---------------------------------------------------------------- 账号

export const accountApi = {
  /** 账号矩阵状态：健康分 / 节流快照 / 设备指纹 */
  matrix: (id: UUID) => api.get<AccountMatrixState>(`/api/accounts/${id}/matrix`),
  list: (query: AccountListQuery, options?: RequestOptions) =>
    api.get<AccountListResponse>('/api/accounts', { ...query }, options),
  summary: () => api.get<AccountSummary>('/api/accounts/summary'),
  create: (payload: AccountCreate) => api.post<AccountOut>('/api/accounts', payload),
  get: (id: UUID) => api.get<AccountOut>(`/api/accounts/${id}`),
  update: (id: UUID, payload: AccountUpdate) => api.patch<AccountOut>(`/api/accounts/${id}`, payload),
  remove: (id: UUID) => api.del<OkResponse>(`/api/accounts/${id}`),
  disable: (id: UUID) => api.post<OkResponse>(`/api/accounts/${id}/disable`),
  enable: (id: UUID) => api.post<OkResponse>(`/api/accounts/${id}/enable`),
  releaseLease: (id: UUID) => api.post<OkResponse>(`/api/accounts/${id}/release-lease`),
  syncDialogs: (id: UUID) => api.post<OkResponse & { task_id?: UUID }>(`/api/accounts/${id}/sync-dialogs`),
  check: (id: UUID) => api.post<CheckResultOut>(`/api/accounts/${id}/check`),
  checkBatch: (payload: CheckRequest) => api.post<CheckResultOut[]>('/api/accounts/check', payload),
  profile: (
    id: UUID,
    payload: {
      first_name?: string;
      last_name?: string;
      bio?: string;
      username?: string;
      photo_url?: string;
    },
  ) => api.post<OkResponse & { task_id?: UUID }>(`/api/accounts/${id}/profile`, payload),
  /** 账号详情一次拿全（详情抽屉用）：账号 + 分组 + 代理 + 租约 + 统计 + 最近记录 */
  overview: (id: UUID) => api.get<AccountOverviewOut>(`/api/accounts/${id}/overview`),
};

/**
 * 批量账号操作（POST /api/accounts/bulk/{action}）。
 * 只覆盖「对已有的号做一次已有操作」：检测、同步会话、分配、改分组、改代理、启停、清租约。
 * 明确不做批量私信 / 群发 / 加群 / 改资料（见 规划.md「不做这些」）。
 */
export const accountBulkApiExtra = {
  /** 申诉解封：模拟真人给官方 @SpamBot 发 /start 并点击「这是误判」（24 小时内不重复） */
  appeal: (payload: BulkWarmupRequest & { with_warmup?: boolean }) =>
    api.post<BulkResultOut>('/api/accounts/bulk/appeal', payload),
  /** 官方机制养号：上线/翻会话/下线，不发消息；可选同步官方限制参数 */
  warmup: (payload: BulkWarmupRequest) => api.post<BulkResultOut>('/api/accounts/bulk/warmup', payload),
  /** 深度验活：连得上 + 会话有效 + 读写权限，复算健康分 */
  probe: (payload: BulkProbeRequest) => api.post<BulkResultOut>('/api/accounts/bulk/probe', payload),
  /** 批量设置节流：每日上限 / 最小间隔 / 解熔断 */
  throttle: (payload: BulkThrottleRequest) => api.post<BulkResultOut>('/api/accounts/bulk/throttle', payload),
};

export const accountBulkApi = {
  /**
   * 通用入口。除 bulk/assign 外都允许**不带 body**（等价 `{}` → 400「没有选中任何账号」），
   * 所以这里 payload 是可选的；assign 必须带 user_id。
   * 空选择 / scope 写法错 / mode 非法 → 400；越权 → 403；号不存在 → 404。
   */
  run: (action: BulkAction, payload?: BulkAccountRequest) =>
    api.post<BulkResultOut>(`/api/accounts/bulk/${action}`, payload ?? {}),
  check: (payload?: BulkAccountRequest) => accountBulkApi.run('check', payload),
  syncDialogs: (payload?: BulkAccountRequest) => accountBulkApi.run('sync-dialogs', payload),
  /** 仅 admin：批量分配 / 取消分配（mode='unassign'，响应 action 会是 unassign） */
  assign: (payload: BulkAccountRequest) => accountBulkApi.run('assign', payload),
  unassign: (payload: Omit<BulkAccountRequest, 'mode'>) =>
    accountBulkApi.run('assign', { ...payload, mode: 'unassign' }),
  group: (payload: BulkAccountRequest) => accountBulkApi.run('group', payload),
  proxy: (payload: BulkAccountRequest) => accountBulkApi.run('proxy', payload),
  status: (payload: BulkAccountRequest) => accountBulkApi.run('status', payload),
  disable: (payload?: BulkAccountRequest) => accountBulkApi.run('disable', payload),
  enable: (payload?: BulkAccountRequest) => accountBulkApi.run('enable', payload),
  releaseLease: (payload?: BulkAccountRequest) => accountBulkApi.run('release-lease', payload),
};

export const accountLoginApi = {
  start: (payload: LoginStartRequest, silent = false) =>
    api.post<LoginStepResponse>('/api/accounts/login/start', payload, { silent }),
  code: (accountId: UUID, code: string, silent = false) =>
    api.post<LoginStepResponse>('/api/accounts/login/code', { account_id: accountId, code }, { silent }),
  password: (accountId: UUID, password: string, silent = false) =>
    api.post<LoginStepResponse>(
      '/api/accounts/login/password',
      { account_id: accountId, password },
      { silent },
    ),
};

// ---------------------------------------------------------------- 账号矩阵（导入 / 健康 / 节流）

export const accountImportApi = {
  /** 支持的导入方式与限制（前端照着渲染引导，不写死格式） */
  formats: () => api.get<ImportFormatsResponse>('/api/accounts/import/formats'),
  /** 解析预览：不写库，先确认清单 */
  parse: (form: FormData) => api.post<ImportParseResponse>('/api/accounts/import/parse', form),
  /** 正式导入 */
  run: (form: FormData) => api.post<ImportResponse>('/api/accounts/import', form),
  batches: () => api.get<ImportBatchOut[]>('/api/accounts/import/batches'),
};

// ---------------------------------------------------------------- 分组

export const groupApi = {
  list: () => api.get<GroupOut[] | Paged<GroupOut>>('/api/groups').then(asList<GroupOut>),
  create: (payload: GroupCreate) => api.post<GroupOut>('/api/groups', payload),
  update: (id: UUID, payload: Partial<GroupCreate>) => api.patch<GroupOut>(`/api/groups/${id}`, payload),
  remove: (id: UUID) => api.del<OkResponse>(`/api/groups/${id}`),
  addAccounts: (id: UUID, accountIds: UUID[]) =>
    api.post<OkResponse>(`/api/groups/${id}/accounts`, { account_ids: accountIds }),
  removeAccounts: (id: UUID, accountIds: UUID[]) =>
    api.post<OkResponse>(`/api/groups/${id}/accounts/remove`, { account_ids: accountIds }),
};

// ---------------------------------------------------------------- 代理

export const proxyApi = {
  list: () => api.get<ProxyOut[] | Paged<ProxyOut>>('/api/proxies').then(asList<ProxyOut>),
  create: (payload: ProxyCreate) => api.post<ProxyOut>('/api/proxies', payload),
  update: (id: UUID, payload: ProxyUpdate) => api.patch<ProxyOut>(`/api/proxies/${id}`, payload),
  remove: (id: UUID) => api.del<OkResponse>(`/api/proxies/${id}`),
  bindAccounts: (id: UUID, accountIds: UUID[]) =>
    api.post<OkResponse>(`/api/proxies/${id}/accounts`, { account_ids: accountIds }),
};

// ---------------------------------------------------------------- 员工 / 分配

export const userApi = {
  list: () => api.get<UserOut[] | Paged<UserOut>>('/api/users').then(asList<UserOut>),
  create: (payload: UserCreate) => api.post<UserOut>('/api/users', payload),
  update: (id: UUID, payload: UserUpdate) => api.patch<UserOut>(`/api/users/${id}`, payload),
  remove: (id: UUID) => api.del<OkResponse>(`/api/users/${id}`),
};

export const assignmentApi = {
  list: () => api.get<AssignmentOut[] | Paged<AssignmentOut>>('/api/assignments').then(asList<AssignmentOut>),
  create: (userId: UUID, accountIds: UUID[]) =>
    api.post<AssignmentOut>('/api/assignments', { user_id: userId, account_ids: accountIds }),
  remove: (userId: UUID, accountIds: UUID[]) =>
    api.del<OkResponse>('/api/assignments', { user_id: userId, account_ids: accountIds }),
};

// ---------------------------------------------------------------- 会话 / 消息

export const dialogApi = {
  /** 客服收件箱：跨账号聚合「有人刚发来、还没处理」的私信，未读优先 */
  inbox: (query?: { limit?: number; only_unread?: boolean }) =>
    api.get<{
      items: {
        dialog_id: string;
        account_id: string | null;
        account_label: string | null;
        title: string;
        username?: string | null;
        unread_count: number;
        last_message_at?: string | null;
        last_message_preview: string;
      }[];
      total: number;
      unread_total: number;
    }>('/api/dialogs/inbox', query),
  list: (query: DialogListQuery, options?: RequestOptions) =>
    api.get<DialogListResponse>('/api/dialogs', { ...query }, options),
  get: (id: UUID) => api.get<DialogOut>(`/api/dialogs/${id}`),
  messages: (id: UUID, params?: { limit?: number; before?: string; q?: string }) =>
    api.get<MessageListResponse>(`/api/dialogs/${id}/messages`, {
      limit: params?.limit ?? 50,
      before: params?.before,
      q: params?.q,
    }),
  read: (id: UUID) => api.post<OkResponse>(`/api/dialogs/${id}/read`, {}),
  sync: (id: UUID, limit = 50) => api.post<OkResponse & { task_id?: UUID }>(`/api/dialogs/${id}/sync`, { limit }),
  drafts: (id: UUID) => api.get<DraftOut[] | Paged<DraftOut>>(`/api/dialogs/${id}/drafts`).then(asList<DraftOut>),
  draft: (id: UUID, instruction: string, options?: RequestOptions) =>
    api.post<DraftOut>(`/api/dialogs/${id}/draft`, { instruction }, { timeoutMs: 60_000, ...options }),
  discardDraft: (draftId: UUID) => api.del<OkResponse>(`/api/drafts/${draftId}`),
};

export const messageApi = {
  send: (dialogId: UUID, text: string, draftId?: UUID | null) =>
    api.post<SendMessageResponse>('/api/messages/send', {
      dialog_id: dialogId,
      text,
      ...(draftId ? { draft_id: draftId } : {}),
    }),
  /** 全局消息检索（GET /api/messages?q=…），支持 sort/order */
  search: (query: MessageListQuery, options?: RequestOptions) =>
    api.get<MessageSearchResponse>('/api/messages', { ...query }, options),
};

// ---------------------------------------------------------------- 任务

export const taskApi = {
  list: (query: TaskListQuery, options?: RequestOptions) =>
    api.get<TaskListResponse>('/api/tasks', { ...query }, options),
  get: (id: UUID) => api.get<TaskOut>(`/api/tasks/${id}`),
  retry: (id: UUID) => api.post<TaskActionResponse>(`/api/tasks/${id}/retry`),
  cancel: (id: UUID) => api.post<TaskActionResponse>(`/api/tasks/${id}/cancel`),
  /**
   * 批量重试（队列运维动作，不是批量发送）：最多 200 条，逐条给结果；
   * 某条不可重试不会让整个请求失败（顶层 ok = failed == 0）。
   * 空数组 → 400，超过 200 → 422。
   */
  bulkRetry: (taskIds: UUID[]) => api.post<TaskBulkRetryResponse>('/api/tasks/bulk/retry', { task_ids: taskIds }),
};

// ---------------------------------------------------------------- 群情报（无感采集）

export const groupIntelApi = {
  /** 概览：群数 / 成员数 / 今日入退群 */
  stats: () => api.get<GroupIntelStats>('/api/group-intel/stats'),
  /** 批量采集：对选中的号采它们已加入的群（只读，不发言） */
  collect: (payload: GroupCollectRequest) => api.post<BulkResultOut>('/api/group-intel/collect', payload),
  /** 按关键词找公开群：走 Telegram 原生搜索（不用第三方群目录站） */
  searchGroups: (payload: {
    scope?: string;
    account_ids?: string[];
    keywords: string[];
    per_keyword?: number;
    min_members?: number;
    kind?: 'any' | 'group' | 'channel';
    limit?: number;
  }) => api.post<BulkResultOut>('/api/group-intel/search-groups', payload),
  // 关键词监听：规则 CRUD + 命中流水
  keywordWatches: () => api.get<{ items: KeywordWatchOut[]; total: number }>('/api/group-intel/keyword-watches'),
  createKeywordWatch: (payload: {
    name?: string;
    keywords: string[];
    enabled?: boolean;
    notify?: boolean;
  }) => api.post<{ ok: boolean; id: string; message: string }>('/api/group-intel/keyword-watches', payload),
  updateKeywordWatch: (id: string, payload: { enabled?: boolean; keywords?: string[]; name?: string }) =>
    api.patch<{ ok: boolean; message: string }>(`/api/group-intel/keyword-watches/${id}`, payload),
  deleteKeywordWatch: (id: string) =>
    api.del<{ ok: boolean; message: string }>(`/api/group-intel/keyword-watches/${id}`),
  // 自动回复规则：命中会自动发消息（带冷却）
  replyRules: () => api.get<{ items: ReplyRuleOut[]; total: number }>('/api/group-intel/reply-rules'),
  createReplyRule: (payload: {
    name?: string;
    keywords: string[];
    reply_text: string;
    match_mode?: 'contains' | 'exact' | 'regex';
    scope?: 'private' | 'group' | 'both';
    priority?: number;
    cooldown_seconds?: number;
  }) => api.post<{ ok: boolean; id: string; message: string }>('/api/group-intel/reply-rules', payload),
  updateReplyRule: (
    id: string,
    payload: { enabled?: boolean; reply_text?: string; keywords?: string[]; cooldown_seconds?: number },
  ) => api.patch<{ ok: boolean; message: string }>(`/api/group-intel/reply-rules/${id}`, payload),
  deleteReplyRule: (id: string) =>
    api.del<{ ok: boolean; message: string }>(`/api/group-intel/reply-rules/${id}`),
  keywordHits: (limit = 100) =>
    api.get<{ items: KeywordHitOut[]; total: number }>('/api/group-intel/keyword-hits', { limit }),
  /** 采集群内对话：成员名单被群主隐藏时的替代方案（对话照样能读，从发言里淘成员） */
  collectMessages: (payload: {
    profile_id: string;
    scope?: string;
    account_ids?: string[];
    days: number;
    exclude_admins: boolean;
    exclude_bots: boolean;
    limit: number;
    /** 只捞聊到这些词的人（留空=全量扫，命中走服务端搜索） */
    keywords?: string[];
  }) => api.post<BulkResultOut>('/api/group-intel/collect-messages', payload),
  /** 按群链接采集：粘贴链接，自动解析群 + 采群员（可选先加入、采完退出） */
  collectByLink: (payload: CollectLinkRequest) =>
    api.post<BulkResultOut>('/api/group-intel/collect-link', payload),
  /** 采集进度：每条任务的阶段、已采人数、失败原因（页面每 5 秒轮询） */
  jobs: (query?: { limit?: number; batch_id?: string; only_active?: boolean }) =>
    api.get<CollectJobsResponse>('/api/group-intel/jobs', { ...query }),
  /** 采集结果打包下载（zip：群总表 + 每群成员 + 事件 + 清单） */
  exportZip: (query?: { profile_ids?: string; batch_id?: string; account_id?: UUID; include_events?: boolean }) =>
    api.download('/api/group-intel/export.zip', { ...query }),
  /** 群档案列表 */
  profiles: (query: { q?: string; account_id?: UUID | null; min_members?: number; page?: number; page_size?: number }) =>
    api.get<GroupProfileListResponse>('/api/group-intel/profiles', { ...query }),
  profile: (id: UUID) => api.get<{ profile: GroupProfileOut; members: Record<string, unknown>; events: Record<string, number> }>(`/api/group-intel/profiles/${id}`),
  members: (id: UUID, query: { q?: string; only_bots?: boolean; exclude_bots?: boolean; status?: string; page?: number; page_size?: number }) =>
    api.get<GroupMemberListResponse>(`/api/group-intel/profiles/${id}/members`, { ...query }),
  events: (query: { tg_chat_id?: number; event_type?: string; hours?: number; page?: number; page_size?: number }) =>
    api.get<GroupEventListResponse>('/api/group-intel/events', { ...query }),
  membersCsvUrl: (profileId: UUID) => `/api/group-intel/members.csv?profile_id=${profileId}`,
};

// ---------------------------------------------------------------- 触达中心（批量运营）

export const campaignApi = {
  bulkPm: (payload: BulkPmRequest) => api.post<BulkResultOut>('/api/campaigns/bulk-pm', payload),
  groupBroadcast: (payload: GroupBroadcastRequest) => api.post<BulkResultOut>('/api/campaigns/group-broadcast', payload),
  materialSend: (payload: MaterialSendRequest) => api.post<BulkResultOut>('/api/campaigns/material-send', payload),
  joinGroup: (payload: JoinGroupRequest) => api.post<BulkResultOut>('/api/campaigns/join-group', payload),
  leaveGroup: (payload: LeaveGroupRequest) => api.post<BulkResultOut>('/api/campaigns/leave-group', payload),
  forceAdd: (payload: ForceAddRequest) => api.post<BulkResultOut>('/api/campaigns/force-add', payload),
  profileUpdate: (payload: ProfileBulkRequest) => api.post<BulkResultOut>('/api/campaigns/profile-update', payload),
  storm: (payload: StormRequest) => api.post<BulkResultOut>('/api/campaigns/storm', payload),
  persona: (payload: PersonaRequest) => api.post<BulkResultOut>('/api/campaigns/persona', payload),
  batches: (query?: { page?: number; page_size?: number }) =>
    api.get<CampaignBatchListResponse>('/api/campaigns/batches', { ...query }),
  batch: (batchId: UUID) => api.get<CampaignBatchOut>(`/api/campaigns/batches/${batchId}`),
  cancelBatch: (batchId: UUID) => api.post<BulkResultOut>(`/api/campaigns/batches/${batchId}/cancel`),
};

// ---------------------------------------------------------------- 素材库

export const materialApi = {
  list: (query?: { kind?: MaterialKind | ''; q?: string; page?: number; page_size?: number }) =>
    api.get<MaterialListResponse>('/api/materials', { ...query }),
  create: (payload: { name: string; text?: string | null }) =>
    api.post<MaterialOut>('/api/materials', { ...payload, kind: 'text' }),
  upload: (name: string, file: File, caption?: string) => {
    const form = new FormData();
    form.append('file', file);
    return api.post<MaterialOut>(
      `/api/materials/upload?name=${encodeURIComponent(name)}${caption ? `&caption=${encodeURIComponent(caption)}` : ''}`,
      form,
    );
  },
  remove: (id: UUID) => api.del<OkResponse>(`/api/materials/${id}`),
  downloadUrl: (id: UUID) => `/api/materials/${id}?download=true`,
};


export const botApi = {
  list: () => api.get<BotOut[] | Paged<BotOut>>('/api/bots').then(asList<BotOut>),
  create: (payload: BotCreate) => api.post<BotOut>('/api/bots', payload),
  update: (id: UUID, payload: BotUpdate) => api.patch<BotOut>(`/api/bots/${id}`, payload),
  remove: (id: UUID) => api.del<OkResponse>(`/api/bots/${id}`),
  webhook: (id: UUID, enable: boolean) =>
    api.post<OkResponse & { detail?: string }>(`/api/bots/${id}/webhook`, { enable }),
  check: (id: UUID) => api.get<BotOut>(`/api/bots/${id}/check`),
};

// ---------------------------------------------------------------- 转发

export const relayApi = {
  list: () => api.get<RelayRouteOut[] | Paged<RelayRouteOut>>('/api/relays').then(asList<RelayRouteOut>),
  create: (payload: RelayRouteCreate) => api.post<RelayRouteOut>('/api/relays', payload),
  update: (id: UUID, payload: RelayRouteUpdate) => api.patch<RelayRouteOut>(`/api/relays/${id}`, payload),
  remove: (id: UUID) => api.del<OkResponse>(`/api/relays/${id}`),
  links: (params: { route_id?: UUID | null; page?: number; page_size?: number }) =>
    api.get<Paged<RelayLinkOut>>('/api/relays/links', { ...params }),
  /** 仅 admin：保存规则前先试通（只发一条测试消息，不碰任何用户号） */
  test: (payload: RelayTestRequest) =>
    api.post<RelayTestResponse>('/api/relays/test', payload, { silent: true }),
};

// ---------------------------------------------------------------- 操作记录

/**
 * 契约第 1~10 节没有给出审计列表路径（schemas/audit.py 已有 AuditListResponse）。
 * 本机后端实测可用路径是 /api/audit，先请求它，404 时再回落到 /api/audit-logs，
 * 并把命中的路径记下来，后续请求不再试探。
 */
let resolvedAuditPath: string | null = null;

export const auditApi = {
  list: async (query: AuditListQuery): Promise<AuditListResponse> => {
    const candidates = resolvedAuditPath ? [resolvedAuditPath] : ['/api/audit', '/api/audit-logs'];
    let lastError: unknown = null;
    for (const path of candidates) {
      try {
        const payload = await api.get<AuditListResponse | Paged<AuditListResponse['items'][number]>>(
          path,
          { ...query },
        );
        resolvedAuditPath = path;
        const paged = payload as AuditListResponse;
        return {
          items: Array.isArray(paged?.items) ? paged.items : [],
          total: typeof paged?.total === 'number' ? paged.total : 0,
          page: paged?.page ?? (query.page || 1),
          page_size: paged?.page_size ?? (query.page_size || 20),
        };
      } catch (err) {
        lastError = err;
        if (err instanceof ApiError && err.status === 404) continue;
        throw err;
      }
    }
    throw lastError;
  },
  /** 已确认可用的审计路径（用于页面提示） */
  resolvedPath: () => resolvedAuditPath,
};

// ---------------------------------------------------------------- 指标趋势

/** GET /api/metrics/trends?window=24h|7d|30d（window / range 两个参数名后端都接受） */
export const metricsApi = {
  trends: (window: MetricsWindow = '24h') =>
    api.get<MetricsTrendsOut>('/api/metrics/trends', { window }, { silent: true }),
};

// ---------------------------------------------------------------- 通知

export const notificationApi = {
  list: (query: NotificationListQuery = {}) =>
    api.get<NotificationListResponse>('/api/notifications', { ...query }, { silent: true }),
  markRead: (id: UUID) =>
    api.post<OkResponse & { notification?: NotificationOut }>(`/api/notifications/${id}/read`, {}),
  markAllRead: () => api.post<OkResponse & { marked?: number }>('/api/notifications/read-all', {}),
};

// ---------------------------------------------------------------- 导出（服务端 CSV）

/**
 * GET /api/export/{resource}.csv，接受与对应列表接口相同的 query（含 sort/order/q）。
 * 注意：导出的是「当前筛选条件下的全部数据」，不受 page/page_size 影响；
 * 后端上限 5 万行，超出会截断并回 X-Export-Truncated: true。
 */
export const exportApi = {
  /** 拿到可直接 window.open 的地址（需要带 JWT 的场景请用 csv()） */
  url: (resource: ExportResource, query?: object) =>
    `/api/export/${resource}.csv${buildQuery(query as Record<string, QueryValue>)}`,
  /** 通用导出：query 传对应列表接口的查询对象即可（筛选条件会原样带给后端） */
  csv: (resource: ExportResource, query?: object): Promise<ExportResult> =>
    api.download(`/api/export/${resource}.csv`, query as Record<string, QueryValue>),
  accounts: (query?: AccountListQuery) => exportApi.csv('accounts', query),
  dialogs: (query?: DialogListQuery) => exportApi.csv('dialogs', query),
  messages: (query?: MessageListQuery) => exportApi.csv('messages', query),
  tasks: (query?: TaskListQuery) => exportApi.csv('tasks', query),
  audit: (query?: AuditListQuery) => exportApi.csv('audit', query),
};

// ---------------------------------------------------------------- 健康检查

export const healthApi = {
  live: () => api.get<{ status: string; service: string; version: string }>('/health', undefined, { silent: true, retries: 0 }),
  ready: () =>
    api.get<{ status: string; database: boolean; redis: boolean }>('/ready', undefined, { silent: true, retries: 0 }),
};

/** 列表接口统一的排序参数（页面把 DataTable 的排序变化直接透传） */
export function sortParams(
  field?: string | null,
  order?: 'asc' | 'desc' | null,
): { sort?: string; order?: 'asc' | 'desc' } {
  if (!field || !order) return {};
  return { sort: field, order };
}
