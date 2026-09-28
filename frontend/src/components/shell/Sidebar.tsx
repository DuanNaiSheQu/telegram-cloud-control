/**
 * Sidebar —— 分组导航 + 折叠 + 当前项高亮 + 未读/异常角标。
 *
 * props 契约：
 * ┌──────────────────┬──────────────────────────────────────────────────────────┐
 * │ collapsed        │ boolean  折叠态（只显示图标 + Tooltip）                    │
 * │ counts           │ ShellCounts  角标数据（useShellData 提供）                 │
 * │ onNavigate       │ () => void  点击导航后回调（窄屏抽屉里用来关闭自己）        │
 * │ onToggleCollapse │ () => void  底部折叠按钮（不传则不显示）                   │
 * │ className/style  │                                                          │
 * └──────────────────┴──────────────────────────────────────────────────────────┘
 * 角标口径：workbench 无角标；任务中心=失败(危险)/待执行(警告)；账号管理=异常；
 *          会话=未读；账号检测=异常。
 */
import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { Tooltip } from 'antd';
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons';
import { NAV_GROUPS, type NavItem } from './nav';
import type { ShellCounts } from './useShellData';

export interface SidebarProps {
  collapsed?: boolean;
  counts: ShellCounts;
  activePath: string;
  onNavigate?: () => void;
  onToggleCollapse?: () => void;
  /** 折叠按钮图标方向（抽屉里隐藏） */
  showCollapseButton?: boolean;
  className?: string;
  style?: CSSProperties;
}

function badgeFor(item: NavItem, counts: ShellCounts): { text: string; tone: string } | null {
  switch (item.badge) {
    case 'abnormal':
      return counts.abnormal > 0 ? { text: String(counts.abnormal), tone: 'is-danger' } : null;
    case 'failed':
      if (counts.failed > 0) return { text: String(counts.failed), tone: 'is-danger' };
      if (counts.pending > 0) return { text: String(counts.pending), tone: 'is-warning' };
      return null;
    case 'unread':
      return counts.unread > 0
        ? { text: counts.unread > 99 ? '99+' : String(counts.unread), tone: 'is-info' }
        : null;
    case 'pending':
      return counts.pending > 0 ? { text: String(counts.pending), tone: 'is-warning' } : null;
    default:
      return null;
  }
}

function isActive(path: string, activePath: string): boolean {
  if (path === '/') return activePath === '/';
  return activePath === path || activePath.startsWith(`${path}/`);
}

export function Sidebar({
  collapsed = false,
  counts,
  activePath,
  onNavigate,
  onToggleCollapse,
  showCollapseButton = true,
  className,
  style,
}: SidebarProps) {
  return (
    <aside
      className={['app-sider', collapsed ? 'is-collapsed' : '', className].filter(Boolean).join(' ')}
      style={style}
      aria-label="主导航"
    >
      <div className="app-logo">
        <span className="app-logo-mark">TG</span>
        {!collapsed ? (
          <span className="app-logo-text">
            Telegram 云控
            <span className="app-logo-sub">内部运维控制台</span>
          </span>
        ) : null}
      </div>

      <nav className="app-nav">
        {NAV_GROUPS.map((group) => (
          <div className="app-nav-group" key={group.key}>
            {!collapsed ? <div className="app-nav-group-title">{group.title}</div> : null}
            {group.items.map((item) => {
              const badge = badgeFor(item, counts);
              const link = (
                <Link
                  to={item.path}
                  className={['app-nav-item', isActive(item.path, activePath) ? 'is-active' : '']
                    .filter(Boolean)
                    .join(' ')}
                  onClick={onNavigate}
                  aria-current={isActive(item.path, activePath) ? 'page' : undefined}
                >
                  <span className="app-nav-icon">{item.icon}</span>
                  {!collapsed ? (
                    <>
                      <span className="app-nav-label">{item.label}</span>
                      {badge ? <span className={`app-nav-badge ${badge.tone}`}>{badge.text}</span> : null}
                    </>
                  ) : null}
                </Link>
              );
              return (
                <div key={item.path}>
                  {collapsed ? (
                    <Tooltip title={badge ? `${item.label}（${badge.text}）` : item.label} placement="right">
                      {link}
                    </Tooltip>
                  ) : (
                    link
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </nav>

      {showCollapseButton && onToggleCollapse ? (
        <div className="app-sider-footer">
          <button
            type="button"
            className="app-icon-button"
            onClick={onToggleCollapse}
            aria-label={collapsed ? '展开侧栏' : '收起侧栏'}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </button>
          {!collapsed ? <span className="tg-muted" style={{ fontSize: 'var(--tg-font-size-xs)' }}>v1.0.0</span> : null}
        </div>
      ) : null}
    </aside>
  );
}

export default Sidebar;
