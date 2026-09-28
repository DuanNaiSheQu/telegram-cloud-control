/**
 * 列表页统一查询状态：分页 / 排序 / 筛选 / 重置，直接产出可传给接口的 query 对象。
 *
 * 用法：
 *   const q = useTableQuery({ filters: { status: '', keyword: '' }, pageSize: 20 });
 *   const { data, loading, error, reload } = useAsyncData(
 *     () => accountApi.list({ ...q.params, sort: q.sort ?? undefined, order: q.order ?? undefined }),
 *     [q.paramsKey],
 *   );
 *   <FilterBar onReset={q.reset} activeFilters={q.activeFilters}>…</FilterBar>
 *   <DataTable total={data?.total} page={q.page} pageSize={q.pageSize}
 *              onPageChange={q.setPage} onSortChange={q.setSort} … />
 */
import { useCallback, useMemo, useState } from 'react';
import type { SortOrder } from '../api/types';

export interface TableQueryOptions<F extends Record<string, unknown>> {
  filters: F;
  pageSize?: number;
  /** 默认排序字段 */
  sort?: string | null;
  order?: SortOrder;
}

/**
 * 筛选项允许的赋值类型：声明类型 + 常见原始类型。
 * 放宽的原因：页面常把初始值写成 `group_id: null`（语义是「不筛选」），
 * 但实际赋值是 string；严格用 F[K] 会逼页面到处写 `as`。
 */
export type FilterValue<T> = T | string | number | boolean | null | undefined;

export interface ActiveFilter {
  key: string;
  label: string;
  value: string;
  /** 由 useTableQuery 生成：点击 Tag 的 × 时调用 */
  onRemove: () => void;
}

export interface TableQueryResult<F extends Record<string, unknown>> {
  page: number;
  pageSize: number;
  sort: string | null;
  order: SortOrder;
  filters: F;
  /** 直接展开给接口：{ page, page_size, ...filters } */
  params: Record<string, unknown> & { page: number; page_size: number };
  /** 值变化时可用于 useAsyncData 依赖 */
  paramsKey: string;
  setPage: (page: number, pageSize?: number) => void;
  setPageSize: (pageSize: number) => void;
  setSort: (field: string | null, order: SortOrder) => void;
  /** 单个筛选项赋值（自动回到第一页） */
  setFilter: <K extends keyof F>(key: K, value: FilterValue<F[K]>) => void;
  /** 批量改筛选项（自动回到第一页） */
  patchFilters: (patch: { [K in keyof F]?: FilterValue<F[K]> }) => void;
  /** 清空筛选 + 回到第一页（保留排序与每页条数） */
  reset: () => void;
  /** 当前生效的筛选项数量（用于「重置(N)」按钮与角标） */
  activeCount: number;
}

export function useTableQuery<F extends Record<string, unknown>>(
  options: TableQueryOptions<F>,
): TableQueryResult<F> {
  const { filters: initialFilters, pageSize: initialPageSize = 20, sort = null, order = null } = options;

  const [page, setPageState] = useState(1);
  const [pageSize, setPageSizeState] = useState(initialPageSize);
  const [sortState, setSortState] = useState<{ field: string | null; order: SortOrder }>({
    field: sort,
    order,
  });
  const [filters, setFilters] = useState<F>(initialFilters);

  const setPage = useCallback((next: number, nextSize?: number) => {
    setPageState(Math.max(1, next));
    if (nextSize) setPageSizeState(nextSize);
  }, []);

  const setPageSize = useCallback((nextSize: number) => {
    setPageSizeState(nextSize);
    setPageState(1);
  }, []);

  const setSort = useCallback((field: string | null, nextOrder: SortOrder) => {
    setSortState({ field, order: nextOrder });
    setPageState(1);
  }, []);

  const setFilter = useCallback(<K extends keyof F>(key: K, value: FilterValue<F[K]>) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setPageState(1);
  }, []);

  const patchFilters = useCallback((patch: { [K in keyof F]?: FilterValue<F[K]> }) => {
    setFilters((current) => ({ ...current, ...patch }));
    setPageState(1);
  }, []);

  const reset = useCallback(() => {
    setFilters(initialFilters);
    setPageState(1);
    // initialFilters 是页面里的字面量常量，不需要进依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const params = useMemo(
    () => ({ page, page_size: pageSize, ...(filters as Record<string, unknown>) }),
    [page, pageSize, filters],
  );

  const paramsKey = useMemo(() => JSON.stringify(params), [params]);

  // 「已选条件」数：值非空的筛选项个数（空字符串/空数组/false/null 都不算）
  const activeCount = useMemo(
    () =>
      Object.values(filters).filter((value) => {
        if (value === '' || value === null || value === undefined || value === false) return false;
        if (Array.isArray(value)) return value.length > 0;
        return true;
      }).length,
    [filters],
  );

  return {
    page,
    pageSize,
    sort: sortState.field,
    order: sortState.order,
    filters,
    params,
    paramsKey,
    setPage,
    setPageSize,
    setSort,
    setFilter,
    patchFilters,
    reset,
    activeCount,
  };
}

/** 把筛选值拼成 FilterBar 的已选条件 Tag（key 为空/默认值的自动跳过） */
export function buildActiveFilters(
  entries: Array<{ key: string; label: string; display: string | null | undefined; clear: () => void }>,
): ActiveFilter[] {
  return entries
    .filter((item) => item.display !== null && item.display !== undefined && item.display !== '')
    .map((item) => ({
      key: item.key,
      label: item.label,
      value: String(item.display),
      onRemove: item.clear,
    }));
}
