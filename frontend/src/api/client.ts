/**
 * fetch 封装：
 * - 自动带 Authorization: Bearer <JWT>
 * - 统一中文错误提示（401 清 token 并跳登录，403/409/422/5xx 分类提示）
 * - 统一解析 {detail: "原因"}（422 的数组 detail 会拼成一句中文）
 * - GET 网络抖动自动重试一次（后端重启时页面不至于立刻报错）
 * - downloadFile：导出 CSV 的二进制通道（带文件名解析）
 */
import { notifyError, notifyWarning } from '../utils/feedback';
import { filenameFromDisposition } from '../utils/download';
import type { ExportResult } from './types';

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

  /** 适合直接展示给值班同事的中文文案 */
  get friendlyMessage(): string {
    return this.message || messageForStatus(this.status, this.detail, this.path);
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
  /** 网络层失败的重试次数（默认 GET 重试 1 次，其它方法 0 次） */
  retries?: number;
  retryDelayMs?: number;
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
  if (status === 429) return '操作太频繁，请稍后再试';
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

function buildHeaders(body: unknown, accept = 'application/json'): Record<string, string> {
  const headers: Record<string, string> = { Accept: accept };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  return headers;
}

/** 带超时/外部 signal 的 fetch */
async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
  signal?: AbortSignal,
): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', () => controller.abort(), { once: true });
  }
  try {
    return await fetch(url, { ...init, signal: controller.signal, credentials: 'same-origin' });
  } finally {
    window.clearTimeout(timer);
  }
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

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

  const retries = options.retries ?? (method === 'GET' ? 1 : 0);
  const retryDelayMs = options.retryDelayMs ?? 400;
  const url = `${path}${buildQuery(query)}`;

  let response: Response | null = null;
  let lastNetworkError: ApiError | null = null;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    if (attempt > 0) await new Promise((resolve) => window.setTimeout(resolve, retryDelayMs * attempt));
    try {
      response = await fetchWithTimeout(
        url,
        { method, headers: buildHeaders(body), body: body === undefined ? undefined : JSON.stringify(body) },
        timeoutMs,
        signal,
      );
      lastNetworkError = null;
      break;
    } catch (err) {
      const aborted = (err as Error)?.name === 'AbortError';
      // 调用方主动取消（切换筛选/离开页面）：不提示、不重试
      if (aborted && signal?.aborted) throw new ApiError(0, '请求已取消', path);
      lastNetworkError = new ApiError(0, aborted ? '请求超时，请稍后重试' : '无法连接后端服务，请确认 API 已启动', path);
      if (attempt === retries) {
        if (!silent) notifyError(lastNetworkError.message);
        throw lastNetworkError;
      }
    }
  }

  if (!response) {
    const error = lastNetworkError ?? new ApiError(0, '无法连接后端服务，请确认 API 已启动', path);
    if (!silent) notifyError(error.message);
    throw error;
  }

  const payload = await parseBody(response);

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

/**
 * 二进制下载（导出 CSV）：
 * 后端回 text/csv + Content-Disposition，这里把 Blob 与文件名一起交给页面，
 * 由页面决定是否直接触发下载（有的场景要先生成预览）。
 */
export async function downloadFile(
  path: string,
  query?: Record<string, QueryValue>,
  options: RequestOptions = {},
): Promise<ExportResult> {
  const { timeoutMs = 120_000, silent, signal } = options;
  const url = `${path}${buildQuery(query)}`;

  let response: Response;
  try {
    response = await fetchWithTimeout(url, { method: 'GET', headers: buildHeaders(undefined) }, timeoutMs, signal);
  } catch (err) {
    if ((err as Error)?.name === 'AbortError' && signal?.aborted) {
      throw new ApiError(0, '导出已取消', path);
    }
    const error = new ApiError(0, '导出失败：无法连接后端服务', path);
    if (!silent) notifyError(error.message);
    throw error;
  }

  if (!response.ok) {
    const payload = await parseBody(response);
    const detail = extractDetail(payload);
    const message = detail || `导出失败（${response.status}）`;
    const error = new ApiError(response.status, message, path, detail, payload);
    if (!silent) notifyError(message);
    throw error;
  }

  const blob = await response.blob();
  const totalHeader = response.headers.get('X-Export-Total');
  return {
    blob,
    filename: filenameFromDisposition(response.headers.get('Content-Disposition'), 'export.csv'),
    total: totalHeader ? Number(totalHeader) : null,
    truncated: response.headers.get('X-Export-Truncated') === 'true',
  };
}

export const api = {
  get: <T>(path: string, query?: Record<string, QueryValue>, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'GET', query }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PUT', body }),
  del: <T>(path: string, query?: Record<string, QueryValue>, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE', query }),
  download: downloadFile,
};
