/**
 * RelativeTime —— 相对时间（3 分钟前），悬浮显示绝对时间，到点自动刷新。
 *
 * props 契约：
 * ┌─────────────┬────────────────────────────────────────────────────────────┐
 * │ value       │ string|null  后端 ISO8601（UTC）时间戳                      │
 * │ fallback    │ string   value 为空时展示，默认 '—'                          │
 * │ refreshMs   │ number   自动重算间隔，默认 30000（0 = 不自动刷新）           │
 * │ showAbsolute│ boolean  是否在相对时间后附带绝对时间，默认 false              │
 * │ prefix      │ ReactNode 前缀（如 <ClockCircleOutlined />）                │
 * │ className   │ string                                                      │
 * └─────────────┴────────────────────────────────────────────────────────────┘
 * 用法：<RelativeTime value={account.last_heartbeat} />（心跳列）
 */
import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { Tooltip } from 'antd';
import dayjs from 'dayjs';
import { formatTime } from '../utils/format';

export interface RelativeTimeProps {
  value?: string | null;
  fallback?: string;
  refreshMs?: number;
  showAbsolute?: boolean;
  prefix?: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export function RelativeTime({
  value,
  fallback = '—',
  refreshMs = 30_000,
  showAbsolute = false,
  prefix,
  className,
  style,
}: RelativeTimeProps) {
  const [, forceTick] = useState(0);

  useEffect(() => {
    if (!value || refreshMs <= 0) return;
    const timer = window.setInterval(() => forceTick((n) => n + 1), refreshMs);
    return () => window.clearInterval(timer);
  }, [value, refreshMs]);

  if (!value) return <span className={className} style={style}>{fallback}</span>;

  const parsed = dayjs(value);
  if (!parsed.isValid()) {
    return (
      <span className={className} style={style}>
        {String(value)}
      </span>
    );
  }

  const relative = parsed.fromNow();
  const absolute = formatTime(value);

  return (
    <Tooltip title={absolute}>
      <span className={className} style={style}>
        {prefix}
        {relative}
        {showAbsolute ? <span className="tg-muted">（{absolute}）</span> : null}
      </span>
    </Tooltip>
  );
}

export default RelativeTime;
