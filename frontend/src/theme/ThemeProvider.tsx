/**
 * 主题运行时：偏好（浅色/深色/跟随系统）→ 生效模式 → CSS 变量 + antd ConfigProvider token。
 *
 * 使用：
 *   <ThemeProvider>            // App.tsx 最外层，包在 ConfigProvider 外面
 *   const { mode, isDark, tokens, antdTheme, preference, setPreference, toggle } = useTheme();
 *
 * 约定：
 *  - 组件样式一律写 var(--tg-*)，不要写死色值；
 *  - 需要 JS 里用色值时，从 useTheme().tokens.color 取（或 cssVars 的 V.* 变量名）。
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { ThemeConfig } from 'antd';
import { tokensFor, type ThemeMode, type ThemePreference, type ThemeTokens } from './tokens';
import { antdThemeFor } from './antdTheme';
import { applyThemeVars } from './cssVars';

export const THEME_STORAGE_KEY = 'tgcc_theme';

const MEDIA_DARK = '(prefers-color-scheme: dark)';

export function systemMode(): ThemeMode {
  if (typeof window === 'undefined' || !window.matchMedia) return 'dark';
  return window.matchMedia(MEDIA_DARK).matches ? 'dark' : 'light';
}

/** 读取本地记忆的偏好；没存过则跟随系统 */
export function readStoredPreference(): ThemePreference {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (raw === 'light' || raw === 'dark' || raw === 'system') return raw;
  } catch {
    /* localStorage 不可用（隐私模式）时跟随系统 */
  }
  return 'system';
}

export function storePreference(preference: ThemePreference): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    /* 忽略 */
  }
}

export function resolveMode(preference: ThemePreference): ThemeMode {
  return preference === 'system' ? systemMode() : preference;
}

export interface ThemeContextValue {
  /** 用户偏好（含 system） */
  preference: ThemePreference;
  /** 实际生效模式 */
  mode: ThemeMode;
  isDark: boolean;
  tokens: ThemeTokens;
  /** 直接给 <ConfigProvider theme={...}> */
  antdTheme: ThemeConfig;
  setPreference: (preference: ThemePreference) => void;
  /** 浅/深一键切换（system 下切到与当前相反的一套） */
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

/** 把主题写到 <html>：data-theme（CSS 选择器兜底）+ 内联 CSS 变量（唯一真源） */
function syncDocument(mode: ThemeMode, preference: ThemePreference): void {
  const root = document.documentElement;
  root.dataset.theme = mode;
  root.dataset.themePreference = preference;
  // 让原生控件（滚动条、日期选择器）跟随明暗
  root.style.colorScheme = mode;
  applyThemeVars(mode, root);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() => readStoredPreference());
  const [mode, setMode] = useState<ThemeMode>(() => resolveMode(readStoredPreference()));

  // 偏好变化：写本地 + 落 DOM
  useEffect(() => {
    storePreference(preference);
    const next = resolveMode(preference);
    setMode(next);
    syncDocument(next, preference);
  }, [preference]);

  // 跟随系统：系统外观变化时实时切换（只在 preference === 'system' 时生效）
  useEffect(() => {
    if (preference !== 'system' || !window.matchMedia) return;
    const mql = window.matchMedia(MEDIA_DARK);
    const onChange = () => {
      const next = mql.matches ? 'dark' : 'light';
      setMode(next);
      syncDocument(next, 'system');
    };
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [preference]);

  // 其它标签页改了主题 → 同步过来
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY) return;
      setPreferenceState(readStoredPreference());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const setPreference = useCallback((next: ThemePreference) => setPreferenceState(next), []);
  const toggle = useCallback(() => {
    setPreferenceState((current) => (resolveMode(current) === 'dark' ? 'light' : 'dark'));
  }, []);

  const value = useMemo<ThemeContextValue>(() => {
    const tokens = tokensFor(mode);
    return {
      preference,
      mode,
      isDark: mode === 'dark',
      tokens,
      antdTheme: antdThemeFor(mode),
      setPreference,
      toggle,
    };
  }, [mode, preference, setPreference, toggle]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme 必须在 ThemeProvider 内使用');
  return ctx;
}

/** 只要当前色板时用这个（少写一层解构） */
export function useTokenColors() {
  return useTheme().tokens.color;
}
