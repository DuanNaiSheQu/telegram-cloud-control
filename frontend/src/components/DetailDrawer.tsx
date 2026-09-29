/**
 * DetailDrawer —— 统一详情抽屉（右侧滑出，服务端数据 + 分区字段 + 底部操作）。
 *
 * props 契约：
 * ┌────────────┬────────────────────────────────────────────────────────────────┐
 * │ open       │ boolean                                                        │
 * │ title      │ ReactNode  标题（一般放主体名，如脱敏手机号）                    │
 * │ subtitle   │ ReactNode  标题下的辅助信息（用户名 / 分组 / 状态）              │
 * │ onClose    │ () => void                                                      │
 * │ width      │ number  默认 620（1920 下可给 720）                             │
 * │ loading    │ boolean  骨架态                                                 │
 * │ error      │ string|null  失败态（带重试）                                    │
 * │ onRetry    │ () => void                                                      │
 * │ sections   │ DetailSection[]  分区：{ title?, items?: DetailItem[], content? } │
 * │            │ DetailItem = { label, value, span?: 1|2|'full', mono?, copyable? }│
 * │ children   │ ReactNode  自定义内容（表格、时间线…）                            │
 * │ extra      │ ReactNode  头部右侧按钮                                          │
 * │ footer     │ ReactNode  底部操作条                                            │
 * │ skeletonRows│ number  默认 6                                                 │
 * └────────────┴────────────────────────────────────────────────────────────────┘
 * 用法：
 *   <DetailDrawer open={!!id} title={account.phone_masked} subtitle={<StatusBadge …/>}
 *     loading={loading} error={error} onRetry={reload}
 *     sections={[{ title:'基本信息', items:[{label:'用户 ID', value:<CopyableText …/>}] }]}
 *     footer={<Space><Button danger>停用</Button></Space>} />
 */
import type { ReactNode } from 'react';
import { Drawer, Typography } from 'antd';
import CopyableText from './CopyableText';
import ErrorState from './ErrorState';
import { CardSkeleton } from './LoadingSkeleton';

export interface DetailItem {
  label: ReactNode;
  value: ReactNode;
  /** 'full' 独占一行；数字为跨列数 */
  span?: 1 | 2 | 'full';
  mono?: boolean;
  copyable?: boolean;
}

export interface DetailSection {
  key?: string;
  title?: ReactNode;
  items?: DetailItem[];
  content?: ReactNode;
}

export interface DetailDrawerProps {
  open: boolean;
  title: ReactNode;
  subtitle?: ReactNode;
  onClose: () => void;
  width?: number;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  sections?: DetailSection[];
  children?: ReactNode;
  extra?: ReactNode;
  footer?: ReactNode;
  skeletonRows?: number;
  className?: string;
}

function renderValue(item: DetailItem): ReactNode {
  if (item.value === null || item.value === undefined || item.value === '') {
    return <span className="tg-detail-value is-empty">—</span>;
  }
  if (item.copyable && (typeof item.value === 'string' || typeof item.value === 'number')) {
    return <CopyableText value={item.value} mono={item.mono} />;
  }
  return <span className={['tg-detail-value', item.mono ? 'tg-mono' : ''].filter(Boolean).join(' ')}>{item.value}</span>;
}

export function DetailDrawer({
  open,
  title,
  subtitle,
  onClose,
  width = 620,
  loading = false,
  error,
  onRetry,
  sections = [],
  children,
  extra,
  footer,
  skeletonRows = 6,
  className,
}: DetailDrawerProps) {
  const hasContent = sections.length > 0 || Boolean(children);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={width}
      title={
        <div className="tg-stack" style={{ gap: 2 }}>
          <span style={{ fontWeight: 'var(--tg-font-weight-semibold)' }}>{title}</span>
          {subtitle ? (
            <Typography.Text type="secondary" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
              {subtitle}
            </Typography.Text>
          ) : null}
        </div>
      }
      extra={extra}
      footer={footer}
      destroyOnHidden
      className={className}
    >
      {error ? (
        <ErrorState error={error} onRetry={onRetry} />
      ) : loading && !hasContent ? (
        <CardSkeleton rows={skeletonRows} />
      ) : (
        <div className="tg-stack" style={{ gap: 'var(--tg-space-xxl)' }}>
          {loading ? <CardSkeleton rows={2} title={false} /> : null}
          {sections.map((section, index) => (
            <section className="tg-detail-section" key={section.key ?? index}>
              {section.title ? <div className="tg-detail-section-title">{section.title}</div> : null}
              {section.items?.length ? (
                <div className="tg-detail-grid">
                  {section.items.map((item, itemIndex) => (
                    <div
                      className={[
                        'tg-detail-item',
                        item.span === 'full' || item.span === 2 ? 'is-wide' : '',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      key={itemIndex}
                      style={typeof item.span === 'number' && item.span > 1 ? { gridColumn: `span ${item.span}` } : undefined}
                    >
                      <span className="tg-detail-label">{item.label}</span>
                      {renderValue(item)}
                    </div>
                  ))}
                </div>
              ) : null}
              {section.content}
            </section>
          ))}
          {children}
        </div>
      )}
    </Drawer>
  );
}

export default DetailDrawer;
