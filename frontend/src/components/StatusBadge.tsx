/**
 * StatusBadge —— 账号状态徽标（7 态配色走 token）。
 *
 * props 契约（向后兼容旧调用：<StatusBadge status label reason />）：
 * ┌───────────┬──────────────────────────────────────────────────────────────┐
 * │ status    │ AccountStatus | null  状态值                                 │
 * │ label     │ string  后端 status_label 优先，没有则用本地中文映射           │
 * │ reason    │ string  status_reason / last_error，悬浮显示                  │
 * │ size      │ 'sm' | 'md'  默认 'md'（sm 用于表格密集列）                    │
 * │ showDot   │ boolean  是否带圆点，默认 true                                │
 * │ variant   │ 'soft'（默认，浅底+描边）| 'outline' | 'text'                 │
 * │ className │ string                                                        │
 * └───────────┴──────────────────────────────────────────────────────────────┘
 * 颜色：--tg-color-account-<status>-{fg,bg,border,dot}（改 tokens.ts 即整体换色）
 */
import type { CSSProperties } from 'react';
import { Tooltip } from 'antd';
import type { AccountStatus } from '../api/types';
import { ACCOUNT_STATUS_LABELS } from '../constants';

export interface StatusBadgeProps {
  status?: AccountStatus | null;
  label?: string | null;
  reason?: string | null;
  size?: 'sm' | 'md';
  showDot?: boolean;
  variant?: 'soft' | 'outline' | 'text';
  className?: string;
  style?: CSSProperties;
}

export function StatusBadge({
  status,
  label,
  reason,
  size = 'md',
  showDot = true,
  variant = 'soft',
  className,
  style,
}: StatusBadgeProps) {
  const key = status ?? 'disabled';
  // 后端将来新增状态时，宁可显示「未知状态」也不要把英文枚举裸露给值班同事；原始值放 title 供排查
  const rawUnknown = status && !ACCOUNT_STATUS_LABELS[status] ? status : null;
  const text = label || (status ? ACCOUNT_STATUS_LABELS[status] : '') || (status ? '未知状态' : '未知');
  const known = Boolean(status);

  const colorFg = known ? `var(--tg-color-account-${key}-fg)` : 'var(--tg-color-neutral)';
  const colorBg = known ? `var(--tg-color-account-${key}-bg)` : 'var(--tg-color-neutral-bg)';
  const colorBorder = known ? `var(--tg-color-account-${key}-border)` : 'var(--tg-color-neutral-border)';
  const colorDot = known ? `var(--tg-color-account-${key}-dot)` : 'var(--tg-color-neutral)';

  const variantStyle: CSSProperties =
    variant === 'soft'
      ? { background: colorBg, borderColor: colorBorder, color: colorFg }
      : variant === 'outline'
        ? { background: 'transparent', borderColor: colorBorder, color: colorFg }
        : { background: 'transparent', borderColor: 'transparent', color: colorFg, paddingLeft: 0, paddingRight: 0 };

  const badge = (
    <span
      title={rawUnknown ? `未知状态（原始值：${rawUnknown}）` : reason || undefined}
      className={['tg-status-badge', className].filter(Boolean).join(' ')}
      style={{
        height: size === 'sm' ? 20 : 24,
        fontSize: size === 'sm' ? 'var(--tg-font-size-xs)' : 'var(--tg-font-size-sm)',
        ...variantStyle,
        ...style,
      }}
    >
      {showDot ? (
        <span
          className="tg-status-dot"
          style={{ width: 6, height: 6, background: colorDot, color: colorDot }}
          aria-hidden
        />
      ) : null}
      {text}
    </span>
  );

  return reason ? (
    <Tooltip title={reason}>
      <span style={{ cursor: 'help' }}>{badge}</span>
    </Tooltip>
  ) : (
    badge
  );
}

export default StatusBadge;
