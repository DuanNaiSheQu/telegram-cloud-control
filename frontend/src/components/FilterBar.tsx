/**
 * FilterBar —— 列表页统一筛选栏（可折叠 + 已选条件 Tag + 重置 + 回车查询）。
 *
 * props 契约：
 * ┌────────────────┬────────────────────────────────────────────────────────────┐
 * │ children       │ ReactNode  筛选控件（Input / Select / DatePicker …）         │
 * │ primary        │ ReactNode  折叠时也显示的控件（一般是关键词搜索框）           │
 * │ extra          │ ReactNode  右侧额外按钮                                      │
 * │ activeFilters  │ ActiveFilter[]  已选条件（useTableQuery 的 buildActiveFilters）│
 * │ onReset        │ () => void  「重置」按钮（同时清空已选条件）                  │
 * │ onSearch       │ () => void  「查询」按钮；在筛选区按回车也会触发              │
 * │ loading        │ boolean     查询中（按钮显示 loading）                       │
 * │ collapsible    │ boolean     是否可折叠，默认 false                           │
 * │ defaultCollapsed│ boolean    默认折叠；不传则窄屏(<1280)自动折叠               │
 * │ resetText      │ string      默认「重置」                                     │
 * │ searchText     │ string      默认「查询」                                     │
 * │ className/style│                                                              │
 * └────────────────┴────────────────────────────────────────────────────────────┘
 * 用法：
 *   <FilterBar collapsible onReset={q.reset} onSearch={reload} loading={loading}
 *              activeFilters={buildActiveFilters([{key:'status',label:'状态',display:...}])}>
 *     <Select … /> <Select … />
 *   </FilterBar>
 */
import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react';
import { Button } from 'antd';
import { CloseOutlined, DownOutlined, ReloadOutlined, SearchOutlined, UpOutlined } from '@ant-design/icons';
import { useBreakpoint } from '../hooks/useMediaQuery';
import type { ActiveFilter } from '../hooks/useTableQuery';

export interface FilterBarProps {
  children?: ReactNode;
  primary?: ReactNode;
  extra?: ReactNode;
  activeFilters?: ActiveFilter[];
  onReset?: () => void;
  onSearch?: () => void;
  loading?: boolean;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  resetText?: string;
  searchText?: string;
  className?: string;
  style?: CSSProperties;
}

export function FilterBar({
  children,
  primary,
  extra,
  activeFilters = [],
  onReset,
  onSearch,
  loading = false,
  collapsible = false,
  defaultCollapsed,
  resetText = '重置',
  searchText = '查询',
  className,
  style,
}: FilterBarProps) {
  const { isCompact } = useBreakpoint();
  const [collapsed, setCollapsed] = useState<boolean>(() => defaultCollapsed ?? false);
  const touchedRef = useRef(false);

  // 窄屏默认折叠，宽屏自动展开（用户手动操作过之后不再自动改）
  useEffect(() => {
    if (!collapsible || touchedRef.current || defaultCollapsed !== undefined) return;
    setCollapsed(isCompact);
  }, [collapsible, isCompact, defaultCollapsed]);

  const toggle = () => {
    touchedRef.current = true;
    setCollapsed((value) => !value);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter' || !onSearch) return;
    const target = event.target as HTMLElement;
    // 多行输入（备注、消息正文）不拦回车
    if (target.tagName === 'TEXTAREA') return;
    event.preventDefault();
    onSearch();
  };

  const showFields = !collapsible || !collapsed;

  return (
    <div className={['tg-filter-bar', className].filter(Boolean).join(' ')} style={style}>
      <div className="tg-filter-main" onKeyDown={handleKeyDown}>
        <div className="tg-filter-fields">
          {primary}
          {showFields ? children : null}
        </div>
        <div className="tg-filter-actions">
          {extra}
          {collapsible ? (
            <Button type="text" onClick={toggle} icon={collapsed ? <DownOutlined /> : <UpOutlined />}>
              {collapsed ? '更多筛选' : '收起筛选'}
            </Button>
          ) : null}
          {onReset ? (
            <Button icon={<ReloadOutlined />} onClick={onReset} disabled={loading}>
              {resetText}
              {activeFilters.length ? `(${activeFilters.length})` : ''}
            </Button>
          ) : null}
          {onSearch ? (
            <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={onSearch}>
              {searchText}
            </Button>
          ) : null}
        </div>
      </div>

      {activeFilters.length ? (
        <div className="tg-filter-active">
          <span className="tg-filter-active-label">已选条件：</span>
          {activeFilters.map((filter) => (
            <span className="tg-filter-tag" key={filter.key}>
              <span className="tg-filter-tag-key">{filter.label}</span>
              <span>{filter.value}</span>
              <button
                type="button"
                className="tg-filter-tag-close"
                aria-label={`移除筛选：${filter.label}`}
                onClick={filter.onRemove}
              >
                <CloseOutlined />
              </button>
            </span>
          ))}
          {onReset ? (
            <Button type="link" size="small" onClick={onReset} style={{ padding: 0 }}>
              全部清除
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export default FilterBar;
