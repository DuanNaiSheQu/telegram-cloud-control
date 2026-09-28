/**
 * 会话列表状态：筛选 + 排序 + 分页追加 + 本地补丁（WS / 未读清零 / 发送后预览更新）。
 * 列表用「追加式分页」（滚动到底加载下一页），所以这里自己维护 items 而不是每次整表替换。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { dialogApi } from '../../api/endpoints';
import type { DialogChannel, DialogKind, DialogOut } from '../../api/types';
import { DIALOG_PAGE_SIZE } from './types';

export interface DialogListFilters {
  channel: DialogChannel | '';
  kind: DialogKind | '';
  account_id: string | null;
  bot_id: string | null;
  only_unread: boolean;
  keyword: string;
}

export const EMPTY_DIALOG_FILTERS: DialogListFilters = {
  channel: '',
  kind: '',
  account_id: null,
  bot_id: null,
  only_unread: false,
  keyword: '',
};

export interface DialogListState {
  filters: DialogListFilters;
  setFilters: (patch: Partial<DialogListFilters>) => void;
  resetFilters: () => void;
  activeCount: number;
  sortOrder: 'desc' | 'asc';
  toggleSort: () => void;
  items: DialogOut[];
  total: number;
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  reload: () => void;
  loadMore: () => void;
  /** WS / 本地动作后只改列表里的某一条，不整表刷新 */
  patchItem: (id: string, patch: Partial<DialogOut>) => void;
  bumpUnread: (id: string) => void;
}

export function useDialogList(): DialogListState {
  const [filters, setFiltersState] = useState<DialogListFilters>(EMPTY_DIALOG_FILTERS);
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');
  const [items, setItems] = useState<DialogOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);

  const load = useCallback(
    async (targetPage: number, append: boolean) => {
      const seq = (seqRef.current += 1);
      if (append) setLoadingMore(true);
      else setLoading(true);
      try {
        const res = await dialogApi.list(
          {
            channel: filters.channel || undefined,
            kind: filters.kind || undefined,
            account_id: filters.account_id ?? undefined,
            bot_id: filters.bot_id ?? undefined,
            only_unread: filters.only_unread || undefined,
            keyword: filters.keyword.trim() || undefined,
            sort: 'last_message_at',
            order: sortOrder,
            page: targetPage,
            page_size: DIALOG_PAGE_SIZE,
          },
          { silent: true },
        );
        if (seq !== seqRef.current) return;
        setItems((prev) => (append ? [...prev, ...res.items] : res.items));
        setTotal(res.total);
        setPage(targetPage);
        setError(null);
      } catch (err) {
        if (seq !== seqRef.current) return;
        setError((err as Error)?.message || '会话列表加载失败');
      } finally {
        if (seq === seqRef.current) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [filters, sortOrder],
  );

  useEffect(() => {
    void load(1, false);
  }, [load]);

  const setFilters = useCallback((patch: Partial<DialogListFilters>) => {
    setFiltersState((prev) => ({ ...prev, ...patch }));
  }, []);

  const resetFilters = useCallback(() => setFiltersState(EMPTY_DIALOG_FILTERS), []);

  const activeCount = Object.values(filters).filter((value) => {
    if (value === '' || value === null || value === undefined || value === false) return false;
    return true;
  }).length;

  const toggleSort = useCallback(() => {
    setSortOrder((order) => (order === 'desc' ? 'asc' : 'desc'));
  }, []);

  const reload = useCallback(() => void load(1, false), [load]);

  const loadMore = useCallback(() => {
    if (items.length < total) void load(page + 1, true);
  }, [items.length, total, page, load]);

  const patchItem = useCallback((id: string, patch: Partial<DialogOut>) => {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }, []);

  const bumpUnread = useCallback((id: string) => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, unread_count: item.unread_count + 1 } : item)),
    );
  }, []);

  return {
    filters,
    setFilters,
    resetFilters,
    activeCount,
    sortOrder,
    toggleSort,
    items,
    total,
    loading,
    loadingMore,
    error,
    reload,
    loadMore,
    patchItem,
    bumpUnread,
  };
}
