/**
 * DataTable —— 列表页统一表格封装（分页 / 排序 / 密度 / 列设置 / 导出按钮位 / 空态 / 失败态）。
 *
 * props 契约：
 * ┌──────────────────┬───────────────────────────────────────────────────────────┐
 * │ columns          │ TableColumnsType<T>  antd 列定义（照旧写 render/sorter）   │
 * │ dataSource       │ T[]                                                      │
 * │ rowKey           │ string | (record)=>string                                │
 * │ loading          │ boolean  首次加载显示骨架，刷新时保留旧数据 + 右上角提示   │
 * │ error            │ string|null  失败态（整表替换为 ErrorState）              │
 * │ onRetry          │ () => void  失败重试 / 手动刷新按钮                       │
 * │ empty            │ EmptyStateProps  空态文案与引导按钮                       │
 * │ total/page/pageSize │ number  服务端分页                                    │
 * │ onPageChange     │ (page, pageSize) => void                                  │
 * │ pageSizeOptions  │ number[]  默认 [10,20,50,100]                            │
 * │ sortField        │ string|null  当前排序字段（后端字段名）                    │
 * │ sortOrder        │ 'asc'|'desc'|null                                        │
 * │ onSortChange     │ (field|null, order|null) => void                          │
 * │ sortableColumns  │ Record<列key, 后端字段名>  传了这些列才可点排序            │
 * │ title            │ ReactNode  工具条左侧标题                                 │
 * │ toolbar          │ ReactNode  工具条左侧自定义内容（批量操作按钮等）          │
 * │ extra            │ ReactNode  工具条右侧自定义内容                           │
 * │ exportAction     │ ReactNode  导出按钮位（自定义导出按钮）                    │
 * │ onExport         │ () => void|Promise<void>  快捷导出（自动渲染「导出 CSV」）  │
 * │ columnSettingsKey│ string  传了就开启「列设置」并按 key 记忆                 │
 * │ densityKey       │ string  传了就记忆密度，默认开启                          │
 * │ defaultDensity   │ 'compact'|'middle'|'comfortable'  默认 'middle'           │
 * │ showDensity      │ boolean  默认 true                                       │
 * │ skeleton         │ boolean  首次加载用骨架屏，默认 true                       │
 * │ scrollX          │ number|string  横向滚动宽度（列多时必填）                  │
 * │ sticky           │ boolean  表头吸顶（长列表）                                │
 * │ rowClassName     │ (record, index) => string                                │
 * │ rowSelection     │ antd 原样透传（批量勾选 + preserveSelectedRowKeys 跨页保持）│
 * │ onRow/expandable │ 透传 antd                                                │
 * └──────────────────┴───────────────────────────────────────────────────────────┘
 * 用法：
 *   <DataTable rowKey="id" columns={columns} dataSource={rows} total={total}
 *     page={q.page} pageSize={q.pageSize} onPageChange={q.setPage}
 *     sortableColumns={{ phone_masked: 'phone', last_heartbeat: 'last_heartbeat' }}
 *     sortField={q.sort} sortOrder={q.order} onSortChange={q.setSort}
 *     loading={loading} error={error} onRetry={reload}
 *     empty={{ art:'accounts', title:'还没有账号', action:<Button>新建账号</Button> }}
 *     onExport={handleExport} columnSettingsKey="accounts" />
 */
import { useMemo, useState, type CSSProperties, type Key, type ReactNode } from 'react';
import { Button, Checkbox, Dropdown, Segmented, Table, Tooltip, Typography } from 'antd';
import type { TableColumnsType, TableProps } from 'antd';
import {
  DownloadOutlined,
  ReloadOutlined,
  SettingOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import EmptyState, { type EmptyStateProps } from './EmptyState';
import ErrorState from './ErrorState';
import { TableSkeleton } from './LoadingSkeleton';
import { useLocalStorage } from '../hooks/useLocalStorage';

export type TableDensity = 'compact' | 'middle' | 'comfortable';

const DENSITY_TO_SIZE: Record<TableDensity, 'small' | 'middle' | 'large'> = {
  compact: 'small',
  middle: 'middle',
  comfortable: 'large',
};

export interface DataTableProps<T> {
  columns: TableColumnsType<T>;
  dataSource: T[];
  rowKey: string | ((record: T) => Key);
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  empty?: EmptyStateProps;
  total?: number;
  page?: number;
  pageSize?: number;
  onPageChange?: (page: number, pageSize: number) => void;
  pageSizeOptions?: number[];
  showTotal?: boolean;
  sortField?: string | null;
  sortOrder?: 'asc' | 'desc' | null;
  onSortChange?: (field: string | null, order: 'asc' | 'desc' | null) => void;
  sortableColumns?: Record<string, string>;
  title?: ReactNode;
  toolbar?: ReactNode;
  extra?: ReactNode;
  exportAction?: ReactNode;
  onExport?: () => void | Promise<void>;
  exportText?: string;
  columnSettingsKey?: string;
  densityKey?: string;
  defaultDensity?: TableDensity;
  showDensity?: boolean;
  skeleton?: boolean;
  skeletonRows?: number;
  scrollX?: number | string;
  size?: 'small' | 'middle' | 'large';
  bordered?: boolean;
  sticky?: boolean;
  rowClassName?: (record: T, index: number) => string;
  onRow?: TableProps<T>['onRow'];
  expandable?: TableProps<T>['expandable'];
  /** 勾选行（批量操作）：直接透传 antd，配合 toolbar 里的「已选 N 个」使用 */
  rowSelection?: TableProps<T>['rowSelection'];
  className?: string;
  style?: CSSProperties;
}

function columnKeyOf<T>(column: TableColumnsType<T>[number]): string {
  const key = (column as { key?: Key }).key;
  if (key !== undefined && key !== null) return String(key);
  const dataIndex = (column as { dataIndex?: unknown }).dataIndex;
  if (typeof dataIndex === 'string') return dataIndex;
  if (Array.isArray(dataIndex)) return dataIndex.join('.');
  return '';
}

export function DataTable<T extends object>({
  columns,
  dataSource,
  rowKey,
  loading = false,
  error,
  onRetry,
  empty,
  total,
  page = 1,
  pageSize = 20,
  onPageChange,
  pageSizeOptions = [10, 20, 50, 100],
  showTotal = true,
  sortField = null,
  sortOrder = null,
  onSortChange,
  sortableColumns,
  title,
  toolbar,
  extra,
  exportAction,
  onExport,
  exportText = '导出 CSV',
  columnSettingsKey,
  densityKey,
  defaultDensity = 'middle',
  showDensity = true,
  skeleton = true,
  skeletonRows = 8,
  scrollX,
  size,
  bordered = false,
  sticky = false,
  rowClassName,
  onRow,
  expandable,
  rowSelection,
  className,
  style,
}: DataTableProps<T>) {
  const [hidden, setHidden] = useLocalStorage<string[]>(
    `${columnSettingsKey ?? 'default'}:hidden_columns`,
    [],
  );
  const [density, setDensity] = useLocalStorage<TableDensity>(
    `${densityKey ?? columnSettingsKey ?? 'default'}:density`,
    defaultDensity,
  );
  const [exporting, setExporting] = useState(false);

  const settingsEnabled = Boolean(columnSettingsKey);

  const settingColumns = useMemo(
    () =>
      columns
        .map((column) => ({ key: columnKeyOf(column), title: (column as { title?: ReactNode }).title }))
        .filter((item) => item.key && item.title),
    [columns],
  );

  const visibleColumns = useMemo(() => {
    if (!settingsEnabled) return columns;
    return columns.filter((column) => {
      const key = columnKeyOf(column);
      return !key || !hidden.includes(key);
    });
  }, [columns, hidden, settingsEnabled]);

  const processedColumns = useMemo(
    () =>
      visibleColumns.map((column) => {
        const key = columnKeyOf(column);
        const field = key ? sortableColumns?.[key] : undefined;
        if (!field) return column;
        return {
          ...column,
          sorter: true,
          showSorterTooltip: false,
          sortOrder: sortField === field && sortOrder ? (sortOrder === 'asc' ? 'ascend' : 'descend') : null,
        } as TableColumnsType<T>[number];
      }),
    [visibleColumns, sortableColumns, sortField, sortOrder],
  );

  const handleChange: TableProps<T>['onChange'] = (pagination, _filters, sorter) => {
    const single = Array.isArray(sorter) ? sorter[0] : sorter;
    if (onSortChange) {
      const columnKey = String(single?.columnKey ?? (single?.field as string) ?? '');
      const field = sortableColumns?.[columnKey] ?? (single?.order ? columnKey : null);
      onSortChange(single?.order ? field : null, (single?.order as 'asc' | 'desc' | undefined) ?? null);
    }
    if (onPageChange) {
      const nextPage = pagination.current ?? 1;
      const nextSize = pagination.pageSize ?? pageSize;
      if (nextPage !== page || nextSize !== pageSize) onPageChange(nextPage, nextSize);
    }
  };

  const handleExport = async () => {
    if (!onExport) return;
    try {
      setExporting(true);
      await onExport();
    } catch {
      /* 导出失败已由 client 弹出提示，这里只负责恢复按钮 */
    } finally {
      setExporting(false);
    }
  };

  const hasRows = dataSource.length > 0;
  const firstLoad = loading && !hasRows && !error;

  const toolbarVisible =
    Boolean(title) || Boolean(toolbar) || Boolean(extra) || Boolean(exportAction) || Boolean(onExport) || Boolean(onRetry) || settingsEnabled || showDensity;

  let body: ReactNode;
  if (error) {
    body = (
      <div style={{ padding: 'var(--tg-space-xl)' }}>
        <ErrorState error={error} onRetry={onRetry} />
      </div>
    );
  } else if (firstLoad && skeleton) {
    body = (
      <div style={{ padding: 'var(--tg-space-lg) var(--tg-layout-card-padding)' }}>
        <TableSkeleton rows={skeletonRows} columns={Math.max(4, Math.min(visibleColumns.length, 8))} />
      </div>
    );
  } else {
    body = (
      <Table<T>
        rowKey={rowKey}
        columns={processedColumns}
        dataSource={dataSource}
        loading={loading && hasRows ? { spinning: true, size: 'small' } : false}
        size={size ?? DENSITY_TO_SIZE[density]}
        bordered={bordered}
        sticky={sticky}
        scroll={scrollX ? { x: scrollX } : undefined}
        onChange={handleChange}
        rowClassName={rowClassName}
        onRow={onRow}
        expandable={expandable}
        rowSelection={rowSelection}
        locale={{
          emptyText: (
            <EmptyState
              compact
              art="search"
              title="没有符合条件的数据"
              description="换个筛选条件，或先清空筛选看看全部数据。"
              {...empty}
            />
          ),
        }}
        pagination={
          total === undefined && !onPageChange
            ? false
            : {
                current: page,
                pageSize,
                total: total ?? dataSource.length,
                showSizeChanger: true,
                pageSizeOptions: pageSizeOptions.map(String),
                showTotal: showTotal ? (value) => `共 ${value} 条` : undefined,
                size: density === 'compact' ? 'small' : 'default',
              }
        }
      />
    );
  }

  return (
    <div className={['tg-table-card', className].filter(Boolean).join(' ')} style={style}>
      {toolbarVisible ? (
        <div className="tg-table-toolbar">
          {title ? <span className="tg-table-toolbar-title">{title}</span> : null}
          {toolbar}
          <div className="tg-table-toolbar-right">
            {loading && hasRows ? (
              <span className="tg-table-meta" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <SyncOutlined spin /> 刷新中…
              </span>
            ) : null}
            {extra}
            {exportAction}
            {onExport ? (
              <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
                {exportText}
              </Button>
            ) : null}
            {showDensity ? (
              <Tooltip title="行高">
                <Segmented
                  size="small"
                  value={density}
                  onChange={(value) => setDensity(value as TableDensity)}
                  options={[
                    { value: 'compact', label: '紧凑' },
                    { value: 'middle', label: '默认' },
                    { value: 'comfortable', label: '宽松' },
                  ]}
                />
              </Tooltip>
            ) : null}
            {settingsEnabled ? (
              <Dropdown
                trigger={['click']}
                placement="bottomRight"
                popupRender={() => (
                  <div
                    style={{
                      minWidth: 200,
                      padding: 'var(--tg-space-lg)',
                      background: 'var(--tg-color-bg-elevated)',
                      border: '1px solid var(--tg-color-border-subtle)',
                      borderRadius: 'var(--tg-radius-lg)',
                      boxShadow: 'var(--tg-shadow-lg)',
                    }}
                  >
                    <div className="tg-flex-between" style={{ marginBottom: 'var(--tg-space-md)' }}>
                      <Typography.Text strong style={{ fontSize: 'var(--tg-font-size-sm)' }}>
                        列设置
                      </Typography.Text>
                      <Button type="link" size="small" onClick={() => setHidden([])}>
                        全选
                      </Button>
                    </div>
                    <Checkbox.Group
                      value={settingColumns.map((c) => c.key).filter((key) => !hidden.includes(key))}
                      onChange={(checked) => {
                        const visible = checked as string[];
                        setHidden(settingColumns.map((c) => c.key).filter((key) => !visible.includes(key)));
                      }}
                      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--tg-space-sm)' }}
                    >
                      {settingColumns.map((column) => (
                        <Checkbox key={column.key} value={column.key}>
                          {column.title}
                        </Checkbox>
                      ))}
                    </Checkbox.Group>
                  </div>
                )}
              >
                <Tooltip title="列设置">
                  <Button type="text" icon={<SettingOutlined />} aria-label="列设置" />
                </Tooltip>
              </Dropdown>
            ) : null}
            {onRetry ? (
              <Tooltip title="刷新">
                <Button type="text" icon={<ReloadOutlined />} loading={loading} onClick={onRetry} aria-label="刷新" />
              </Tooltip>
            ) : null}
          </div>
        </div>
      ) : null}
      <div className="tg-table-body">{body}</div>
    </div>
  );
}

export default DataTable;
