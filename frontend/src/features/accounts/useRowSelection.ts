/**
 * 行多选状态（Accounts / Detection 共用，页面私有）。
 *
 * DataTable 暂未透传 antd 的 rowSelection（共享组件不加页面私有能力），
 * 这里用「复选框列 + 本页全选」实现同样的多选语义，跨页保留已选集合。
 */
import { useCallback, useMemo, useState } from 'react';

export interface RowSelectionState {
  selectedIds: string[];
  count: number;
  isSelected: (id: string) => boolean;
  /** 单行勾选 */
  toggleOne: (id: string, checked: boolean) => void;
  /** 整页勾选 / 取消（配合表头复选框） */
  togglePage: (pageIds: string[], checked: boolean) => void;
  /** 当前页是否全部勾选（表头复选框 checked） */
  pageAllSelected: (pageIds: string[]) => boolean;
  /** 当前页是否部分勾选（表头复选框 indeterminate） */
  pageSomeSelected: (pageIds: string[]) => boolean;
  clear: () => void;
}

export function useRowSelection(): RowSelectionState {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const isSelected = useCallback((id: string) => selectedSet.has(id), [selectedSet]);

  const toggleOne = useCallback((id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      if (checked && !prev.includes(id)) return [...prev, id];
      if (!checked) return prev.filter((item) => item !== id);
      return prev;
    });
  }, []);

  const togglePage = useCallback((pageIds: string[], checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      pageIds.forEach((id) => (checked ? next.add(id) : next.delete(id)));
      return [...next];
    });
  }, []);

  const pageAllSelected = useCallback(
    (pageIds: string[]) => pageIds.length > 0 && pageIds.every((id) => selectedSet.has(id)),
    [selectedSet],
  );

  const pageSomeSelected = useCallback(
    (pageIds: string[]) => pageIds.some((id) => selectedSet.has(id)),
    [selectedSet],
  );

  const clear = useCallback(() => setSelectedIds([]), []);

  return {
    selectedIds,
    count: selectedIds.length,
    isSelected,
    toggleOne,
    togglePage,
    pageAllSelected,
    pageSomeSelected,
    clear,
  };
}
