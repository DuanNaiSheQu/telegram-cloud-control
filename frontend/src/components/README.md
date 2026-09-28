# 共享组件库（页面负责人照这个用）

> 文档索引：[docs/README.md](../../../docs/README.md) · 相邻：主题 token [../theme/README.md](../theme/README.md) · 贡献指南 [docs/CONTRIBUTING.md](../../../docs/CONTRIBUTING.md)

> 目标：页面只消费这里的组件 + `theme/tokens.ts` 的变量，**不自己写样式、不写死色值**。
> 每个组件的完整 props 契约写在文件头注释里；本文件是速查表。
> 开发环境打开 **http://127.0.0.1:5173/__components** 可以看到全部组件的真实渲染（深/浅色都切一遍）。

## 0. 页面骨架（每个页面的标准结构）

```tsx
import {
  PageContainer, StatGrid, StatCard, SectionCard, DataTable, FilterBar,
  EmptyState, ErrorState, StatusBadge, ConfirmModal, DetailDrawer,
} from '../components';
import { useTableQuery, buildActiveFilters } from '../hooks/useTableQuery';
import { useAsyncData } from '../hooks/useAsyncData';
import { accountApi, exportApi } from '../api/endpoints';

export default function Accounts() {
  const q = useTableQuery({ filters: { status: '', keyword: '' }, pageSize: 20 });

  const { data, loading, error, reload } = useAsyncData(
    () => accountApi.list({ ...q.params, sort: q.sort ?? undefined, order: q.order ?? undefined }),
    [q.paramsKey, q.sort, q.order],
  );

  return (
    <PageContainer
      title="账号管理"
      description="状态、分组、心跳、当前任务；异常口径与工作台一致。"
      actions={<Button type="primary">新建账号</Button>}
    >
      <StatGrid>
        <StatCard title="账号总数" value={data?.summary?.total ?? 0} tone="neutral" />
        {/* … */}
      </StatGrid>

      <FilterBar collapsible onReset={q.reset} onSearch={reload} loading={loading}
        activeFilters={buildActiveFilters([
          { key: 'status', label: '状态', display: q.filters.status, clear: () => q.setFilter('status', '') },
        ])}>
        <Input value={q.filters.keyword} onChange={(e) => q.setFilter('keyword', e.target.value)} allowClear />
      </FilterBar>

      <DataTable
        rowKey="id"
        columns={columns}
        dataSource={data?.items ?? []}
        total={data?.total}
        page={q.page} pageSize={q.pageSize} onPageChange={q.setPage}
        loading={loading} error={error} onRetry={reload}
        sortableColumns={{ phone_masked: 'phone', last_heartbeat: 'last_heartbeat' }}
        sortField={q.sort} sortOrder={q.order} onSortChange={q.setSort}
        columnSettingsKey="accounts"
        scrollX={1400}
        onExport={async () => { const r = await exportApi.accounts({ ...q.params }); downloadBlob(r.blob, r.filename); }}
        empty={{ art: 'accounts', title: '还没有账号', action: <Button type="primary">新建账号</Button> }}
      />
    </PageContainer>
  );
}
```

**不写死色值**：颜色/间距/圆角用 `var(--tg-*)`；确实需要 JS 色值时用 `useTheme().tokens.color`。

## 1. 布局与容器

| 组件 | 关键 props | 说明 |
|---|---|---|
| `PageContainer` | `title`(必填) `description` `actions` `breadcrumb` `tabs` `gap:'normal'\|'tight'` `children` | 页面第一层。title 渲染唯一 `<h1>` |
| `PageHeader` | 同上（不含 children） | 自定义布局时单独用 |
| `StatGrid` | `minWidth`(默认 210) `children` | 统计卡一行，按宽度自动 2/4/6 列 |
| `SectionCard` | `title` `subtitle` `extra` `loading` `skeletonRows` `error` `onRetry` `empty` `bodyPadding:'normal'\|'tight'\|'none'` `hoverable` | 区块卡片，自带 loading/error/empty 三态 |
| `ErrorBoundary` | `title` `description` `onReset` `compact` | 局部兜底（外壳已给每个页面套了一层） |
| `NotFound` | `pathname` `onBack` | 404，外壳内渲染 |

## 2. 数据展示

| 组件 | 关键 props | 说明 |
|---|---|---|
| `StatCard` | `title` `value` `unit` `icon` `tone:'primary'\|'success'\|'warning'\|'danger'\|'info'\|'neutral'` `delta:{value,suffix,label,goodWhen:'up'\|'down'\|'none',formatter}` `trend:number[]` `hint` `footer` `loading` `onClick` | 数字 + 环比 + 图标 + 迷你趋势 |
| `DataTable<T>` | 见下方专项 | 列表页标准表格 |
| `TrendSparkline` | `data:(number\|{t,v})[]` `width` `height` `color` `area` `strokeWidth` `showLastDot` `showMinMax` `baseline` `formatValue` `emptyText` | 纯 SVG，无图表库 |
| `CopyableText` | `value` `display` `mono` `maxLength` `truncate:'end'\|'middle'` `tooltip` `onCopied` | 长 ID / 手机号；复制失败会提示 |
| `RelativeTime` | `value` `fallback` `refreshMs` `showAbsolute` `prefix` | 「3 分钟前」，30s 自动重算，悬浮看绝对时间 |
| `DetailDrawer` | `open` `title` `subtitle` `onClose` `width` `loading` `error` `onRetry` `sections:DetailSection[]` `children` `extra` `footer` | 详情抽屉；`DetailItem={label,value,span:'full'\|1\|2,mono,copyable}` |

### DataTable props

| prop | 类型 | 说明 |
|---|---|---|
| `columns` / `dataSource` / `rowKey` | antd 原样 | 必填 |
| `loading` | boolean | 首次加载 → 骨架屏；已有数据 → 保留旧数据 + 右上角「刷新中」 |
| `error` / `onRetry` | string \| null / fn | 失败态整表替换为 ErrorState，带重试 |
| `empty` | EmptyStateProps | 空态文案/引导按钮 |
| `total` `page` `pageSize` `onPageChange(page,pageSize)` | 服务端分页 | 不传 `total`/`onPageChange` 则不显示分页 |
| `sortField` `sortOrder` `onSortChange(field\|null, order\|null)` | `'asc'\|'desc'\|null` | 服务端排序 |
| `sortableColumns` | `Record<列key, 后端字段名>` | **只有登记过的列可点排序** |
| `title` `toolbar` `extra` `exportAction` | ReactNode | 工具条；`exportAction` 是导出按钮位 |
| `onExport` `exportText` | fn / string | 快捷导出按钮（自己调 `exportApi.*` 再 `downloadBlob`） |
| `columnSettingsKey` | string | 传了就开启「列设置」并按 key 记忆 |
| `densityKey` `defaultDensity` `showDensity` | string / `'compact'\|'middle'\|'comfortable'` | 行高记忆 |
| `skeleton` `skeletonRows` | boolean / number | 首屏骨架 |
| `scrollX` `sticky` `bordered` `size` `rowClassName` `onRow` `expandable` | antd 原样透传 | 列多时给 `scrollX`（如 1400） |

## 3. 状态与反馈

| 组件 | 关键 props | 说明 |
|---|---|---|
| `StatusBadge` | `status` `label` `reason` `size:'sm'\|'md'` `showDot` `variant:'soft'\|'outline'\|'text'` | 账号 7 态；`label` 用后端 `status_label` |
| `StatusDot` | `status` `kind:'account'\|'task'` `tone` `size` `pulse` `label` `tooltip` | 状态圆点，运行中/在线加 `pulse` |
| `TaskStatusTag` | `status` `label` `size` `showDot` | 任务状态 |
| `TaskTypeTag` | `type` `label` | 任务类型 |
| `CurrentTaskTag` | `task` `label` | 账号当前任务（空闲/同步/等待确认/转发） |
| `MessageStatusTag` | `status` `label` | 消息状态 |
| `SoftTag` | `tone` `children` | 自定义语义色标签 |
| `EmptyState` | `art:'search'\|'list'\|'chart'\|'inbox'\|'error'\|'accounts'\|'message'\|'task'\|'network'\|ReactNode` `title` `description` `action` `secondaryAction` `compact` | 空态（内联 SVG 插画） |
| `ErrorState` | `title` `description` `error` `onRetry` `retryText` `extra` `compact` | 失败态，永不白屏 |
| `CardSkeleton` `TableSkeleton` `ListSkeleton` `StatSkeleton` `ChartSkeleton` `PageSkeleton` | `rows` `columns` `count` `height` `avatar` `title` | 骨架屏五型 |
| `toast`（`utils/feedback`） | `toast.success/error/warning/info/loading/notify` | 统一中文提示，相同内容 2s 内去重 |

## 4. 交互组件

| 组件 | 关键 props | 说明 |
|---|---|---|
| `FilterBar` | `children` `primary` `extra` `activeFilters` `onReset` `onSearch` `loading` `collapsible` `defaultCollapsed` | 可折叠筛选；回车即查询；底部已选条件 Tag |
| `ConfirmModal` | `open` `title` `content` `description` `okText` `cancelText` `danger` `loading` `onOk` `onCancel` `confirmPhrase` `extra` | 二次确认；`confirmPhrase` 用于高危操作（需原样输入） |
| `DetailDrawer` | 见上表 | 详情抽屉 |
| `GlobalSearch` | `open` `onClose`（外壳已内置，⌘K/Ctrl+K） | 全局搜索：页面/账号/会话/消息 |

## 5. hooks

| hook | 说明 |
|---|---|
| `useAsyncData(fetcher, deps, {immediate,silentError,onSuccess,onError})` | `{data,loading,error,reload,refetch,setData,initialLoading}`；并发安全、刷新保留旧数据 |
| `useTableQuery({filters,pageSize,sort,order})` | `{page,pageSize,sort,order,filters,params,paramsKey,setPage,setPageSize,setSort,setFilter,patchFilters,reset,activeCount}` |
| `buildActiveFilters([{key,label,display,clear}])` | 生成 `FilterBar.activeFilters` |
| `useInterval(cb, delay)` / `useVisibilityRefresh(cb)` | 轮询 / 切回标签页刷新 |
| `useDebouncedValue(value, ms)` / `useDebouncedCallback(fn, ms)` | 防抖 |
| `useBreakpoint()` | `{width,isNarrow(<1024),isCompact(<1280),isWide(>=1600)}` |
| `useMediaQuery(query)` | 任意媒体查询 |
| `useLocalStorage(key, default)` | 与 localStorage 同步的状态（列设置/密度/折叠） |
| `useWebSocket(enabled)` | `{status,subscribe,unsubscribe,onEvent}`（全局单例） |
| `useWsEvent(kind, handler)` | 只订阅某类推送：`useWsEvent('message', e => …)` |
| `useTheme()` | `{mode,isDark,tokens,antdTheme,preference,setPreference,toggle}` |

## 6. API 层速查

```ts
import { accountApi, accountBulkApi, exportApi, dialogApi, messageApi,
         taskApi, metricsApi, notificationApi, healthApi, sortParams } from '../api/endpoints';
import { ApiError, downloadFile } from '../api/client';

accountApi.list(query, { silent: true })      // 第二参数可静默（不弹全局提示）
accountApi.overview(id)                       // 账号详情一次拿全
accountBulkApi.check({ scope: 'group:<id>' }) // 批量：check/syncDialogs/assign/group/proxy/status/disable/enable/releaseLease
metricsApi.trends('24h')                      // 趋势序列
notificationApi.list({ unread_only: true })   // 通知
exportApi.accounts(query)                     // → {blob, filename, total, truncated}
```

错误对象 `ApiError`：`status`（0=网络/超时）、`detail`、`friendlyMessage`（中文）、`isNetworkError`。
**不做**：批量私信 / 群发 / 素材群发 / 批量加群 / 批量退群 / 强拉进群 / 批量改资料（见 `规划.md`「不做这些」）——
API 层与 UI 层都不提供入口。

## 7. 换皮验收清单（改 tokens.ts 后自查）

1. `npm run dev` → 打开 `/__components`，深/浅色各切一遍，确认无写死色值残留；
2. 1280 / 1440 / 1920 三档宽度，以及 1024 窄屏（侧栏变图标条、内容区自适应）；
3. 表格长文本用 `.ellipsis` / `.tg-clamp-2`，窄屏不出现横向滚动条（列多时给 `scrollX`）；
4. 空数据、后端 500、接口超时三种情况都不白屏（`EmptyState` / `ErrorState` / `toast`）。
