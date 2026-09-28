import { useMemo, useState } from 'react';
import { Link, Navigate, Outlet, useLocation } from 'react-router-dom';
import {
  Avatar,
  Badge,
  Button,
  Dropdown,
  Layout as AntLayout,
  Menu,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { MenuProps } from 'antd';
import {
  ApiOutlined,
  DashboardOutlined,
  FileSearchOutlined,
  FolderOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  ScheduleOutlined,
  ShareAltOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useAuth } from '../auth/AuthContext';
import { USER_ROLE_LABELS } from '../constants';
import { WS_STATUS_TEXT, useWebSocket } from '../hooks/useWebSocket';
import type { WsStatus } from '../api/types';

const { Header, Sider, Content } = AntLayout;

interface NavItem {
  path: string;
  label: string;
  icon: React.ReactNode;
}

/**
 * 侧栏顺序照 规划.md；「Bot 管理」「操作记录」是按后端契约新增的两个入口
 * （Bot 管理独立成页，不在 Bot 转发页里做 Tab，便于直接看 Token / Webhook 状态）。
 */
export const NAV_ITEMS: NavItem[] = [
  { path: '/', label: '工作台', icon: <DashboardOutlined /> },
  { path: '/tasks', label: '任务中心', icon: <ScheduleOutlined /> },
  { path: '/accounts', label: '账号管理', icon: <UserOutlined /> },
  { path: '/groups', label: '账号分组', icon: <FolderOutlined /> },
  { path: '/detection', label: '账号检测', icon: <SafetyCertificateOutlined /> },
  { path: '/network', label: '网络', icon: <ApiOutlined /> },
  { path: '/dialogs', label: '会话', icon: <MessageOutlined /> },
  { path: '/relay', label: 'Bot 转发', icon: <ShareAltOutlined /> },
  { path: '/bots', label: 'Bot 管理', icon: <RobotOutlined /> },
  { path: '/assignments', label: '员工分配', icon: <TeamOutlined /> },
  { path: '/audit', label: '操作记录', icon: <FileSearchOutlined /> },
];

const WS_BADGE_STATUS: Record<WsStatus, 'success' | 'processing' | 'default'> = {
  open: 'success',
  connecting: 'processing',
  closed: 'default',
};

export function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const { status } = useWebSocket(true);

  const selectedKey = useMemo(() => {
    const candidates = NAV_ITEMS.filter(
      (item) => item.path !== '/' && (location.pathname === item.path || location.pathname.startsWith(`${item.path}/`)),
    ).sort((a, b) => b.path.length - a.path.length);
    return candidates[0]?.path ?? '/';
  }, [location.pathname]);

  const currentTitle = NAV_ITEMS.find((item) => item.path === selectedKey)?.label ?? '控制台';

  const userMenu: MenuProps['items'] = [
    {
      key: 'profile',
      label: (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{user?.display_name || user?.username}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {user ? USER_ROLE_LABELS[user.role] ?? user.role : ''} · {user?.username}
          </Typography.Text>
        </Space>
      ),
      disabled: true,
    },
    { type: 'divider' },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: () => {
        void logout();
      },
    },
  ];

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider
        theme="dark"
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        trigger={null}
        breakpoint="lg"
        width={208}
        collapsedWidth={64}
      >
        <div className="app-logo">
          <span className="app-logo-mark">TG</span>
          {!collapsed && <span className="app-logo-text">Telegram 云控</span>}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={NAV_ITEMS.map((item) => ({
            key: item.path,
            icon: item.icon,
            label: <Link to={item.path}>{item.label}</Link>,
          }))}
        />
      </Sider>

      <AntLayout>
        <Header className="app-header">
          <Space size="middle">
            <Button
              type="text"
              aria-label={collapsed ? '展开侧栏' : '收起侧栏'}
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((value) => !value)}
            />
            <Typography.Title level={5} style={{ margin: 0 }}>
              {currentTitle}
            </Typography.Title>
          </Space>

          <Space size="middle">
            <Tooltip title={WS_STATUS_TEXT[status]}>
              <span>
                <Badge status={WS_BADGE_STATUS[status]} text={WS_STATUS_TEXT[status]} />
              </span>
            </Tooltip>
            {user?.role ? (
              <Tag color={user.role === 'admin' ? 'gold' : 'blue'}>{USER_ROLE_LABELS[user.role] ?? user.role}</Tag>
            ) : null}
            <Dropdown menu={{ items: userMenu }} trigger={['click']} placement="bottomRight">
              <Space style={{ cursor: 'pointer' }}>
                <Avatar size="small" icon={<UserOutlined />} />
                <span>{user?.display_name || user?.username || '未登录'}</span>
              </Space>
            </Dropdown>
          </Space>
        </Header>

        <Content className="app-content">
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
}

/** 未登录时兜底：直接回登录页 */
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

export default Layout;
