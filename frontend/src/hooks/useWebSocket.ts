/**
 * WebSocket 长连接：WS /api/ws?token=<JWT>
 * - 断线指数退避重连（1s → 30s）
 * - 订阅按 dialog_id 引用计数，重连后自动补订阅
 * - 25s 一次 {"op":"ping"} 保活（服务端回 {"op":"pong"}）
 */
import { useCallback, useEffect, useState } from 'react';
import { getToken } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { WsRawEvent, WsServerEvent, WsStatus } from '../api/types';

type EventListener = (event: WsServerEvent) => void;
type StatusListener = (status: WsStatus) => void;

const MAX_BACKOFF_MS = 30_000;
const PING_INTERVAL_MS = 25_000;

function wsUrl(token: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/api/ws?token=${encodeURIComponent(token)}`;
}

export class WsClient {
  private socket: WebSocket | null = null;
  private token: string | null = null;
  private readonly refs = new Map<string, number>();
  private readonly listeners = new Set<EventListener>();
  private readonly statusListeners = new Set<StatusListener>();
  private reconnectTimer: number | null = null;
  private pingTimer: number | null = null;
  private attempt = 0;
  private closedByUs = false;
  private currentStatus: WsStatus = 'closed';

  get status(): WsStatus {
    return this.currentStatus;
  }

  /** 已订阅的会话 id（调试用） */
  get subscribedDialogs(): string[] {
    return [...this.refs.keys()];
  }

  connect(token: string): void {
    if (!token) return;
    if (this.token === token && (this.currentStatus === 'open' || this.currentStatus === 'connecting')) {
      return;
    }
    this.token = token;
    this.closedByUs = false;
    this.attempt = 0;
    this.open();
  }

  disconnect(): void {
    this.closedByUs = true;
    this.token = null;
    this.clearTimers();
    const socket = this.socket;
    this.socket = null;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      socket.close();
    }
    this.setStatus('closed');
  }

  subscribe(dialogIds: string[]): void {
    const fresh: string[] = [];
    dialogIds.filter(Boolean).forEach((id) => {
      const count = this.refs.get(id) ?? 0;
      this.refs.set(id, count + 1);
      if (count === 0) fresh.push(id);
    });
    if (fresh.length) this.send({ op: 'subscribe', dialog_ids: fresh });
  }

  unsubscribe(dialogIds: string[]): void {
    const gone: string[] = [];
    dialogIds.filter(Boolean).forEach((id) => {
      const count = this.refs.get(id) ?? 0;
      if (count <= 1) {
        this.refs.delete(id);
        gone.push(id);
      } else {
        this.refs.set(id, count - 1);
      }
    });
    if (gone.length) this.send({ op: 'unsubscribe', dialog_ids: gone });
  }

  addListener(listener: EventListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  addStatusListener(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    listener(this.currentStatus);
    return () => {
      this.statusListeners.delete(listener);
    };
  }

  private open(): void {
    if (!this.token) return;
    this.clearTimers();
    this.setStatus('connecting');

    let socket: WebSocket;
    try {
      socket = new WebSocket(wsUrl(this.token));
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.onopen = () => {
      this.attempt = 0;
      this.setStatus('open');
      this.resendSubscriptions();
      this.startPing();
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      let payload: unknown;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (!payload || typeof payload !== 'object') return;
      const data = payload as WsRawEvent;
      if ('op' in data && data.op === 'pong') return;
      this.listeners.forEach((listener) => {
        try {
          listener(data as WsServerEvent);
        } catch {
          /* 单个订阅者异常不影响其它 */
        }
      });
    };

    socket.onerror = () => {
      /* 具体原因由 onclose 统一处理 */
    };

    socket.onclose = () => {
      this.stopPing();
      if (this.socket === socket) this.socket = null;
      this.setStatus('closed');
      if (!this.closedByUs) this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.closedByUs || !this.token || this.reconnectTimer !== null) return;
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** this.attempt) + Math.floor(Math.random() * 300);
    this.attempt += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.open();
    }, delay);
  }

  private resendSubscriptions(): void {
    const ids = [...this.refs.keys()];
    if (ids.length) this.send({ op: 'subscribe', dialog_ids: ids });
  }

  private send(payload: Record<string, unknown>): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(payload));
    }
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = window.setInterval(() => this.send({ op: 'ping' }), PING_INTERVAL_MS);
  }

  private stopPing(): void {
    if (this.pingTimer !== null) {
      window.clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private clearTimers(): void {
    this.stopPing();
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private setStatus(status: WsStatus): void {
    if (this.currentStatus === status) return;
    this.currentStatus = status;
    this.statusListeners.forEach((listener) => {
      try {
        listener(status);
      } catch {
        /* 忽略 */
      }
    });
  }
}

export const wsClient = new WsClient();

export interface UseWebSocketResult {
  status: WsStatus;
  subscribe: (dialogIds: string[]) => void;
  unsubscribe: (dialogIds: string[]) => void;
  /** 注册事件监听，返回取消函数 */
  onEvent: (listener: EventListener) => () => void;
}

/**
 * 组件里用这个 hook 拿连接状态、订阅会话、监听推送。
 * 连接在 token 就绪时建立，退出登录（token 清空）时自动断开。
 */
export function useWebSocket(enabled = true): UseWebSocketResult {
  const { token } = useAuth();
  const [status, setStatus] = useState<WsStatus>(wsClient.status);

  useEffect(() => {
    if (!enabled || !token || !getToken()) {
      wsClient.disconnect();
      setStatus('closed');
      return;
    }
    wsClient.connect(token);
    const off = wsClient.addStatusListener(setStatus);
    return () => {
      off();
      // 退出登录 / token 失效导致组件卸载时把连接收掉
      if (!getToken()) wsClient.disconnect();
    };
  }, [enabled, token]);

  const subscribe = useCallback((dialogIds: string[]) => wsClient.subscribe(dialogIds), []);
  const unsubscribe = useCallback((dialogIds: string[]) => wsClient.unsubscribe(dialogIds), []);
  const onEvent = useCallback((listener: EventListener) => wsClient.addListener(listener), []);

  return { status, subscribe, unsubscribe, onEvent };
}

export const WS_STATUS_TEXT: Record<WsStatus, string> = {
  open: '实时连接正常',
  connecting: '实时连接中…',
  closed: '实时连接已断开',
};
