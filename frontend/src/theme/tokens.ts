/**
 * 设计 token —— 全站唯一的「换皮入口」。
 *
 * 换皮规则（硬约束）：
 *  1. 颜色 / 间距 / 圆角 / 阴影 / 字体 / 动效 只允许来自本文件；
 *     页面与组件里禁止写死色值（用 CSS 变量 `var(--tg-color-*)` 或 `useTheme().tokens`）。
 *  2. 本文件在运行时被 `theme/cssVars.ts` 展开成 CSS 变量注入到 <html>（内联样式），
 *     同时被 `antdThemeFor(mode)` 映射成 antd v5 的 ConfigProvider token。
 *     —— 因此「只改这里」即可让 antd 组件与自研组件同步换皮，不会出现两种蓝。
 *  3. styles.css 里的 `:root` / `[data-theme='dark']` 是首屏（JS 未执行前）的兜底副本，
 *     运行时会被本文件注入的同名变量覆盖；改色以本文件为准，兜底块仅用于防止闪白。
 *  4. 新增 token：在对应分组里加字段即可，CSS 变量名自动生成为
 *     `--tg-<分组>-<kebab-case 字段>`（嵌套对象用 `-` 连接）。
 */
import type { AccountStatus, TaskStatus } from '../api/types';

export type ThemeMode = 'light' | 'dark';
/** 用户偏好：浅色 / 深色 / 跟随系统 */
export type ThemePreference = ThemeMode | 'system';

/** 状态色的四件套：文字、底色、描边、圆点 */
export interface StatusColor {
  /** 文本/图标色 */
  fg: string;
  /** 浅底色（Tag / Alert / 徽标背景） */
  bg: string;
  /** 描边色 */
  border: string;
  /** 圆点/进度条实心色 */
  dot: string;
}

export interface ColorTokens {
  // ---------------------------------------------------------------- 品牌
  /** 主色（Telegram 蓝） */
  primary: string;
  primaryHover: string;
  primaryActive: string;
  /** 主色浅底（选中行、浅色按钮底） */
  primaryBg: string;
  primaryBgHover: string;
  /** 主色描边 */
  primaryBorder: string;
  /** 主色上的文字 */
  onPrimary: string;
  /** 品牌渐变（Logo / 强调块） */
  gradientFrom: string;
  gradientTo: string;

  // ---------------------------------------------------------------- 层级背景
  /** 页面最底层背景 */
  bgApp: string;
  /** 侧栏背景 */
  bgSider: string;
  /** 侧栏 hover / 选中 */
  bgSiderHover: string;
  bgSiderActive: string;
  /** 顶栏背景 */
  bgTopbar: string;
  /** 卡片 / 面板 */
  bgCard: string;
  bgCardHover: string;
  /** 浮层（Dropdown / Popover / Modal） */
  bgElevated: string;
  /** 下沉区（表头、代码块、聊天区） */
  bgSunken: string;
  /** 输入框 */
  bgInput: string;
  /** 通用 hover / 选中 */
  bgHover: string;
  bgActive: string;
  bgSelected: string;
  /** 蒙层 */
  bgMask: string;
  /** 骨架屏底色 */
  bgSkeleton: string;
  /** 滚动条 */
  scrollThumb: string;
  scrollThumbHover: string;
  /** 深色气泡提示（antd Tooltip / 悬浮说明） */
  tooltipBg: string;
  tooltipText: string;
  /** 骨架屏高光 */
  skeletonHighlight: string;

  // ---------------------------------------------------------------- 文本
  textPrimary: string;
  textSecondary: string;
  textTertiary: string;
  textDisabled: string;
  textInverse: string;
  textLink: string;
  textLinkHover: string;

  // ---------------------------------------------------------------- 边框
  border: string;
  borderStrong: string;
  borderSubtle: string;
  /** 聚焦描边 */
  borderFocus: string;
  divider: string;

  // ---------------------------------------------------------------- 语义状态
  success: string;
  successHover: string;
  successBg: string;
  successBorder: string;
  warning: string;
  warningHover: string;
  warningBg: string;
  warningBorder: string;
  danger: string;
  dangerHover: string;
  dangerBg: string;
  dangerBorder: string;
  info: string;
  infoBg: string;
  infoBorder: string;
  neutral: string;
  neutralBg: string;
  neutralBorder: string;

  // ---------------------------------------------------------------- 业务：账号 7 态
  /** 账号状态配色：pending/healthy/needs_code/frozen/invalid/dead/disabled */
  account: Record<AccountStatus, StatusColor>;
  /** 任务状态配色 */
  task: Record<TaskStatus, StatusColor>;

  // ---------------------------------------------------------------- 图表
  chart1: string;
  chart2: string;
  chart3: string;
  chart4: string;
  chart5: string;
  chart6: string;
  chartGrid: string;
  chartAxis: string;

  /** 阴影基色（rgba，供自定义阴影拼接） */
  shadowColor: string;
}

export interface SpaceTokens {
  none: number;
  xxs: number;
  xs: number;
  sm: number;
  md: number;
  lg: number;
  xl: number;
  xxl: number;
  xxxl: number;
  huge: number;
  giant: number;
  colossal: number;
  mega: number;
}

export interface RadiusTokens {
  none: number;
  xs: number;
  sm: number;
  md: number;
  lg: number;
  /** 卡片圆角（列表卡片 / 面板） */
  card: number;
  /** 大卡片圆角 */
  cardLg: number;
  /** 表单控件圆角 */
  control: number;
  /** 胶囊 */
  pill: number;
}

export interface FontTokens {
  family: string;
  familyMono: string;
  sizeXs: number;
  sizeSm: number;
  sizeMd: number;
  size: number;
  sizeLg: number;
  sizeXl: number;
  sizeTitle: number;
  sizeDisplay: number;
  weightRegular: number;
  weightMedium: number;
  weightSemibold: number;
  weightBold: number;
  lineTight: number;
  lineNormal: number;
  lineLoose: number;
  letterTight: string;
}

export interface ShadowTokens {
  none: string;
  xs: string;
  sm: string;
  md: string;
  lg: string;
  xl: string;
  /** 聚焦光环 */
  focus: string;
  /** 顶部高光（深色卡片描边感） */
  inset: string;
}

export interface MotionTokens {
  durationFast: number;
  durationBase: number;
  durationSlow: number;
  easeStandard: string;
  easeOut: string;
  easeInOut: string;
}

export interface LayoutTokens {
  /** 侧栏展开宽度 */
  siderWidth: number;
  /** 侧栏折叠宽度 */
  siderCollapsedWidth: number;
  /** 顶栏高度 */
  topbarHeight: number;
  /** 内容区最大宽度（1920 下居中，避免一行拉太长） */
  contentMaxWidth: number;
  contentPaddingX: number;
  contentPaddingY: number;
  /** 卡片/区块之间的垂直间距 */
  pageGap: number;
  /** 卡片内边距 */
  cardPadding: number;
  /** 表单控件高度 */
  controlHeight: number;
  controlHeightSm: number;
  controlHeightLg: number;
}

export interface ZIndexTokens {
  base: number;
  sticky: number;
  topbar: number;
  sider: number;
  drawer: number;
  modal: number;
  toast: number;
  tooltip: number;
}

/** 窄屏断点（px）：小于 narrow 时侧栏改为抽屉 */
export const BREAKPOINTS = {
  sm: 576,
  md: 768,
  lg: 992,
  /** 1280：设计基准宽度 */
  xl: 1280,
  xxl: 1600,
  /** 1920：大屏 */
  ultra: 1920,
} as const;

/** 8px 网格：grid(2) = 16px。间距优先用 space.* 语义值，偶尔用 grid() 表达特殊值。 */
export const grid = (units: number): number => units * 8;

export const SPACE: SpaceTokens = {
  none: 0,
  xxs: 2,
  xs: 4,
  sm: 6,
  md: 8,
  lg: 12,
  xl: 16,
  xxl: 20,
  xxxl: 24,
  huge: 32,
  giant: 40,
  colossal: 48,
  mega: 64,
};

/** 圆角：卡片 12/14，控件 8，胶囊 999 —— 参考图校准时优先改这里 */
export const RADIUS: RadiusTokens = {
  none: 0,
  xs: 4,
  sm: 6,
  md: 8,
  lg: 10,
  card: 14,
  cardLg: 16,
  control: 8,
  pill: 999,
};

export const FONT: FontTokens = {
  family:
    '-apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif',
  familyMono:
    'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", "Courier New", monospace',
  sizeXs: 11,
  sizeSm: 12,
  sizeMd: 13,
  size: 14,
  sizeLg: 16,
  sizeXl: 18,
  sizeTitle: 20,
  sizeDisplay: 28,
  weightRegular: 400,
  weightMedium: 500,
  weightSemibold: 600,
  weightBold: 700,
  lineTight: 1.25,
  lineNormal: 1.55,
  lineLoose: 1.75,
  letterTight: '-0.01em',
};

export const MOTION: MotionTokens = {
  durationFast: 120,
  durationBase: 180,
  durationSlow: 260,
  easeStandard: 'cubic-bezier(0.2, 0, 0, 1)',
  easeOut: 'cubic-bezier(0.16, 1, 0.3, 1)',
  easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
};

export const LAYOUT: LayoutTokens = {
  siderWidth: 232,
  siderCollapsedWidth: 64,
  topbarHeight: 56,
  contentMaxWidth: 1680,
  contentPaddingX: 24,
  contentPaddingY: 20,
  pageGap: 16,
  cardPadding: 20,
  controlHeight: 34,
  controlHeightSm: 28,
  controlHeightLg: 40,
};

export const Z_INDEX: ZIndexTokens = {
  base: 0,
  sticky: 10,
  topbar: 100,
  sider: 90,
  drawer: 1000,
  modal: 1100,
  toast: 1200,
  tooltip: 1300,
};

/** 账号状态 7 态 + 任务状态：浅色主题 */
const ACCOUNT_LIGHT: Record<AccountStatus, StatusColor> = {
  healthy: { fg: '#0f7b52', bg: '#e6f7ef', border: '#b7e6d0', dot: '#12a06a' },
  pending: { fg: '#9a6700', bg: '#fff7e6', border: '#ffe0a3', dot: '#d99a00' },
  needs_code: { fg: '#b45309', bg: '#fff2e8', border: '#ffd8bf', dot: '#f97316' },
  frozen: { fg: '#b42318', bg: '#fef3f2', border: '#fecdca', dot: '#e5484d' },
  limited: { fg: '#9a6700', bg: '#fff7e6', border: '#ffe0a3', dot: '#d99a00' },
  invalid: { fg: '#93370d', bg: '#fdf1ec', border: '#f5cfc0', dot: '#d2603a' },
  dead: { fg: '#52606d', bg: '#f1f3f5', border: '#dfe3e8', dot: '#8b95a1' },
  disabled: { fg: '#667085', bg: '#f4f5f7', border: '#e4e7ec', dot: '#98a2b3' },
};

const ACCOUNT_DARK: Record<AccountStatus, StatusColor> = {
  healthy: { fg: '#4ade9f', bg: 'rgba(18, 160, 106, 0.16)', border: 'rgba(74, 222, 159, 0.32)', dot: '#34d399' },
  pending: { fg: '#fbbf4d', bg: 'rgba(217, 154, 0, 0.16)', border: 'rgba(251, 191, 77, 0.32)', dot: '#fbbf24' },
  needs_code: { fg: '#fdab6b', bg: 'rgba(249, 115, 22, 0.16)', border: 'rgba(253, 171, 107, 0.32)', dot: '#fb923c' },
  frozen: { fg: '#ff8b85', bg: 'rgba(229, 72, 77, 0.16)', border: 'rgba(255, 139, 133, 0.32)', dot: '#f87171' },
  limited: { fg: '#fbbf4d', bg: 'rgba(217, 154, 0, 0.16)', border: 'rgba(251, 191, 77, 0.32)', dot: '#fbbf24' },
  invalid: { fg: '#f0a58a', bg: 'rgba(210, 96, 58, 0.16)', border: 'rgba(240, 165, 138, 0.32)', dot: '#e07a56' },
  dead: { fg: '#a3aab4', bg: 'rgba(139, 149, 161, 0.16)', border: 'rgba(163, 170, 180, 0.28)', dot: '#8b95a1' },
  disabled: { fg: '#8b93a1', bg: 'rgba(152, 162, 179, 0.14)', border: 'rgba(139, 147, 161, 0.26)', dot: '#7b8494' },
};

const TASK_LIGHT: Record<TaskStatus, StatusColor> = {
  pending: { fg: '#0958d9', bg: '#eaf2ff', border: '#c7dcff', dot: '#2f6fed' },
  pending_confirmation: { fg: '#9a6700', bg: '#fff7e6', border: '#ffe0a3', dot: '#d99a00' },
  running: { fg: '#0958d9', bg: '#eaf2ff', border: '#c7dcff', dot: '#2f6fed' },
  completed: { fg: '#0f7b52', bg: '#e6f7ef', border: '#b7e6d0', dot: '#12a06a' },
  failed: { fg: '#b42318', bg: '#fef3f2', border: '#fecdca', dot: '#e5484d' },
  cancelled: { fg: '#667085', bg: '#f4f5f7', border: '#e4e7ec', dot: '#98a2b3' },
};

const TASK_DARK: Record<TaskStatus, StatusColor> = {
  pending: { fg: '#8ab8ff', bg: 'rgba(47, 111, 237, 0.16)', border: 'rgba(138, 184, 255, 0.3)', dot: '#5b93f5' },
  pending_confirmation: { fg: '#fbbf4d', bg: 'rgba(217, 154, 0, 0.16)', border: 'rgba(251, 191, 77, 0.32)', dot: '#fbbf24' },
  running: { fg: '#7cc4ff', bg: 'rgba(42, 171, 238, 0.18)', border: 'rgba(124, 196, 255, 0.32)', dot: '#38bdf8' },
  completed: { fg: '#4ade9f', bg: 'rgba(18, 160, 106, 0.16)', border: 'rgba(74, 222, 159, 0.32)', dot: '#34d399' },
  failed: { fg: '#ff8b85', bg: 'rgba(229, 72, 77, 0.16)', border: 'rgba(255, 139, 133, 0.32)', dot: '#f87171' },
  cancelled: { fg: '#8b93a1', bg: 'rgba(152, 162, 179, 0.14)', border: 'rgba(139, 147, 161, 0.26)', dot: '#7b8494' },
};

/** 浅色：干净的白底控制台（不发灰），描边柔和 */
const COLORS_LIGHT: ColorTokens = {
  primary: '#2aabee',
  primaryHover: '#4bb8f0',
  primaryActive: '#1e97d6',
  primaryBg: '#eaf6fe',
  primaryBgHover: '#dceffc',
  primaryBorder: '#a8dcf8',
  onPrimary: '#ffffff',
  gradientFrom: '#2aabee',
  gradientTo: '#229ed9',

  bgApp: '#f6f7f9',
  bgSider: '#ffffff',
  bgSiderHover: '#f2f5f9',
  bgSiderActive: '#e8f4fd',
  bgTopbar: '#ffffff',
  bgCard: '#ffffff',
  bgCardHover: '#fafbfc',
  bgElevated: '#ffffff',
  bgSunken: '#f7f8fa',
  bgInput: '#ffffff',
  bgHover: 'rgba(16, 24, 40, 0.04)',
  bgActive: 'rgba(16, 24, 40, 0.07)',
  bgSelected: '#e8f4fd',
  bgMask: 'rgba(16, 24, 40, 0.45)',
  bgSkeleton: 'rgba(16, 24, 40, 0.06)',
  scrollThumb: 'rgba(16, 24, 40, 0.18)',
  scrollThumbHover: 'rgba(16, 24, 40, 0.3)',
  tooltipBg: '#101828',
  tooltipText: '#ffffff',
  skeletonHighlight: 'rgba(16, 24, 40, 0.1)',

  textPrimary: '#101828',
  textSecondary: '#475467',
  textTertiary: '#667085',
  textDisabled: '#98a2b3',
  textInverse: '#ffffff',
  textLink: '#1e97d6',
  textLinkHover: '#2aabee',

  border: '#e4e7ec',
  borderStrong: '#d0d5dd',
  borderSubtle: '#eef0f4',
  borderFocus: '#2aabee',
  divider: '#eceff3',

  success: '#12a06a',
  successHover: '#0f8b5c',
  successBg: '#e6f7ef',
  successBorder: '#b7e6d0',
  warning: '#d99a00',
  warningHover: '#bf8800',
  warningBg: '#fff7e6',
  warningBorder: '#ffe0a3',
  danger: '#e5484d',
  dangerHover: '#cf3b40',
  dangerBg: '#fef3f2',
  dangerBorder: '#fecdca',
  info: '#2aabee',
  infoBg: '#eaf6fe',
  infoBorder: '#a8dcf8',
  neutral: '#667085',
  neutralBg: '#f4f5f7',
  neutralBorder: '#e4e7ec',

  account: ACCOUNT_LIGHT,
  task: TASK_LIGHT,

  chart1: '#2aabee',
  chart2: '#12a06a',
  chart3: '#f79009',
  chart4: '#7a5af8',
  chart5: '#e5484d',
  chart6: '#0ba5ec',
  chartGrid: '#eceff3',
  chartAxis: '#98a2b3',

  shadowColor: 'rgba(16, 24, 40, 0.08)',
};

/** 深色：分层灰蓝（不糊成一片），柔和描边 + 低对比阴影 */
const COLORS_DARK: ColorTokens = {
  primary: '#2aabee',
  primaryHover: '#4cbcff',
  primaryActive: '#1e97d6',
  primaryBg: 'rgba(42, 171, 238, 0.16)',
  primaryBgHover: 'rgba(42, 171, 238, 0.24)',
  primaryBorder: 'rgba(42, 171, 238, 0.42)',
  onPrimary: '#04141f',
  gradientFrom: '#2aabee',
  gradientTo: '#1e97d6',

  bgApp: '#0d1117',
  bgSider: '#111721',
  bgSiderHover: 'rgba(255, 255, 255, 0.05)',
  bgSiderActive: 'rgba(42, 171, 238, 0.16)',
  bgTopbar: '#111721',
  bgCard: '#151c26',
  bgCardHover: '#1a2230',
  bgElevated: '#1b2331',
  bgSunken: '#10161f',
  bgInput: '#0f151d',
  bgHover: 'rgba(255, 255, 255, 0.05)',
  bgActive: 'rgba(255, 255, 255, 0.09)',
  bgSelected: 'rgba(42, 171, 238, 0.16)',
  bgMask: 'rgba(3, 6, 10, 0.65)',
  bgSkeleton: 'rgba(255, 255, 255, 0.07)',
  scrollThumb: 'rgba(255, 255, 255, 0.16)',
  scrollThumbHover: 'rgba(255, 255, 255, 0.28)',
  tooltipBg: '#1f2937',
  tooltipText: '#f1f5f9',
  skeletonHighlight: 'rgba(255, 255, 255, 0.12)',

  textPrimary: '#e8edf4',
  textSecondary: '#a9b4c4',
  textTertiary: '#7d8899',
  textDisabled: '#5a6577',
  textInverse: '#0d1117',
  textLink: '#5cc0f5',
  textLinkHover: '#8ad3ff',

  border: '#25303f',
  borderStrong: '#334155',
  borderSubtle: '#1c2532',
  borderFocus: '#2aabee',
  divider: '#1f2937',

  success: '#34d399',
  successHover: '#4ade9f',
  successBg: 'rgba(18, 160, 106, 0.16)',
  successBorder: 'rgba(74, 222, 159, 0.32)',
  warning: '#fbbf24',
  warningHover: '#fcd34d',
  warningBg: 'rgba(217, 154, 0, 0.16)',
  warningBorder: 'rgba(251, 191, 77, 0.32)',
  danger: '#f87171',
  dangerHover: '#ff9a95',
  dangerBg: 'rgba(229, 72, 77, 0.16)',
  dangerBorder: 'rgba(255, 139, 133, 0.32)',
  info: '#2aabee',
  infoBg: 'rgba(42, 171, 238, 0.16)',
  infoBorder: 'rgba(42, 171, 238, 0.42)',
  neutral: '#8b93a1',
  neutralBg: 'rgba(152, 162, 179, 0.14)',
  neutralBorder: 'rgba(139, 147, 161, 0.26)',

  account: ACCOUNT_DARK,
  task: TASK_DARK,

  chart1: '#38bdf8',
  chart2: '#34d399',
  chart3: '#fbbf24',
  chart4: '#a78bfa',
  chart5: '#f87171',
  chart6: '#22d3ee',
  chartGrid: 'rgba(255, 255, 255, 0.08)',
  chartAxis: '#6b7688',

  shadowColor: 'rgba(0, 0, 0, 0.45)',
};

/** 阴影：浅色靠柔和灰，深色靠更深的黑 + 顶部高光 */
const SHADOW_LIGHT: ShadowTokens = {
  none: 'none',
  xs: '0 1px 2px rgba(16, 24, 40, 0.05)',
  sm: '0 1px 3px rgba(16, 24, 40, 0.08), 0 1px 2px rgba(16, 24, 40, 0.04)',
  md: '0 4px 12px rgba(16, 24, 40, 0.08), 0 1px 3px rgba(16, 24, 40, 0.05)',
  lg: '0 12px 28px rgba(16, 24, 40, 0.12), 0 2px 6px rgba(16, 24, 40, 0.05)',
  xl: '0 24px 48px rgba(16, 24, 40, 0.16), 0 4px 12px rgba(16, 24, 40, 0.06)',
  focus: '0 0 0 3px rgba(42, 171, 238, 0.22)',
  inset: 'inset 0 1px 0 rgba(255, 255, 255, 0.6)',
};

const SHADOW_DARK: ShadowTokens = {
  none: 'none',
  xs: '0 1px 2px rgba(0, 0, 0, 0.4)',
  sm: '0 1px 3px rgba(0, 0, 0, 0.5), 0 1px 2px rgba(0, 0, 0, 0.3)',
  md: '0 6px 16px rgba(0, 0, 0, 0.45), 0 1px 3px rgba(0, 0, 0, 0.3)',
  lg: '0 14px 32px rgba(0, 0, 0, 0.55), 0 2px 8px rgba(0, 0, 0, 0.35)',
  xl: '0 26px 52px rgba(0, 0, 0, 0.62), 0 6px 16px rgba(0, 0, 0, 0.4)',
  focus: '0 0 0 3px rgba(42, 171, 238, 0.32)',
  inset: 'inset 0 1px 0 rgba(255, 255, 255, 0.05)',
};

export interface ThemeTokens {
  mode: ThemeMode;
  color: ColorTokens;
  space: SpaceTokens;
  radius: RadiusTokens;
  font: FontTokens;
  shadow: ShadowTokens;
  motion: MotionTokens;
  layout: LayoutTokens;
  zIndex: ZIndexTokens;
}

export const TOKENS: Record<ThemeMode, ThemeTokens> = {
  light: {
    mode: 'light',
    color: COLORS_LIGHT,
    space: SPACE,
    radius: RADIUS,
    font: FONT,
    shadow: SHADOW_LIGHT,
    motion: MOTION,
    layout: LAYOUT,
    zIndex: Z_INDEX,
  },
  dark: {
    mode: 'dark',
    color: COLORS_DARK,
    space: SPACE,
    radius: RADIUS,
    font: FONT,
    shadow: SHADOW_DARK,
    motion: MOTION,
    layout: LAYOUT,
    zIndex: Z_INDEX,
  },
};

export function tokensFor(mode: ThemeMode): ThemeTokens {
  return TOKENS[mode];
}
