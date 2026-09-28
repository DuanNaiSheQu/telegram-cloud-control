/**
 * 侧栏导航配置（分组 + 角标）。
 * 侧栏顺序与分组照 规划.md「页面 / 侧栏」一节；「Bot 管理」「操作记录」是按后端契约补的入口。
 */
import type { ReactNode } from 'react';
import {
  ApiOutlined,
  DashboardOutlined,
  FileSearchOutlined,
  FolderOutlined,
  MessageOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  ScheduleOutlined,
  SendOutlined,
  ShareAltOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons';
import type { Tone } from '../../constants';

export type NavBadgeSource = 'abnormal' | 'unread' | 'failed' | 'pending';

export interface NavItem {
  path: string;
  label: string;
  icon: ReactNode;
  /** 一句话说明：面包屑 / 全局搜索 / 无权限提示都会用到 */
  description?: string;
  badge?: NavBadgeSource;
  badgeTone?: Tone;
}

export interface NavGroup {
  key: string;
  title: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'overview',
    title: '总览',
    items: [
      {
        path: '/',
        label: '工作台',
        icon: <DashboardOutlined />,
        description: '在线数、异常数、失败任务',
      },
    ],
  },
  {
    key: 'accounts',
    title: '账号',
    items: [
      {
        path: '/accounts',
        label: '账号管理',
        icon: <UserOutlined />,
        description: '状态、分组、心跳、当前任务、单号检测',
        badge: 'abnormal',
        badgeTone: 'danger',
      },
      { path: '/groups', label: '账号分组', icon: <FolderOutlined />, description: '内部标签，用来把号分给同事' },
      {
        path: '/detection',
        label: '账号检测',
        icon: <SafetyCertificateOutlined />,
        description: '连得上、要验证码、会话失效',
      },
      { path: '/network', label: '网络', icon: <ApiOutlined />, description: '账号出站地址（代理）' },
    ],
  },
  {
    key: 'messages',
    title: '消息',
    items: [
      {
        path: '/dialogs',
        label: '会话',
        icon: <MessageOutlined />,
        description: '群聊和私信',
        badge: 'unread',
        badgeTone: 'info',
      },
      { path: '/relay', label: 'Bot 转发', icon: <ShareAltOutlined />, description: '新消息转发到员工群' },
      { path: '/bots', label: 'Bot 管理', icon: <RobotOutlined />, description: 'Token、Webhook、自动回复' },
    ],
  },
  {
    key: 'ops',
    title: '运营',
    items: [
      {
        path: '/tasks',
        label: '任务中心',
        icon: <ScheduleOutlined />,
        description: '同步、单条发送、转发，含失败原因与重试次数',
        badge: 'failed',
        badgeTone: 'danger',
      },
      { path: '/assignments', label: '员工分配', icon: <TeamOutlined />, description: '谁可以操作哪个号' },
      { path: '/audit', label: '操作记录', icon: <FileSearchOutlined />, description: '谁在什么时间对哪个号做了什么' },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((group) => group.items);

/** 按当前路径找命中的导航项（长路径优先，避免 /accounts 命中 /） */
export function matchNav(pathname: string): { group: NavGroup; item: NavItem } | undefined {
  const candidates: Array<{ group: NavGroup; item: NavItem }> = [];
  NAV_GROUPS.forEach((group) => {
    group.items.forEach((item) => {
      if (item.path === '/') {
        if (pathname === '/') candidates.push({ group, item });
        return;
      }
      if (pathname === item.path || pathname.startsWith(`${item.path}/`)) candidates.push({ group, item });
    });
  });
  return candidates.sort((a, b) => b.item.path.length - a.item.path.length)[0];
}
