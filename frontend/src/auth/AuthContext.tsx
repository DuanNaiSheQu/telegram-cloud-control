import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, getToken, onUnauthorized, setToken as persistToken } from '../api/client';
import { authApi } from '../api/endpoints';
import { notifyError } from '../utils/feedback';
import type { UserOut } from '../api/types';

const USER_KEY = 'tgcc_user';

/** 缓存当前用户（只用于展示；权限一律以后端为准） */
function readCachedUser(): UserOut | null {
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as UserOut) : null;
  } catch {
    return null;
  }
}

function writeCachedUser(user: UserOut | null): void {
  try {
    if (user) window.localStorage.setItem(USER_KEY, JSON.stringify(user));
    else window.localStorage.removeItem(USER_KEY);
  } catch {
    /* 忽略 */
  }
}

interface AuthContextValue {
  user: UserOut | null;
  token: string | null;
  /** 首次 /api/auth/me 是否已完成（用于避免刷新页面时闪回登录页） */
  ready: boolean;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<UserOut>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [token, setTokenState] = useState<string | null>(() => getToken());
  // 有 token 时先用上次缓存的用户渲染，避免刷新页面时闪一下登录页
  const [user, setUser] = useState<UserOut | null>(() => (getToken() ? readCachedUser() : null));
  const [ready, setReady] = useState<boolean>(() => !getToken() || Boolean(readCachedUser()));
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const clearSession = useCallback(() => {
    persistToken(null); // WS 连接由 useWebSocket 在 token 清空后自行断开
    writeCachedUser(null);
    setTokenState(null);
    setUser(null);
    setReady(true);
  }, []);

  // 401：清 token、断开长连接、回登录页
  useEffect(() => {
    return onUnauthorized(() => {
      clearSession();
      navigate('/login', { replace: true });
    });
  }, [clearSession, navigate]);

  const refresh = useCallback(async () => {
    const current = getToken();
    if (!current) {
      setUser(null);
      setReady(true);
      return;
    }
    try {
      const me = await authApi.me();
      if (!mountedRef.current) return;
      setUser(me);
      writeCachedUser(me);
      setTokenState(current);
    } catch (err) {
      if (!mountedRef.current) return;
      const status = err instanceof ApiError ? err.status : 0;
      if (status === 401 || status === 403) {
        // 令牌确实失效：清干净回登录页（401 已由 client 广播）
        clearSession();
      } else if (!readCachedUser()) {
        // 既没有缓存用户、又拿不到 /me：只能让用户重新登录
        clearSession();
      } else {
        // 后端 5xx / 网络抖动：不要把人踢下线，先用上次身份继续值班
        notifyError(`无法校验登录状态（${(err as Error).message}），先用上次的身份继续`);
      }
    } finally {
      if (mountedRef.current) setReady(true);
    }
  }, [clearSession]);

  // 首次进入：有 token 就换回当前用户
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const result = await authApi.login(username.trim(), password);
    persistToken(result.access_token);
    writeCachedUser(result.user);
    setTokenState(result.access_token);
    setUser(result.user);
    setReady(true);
    return result.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      /* 后端不可用时也要能退出 */
    }
    clearSession();
    navigate('/login', { replace: true });
  }, [clearSession, navigate]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      ready,
      isAdmin: user?.role === 'admin',
      login,
      logout,
      refresh,
    }),
    [user, token, ready, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用');
  return ctx;
}
