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

export function readJson<T>(key: string, fallback: T): T {
  const raw = readRaw(key);
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
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
