/**
 * EmptyState —— 统一空态（纯 SVG 插画，不引额外依赖）。
 *
 * props 契约：
 * ┌──────────────┬──────────────────────────────────────────────────────────────┐
 * │ art          │ 'search'|'list'|'chart'|'inbox'|'error'|'accounts'|'message' │
 * │              │ |'task'|'network'|ReactNode  默认 'inbox'                    │
 * │ title        │ ReactNode  默认「暂无数据」                                   │
 * │ description  │ ReactNode  一句话说明「为什么空 / 下一步做什么」               │
 * │ action       │ ReactNode  主引导按钮（如 <Button type="primary">新建账号</Button>）│
 * │ secondaryAction │ ReactNode 次要按钮                                        │
 * │ compact      │ boolean    卡片内嵌用，尺寸更小（默认 false）                  │
 * │ children     │ ReactNode  追加内容（例如提示列表）                            │
 * │ className    │ string                                                        │
 * └──────────────┴──────────────────────────────────────────────────────────────┘
 * 用法：<EmptyState art="search" title="没有匹配的账号" description="试着放宽筛选条件"
 *                  action={<Button onClick={onReset}>重置筛选</Button>} />
 */
import type { CSSProperties, ReactNode } from 'react';

export type EmptyArt =
  | 'search'
  | 'list'
  | 'chart'
  | 'inbox'
  | 'error'
  | 'accounts'
  | 'message'
  | 'task'
  | 'network';

export interface EmptyStateProps {
  art?: EmptyArt | ReactNode;
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  secondaryAction?: ReactNode;
  compact?: boolean;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}

const ART_SIZE = 40;

function Art({ kind }: { kind: EmptyArt }) {
  const common = {
    width: ART_SIZE,
    height: ART_SIZE,
    viewBox: '0 0 48 48',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.5,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  };
  switch (kind) {
    case 'search':
      return (
        <svg {...common}>
          <circle cx="21" cy="21" r="12" />
          <path d="M30 30l10 10" />
          <path d="M16 21h10" />
        </svg>
      );
    case 'chart':
      return (
        <svg {...common}>
          <path d="M8 38h32" />
          <path d="M12 32V20" />
          <path d="M20 32V12" />
          <path d="M28 32v-8" />
          <path d="M36 32V16" />
        </svg>
      );
    case 'accounts':
      return (
        <svg {...common}>
          <circle cx="20" cy="18" r="7" />
          <path d="M8 38c0-6.1 5.4-10 12-10s12 3.9 12 10" />
          <path d="M34 20h8" />
          <path d="M38 16v8" />
        </svg>
      );
    case 'message':
      return (
        <svg {...common}>
          <path d="M10 12h28a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H22l-8 7v-7h-4a2 2 0 0 1-2-2V14a2 2 0 0 1 2-2z" />
          <path d="M17 20h14" />
          <path d="M17 25h9" />
        </svg>
      );
    case 'task':
      return (
        <svg {...common}>
          <rect x="10" y="9" width="28" height="30" rx="3" />
          <path d="M17 17h14" />
          <path d="M17 24h14" />
          <path d="M17 31h8" />
        </svg>
      );
    case 'network':
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="15" />
          <path d="M9 24h30" />
          <path d="M24 9c4.5 4.6 6.8 9.6 6.8 15S28.5 34.4 24 39c-4.5-4.6-6.8-9.6-6.8-15S19.5 13.6 24 9z" />
        </svg>
      );
    case 'error':
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="15" />
          <path d="M24 16v10" />
          <path d="M24 31.5h.01" />
        </svg>
      );
    case 'list':
      return (
        <svg {...common}>
          <rect x="10" y="10" width="28" height="28" rx="3" />
          <path d="M16 18h16" />
          <path d="M16 24h16" />
          <path d="M16 30h9" />
        </svg>
      );
    case 'inbox':
    default:
      return (
        <svg {...common}>
          <path d="M10 28l4-14h20l4 14v8a2 2 0 0 1-2 2H12a2 2 0 0 1-2-2v-8z" />
          <path d="M10 28h8l2 4h8l2-4h8" />
        </svg>
      );
  }
}

export function EmptyState({
  art = 'inbox',
  title = '暂无数据',
  description,
  action,
  secondaryAction,
  compact = false,
  className,
  style,
  children,
}: EmptyStateProps) {
  const isNode = art !== null && typeof art === 'object';
  return (
    <div className={['tg-empty', compact ? 'is-compact' : '', className].filter(Boolean).join(' ')} style={style}>
      <div className="tg-empty-art">{isNode ? (art as ReactNode) : <Art kind={art as EmptyArt} />}</div>
      {title ? <div className="tg-empty-title">{title}</div> : null}
      {description ? <div className="tg-empty-desc">{description}</div> : null}
      {action || secondaryAction ? (
        <div className="tg-empty-actions">
          {action}
          {secondaryAction}
        </div>
      ) : null}
      {children}
    </div>
  );
}

export default EmptyState;
