/** 列表页共用的取数/刷新/错误状态。 */
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
  reload: () => Promise<T | null>;
  setData: Dispatch<SetStateAction<T | null>>;
}

export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  options: { immediate?: boolean } = {},
): AsyncState<T> {
  const { immediate = true } = options;
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(immediate);
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);

  const reload = useCallback(async (): Promise<T | null> => {
    const seq = (seqRef.current += 1);
    setLoading(true);
    try {
      const result = await fetcherRef.current();
      if (seq === seqRef.current) {
        setData(result);
        setError(null);
      }
      return result;
    } catch (err) {
      if (seq === seqRef.current) setError((err as Error)?.message ?? '加载失败');
      return null;
    } finally {
      if (seq === seqRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (immediate) void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error, reload, setData };
}

/** 定时轮询；delay 为 null 时不启动 */
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
