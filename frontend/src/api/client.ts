/**
 * fetch 封装：
 * - 自动带 Authorization: Bearer <JWT>
 * - 统一中文错误提示（401 清 token 并跳登录，403/409/422/5xx 分类提示）
 * - 统一解析 {detail: "原因"}
 */
import { notifyError, notifyWarning } from '../utils/feedback';

export const TOKEN_KEY = 'tgcc_token';

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* localStorage 不可用时忽略 */
  }
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly path: string;
  readonly body: unknown;

  constructor(status: number, message: string, path: string, detail = '', body: unknown = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.path = path;
    this.body = body;
  }

  /** 网络层失败（连不上 / 超时），没有 HTTP 状态码 */
  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

export type QueryValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | Array<string | number>;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  query?: Record<string, QueryValue>;
  body?: unknown;
  /** 不弹全局错误提示（页面自己展示） */
  silent?: boolean;
  /** 毫秒，默认 30s */
  timeoutMs?: number;
  signal?: AbortSignal;
  /** 401 时是否清 token 跳登录（登录接口自己关掉） */
  authRedirect?: boolean;
}

export function buildQuery(query?: Record<string, QueryValue>): string {
  if (!query) return '';
  const parts: string[] = [];
  for (const [key, raw] of Object.entries(query)) {
    if (raw === undefined || raw === null || raw === '') continue;
    if (Array.isArray(raw)) {
      if (raw.length === 0) continue;
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(raw.join(','))}`);
    } else {
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(raw))}`);
    }
  }
  return parts.length ? `?${parts.join('&')}` : '';
}

/** 后端 422 的 detail 是数组，其它情况是字符串 */
function extractDetail(body: unknown): string {
  if (!body || typeof body !== 'object') return '';
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object') {
          const rec = item as { msg?: string; loc?: Array<string | number> };
          const loc = Array.isArray(rec.loc) ? rec.loc.filter((p) => p !== 'body').join('.') : '';
          return loc ? `${loc}: ${rec.msg ?? ''}` : (rec.msg ?? '');
        }
        return String(item);
      })
      .filter(Boolean)
      .join('；');
  }
  return '';
}

function messageForStatus(status: number, detail: string, path: string): string {
  if (detail) return detail;
  if (status === 400) return '请求参数不正确';
  if (status === 401) return '登录已过期，请重新登录';
  if (status === 403) return '没有权限执行该操作';
  if (status === 404) return `接口不存在（404）：${path}`;
  if (status === 409) return '当前状态不允许该操作，请刷新后重试';
  if (status === 422) return '参数校验失败';
  if (status >= 500) return `服务端错误（${status}），请稍后重试`;
  return `请求失败（${status}）`;
}

type UnauthorizedHandler = () => void;
const unauthorizedHandlers = new Set<UnauthorizedHandler>();
let lastUnauthorizedAt = 0;

/** AuthContext 注册：401 时清 token 并跳登录 */
export function onUnauthorized(handler: UnauthorizedHandler): () => void {
  unauthorizedHandlers.add(handler);
  return () => {
    unauthorizedHandlers.delete(handler);
  };
}

function emitUnauthorized(): void {
  const now = Date.now();
  unauthorizedHandlers.forEach((handler) => {
    try {
      handler();
    } catch {
      /* 单个处理函数异常不影响其它 */
    }
  });
  if (now - lastUnauthorizedAt > 3000) {
    lastUnauthorizedAt = now;
    notifyWarning('登录已过期，请重新登录');
  }
}

const DEFAULT_TIMEOUT = 30_000;

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = 'GET',
    query,
    body,
    silent,
    timeoutMs = DEFAULT_TIMEOUT,
    signal,
    authRedirect = true,
  } = options;

  const headers: Record<string, string> = { Accept: 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  let response: Response;
  try {
    response = await fetch(`${path}${buildQuery(query)}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      credentials: 'same-origin',
    });
  } catch (err) {
    window.clearTimeout(timer);
    if ((err as Error)?.name === 'AbortError') {
      const timeoutError = new ApiError(0, '请求超时，请稍后重试', path);
      if (!silent) notifyError(timeoutError.message);
      throw timeoutError;
    }
    const networkError = new ApiError(0, '无法连接后端服务，请确认 API 已启动', path);
    if (!silent) notifyError(networkError.message);
    throw networkError;
  }
  window.clearTimeout(timer);

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail = extractDetail(payload);
    const message = messageForStatus(response.status, detail, path);
    const error = new ApiError(response.status, message, path, detail, payload);
    if (response.status === 401 && authRedirect) {
      setToken(null);
      emitUnauthorized();
    } else if (!silent) {
      notifyError(message);
    }
    throw error;
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, query?: Record<string, QueryValue>, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'GET', query }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
  del: <T>(path: string, query?: Record<string, QueryValue>, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE', query }),
};
