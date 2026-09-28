/** 列表页 / 详情页共用的取数、刷新、错误状态。 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  /** 重新取数（返回最新数据，失败返回 null） */
  reload: () => Promise<T | null>;
  /** reload 的别名，语义更直白 */
  refetch: () => Promise<T | null>;
  setData: Dispatch<SetStateAction<T | null>>;
  /** 首次加载中（没有旧数据）—— 用来区分「骨架屏」和「静默刷新」 */
  initialLoading: boolean;
}

export interface AsyncOptions<T> {
  /** false 时不自动请求（等依赖就绪再手动 reload） */
  immediate?: boolean;
  /** 请求失败时不写 error 状态（页面自己处理，例如静默轮询） */
  silentError?: boolean;
  onSuccess?: (data: T) => void;
  onError?: (error: Error) => void;
}

/**
 * 统一的异步取数：
 * - 并发安全：只接受最后一次请求的结果（seq 比对），切换筛选条件不会串数据；
 * - 刷新时保留旧数据（loading=true 但 data 不置空），列表页不会闪白；
 * - 错误统一成中文 message，交给页面渲染 ErrorState，或由 client 弹出 toast。
 */
export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  options: AsyncOptions<T> = {},
): AsyncState<T> {
  const { immediate = true, silentError = false, onSuccess, onError } = options;
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const silentErrorRef = useRef(silentError);
  silentErrorRef.current = silentError;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(immediate);
  const [error, setError] = useState<string | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const seqRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const reload = useCallback(async (): Promise<T | null> => {
    const seq = (seqRef.current += 1);
    setLoading(true);
    try {
      const result = await fetcherRef.current();
      if (seq === seqRef.current && mountedRef.current) {
        setData(result);
        setError(null);
        setLoadedOnce(true);
        onSuccessRef.current?.(result);
      }
      return result;
    } catch (err) {
      const message = (err as Error)?.message ?? '加载失败，请稍后重试';
      if (seq === seqRef.current && mountedRef.current) {
        if (!silentErrorRef.current) setError(message);
        setLoadedOnce(true);
        onErrorRef.current?.(err as Error);
      }
      return null;
    } finally {
      if (seq === seqRef.current && mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (immediate) void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return {
    data,
    loading,
    error,
    reload,
    refetch: reload,
    setData,
    initialLoading: loading && !loadedOnce,
  };
}

/** 定时轮询；delay 为 null 时不启动。回调始终用最新的闭包。 */
export function useInterval(callback: () => void, delay: number | null): void {
  const savedRef = useRef(callback);
  useEffect(() => {
    savedRef.current = callback;
  }, [callback]);

  useEffect(() => {
    if (delay === null) return;
    const timer = window.setInterval(() => savedRef.current(), delay);
    return () => window.clearInterval(timer);
  }, [delay]);
}

/** 页面重新可见时触发（切回标签页自动刷新，避免看到过期数据） */
export function useVisibilityRefresh(callback: () => void, enabled = true): void {
  const savedRef = useRef(callback);
  useEffect(() => {
    savedRef.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled) return;
    const onVisible = () => {
      if (document.visibilityState === 'visible') savedRef.current();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [enabled]);
}
