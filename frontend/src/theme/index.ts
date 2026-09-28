/**
 * 主题模块统一出口。
 *
 * 页面 / 组件只从这里 import：
 *   import { useTheme, V } from '../theme';           // 变量名常量 V.*
 *   const { tokens, isDark } = useTheme();            // 需要具体色值时
 *   样式里写 var(--tg-color-primary) 等变量。
 */
export {
  TOKENS,
  tokensFor,
  grid,
  SPACE,
  RADIUS,
  FONT,
  MOTION,
  LAYOUT,
  Z_INDEX,
  BREAKPOINTS,
  type ThemeMode,
  type ThemePreference,
  type ThemeTokens,
  type ColorTokens,
  type StatusColor,
  type SpaceTokens,
  type RadiusTokens,
  type FontTokens,
  type ShadowTokens,
  type MotionTokens,
  type LayoutTokens,
  type ZIndexTokens,
} from './tokens';

export { antdThemeFor } from './antdTheme';

export {
  V,
  cssVar,
  applyThemeVars,
  themeCssVars,
  themeVarsCss,
  readVar,
} from './cssVars';

export {
  ThemeProvider,
  useTheme,
  useTokenColors,
  THEME_STORAGE_KEY,
  readStoredPreference,
  resolveMode,
  systemMode,
  type ThemeContextValue,
} from './ThemeProvider';
