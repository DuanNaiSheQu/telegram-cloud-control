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
import { useEffect, useState } from 'react';
import { ABOUT_SEEN_KEY, AboutModal } from './AboutModal';
import { InfoCircleOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';

export interface UserMenuProps {
  name: string;
  roleLabel?: string;
  isAdmin?: boolean;
  onLogout: () => void;
}

export function UserMenu({ name, roleLabel, isAdmin = false, onLogout }: UserMenuProps) {
  const [aboutOpen, setAboutOpen] = useState(false);

  // 首次进入自动弹一次声明：部署者未必翻 README，但一定会登录控制台，
  // 而"操作真实账号有风险"这件事必须在动手之前看到。读过就不再打扰。
  useEffect(() => {
    try {
      if (localStorage.getItem(ABOUT_SEEN_KEY)) return;
      setAboutOpen(true);
    } catch {
      /* 隐私模式下 localStorage 可能不可用，忽略即可 */
    }
  }, []);

  const closeAbout = () => {
    setAboutOpen(false);
    try {
      localStorage.setItem(ABOUT_SEEN_KEY, '1');
    } catch {
      /* 同上 */
    }
  };
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
      // 声明与赞助入口：首次进入会自动弹一次，之后从这里随时回看
      key: 'about',
      icon: <InfoCircleOutlined />,
      label: '关于 · 赞助 · 声明',
      onClick: () => setAboutOpen(true),
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
    <>
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
      <AboutModal open={aboutOpen} onClose={closeAbout} />
    </>
  );
}

export default UserMenu;
