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
import { getToken, onUnauthorized, setToken as persistToken } from '../api/client';
import { authApi } from '../api/endpoints';
import type { UserOut } from '../api/types';

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
  const [user, setUser] = useState<UserOut | null>(null);
  const [ready, setReady] = useState<boolean>(() => !getToken());
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const clearSession = useCallback(() => {
    persistToken(null); // WS 连接由 useWebSocket 在 token 清空后自行断开
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
      setTokenState(current);
    } catch {
      if (!mountedRef.current) return;
      persistToken(null);
      setTokenState(null);
      setUser(null);
    } finally {
      if (mountedRef.current) setReady(true);
    }
  }, []);

  // 首次进入：有 token 就换回当前用户
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const result = await authApi.login(username.trim(), password);
    persistToken(result.access_token);
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
