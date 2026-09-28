/** localStorage 安全封装：隐私模式 / 配额满 / 脏数据都不抛异常。 */

export function readRaw(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeRaw(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* 忽略：内存态仍然可用 */
  }
}

/**
 * 读出来的值和默认值做一次浅合并：对象类型逐字段兜底，数组字段非法则回退成默认数组。
 *
 * 为什么需要：localStorage 里可能留着旧版本的结构、被手工改过的内容，或者只写了一半的对象
 * （例如 `{}`）。直接当成完整对象用，就会让 `state.xxx.includes(...)` 这类调用读到 undefined，
 * 轻则一个组件白屏，重则整页被 ErrorBoundary 兜住。
 */
function mergeWithDefault<T>(parsed: unknown, fallback: T): T {
  if (parsed === null || parsed === undefined) return fallback;
  if (Array.isArray(fallback)) {
    return (Array.isArray(parsed) ? parsed : fallback) as T;
  }
  if (typeof fallback === 'object' && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const merged: Record<string, unknown> = { ...(fallback as Record<string, unknown>) };
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      const expected = (fallback as Record<string, unknown>)[key];
      if (Array.isArray(expected) && !Array.isArray(value)) continue; // 期望数组却拿到别的 → 用默认
      merged[key] = value;
    }
    return merged as T;
  }
  return parsed as T;
}

export function readJson<T>(key: string, fallback: T): T {
  const raw = readRaw(key);
  if (!raw) return fallback;
  try {
    return mergeWithDefault<T>(JSON.parse(raw), fallback);
  } catch {
    return fallback;
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    writeRaw(key, JSON.stringify(value));
  } catch {
    /* 循环引用等异常忽略 */
  }
}

/** 带前缀的命名空间，避免和别的项目/页面冲突 */
export function namespaced(prefix: string) {
  const withPrefix = (key: string) => `${prefix}:${key}`;
  return {
    get: (key: string) => readRaw(withPrefix(key)),
    set: (key: string, value: string | null) => writeRaw(withPrefix(key), value),
    getJson: <T>(key: string, fallback: T) => readJson<T>(withPrefix(key), fallback),
    setJson: (key: string, value: unknown) => writeJson(withPrefix(key), value),
  };
}

/** 列设置 / 密度 / 每页条数等 UI 偏好的存储命名空间 */
export const uiStorage = namespaced('tgcc_ui');
