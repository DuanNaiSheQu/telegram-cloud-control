/** 响应式断点：外壳用它决定侧栏是展开 / 折叠 / 抽屉。 */
import { useEffect, useState } from 'react';
import { BREAKPOINTS } from '../theme/tokens';

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}

export interface BreakpointState {
  width: number;
  /** < 1024：窄屏，侧栏改用抽屉 */
  isNarrow: boolean;
  /** < 1280：紧凑，筛选栏默认折叠 */
  isCompact: boolean;
  /** >= 1600：宽屏，卡片可以一行 4-6 个 */
  isWide: boolean;
}

export function useBreakpoint(): BreakpointState {
  const [width, setWidth] = useState<number>(() =>
    typeof window === 'undefined' ? BREAKPOINTS.xl : window.innerWidth,
  );

  useEffect(() => {
    let frame = 0;
    const onResize = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => setWidth(window.innerWidth));
    };
    window.addEventListener('resize', onResize);
    onResize();
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', onResize);
    };
  }, []);

  return {
    width,
    isNarrow: width < BREAKPOINTS.lg + 32, // 1024
    isCompact: width < BREAKPOINTS.xl, // 1280
    isWide: width >= BREAKPOINTS.xxl, // 1600
  };
}
