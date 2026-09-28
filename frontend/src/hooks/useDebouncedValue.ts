/** 值防抖：搜索框输入 / 筛选联动时用，避免每敲一个字都打后端。 */
import { useEffect, useState } from 'react';

export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    if (delayMs <= 0) {
      setDebounced(value);
      return;
    }
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}

/** 防抖回调（保留 this/参数透传语义，组件里最常用形式） */
export function useDebouncedCallback<A extends unknown[]>(
  callback: (...args: A) => void,
  delayMs = 300,
): (...args: A) => void {
  const [state] = useState(() => ({ timer: 0 as number, callback }));
  state.callback = callback;

  useEffect(() => () => window.clearTimeout(state.timer), [state]);

  return (...args: A) => {
    window.clearTimeout(state.timer);
    state.timer = window.setTimeout(() => state.callback(...args), delayMs);
  };
}
