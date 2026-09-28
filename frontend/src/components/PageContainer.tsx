/**
 * PageContainer / PageHeader —— 页面头 + 内容容器（每个页面的第一层）。
 *
 * props 契约（PageContainer）：
 * ┌────────────┬────────────────────────────────────────────────────────────────┐
 * │ title      │ ReactNode  页面标题（必填，页面只有一个 h1）                     │
 * │ description│ ReactNode  一句话说明（取值口径 / 操作提示）                     │
 * │ actions    │ ReactNode  右上角操作区（主按钮放最右）                          │
 * │ breadcrumb │ {title, href?}[]  面包屑（不传则由外壳顶栏统一显示）             │
 * │ tabs       │ ReactNode  标题下方 Tabs（可选）                                │
 * │ gap        │ 'normal'|'tight'  区块间距，默认 normal（16 / 8 px）             │
 * │ children   │ ReactNode                                                       │
 * └────────────┴────────────────────────────────────────────────────────────────┘
 * 用法：
 *   <PageContainer title="账号管理" description="共 12 个号，异常 2 个"
 *                  actions={<Space><Button>同步</Button><Button type="primary">新建</Button></Space>}>
 *     <StatGrid>…</StatGrid>
 *     <DataTable … />
 *   </PageContainer>
 */
import type { CSSProperties, ReactNode } from 'react';
import { Link } from 'react-router-dom';

export interface Crumb {
  title: ReactNode;
  href?: string;
}

export interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  breadcrumb?: Crumb[];
  tabs?: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export function PageHeader({ title, description, actions, breadcrumb, tabs, className, style }: PageHeaderProps) {
  return (
    <header className={['tg-page-header', className].filter(Boolean).join(' ')} style={style}>
      <div className="tg-page-header-main">
        {breadcrumb && breadcrumb.length ? (
          <nav className="app-breadcrumb" aria-label="面包屑">
            {breadcrumb.map((crumb, index) => (
              <span key={`${String(crumb.title)}-${index}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--tg-space-sm)' }}>
                {index > 0 ? <span className="app-breadcrumb-sep">/</span> : null}
                {crumb.href ? <Link to={crumb.href}>{crumb.title}</Link> : <span>{crumb.title}</span>}
              </span>
            ))}
          </nav>
        ) : null}
        <h1 className="tg-page-title">{title}</h1>
        {description ? <p className="tg-page-desc">{description}</p> : null}
      </div>
      {actions ? <div className="tg-page-actions">{actions}</div> : null}
      {tabs ? <div style={{ flexBasis: '100%' }}>{tabs}</div> : null}
    </header>
  );
}

export interface PageContainerProps extends PageHeaderProps {
  children: ReactNode;
  gap?: 'normal' | 'tight';
}

export function PageContainer({
  title,
  description,
  actions,
  breadcrumb,
  tabs,
  children,
  gap = 'normal',
  className,
  style,
}: PageContainerProps) {
  return (
    <div
      className={['tg-page', className].filter(Boolean).join(' ')}
      style={{ gap: gap === 'tight' ? 'var(--tg-space-md)' : undefined, ...style }}
    >
      <PageHeader
        title={title}
        description={description}
        actions={actions}
        breadcrumb={breadcrumb}
        tabs={tabs}
      />
      {children}
    </div>
  );
}

/** 统计卡一行（自动换行：1280 下 4 个，1920 下 6 个，窄屏 2 个） */
export function StatGrid({ children, minWidth = 210, className, style }: { children: ReactNode; minWidth?: number; className?: string; style?: CSSProperties }) {
  return (
    <div
      className={className}
      style={{
        display: 'grid',
        gap: 'var(--tg-layout-page-gap)',
        gridTemplateColumns: `repeat(auto-fit, minmax(${minWidth}px, 1fr))`,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export default PageContainer;
