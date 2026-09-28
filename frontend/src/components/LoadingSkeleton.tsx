/**
 * LoadingSkeleton —— 统一骨架屏（卡片 / 表格 / 列表 / 统计卡 / 图表 / 整页）。
 *
 * props 契约：
 *   <CardSkeleton rows={4} />                        区块加载
 *   <TableSkeleton rows={8} columns={6} />           表格加载（表头 + 行）
 *   <ListSkeleton rows={6} avatar />                 列表/会话列表加载
 *   <StatSkeleton count={4} />                       统计卡一行加载
 *   <ChartSkeleton height={220} />                   图表加载
 *   <PageSkeleton title />                           路由级 Suspense 兜底
 *
 * 通用 props：rows / columns / height / count / avatar / title / className / style
 * 全部用 token 变量着色，深色下不会出现白块。
 */
import type { CSSProperties, ReactNode } from 'react';

interface BlockProps {
  width?: number | string;
  height?: number | string;
  radius?: string;
  style?: CSSProperties;
}

function Block({ width = '100%', height = 12, radius = 'var(--tg-radius-sm)', style }: BlockProps) {
  return <div className="tg-skeleton-block" style={{ width, height, borderRadius: radius, ...style }} />;
}

export interface SkeletonProps {
  rows?: number;
  columns?: number;
  height?: number | string;
  count?: number;
  avatar?: boolean;
  title?: boolean;
  className?: string;
  style?: CSSProperties;
}

export function CardSkeleton({ rows = 4, title = true, className, style }: SkeletonProps) {
  return (
    <div className={['tg-skeleton', className].filter(Boolean).join(' ')} style={style} aria-busy="true" aria-live="polite">
      {title ? <Block width={140} height={16} /> : null}
      {Array.from({ length: rows }).map((_, index) => (
        <Block key={index} width={index === rows - 1 ? '62%' : '100%'} />
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 8, columns = 6, className, style }: SkeletonProps) {
  return (
    <div
      className={['tg-skeleton', className].filter(Boolean).join(' ')}
      style={{ gap: 'var(--tg-space-md)', padding: 'var(--tg-space-lg) 0', ...style }}
      aria-busy="true"
      aria-live="polite"
    >
      <div className="tg-skeleton-row" style={{ paddingBottom: 'var(--tg-space-md)' }}>
        {Array.from({ length: columns }).map((_, index) => (
          <Block key={index} height={14} width={index === 0 ? '18%' : '12%'} />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div className="tg-skeleton-row" key={rowIndex}>
          {Array.from({ length: columns }).map((_, colIndex) => (
            <Block
              key={colIndex}
              height={12}
              width={colIndex === 0 ? '18%' : `${8 + ((rowIndex + colIndex) % 4) * 2}%`}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function ListSkeleton({ rows = 6, avatar = true, className, style }: SkeletonProps) {
  return (
    <div className={['tg-skeleton', className].filter(Boolean).join(' ')} style={style} aria-busy="true" aria-live="polite">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} style={{ display: 'flex', gap: 'var(--tg-space-lg)', alignItems: 'center' }}>
          {avatar ? <Block width={36} height={36} radius="var(--tg-radius-md)" /> : null}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Block width={`${40 + ((index * 7) % 30)}%`} height={12} />
            <Block width={`${25 + ((index * 11) % 40)}%`} height={10} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function StatSkeleton({ count = 4, className, style }: SkeletonProps) {
  return (
    <div
      className={className}
      style={{ display: 'grid', gap: 'var(--tg-layout-page-gap)', gridTemplateColumns: `repeat(auto-fit, minmax(220px, 1fr))`, ...style }}
    >
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="tg-stat-card">
          <div className="tg-flex-between">
            <Block width={72} height={12} />
            <Block width={32} height={32} radius="var(--tg-radius-md)" />
          </div>
          <Block width={96} height={28} radius="var(--tg-radius-md)" />
          <Block width={120} height={10} />
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 220, className, style }: SkeletonProps) {
  return (
    <div
      className={['tg-skeleton', className].filter(Boolean).join(' ')}
      style={{ height, justifyContent: 'flex-end', ...style }}
      aria-busy="true"
    >
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 'var(--tg-space-md)', height: '100%' }}>
        {[45, 70, 35, 88, 60, 75, 52, 95, 40, 66, 58, 80].map((h, index) => (
          <Block key={index} height={`${h}%`} radius="var(--tg-radius-sm)" />
        ))}
      </div>
    </div>
  );
}

/** 路由级 Suspense 兜底：外壳已经在，只铺内容区 */
export function PageSkeleton({ title = true, className, style, children }: SkeletonProps & { children?: ReactNode }) {
  return (
    <div className={['tg-page', className].filter(Boolean).join(' ')} style={style} aria-busy="true" aria-live="polite">
      {title ? (
        <div className="tg-page-header-main">
          <Block width={180} height={22} radius="var(--tg-radius-md)" />
          <Block width={320} height={12} />
        </div>
      ) : null}
      <StatSkeleton count={4} />
      <div className="tg-card" style={{ padding: 'var(--tg-space-xl)' }}>
        <TableSkeleton rows={6} columns={5} />
      </div>
      {children}
    </div>
  );
}

export default PageSkeleton;
