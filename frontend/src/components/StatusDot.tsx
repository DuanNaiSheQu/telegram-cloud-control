/**
 * StatusDot —— 状态圆点（账号 7 态 / 任务状态 / 任意语义色）。
 *
 * props 契约：
 * ┌───────────┬──────────────────────────────────────────────────────────────┐
 * │ status    │ AccountStatus | TaskStatus | null  状态值                    │
 * │ kind      │ 'account' | 'task'  默认 'account'（决定取哪组 token）        │
 * │ tone      │ Tone  直接指定语义色，传了就忽略 status/kind                   │
 * │ size      │ number  直径 px，默认 8                                       │
 * │ pulse     │ boolean 呼吸动画（运行中 / 在线用）                            │
 * │ label     │ ReactNode  右侧文字                                          │
 * │ tooltip   │ ReactNode  悬浮说明（一般放 status_reason / last_error）       │
 * │ className │ string                                                        │
 * └───────────┴──────────────────────────────────────────────────────────────┘
 * 颜色全部来自 CSS 变量：--tg-color-account-<status>-dot / --tg-color-task-<status>-dot / --tg-color-<tone>
 */
import type { CSSProperties, ReactNode } from 'react';
import { Tooltip } from 'antd';
import type { AccountStatus, TaskStatus } from '../api/types';
import { ACCOUNT_STATUS_LABELS, TASK_STATUS_LABELS, type Tone } from '../constants';

export interface StatusDotProps {
  status?: AccountStatus | TaskStatus | null;
  kind?: 'account' | 'task';
  tone?: Tone;
  size?: number;
  pulse?: boolean;
  label?: ReactNode;
  tooltip?: ReactNode;
  className?: string;
  style?: CSSProperties;
}

function resolveColor(kind: 'account' | 'task', status?: string | null, tone?: Tone): string {
  if (tone) return `var(--tg-color-${tone})`;
  if (!status) return 'var(--tg-color-neutral)';
  return kind === 'account'
    ? `var(--tg-color-account-${status}-dot)`
    : `var(--tg-color-task-${status}-dot)`;
}

export function StatusDot({
  status,
  kind = 'account',
  tone,
  size = 8,
  pulse = false,
  label,
  tooltip,
  className,
  style,
}: StatusDotProps) {
  const color = resolveColor(kind, status as string | null | undefined, tone);
  const text =
    label ??
    (status
      ? kind === 'account'
        ? ACCOUNT_STATUS_LABELS[status as AccountStatus]
        : TASK_STATUS_LABELS[status as TaskStatus]
      : undefined);

  const dot = (
    <span
      className={['tg-status-dot', pulse ? 'is-pulse' : '', className].filter(Boolean).join(' ')}
      style={{
        width: size,
        height: size,
        background: color,
        color,
        ...style,
      }}
      aria-hidden={text ? undefined : true}
    />
  );

  const content = (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--tg-color-text-secondary)' }}>
      {dot}
      {text ? <span>{text}</span> : null}
    </span>
  );

  return tooltip ? <Tooltip title={tooltip}>{content}</Tooltip> : content;
}

export default StatusDot;
