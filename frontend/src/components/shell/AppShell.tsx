/**
 * AppShell —— 工作台外壳：侧栏 + 顶栏 + 内容区（+ 窄屏抽屉 + 全局搜索）。
 *
 * 结构：
 *   <AppShell>            → 内含 <Outlet/>，放在受保护路由的 element 里
 *     <Sidebar/>          → 分组导航 + 折叠 + 角标
 *     <Topbar/>           → 面包屑 + 搜索 + 连接状态 + 主题 + 通知 + 用户
 *     <main class="app-content"><div class="app-content-inner"><Outlet/></div></main>
 *
 * 自适应：≥1280 侧栏展开；1024~1279 折叠为图标条；<1024 改为左侧抽屉。
 * 内容区最大宽度由 token --tg-layout-content-max-width 控制（1920 下居中）。
 */
import { Suspense, useEffect, useState } from 'react';
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Badge, Drawer } from 'antd';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import GlobalSearch from './GlobalSearch';
import { matchNavTrail } from './nav';
import { useShellData } from './useShellData';
import { useAuth } from '../../auth/AuthContext';
import { useBreakpoint } from '../../hooks/useMediaQuery';
import { useLocalStorage } from '../../hooks/useLocalStorage';
import { useWebSocket } from '../../hooks/useWebSocket';
import { USER_ROLE_LABELS } from '../../constants';
import { ErrorBoundary } from '../ErrorBoundary';
import { PageSkeleton } from '../LoadingSkeleton';

const SIDEBAR_STORAGE_KEY = 'tgcc_ui:sidebar_collapsed';

export function AppShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { isNarrow, isCompact } = useBreakpoint();
  /**
   * 折叠状态分两层：
   *  - userCollapsed：用户手动点过折叠按钮的结果，持久化到 localStorage；
   *  - collapsed：实际生效值 = 用户显式选择 ?? 窄屏(<1280)自动折叠。
   * 这样做的好处是「在 1024 上自动收起」不会被写进本地存储，
   * 换到 1440 大屏后侧栏会自己展开，不会永久卡在折叠态。
   */
  const [userCollapsed, setUserCollapsed] = useLocalStorage<boolean | null>(SIDEBAR_STORAGE_KEY, null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  const shell = useShellData();
  const { status: wsStatus } = useWebSocket(true);

  const collapsed = isNarrow ? true : (userCollapsed ?? isCompact);
  const toggleCollapse = () => setUserCollapsed(!collapsed);

  // ⌘K / Ctrl+K 唤起全局搜索
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setSearchOpen((open) => !open);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  // 路由变化时关掉窄屏抽屉
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  // 面包屑走完整链：运营 / 营销中心 / 素材库（子菜单模式的层级在这里也看得见，前级可点击）
  const matched = matchNavTrail(location.pathname);
  const breadcrumb = matched
    ? [
        { title: matched.group.title },
        ...matched.trail.map((node, index) => ({
          title: node.label,
          // 前级给可跳转地址：父节点（营销中心）进它的第一个子页面
          href:
            index < matched.trail.length - 1 ? node.children?.[0]?.path ?? node.path : undefined,
        })),
      ]
    : [{ title: '控制台' }];

  const sidebar = (
    <Sidebar
      collapsed={isNarrow ? false : collapsed}
      counts={shell.counts}
      activePath={location.pathname}
      onNavigate={() => setDrawerOpen(false)}
      onToggleCollapse={isNarrow ? undefined : toggleCollapse}
      showCollapseButton={!isNarrow}
    />
  );

  return (
    <div className="app-shell">
      {isNarrow ? (
        <Drawer
          open={drawerOpen}
          placement="left"
          onClose={() => setDrawerOpen(false)}
          closable={false}
          width={264}
          styles={{ body: { padding: 0, background: 'var(--tg-color-bg-sider)' } }}
        >
          {sidebar}
        </Drawer>
      ) : (
        sidebar
      )}

      <div className="app-main">
        <Topbar
          breadcrumb={breadcrumb}
          sidebarCollapsed={collapsed}
          isNarrow={isNarrow}
          onToggleSidebar={() => (isNarrow ? setDrawerOpen(true) : toggleCollapse())}
          onOpenSearch={() => setSearchOpen(true)}
          wsStatus={wsStatus}
          notifications={{
            items: shell.notifications,
            unread: shell.unreadNotifications,
            loading: shell.notificationsLoading,
            derived: shell.notificationsAreDerived,
            onRefresh: shell.refreshNotifications,
            onMarkRead: (id) => void shell.markRead(id),
            onMarkAllRead: () => void shell.markAllRead(),
            onNavigate: (link) => navigate(link),
          }}
          user={{
            name: user?.display_name || user?.username || '未登录',
            roleLabel: user ? USER_ROLE_LABELS[user.role] ?? user.role : '—',
            isAdmin: user?.role === 'admin',
            onLogout: () => void logout(),
          }}
        />

        <main className="app-content">
          <div className="app-content-inner">
            {/* 每个页面各自一个错误边界：某个页面崩了，外壳和其它页面照常可用。
                路由级懒加载的骨架放在外壳内，切页时侧栏/顶栏不闪。 */}
            <ErrorBoundary key={location.pathname}>
              <Suspense fallback={<PageSkeleton />}>
                <Outlet />
              </Suspense>
            </ErrorBoundary>
          </div>
        </main>
      </div>

      <GlobalSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}

/** 未登录时兜底：直接回登录页（校验中显示骨架，避免刷新闪回登录页） */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, token, ready } = useAuth();
  if (!ready) {
    return (
      <div className="app-center">
        <Badge status="processing" text="正在校验登录状态…" />
      </div>
    );
  }
  if (!user || !token) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

export default AppShell;
