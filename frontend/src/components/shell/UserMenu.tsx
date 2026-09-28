/**
 * UserMenu —— 顶栏当前用户菜单（身份 + 退出登录）。
 *
 * props 契约：
 * ┌───────────┬──────────────────────────────────────────────────────────────┐
 * │ name      │ string  展示名 / 用户名                                       │
 * │ roleLabel │ string  角色中文（管理员 / 操作员）                            │
 * │ isAdmin   │ boolean 管理员标记                                            │
 * │ onLogout  │ () => void                                                    │
 * │ onOpenProfile │ () => void  可选：打开「我的资料」                          │
 * └───────────┴──────────────────────────────────────────────────────────────┘
 */
import { Avatar, Dropdown, Space, Tag, Typography } from 'antd';
import type { MenuProps } from 'antd';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';

export interface UserMenuProps {
  name: string;
  roleLabel?: string;
  isAdmin?: boolean;
  onLogout: () => void;
}

export function UserMenu({ name, roleLabel, isAdmin = false, onLogout }: UserMenuProps) {
  const items: MenuProps['items'] = [
    {
      key: 'profile',
      disabled: true,
      label: (
        <Space direction="vertical" size={0} style={{ padding: '2px 0' }}>
          <Typography.Text strong>{name}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
            {roleLabel ?? '—'}
            {isAdmin ? ' · 可管全部账号与员工' : ' · 只能操作分配到的账号'}
          </Typography.Text>
        </Space>
      ),
    },
    { type: 'divider' },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
      onClick: onLogout,
    },
  ];

  return (
    <Dropdown menu={{ items }} trigger={['click']} placement="bottomRight">
      <div className="app-user-trigger" role="button" tabIndex={0} aria-label="当前用户菜单">
        <Avatar
          size={28}
          style={{ background: 'var(--tg-color-primary-bg)', color: 'var(--tg-color-primary)' }}
          icon={<UserOutlined />}
        />
        <span className="app-user-meta">
          <span className="app-user-name">{name}</span>
          <span className="app-user-role">{roleLabel ?? '—'}</span>
        </span>
        {isAdmin ? (
          <Tag
            style={{
              marginInlineEnd: 0,
              background: 'var(--tg-color-warning-bg)',
              borderColor: 'var(--tg-color-warning-border)',
              color: 'var(--tg-color-warning)',
            }}
          >
            管理员
          </Tag>
        ) : null}
      </div>
    </Dropdown>
  );
}

export default UserMenu;
