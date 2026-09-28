/** 与 localStorage 同步的 useState：主题以外的 UI 偏好（密度、列设置、侧栏折叠）用它。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { readJson, writeJson } from '../utils/storage';

export function useLocalStorage<T>(key: string, defaultValue: T): [T, (value: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => readJson<T>(key, defaultValue));
  const keyRef = useRef(key);
  keyRef.current = key;

  const update = useCallback((next: T | ((prev: T) => T)) => {
    setValue((prev) => {
      const resolved = typeof next === 'function' ? (next as (p: T) => T)(prev) : next;
      writeJson(keyRef.current, resolved);
      return resolved;
    });
  }, []);

  // 其它标签页改了同一份偏好 → 同步
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== key || event.newValue === null) return;
      try {
        setValue(JSON.parse(event.newValue) as T);
      } catch {
        /* 脏数据忽略 */
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [key]);

  return [value, update];
}
