/**
 * Sidebar —— 子菜单式导航：分组可折叠、含子项的菜单可展开、当前项高亮 + 未读/异常角标。
 *
 * props 契约：
 * ┌──────────────────┬──────────────────────────────────────────────────────────┐
 * │ collapsed        │ boolean  折叠态（只显示图标 + Tooltip，子菜单不展开）        │
 * │ counts           │ ShellCounts  角标数据（useShellData 提供）                 │
 * │ activePath       │ string  当前路径（决定高亮与自动展开）                      │
 * │ onNavigate       │ () => void  点击导航后回调（窄屏抽屉里用来关闭自己）        │
 * │ onToggleCollapse │ () => void  底部折叠按钮（不传则不显示）                    │
 * │ className/style  │                                                          │
 * └──────────────────┴──────────────────────────────────────────────────────────┘
 *
 * 展开状态：
 * - 分组折叠、父项展开都记在 localStorage（键 tgcc_nav_state），刷新后保持原样；
 * - 当前路径所在的父链自动展开（点深层链接进来也能看到自己在哪）；
 * - 侧栏整体折叠时只留一级图标：含子项的项直接进它的第一个子页面（Tooltip 说明）。
 */
import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { Tooltip } from 'antd';
import { DownOutlined, MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons';
import { NAV_GROUPS, parentsOf, type NavGroup, type NavItem } from './nav';
import { useLocalStorage } from '../../hooks/useLocalStorage';
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

interface NavOpenState {
  /** 被收起的分组 key */
  closedGroups: string[];
  /** 被收起的父项 path（营销中心这类） */
  closedItems: string[];
}

const NAV_STATE_KEY = 'tgcc_nav_state';

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

/** 该项（或它的任一子项）是否命中当前路径 */
function itemActive(item: NavItem, activePath: string): boolean {
  if (item.children?.length) return item.children.some((child) => isActive(child.path, activePath));
  return isActive(item.path, activePath);
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
  const [openState, setOpenState] = useLocalStorage<NavOpenState>(NAV_STATE_KEY, {
    closedGroups: [],
    closedItems: [],
  });
  const autoParents = useMemo(() => parentsOf(activePath), [activePath]);
  // 用户本次会话里手动展开过的父项（点击后立即生效，不受历史收起记录影响）
  const [justOpened, setJustOpened] = useState<string[]>([]);

  // 进入深层页面时，把父链从「被收起」名单里移除：保证高亮项可见
  useEffect(() => {
    if (!autoParents.length) return;
    setOpenState((prev) => {
      const groupKeys = NAV_GROUPS.filter((group) => group.items.some((item) => item.path === autoParents[0])).map(
        (group) => group.key,
      );
      const closedItems = prev.closedItems.filter((path) => !autoParents.includes(path));
      const closedGroups = prev.closedGroups.filter((key) => !groupKeys.includes(key));
      if (closedItems.length === prev.closedItems.length && closedGroups.length === prev.closedGroups.length) {
        return prev;
      }
      return { closedGroups, closedItems };
    });
  }, [autoParents, setOpenState]);

  const groupOpen = (group: NavGroup) => !openState.closedGroups.includes(group.key);

  const itemOpen = (item: NavItem) =>
    justOpened.includes(item.path) || !openState.closedItems.includes(item.path);

  const toggleGroup = (group: NavGroup) =>
    setOpenState((prev) => ({
      ...prev,
      closedGroups: prev.closedGroups.includes(group.key)
        ? prev.closedGroups.filter((key) => key !== group.key)
        : [...prev.closedGroups, group.key],
    }));

  const toggleItem = (item: NavItem) =>
    setOpenState((prev) => {
      const isClosed = prev.closedItems.includes(item.path) && !justOpened.includes(item.path);
      if (isClosed) setJustOpened((list) => [...list, item.path]);
      else setJustOpened((list) => list.filter((path) => path !== item.path));
      return {
        ...prev,
        closedItems: isClosed
          ? prev.closedItems.filter((path) => path !== item.path)
          : [...new Set([...prev.closedItems, item.path])],
      };
    });

  const renderLeaf = (item: NavItem, depth: 1 | 2) => {
    const badge = badgeFor(item, counts);
    const active = isActive(item.path, activePath);
    const link = (
      <Link
        to={item.path}
        className={['app-nav-item', depth === 2 ? 'is-sub' : '', active ? 'is-active' : '']
          .filter(Boolean)
          .join(' ')}
        onClick={onNavigate}
        aria-current={active ? 'page' : undefined}
      >
        {item.icon ? <span className="app-nav-icon">{item.icon}</span> : null}
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
  };

  const renderItem = (item: NavItem) => {
    if (!item.children?.length) return <div key={item.path}>{renderLeaf(item, 1)}</div>;

    const active = itemActive(item, activePath);
    const first = item.children[0];
    // 整栏折叠：只给一个入口，直接进第一个子页面
    if (collapsed) {
      return (
        <div key={item.path}>
          <Tooltip title={`${item.label}（进入「${first.label}」）`} placement="right">
            <Link
              to={first.path}
              className={['app-nav-item', active ? 'is-active' : ''].filter(Boolean).join(' ')}
              onClick={onNavigate}
            >
              <span className="app-nav-icon">{item.icon}</span>
            </Link>
          </Tooltip>
        </div>
      );
    }

    const open = itemOpen(item);
    return (
      <div key={item.path} className="app-nav-parent">
        <button
          type="button"
          className={['app-nav-item', 'is-parent', active ? 'is-active' : ''].filter(Boolean).join(' ')}
          onClick={() => toggleItem(item)}
          aria-expanded={open}
          aria-label={`${item.label}（${open ? '收起' : '展开'}子菜单）`}
        >
          <span className="app-nav-icon">{item.icon}</span>
          <span className="app-nav-label">{item.label}</span>
          <DownOutlined className={['app-nav-chevron', open ? 'is-open' : ''].filter(Boolean).join(' ')} />
        </button>
        {open ? <div className="app-nav-sub">{item.children.map((child) => renderLeaf(child, 2))}</div> : null}
      </div>
    );
  };

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
        {NAV_GROUPS.map((group) => {
          const open = groupOpen(group);
          return (
            <div className={['app-nav-group', open ? '' : 'is-collapsed'].filter(Boolean).join(' ')} key={group.key}>
              {!collapsed ? (
                <button
                  type="button"
                  className="app-nav-group-title"
                  onClick={() => toggleGroup(group)}
                  aria-expanded={open}
                >
                  <span>{group.title}</span>
                  <DownOutlined className={['app-nav-chevron', open ? 'is-open' : ''].filter(Boolean).join(' ')} />
                </button>
              ) : (
                <div className="app-nav-group-divider" aria-hidden />
              )}
              <div className="app-nav-group-body">{group.items.map((item) => renderItem(item))}</div>
            </div>
          );
        })}
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
          {!collapsed ? (
            <span className="tg-muted" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
              v1.0.0
            </span>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}

export default Sidebar;
