/**
 * Topbar —— 顶栏：面包屑 + 全局搜索入口 + 实时连接状态 + 主题开关 + 通知铃铛 + 用户菜单。
 *
 * props 契约：
 * ┌──────────────────┬──────────────────────────────────────────────────────────┐
 * │ breadcrumb       │ {title, href?}[]  当前页面路径（由 AppShell 按路由推导）   │
 * │ onToggleSidebar  │ () => void  折叠/展开侧栏（窄屏是打开抽屉）               │
 * │ sidebarCollapsed │ boolean                                                │
 * │ isNarrow         │ boolean  窄屏下隐藏文字，只留图标                         │
 * │ onOpenSearch     │ () => void                                              │
 * │ searchShortcut   │ string  显示的快捷键提示，默认 '⌘K' / 'Ctrl K'           │
 * │ wsStatus         │ WsStatus                                                │
 * │ notifications    │ NotificationBell 的一组 props（透传）                     │
 * │ user             │ UserMenu 的一组 props（透传）                             │
 * └──────────────────┴──────────────────────────────────────────────────────────┘
 */
import { Tooltip } from 'antd';
import { MenuFoldOutlined, MenuUnfoldOutlined, SearchOutlined } from '@ant-design/icons';
import ConnectionStatus from './ConnectionStatus';
import NotificationBell, { type NotificationBellProps } from './NotificationBell';
import ThemeToggle from './ThemeToggle';
import UserMenu, { type UserMenuProps } from './UserMenu';
import type { WsStatus } from '../../api/types';

export interface TopbarProps {
  breadcrumb: Array<{ title: string; href?: string }>;
  onToggleSidebar: () => void;
  sidebarCollapsed: boolean;
  isNarrow: boolean;
  onOpenSearch: () => void;
  searchShortcut?: string;
  wsStatus?: WsStatus;
  notifications?: NotificationBellProps;
  user?: UserMenuProps;
}

export function Topbar({
  breadcrumb,
  onToggleSidebar,
  sidebarCollapsed,
  isNarrow,
  onOpenSearch,
  searchShortcut = /Mac|iPhone|iPad/.test(navigator.platform || '') ? '⌘K' : 'Ctrl K',
  wsStatus,
  notifications,
  user,
}: TopbarProps) {
  return (
    <header className="app-topbar">
      <div className="app-topbar-left">
        <button
          type="button"
          className="app-icon-button"
          onClick={onToggleSidebar}
          aria-label={isNarrow ? '打开导航' : sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
        >
          {sidebarCollapsed || isNarrow ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </button>

        <nav className="app-breadcrumb" aria-label="当前位置">
          {breadcrumb.map((crumb, index) => (
            <span key={`${crumb.title}-${index}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--tg-space-sm)' }}>
              {index > 0 ? <span className="app-breadcrumb-sep">/</span> : null}
              {index === breadcrumb.length - 1 ? (
                <span className="app-breadcrumb-current">{crumb.title}</span>
              ) : (
                <span>{crumb.title}</span>
              )}
            </span>
          ))}
        </nav>
      </div>

      <div className="app-topbar-right">
        <Tooltip title={`全局搜索（${searchShortcut}）`}>
          <button type="button" className="app-search-trigger" onClick={onOpenSearch} aria-label="全局搜索">
            <SearchOutlined />
            <span className="app-search-text">搜索账号、会话、消息…</span>
            <span className="tg-kbd">{searchShortcut}</span>
          </button>
        </Tooltip>

        <ConnectionStatus status={wsStatus} showText={!isNarrow} />

        <span className="app-topbar-divider" />

        <ThemeToggle />

        {notifications ? <NotificationBell {...notifications} /> : null}

        <span className="app-topbar-divider" />

        {user ? <UserMenu {...user} /> : null}
      </div>
    </header>
  );
}

export default Topbar;
