/**
 * SectionCard —— 区块卡片（标题 + 说明 + 右侧操作 + 内容），列表/图表/表单都套它。
 *
 * props 契约：
 * ┌──────────────┬────────────────────────────────────────────────────────────┐
 * │ title        │ ReactNode  标题（缺省则不渲染 header，只剩内容）              │
 * │ subtitle     │ ReactNode  标题下的一句话说明                                │
 * │ extra        │ ReactNode  右上角操作区（按钮 / 筛选 / Segmented）            │
 * │ children     │ ReactNode  内容                                             │
 * │ loading      │ boolean    显示骨架屏（默认 4 行）                          │
 * │ skeletonRows │ number     骨架行数，默认 4                                  │
 * │ error        │ string|null 失败态（显示 ErrorState + 重试）                 │
 * │ onRetry      │ () => void 失败态重试                                        │
 * │ empty        │ boolean|EmptyStateProps  内容为空时显示空态                   │
 * │ bodyPadding  │ 'normal'|'tight'|'none'  默认 'normal'（20 / 12 / 0 px）      │
 * │ hoverable    │ boolean    悬浮抬升（可点击卡片用）                          │
 * │ className    │ string / style?: CSSProperties                               │
 * └──────────────┴────────────────────────────────────────────────────────────┘
 * 用法：
 *   <SectionCard title="最近失败任务" subtitle="按创建时间倒序" extra={<Button>全部</Button>}>
 *     <DataTable … />
 *   </SectionCard>
 */
import type { CSSProperties, ReactNode } from 'react';
import EmptyState, { type EmptyStateProps } from './EmptyState';
import ErrorState from './ErrorState';
import { CardSkeleton } from './LoadingSkeleton';

export interface SectionCardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  extra?: ReactNode;
  children?: ReactNode;
  loading?: boolean;
  skeletonRows?: number;
  error?: string | null;
  onRetry?: () => void;
  empty?: boolean | EmptyStateProps;
  bodyPadding?: 'normal' | 'tight' | 'none';
  hoverable?: boolean;
  className?: string;
  style?: CSSProperties;
  id?: string;
}

export function SectionCard({
  title,
  subtitle,
  extra,
  children,
  loading = false,
  skeletonRows = 4,
  error,
  onRetry,
  empty,
  bodyPadding = 'normal',
  hoverable = false,
  className,
  style,
  id,
}: SectionCardProps) {
  const bodyClass = [
    'tg-section-body',
    bodyPadding === 'none' ? 'is-flush' : '',
    bodyPadding === 'tight' ? 'is-tight' : '',
  ]
    .filter(Boolean)
    .join(' ');

  let body: ReactNode = children;
  if (error) {
    body = <ErrorState error={error} onRetry={onRetry} compact />;
  } else if (loading) {
    body = <CardSkeleton rows={skeletonRows} />;
  } else if (empty) {
    body = <EmptyState compact {...(typeof empty === 'object' ? empty : {})} />;
  }

  return (
    <section
      id={id}
      className={['tg-card', hoverable ? 'is-hoverable' : '', className].filter(Boolean).join(' ')}
      style={style}
    >
      {title || extra ? (
        <header className="tg-section-card-header">
          <div className="tg-section-title-wrap">
            <div className="tg-section-title">{title}</div>
            {subtitle ? <div className="tg-section-subtitle">{subtitle}</div> : null}
          </div>
          {extra ? <div className="tg-section-extra">{extra}</div> : null}
        </header>
      ) : null}
      <div className={bodyClass}>{body}</div>
    </section>
  );
}

export default SectionCard;
