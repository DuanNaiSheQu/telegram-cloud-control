/**
 * token → CSS 变量。
 *
 * 运行时会由 ThemeProvider 把当前主题的全部变量以「内联样式」写到 <html> 上
 * （内联样式优先级高于任何样式表规则），因此 tokens.ts 是唯一真源：
 * 改 tokens.ts → 自研组件（var(--tg-*)）与 antd（ConfigProvider token）同时换皮。
 *
 * styles.css 里另外有一份同名的静态兜底（`:root` / `[data-theme='dark']`），
 * 只用于 JS 执行前的首屏，防止闪白；运行时会立刻被这里的注入覆盖。
 */
import { TOKENS, type ThemeMode, type ThemeTokens } from './tokens';

/** camelCase → kebab-case */
export function kebab(input: string): string {
  return input.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();
}

/** 分组前缀 */
const GROUP_PREFIX: Record<string, string> = {
  color: '--tg-color',
  space: '--tg-space',
  radius: '--tg-radius',
  font: '--tg-font',
  shadow: '--tg-shadow',
  motion: '--tg-motion',
  layout: '--tg-layout',
  zIndex: '--tg-z',
};

function formatNumberValue(path: string[], value: number): string {
  const key = path[path.length - 1];
  const group = path[0];
  if (group === 'zIndex') return String(value);
  if (/^duration/.test(key)) return `${value}ms`;
  if (/^weight/.test(key) || /^line/.test(key) || key === 'opacity') return String(value);
  return `${value}px`;
}

function flatten(
  node: Record<string, unknown>,
  path: string[],
  out: Record<string, string>,
): void {
  for (const [key, value] of Object.entries(node)) {
    if (key === 'mode') continue;
    const next = [...path, key];
    if (value !== null && typeof value === 'object') {
      flatten(value as Record<string, unknown>, next, out);
    } else if (typeof value === 'string') {
      out[`${GROUP_PREFIX[path[0]] ?? '--tg'}-${next.slice(1).map(kebab).join('-')}`] = value;
    } else if (typeof value === 'number') {
      out[`${GROUP_PREFIX[path[0]] ?? '--tg'}-${next.slice(1).map(kebab).join('-')}`] =
        formatNumberValue(next, value);
    }
  }
}

/** 展开某个主题的全部 CSS 变量（变量名 → 值） */
export function themeCssVars(mode: ThemeMode): Record<string, string> {
  const out: Record<string, string> = {};
  flatten(TOKENS[mode] as unknown as Record<string, unknown>, [], out);
  out['--tg-theme'] = mode;
  out['--tg-color-scheme'] = mode;
  return out;
}

/** 生成一段可直接贴进 styles.css 的兜底文本（`npm run theme:css` 会打印它） */
export function themeVarsCss(mode: ThemeMode, selector = ':root'): string {
  const vars = themeCssVars(mode);
  const body = Object.entries(vars)
    .map(([name, value]) => `  ${name}: ${value};`)
    .join('\n');
  return `${selector} {\n${body}\n}`;
}

/** 把变量写到元素上（默认 <html>），返回是否成功 */
export function applyThemeVars(
  mode: ThemeMode,
  target?: HTMLElement | null,
  tokens?: ThemeTokens,
): void {
  const root = target ?? (typeof document === 'undefined' ? null : document.documentElement);
  if (!root) return;
  const vars = themeCssVars(mode);
  if (tokens) {
    // tokens 参数保留给「运行时微调」场景（例如参考图校准后只改局部数值）
    const patch = collectOverrides(tokens);
    Object.assign(vars, patch);
  }
  for (const [name, value] of Object.entries(vars)) {
    root.style.setProperty(name, value);
  }
}

/**
 * 允许调用方传入一份「已改过的 tokens」来覆盖默认值。
 * 目前 ThemeProvider 不传，保留此能力给后续灰度换皮使用。
 */
function collectOverrides(tokens: ThemeTokens): Record<string, string> {
  const out: Record<string, string> = {};
  flatten(tokens as unknown as Record<string, unknown>, [], out);
  return out;
}

/** 读取元素上当前的变量值（调试 / 测试用） */
export function readVar(name: string, target?: HTMLElement | null): string {
  const root = target ?? (typeof document === 'undefined' ? null : document.documentElement);
  if (!root) return '';
  return getComputedStyle(root).getPropertyValue(name).trim();
}

/**
 * 由分组 + 路径拼变量名，供个别需要动态拼色的组件使用：
 *   cssVar('color', 'account', 'healthy', 'fg') → 'var(--tg-color-account-healthy-fg)'
 */
export function cssVar(group: string, ...path: string[]): string {
  const prefix = GROUP_PREFIX[group] ?? `--tg-${kebab(group)}`;
  return `var(${[prefix, ...path.map(kebab)].join('-')})`;
}

/** 常用变量名（供 TS 侧引用，避免拼错） */
export const V = {  primary: 'var(--tg-color-primary)',
  textPrimary: 'var(--tg-color-text-primary)',
  textSecondary: 'var(--tg-color-text-secondary)',
  textTertiary: 'var(--tg-color-text-tertiary)',
  border: 'var(--tg-color-border)',
  borderSubtle: 'var(--tg-color-border-subtle)',
  bgCard: 'var(--tg-color-bg-card)',
  bgApp: 'var(--tg-color-bg-app)',
  radiusCard: 'var(--tg-radius-card)',
  radiusControl: 'var(--tg-radius-control)',
  spaceLg: 'var(--tg-space-lg)',
  spaceXl: 'var(--tg-space-xl)',
  shadowSm: 'var(--tg-shadow-sm)',
  shadowMd: 'var(--tg-shadow-md)',
  fontFamily: 'var(--tg-font-family)',
  fontFamilyMono: 'var(--tg-font-family-mono)',
} as const;
