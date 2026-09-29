/**
 * 侧栏导航配置：树形结构（分组 → 菜单项 → 子菜单）。
 *
 * 结构约定：
 * - `NavGroup` 是一级分组（总览 / 账号 / 消息 / 运营），分组标题可折叠；
 * - `NavItem` 可以是叶子（有 path，点击跳转），也可以带 `children`（点击只展开子菜单）；
 * - 触达中心是唯一的三级菜单：分组「运营」→ 触达中心 → 素材库 / 批量私信 / … / 批次进度，
 *   每个子项是独立路由 `/campaigns/<section>`，页面内不再堆 Tab。
 *
 * 兼容导出：`NAV_ITEMS` 是全部叶子（全局搜索、全局搜索的结果列表用它）。
 */
import type { ReactNode } from 'react';
import {
  ApiOutlined,
  AppstoreOutlined,
  CommentOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  FileSearchOutlined,
  FolderOutlined,
  IdcardOutlined,
  RadarChartOutlined,
  InboxOutlined,
  MailOutlined,
  MergeCellsOutlined,
  MessageOutlined,
  NotificationOutlined,
  ProfileOutlined,
  RobotOutlined,
  RocketOutlined,
  SafetyCertificateOutlined,
  ScheduleOutlined,
  SendOutlined,
  ShareAltOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons';
import type { Tone } from '../../constants';

export type NavBadgeSource = 'abnormal' | 'unread' | 'failed' | 'pending';

export interface NavItem {
  path: string;
  label: string;
  icon?: ReactNode;
  /** 一句话说明：面包屑 / 全局搜索 / 无权限提示都会用到 */
  description?: string;
  badge?: NavBadgeSource;
  badgeTone?: Tone;
  /** 子菜单：给 children 时该项本身不跳转，只负责展开 */
  children?: NavItem[];
}

export interface NavGroup {
  key: string;
  title: string;
  items: NavItem[];
}

/** 触达中心的 11 个子页面（三级菜单，独立路由） */
export const CAMPAIGN_CHILDREN: NavItem[] = [
  { path: '/campaigns/materials', label: '素材库', icon: <FolderOutlined />, description: '文字与媒体素材，批量动作共用' },
  { path: '/campaigns/bulk-pm', label: '批量私信', icon: <SendOutlined />, description: '一批号各向目标逐个发消息' },
  { path: '/campaigns/broadcast', label: '群发', icon: <NotificationOutlined />, description: '一批号各向指定群发一条' },
  { path: '/campaigns/material-send', label: '素材群发', icon: <InboxOutlined />, description: '按素材库内容发给群或私信目标' },
  { path: '/campaigns/join', label: '加群', icon: <MergeCellsOutlined />, description: '邀请链接或公开群，一批号一起进' },
  { path: '/campaigns/leave', label: '退群', icon: <DeploymentUnitOutlined />, description: '一批号退出同一个群' },
  { path: '/campaigns/force-add', label: '强拉进群', icon: <TeamOutlined />, description: '管理员把成员拉进群' },
  { path: '/campaigns/profile', label: '批量改资料', icon: <IdcardOutlined />, description: '统一改名 / 简介 / 用户名 / 头像' },
  { path: '/campaigns/storm', label: '吵群', icon: <ThunderboltOutlined />, description: '文本池 + 随机间隔连续发言' },
  { path: '/campaigns/persona', label: '拟人发言', icon: <CommentOutlined />, description: 'AI 按人设生成话术连续发言' },
  { path: '/campaigns/batches', label: '批次进度', icon: <ProfileOutlined />, description: '按批次查进度、取消未完成任务' },
];

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
      { path: '/groups', label: '账号分组', icon: <AppstoreOutlined />, description: '自定义标签，用来把号分给同事' },
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
    items: [    {
      path: '/inbox',
      label: '客服收件箱',
      icon: <MailOutlined />,
      description: '跨账号汇总待处理私信，未读优先，点进去直接回复',
    },

      {
        path: '/dialogs',
        label: '会话',
        icon: <MessageOutlined />,
        description: '群聊和私信',
        badge: 'unread',
        badgeTone: 'info',
      },
      {
        path: '/group-intel',
        label: '群情报',
        icon: <RadarChartOutlined />,
        description: '入群即采：群档案、成员名单与入退群流水',
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
      {
        path: '/campaigns',
        label: '触达中心',
        icon: <RocketOutlined />,
        description: '批量私信、群发、素材、加退群、强拉、改资料、吵群、拟人发言',
        children: CAMPAIGN_CHILDREN,
      },
      { path: '/assignments', label: '员工分配', icon: <TeamOutlined />, description: '谁可以操作哪个号' },
      { path: '/audit', label: '操作记录', icon: <FileSearchOutlined />, description: '谁在什么时间对哪个号做了什么' },
    ],
  },
];

/** 全部叶子项（递归展开；全局搜索 / 快捷键跳转用它） */
export const NAV_ITEMS: NavItem[] = (() => {
  const leaves: NavItem[] = [];
  const walk = (items: NavItem[]) => {
    items.forEach((item) => {
      if (item.children?.length) walk(item.children);
      else leaves.push(item);
    });
  };
  NAV_GROUPS.forEach((group) => walk(group.items));
  return leaves;
})();

export interface NavMatch {
  group: NavGroup;
  /** 命中的叶子项 */
  item: NavItem;
  /** 从分组到叶子的完整链（含分组标题），面包屑用它 */
  trail: NavItem[];
}

function collectTrail(items: NavItem[], pathname: string, parents: NavItem[]): NavItem[] | null {
  for (const item of items) {
    const chain = [...parents, item];
    if (item.children?.length) {
      const found = collectTrail(item.children, pathname, chain);
      if (found) return found;
      continue;
    }
    if (item.path === '/') {
      if (pathname === '/') return chain;
      continue;
    }
    if (pathname === item.path || pathname.startsWith(`${item.path}/`)) return chain;
  }
  return null;
}

/** 按当前路径找命中链：最长的 path 优先（避免 /campaigns 抢 /campaigns/materials） */
export function matchNavTrail(pathname: string): NavMatch | undefined {
  let best: { group: NavGroup; trail: NavItem[] } | undefined;
  NAV_GROUPS.forEach((group) => {
    const trail = collectTrail(group.items, pathname, []);
    if (!trail) return;
    const leaf = trail[trail.length - 1];
    const current = best ? best.trail[best.trail.length - 1] : undefined;
    if (!current || leaf.path.length > current.path.length) best = { group, trail };
  });
  if (!best) return undefined;
  const item = best.trail[best.trail.length - 1];
  return { group: best.group, item, trail: best.trail };
}

/** 兼容旧调用：只取分组与叶子项 */
export function matchNav(pathname: string): { group: NavGroup; item: NavItem } | undefined {
  const matched = matchNavTrail(pathname);
  return matched ? { group: matched.group, item: matched.item } : undefined;
}

/** 该路径所属的分组 key 与父级路径（侧栏据此默认展开） */
export function parentsOf(pathname: string): string[] {
  const matched = matchNavTrail(pathname);
  if (!matched) return [];
  return matched.trail.slice(0, -1).map((node) => node.path);
}
