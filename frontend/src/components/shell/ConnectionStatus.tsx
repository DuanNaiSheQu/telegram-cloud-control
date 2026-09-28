/**
 * ConnectionStatus —— 顶栏实时连接状态（WS /api/ws）。
 *
 * props 契约：
 * ┌──────────┬────────────────────────────────────────────────────────────────┐
 * │ status   │ 'connecting'|'open'|'closed'  不传则自己订阅（useWebSocket）    │
 * │ showText │ boolean  是否显示文字，默认 true（窄屏自动只显示圆点）           │
 * └──────────┴────────────────────────────────────────────────────────────────┘
 * 颜色：open=success / connecting=warning / closed=neutral（走 token）
 */
import { Tooltip } from 'antd';
import { WS_STATUS_TEXT, useWebSocket } from '../../hooks/useWebSocket';
import type { WsStatus } from '../../api/types';

export interface ConnectionStatusProps {
  status?: WsStatus;
  showText?: boolean;
}

const TONE_CLASS: Record<WsStatus, string> = {
  open: 'is-open',
  connecting: 'is-connecting',
  closed: 'is-closed',
};

const DOT_COLOR: Record<WsStatus, string> = {
  open: 'var(--tg-color-success)',
  connecting: 'var(--tg-color-warning)',
  closed: 'var(--tg-color-neutral)',
};

const HINT: Record<WsStatus, string> = {
  open: '新消息会实时推到当前打开的会话',
  connecting: '正在建立长连接，稍后自动重试',
  closed: '长连接已断开，页面会指数退避重连；数据仍以 Postgres 为准',
};

export function ConnectionStatus({ status: statusProp, showText = true }: ConnectionStatusProps) {
  // 始终以 enabled=true 订阅：wsClient 是单例，重复调用只会复用同一条连接；
  // 传 status 只是让外壳把状态透传下来（避免每个顶栏组件各自 setState）。
  const hook = useWebSocket(true);
  const status = statusProp ?? hook.status;

  return (
    <Tooltip title={`${WS_STATUS_TEXT[status]}（${HINT[status]}）`}>
      <span className={`app-conn ${TONE_CLASS[status]}`} role="status" aria-live="polite">
        <span
          className={['tg-status-dot', status === 'connecting' ? 'is-pulse' : ''].filter(Boolean).join(' ')}
          style={{ width: 7, height: 7, background: DOT_COLOR[status], color: DOT_COLOR[status] }}
        />
        {showText ? <span className="app-conn-text">{WS_STATUS_TEXT[status]}</span> : null}
      </span>
    </Tooltip>
  );
}

export default ConnectionStatus;
