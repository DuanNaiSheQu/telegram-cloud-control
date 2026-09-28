/**
 * 登录页「记住用户名」的本地存储。
 * 只存用户名，不存口令；口令永远不进 localStorage。
 */
const REMEMBER_KEY = 'tgcc_remember_username';

export function readRememberedUsername(): string {
  try {
    return window.localStorage.getItem(REMEMBER_KEY) ?? '';
  } catch {
    return '';
  }
}

export function writeRememberedUsername(username: string | null): void {
  try {
    if (username) window.localStorage.setItem(REMEMBER_KEY, username);
    else window.localStorage.removeItem(REMEMBER_KEY);
  } catch {
    /* localStorage 不可用时忽略 */
  }
}

const HINT_KEY = 'tgcc_login_hint_dismissed';

/** 首次进入登录页的引导提示：是否已被用户关掉 */
export function isLoginHintDismissed(): boolean {
  try {
    return window.localStorage.getItem(HINT_KEY) === '1';
  } catch {
    return false;
  }
}

export function dismissLoginHint(): void {
  try {
    window.localStorage.setItem(HINT_KEY, '1');
  } catch {
    /* 忽略 */
  }
}
