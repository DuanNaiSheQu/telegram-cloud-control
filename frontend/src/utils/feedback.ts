/**
 * 全局提示（Toast）统一封装。
 *
 * 用法（组件内推荐用 `App.useApp()` 的 message/notification；
 * 非组件代码 —— 比如 api/client.ts 的失败提示 —— 用这里的 toast）：
 *
 *   toast.success('已停用 2 个账号');
 *   toast.error('无法连接后端服务，请确认 API 已启动');
 *   toast.warning('登录已过期，请重新登录');
 *   toast.info('已复制');
 *
 * 约定：
 *  - 全站中文文案；
 *  - 相同内容 2 秒内只弹一次（去重），避免列表页并发请求同时失败时刷屏；
 *  - App 挂载前（messageApi 未绑定）不会静默丢消息：错误会落到 console。
 */
import type { MessageInstance } from 'antd/es/message/interface';
import type { NotificationInstance } from 'antd/es/notification/interface';
import type { ReactNode } from 'react';

let messageApi: MessageInstance | null = null;
let notificationApi: NotificationInstance | null = null;

/** 由 App.tsx 的 FeedbackBridge 注入（在 AntdApp 上下文里拿到的实例） */
export function bindMessageApi(instance: MessageInstance | null): void {
  messageApi = instance;
}

/** 可选：把 notification 实例也交给非组件代码（长文案/带描述的通知） */
export function bindNotificationApi(instance: NotificationInstance | null): void {
  notificationApi = instance;
}

export function getMessageApi(): MessageInstance | null {
  return messageApi;
}

export interface ToastOptions {
  /** 同一个 key 的消息会被替换而不是叠加 */
  key?: string;
  /** 秒 */
  duration?: number;
  /** 第二行描述（仅 notification 用） */
  description?: ReactNode;
  /** 关闭去重（默认开启） */
  dedupe?: boolean;
}

const RECENT = new Map<string, number>();
const DEDUPE_WINDOW_MS = 2000;

function shouldSkip(kind: string, content: string, options?: ToastOptions): boolean {
  if (options?.dedupe === false || options?.key) return false;
  const key = `${kind}:${content}`;
  const now = Date.now();
  const last = RECENT.get(key);
  if (last && now - last < DEDUPE_WINDOW_MS) return true;
  RECENT.set(key, now);
  // 顺手清理过期项，避免 Map 无限增长
  if (RECENT.size > 50) {
    for (const [k, t] of RECENT) {
      if (now - t > DEDUPE_WINDOW_MS) RECENT.delete(k);
    }
  }
  return false;
}

function emit(
  kind: 'success' | 'error' | 'warning' | 'info' | 'loading',
  content: string,
  options?: ToastOptions,
): void {
  if (shouldSkip(kind, content, options)) return;
  if (!messageApi) {
    if (kind === 'error') console.error('[toast.error]', content);
    return;
  }
  messageApi[kind]({ content, key: options?.key, duration: options?.duration });
}

export const toast = {
  success: (content: string, options?: ToastOptions) => emit('success', content, options),
  error: (content: string, options?: ToastOptions) => emit('error', content, options),
  warning: (content: string, options?: ToastOptions) => emit('warning', content, options),
  info: (content: string, options?: ToastOptions) => emit('info', content, options),
  loading: (content: string, options?: ToastOptions) => emit('loading', content, options),
  /** 顶部横幅式通知（长文案 / 需要操作的场景） */
  notify: (
    kind: 'success' | 'error' | 'warning' | 'info',
    title: string,
    options?: ToastOptions,
  ): void => {
    if (!notificationApi) {
      emit(kind, title, options);
      return;
    }
    notificationApi[kind]({
      message: title,
      description: options?.description,
      key: options?.key,
      duration: options?.duration ?? 4.5,
    });
  },
  destroy: (): void => {
    messageApi?.destroy();
    RECENT.clear();
  },
};

// ---------------------------------------------------------------- 兼容旧 API
// 旧代码（api/client.ts、AuthContext、各页面）一直在用这几个函数名，保留不动。

export function notifyError(content: string): void {
  toast.error(content);
}

export function notifySuccess(content: string): void {
  toast.success(content);
}

export function notifyInfo(content: string): void {
  toast.info(content);
}

export function notifyWarning(content: string): void {
  toast.warning(content);
}
