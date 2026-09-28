/**
 * 接口封装。路径与 docs/API_CONTRACT.md（v1）逐条对应。
 * 所有函数只做「拼路径 + 传参 + 解析」，不做业务判断。
 */
import { ApiError, api } from './client';
import type {
  AccountCreate,
  AccountListQuery,
  AccountListResponse,
  AccountOut,
  AccountSummary,
  AccountUpdate,
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
  GroupCreate,
  GroupOut,
  LoginStartRequest,
  LoginStepResponse,
  MessageListResponse,
  OkResponse,
  Paged,
  ProxyCreate,
  ProxyOut,
  ProxyUpdate,
  RelayLinkOut,
  RelayRouteCreate,
  RelayRouteOut,
  RelayRouteUpdate,
  SendMessageResponse,
  TaskActionResponse,
  TaskListQuery,
  TaskListResponse,
  TaskOut,
  TokenResponse,
  UserCreate,
  UserOut,
  UserUpdate,
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
  list: (query: AccountListQuery) => api.get<AccountListResponse>('/api/accounts', { ...query }),
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
  list: (query: DialogListQuery) => api.get<DialogListResponse>('/api/dialogs', { ...query }),
  get: (id: UUID) => api.get<DialogOut>(`/api/dialogs/${id}`),
  messages: (id: UUID, params?: { limit?: number; before?: string }) =>
    api.get<MessageListResponse>(`/api/dialogs/${id}/messages`, { limit: params?.limit ?? 50, before: params?.before }),
  read: (id: UUID) => api.post<OkResponse>(`/api/dialogs/${id}/read`, {}),
  sync: (id: UUID, limit = 50) => api.post<OkResponse & { task_id?: UUID }>(`/api/dialogs/${id}/sync`, { limit }),
  drafts: (id: UUID) => api.get<DraftOut[] | Paged<DraftOut>>(`/api/dialogs/${id}/drafts`).then(asList<DraftOut>),
  draft: (id: UUID, instruction: string) =>
    api.post<DraftOut>(`/api/dialogs/${id}/draft`, { instruction }, { timeoutMs: 60_000 }),
  discardDraft: (draftId: UUID) => api.del<OkResponse>(`/api/drafts/${draftId}`),
};

export const messageApi = {
  send: (dialogId: UUID, text: string, draftId?: UUID | null) =>
    api.post<SendMessageResponse>('/api/messages/send', {
      dialog_id: dialogId,
      text,
      ...(draftId ? { draft_id: draftId } : {}),
    }),
};

// ---------------------------------------------------------------- 任务

export const taskApi = {
  list: (query: TaskListQuery) => api.get<TaskListResponse>('/api/tasks', { ...query }),
  get: (id: UUID) => api.get<TaskOut>(`/api/tasks/${id}`),
  retry: (id: UUID) => api.post<TaskActionResponse>(`/api/tasks/${id}/retry`),
  cancel: (id: UUID) => api.post<TaskActionResponse>(`/api/tasks/${id}/cancel`),
};

// ---------------------------------------------------------------- Bot

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
