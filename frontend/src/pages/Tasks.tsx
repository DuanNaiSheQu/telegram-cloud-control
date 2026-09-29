/**
 * 任务中心：状态/类型/账号/Bot/只看失败筛选 + 服务端排序 + 分页 +
 * 状态汇总（含 overdue/stuck）+ 失败原因完整展示（Tooltip + 展开行）+
 * 单条重试/取消 + 勾选批量重试（POST /api/tasks/bulk/retry，404 时回退逐条）+
 * 自动刷新开关 + 详情抽屉（payload/result/error/worker_id/时间线）+ 导出 CSV。
 */
import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button, Checkbox, Select, Space, Switch, Tooltip, Typography } from 'antd';
import type { TableColumnsType } from 'antd';
import { RedoOutlined, StopOutlined, FileSearchOutlined } from '@ant-design/icons';
import {
  DataTable,
  FilterBar,
  PageContainer,
  RelativeTime,
  TaskStatusTag,
  TaskTypeTag,
} from '../components';
import { api, ApiError } from '../api/client';
import { accountApi, botApi, dashboardApi, exportApi, taskApi } from '../api/endpoints';
import { useAsyncData, useInterval } from '../hooks/useAsyncData';
import { useTableQuery, buildActiveFilters } from '../hooks/useTableQuery';
import { useWsEvent } from '../hooks/useWebSocket';
import { downloadBlob } from '../utils/download';
import { formatTime, stringifyDetail } from '../utils/format';
import { toast } from '../utils/feedback';
import { TASK_STATUS_OPTIONS, TASK_TYPE_OPTIONS } from '../constants';
import type { TaskOut, TaskStatus, TaskType } from '../api/types';
import { JsonBlock } from '../features/tasks/JsonBlock';
import { TaskDetailDrawer } from '../features/tasks/TaskDetailDrawer';
import '../features/tasks/tasks.css';

const REFRESH_MS = 10_000;

/** POST /api/tasks/bulk/retry 的响应（后端逐条给结果） */
interface BulkRetryOut {
  ok: boolean;
  requested: number;
  succeeded: number;
  failed: number;
  results: Array<{ task_id: string; ok: boolean; message: string }>;
}

/** 每个状态对应的视觉语义：数字用它自己的颜色，异常态才抢眼 */
const STATUS_CHIP_TONE: Record<TaskStatus, string> = {
  pending: 'is-neutral',
  pending_confirmation: 'is-info',
  running: 'is-info',
  completed: 'is-success',
  failed: 'is-danger',
  cancelled: 'is-muted',
};

const STATUS_CHIP_ORDER: TaskStatus[] = [
  'pending',
  'pending_confirmation',
  'running',
  'completed',
  'failed',
  'cancelled',
];

export default function Tasks() {
  const [searchParams] = useSearchParams();

  const q = useTableQuery({
    filters: {
      status: (searchParams.get('status') as TaskStatus) || ('' as TaskStatus | ''),
      type: (searchParams.get('type') as TaskType) || ('' as TaskType | ''),
      account_id: searchParams.get('account_id') as string | null,
      bot_id: null as string | null,
      only_failed: searchParams.get('only_failed') === 'true',
    },
    pageSize: 20,
  });

  const tasks = useAsyncData(
    () =>
      taskApi.list({
        ...q.params,
        sort: q.sort ?? undefined,
        order: q.order ?? undefined,
      }),
    [q.paramsKey, q.sort, q.order],
  );
  // overdue / stuck 来自工作台口径（后端只在 dashboard 给这两个数）
  const dashboard = useAsyncData(() => dashboardApi.get(), [], { silentError: true });
  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }, { silent: true }), []);
  const bots = useAsyncData(async () => {
    try {
      return await botApi.list();
    } catch {
      return [];
    }
  }, []);

  const [autoRefresh, setAutoRefresh] = useState(true);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  // 展开行控制：「日志」按钮和行首的展开箭头共用这一份状态，
  // 之前只能点那个不起眼的小箭头才能看到日志，很多人根本不知道有这功能
  const [expandedIds, setExpandedIds] = useState<string[]>([]);
  const toggleExpanded = (id: string) =>
    setExpandedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  const [batchRetrying, setBatchRetrying] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);

  useInterval(() => {
    void tasks.reload();
  }, autoRefresh ? REFRESH_MS : null);

  // 任务状态变化（WS 推送）就刷新一次，让重试/取消结果尽快反映
  useWsEvent('task', () => {
    void tasks.reload();
  });

  const counts = tasks.data?.counts ?? {};
  const failedCount = counts.failed ?? 0;
  const pageItems = tasks.data?.items ?? [];
  const selectedOnPage = pageItems.filter((item) => selectedIds.includes(item.id)).length;

  const toggleOne = (id: string, checked: boolean) => {
    setSelectedIds((prev) => (checked ? [...prev, id] : prev.filter((item) => item !== id)));
  };

  const togglePage = (checked: boolean) => {
    setSelectedIds((prev) => {
      const pageIds = pageItems.map((item) => item.id);
      if (checked) return [...new Set([...prev, ...pageIds])];
      return prev.filter((id) => !pageIds.includes(id));
    });
  };

  const handleRetry = async (task: TaskOut) => {
    try {
      const res = await taskApi.retry(task.id);
      toast.success(res.message || '已重新排队');
      void tasks.reload();
    } catch {
      /* client 已统一提示 */
    }
  };

  const handleCancel = async (task: TaskOut) => {
    try {
      const res = await taskApi.cancel(task.id);
      toast.success(res.message || '已取消该任务');
      void tasks.reload();
    } catch {
      /* client 已统一提示 */
    }
  };

  /** 一键重试全部失败：先按当前筛选拉出失败任务 id，再走批量重试接口 */
  const retryAllFailed = async () => {
    setBatchRetrying(true);
    try {
      const list = await taskApi.list(
        { status: 'failed', page: 1, page_size: 200 },
        { silent: true },
      );
      const ids = (list.items ?? []).map((item) => item.id);
      if (!ids.length) {
        toast.info('当前没有失败的任务');
        return;
      }
      const res = await api.post<BulkRetryOut>('/api/tasks/bulk/retry', { task_ids: ids }, { silent: true });
      if (res.failed === 0) {
        toast.success(`已重新排队 ${res.succeeded} 个失败任务`);
      } else {
        toast.warning(`重试完成：成功 ${res.succeeded} 个，失败 ${res.failed} 个`);
      }
      void tasks.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setBatchRetrying(false);
    }
  };

  const handleBatchRetry = async () => {
    if (!selectedIds.length) return;
    setBatchRetrying(true);
    try {
      const res = await api.post<BulkRetryOut>(
        '/api/tasks/bulk/retry',
        { task_ids: selectedIds },
        { silent: true },
      );
      if (res.failed === 0) {
        toast.success(`批量重试成功：${res.succeeded} 个任务已重新排队`);
      } else {
        const first = res.results.find((item) => !item.ok)?.message ?? '';
        toast.warning(
          `批量重试完成：成功 ${res.succeeded} 个，失败 ${res.failed} 个`
          + `${first ? `（${first}${res.failed > 1 ? ' 等' : ''}）` : ''}`,
          { duration: 6 },
        );
      }
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.status === 404) {
        // 后端还没有 bulk/retry 时的回退：逐条重试（retry 幂等：已 pending 会回 400）
        let ok = 0;
        const failures: string[] = [];
        for (const id of selectedIds) {
          try {
            await taskApi.retry(id);
            ok += 1;
          } catch (inner) {
            failures.push((inner as Error).message);
          }
        }
        if (failures.length === 0) toast.success(`批量重试成功：${ok} 个任务已重新排队`);
        else toast.warning(`批量重试完成：成功 ${ok} 个，失败 ${failures.length} 个（${failures[0]}）`, { duration: 6 });
      } else {
        toast.error(apiError.friendlyMessage || '批量重试失败');
      }
    } finally {
      setBatchRetrying(false);
      setSelectedIds([]);
      void tasks.reload();
    }
  };

  const handleExport = async () => {
    const res = await exportApi.tasks({
      ...q.params,
      sort: q.sort ?? undefined,
      order: q.order ?? undefined,
    });
    downloadBlob(res.blob, res.filename);
  };

  const columns = useMemo<TableColumnsType<TaskOut>>(() => {
    const selectColumn: TableColumnsType<TaskOut>[number] = {
      key: 'select',
      width: 42,
      fixed: 'left',
      title: (
        <Checkbox
          checked={pageItems.length > 0 && selectedOnPage === pageItems.length}
          indeterminate={selectedOnPage > 0 && selectedOnPage < pageItems.length}
          onChange={(event) => togglePage(event.target.checked)}
          aria-label="选择本页全部任务"
        />
      ),
      render: (_: unknown, record: TaskOut) => (
        <Checkbox
          checked={selectedIds.includes(record.id)}
          onChange={(event) => toggleOne(record.id, event.target.checked)}
          onClick={(event) => event.stopPropagation()}
          aria-label={`选择任务 ${record.id}`}
        />
      ),
    };

    return [
      selectColumn,
      {
        title: '类型',
        key: 'type',
        dataIndex: 'type',
        width: 150,
        render: (_: unknown, record) => <TaskTypeTag type={record.type} label={record.type_label} />,
      },
      {
        title: '状态',
        key: 'status',
        dataIndex: 'status',
        width: 120,
        render: (_: unknown, record) => <TaskStatusTag status={record.status} label={record.status_label} />,
      },
      {
        title: '账号 / Bot',
        key: 'owner',
        dataIndex: 'account_label',
        width: 150,
        render: (_: unknown, record) => {
          if (record.account_label) {
            return (
              <Tooltip title={`账号 ID ${record.account_id ?? '—'}`}>
                <span>{record.account_label}</span>
              </Tooltip>
            );
          }
          if (record.bot_label) {
            return <SoftTagBot label={record.bot_label} />;
          }
          return <Typography.Text type="secondary">—</Typography.Text>;
        },
      },
      {
        title: '失败原因',
        key: 'error',
        dataIndex: 'error',
        width: 320,
        render: (value: string) =>
          value ? (
            <Tooltip title={<div style={{ maxWidth: 520, whiteSpace: 'pre-wrap' }}>{value}</div>}>
              <span className="tg-clamp-cell tg-text-danger">{value}</span>
            </Tooltip>
          ) : (
            <Typography.Text type="secondary">—</Typography.Text>
          ),
      },
      {
        title: '重试次数',
        key: 'attempts',
        dataIndex: 'attempts',
        width: 100,
        render: (value: number, record) => (
          <Typography.Text
            style={{
              color: record.status === 'failed' && value >= record.max_attempts ? 'var(--tg-color-danger)' : undefined,
            }}
          >
            {value}/{record.max_attempts}
          </Typography.Text>
        ),
      },
      {
        title: '创建时间',
        key: 'created_at',
        dataIndex: 'created_at',
        width: 150,
        render: (value: string | null) => <RelativeTime value={value} />,
      },
      { title: '开始时间', key: 'started_at', dataIndex: 'started_at', width: 150, render: (v: string | null) => formatTime(v) },
      { title: '完成时间', key: 'completed_at', dataIndex: 'completed_at', width: 150, render: (v: string | null) => formatTime(v) },
      {
        title: 'Worker',
        key: 'worker_id',
        dataIndex: 'worker_id',
        width: 130,
        render: (value: string | null) =>
          value ? (
            <Typography.Text code style={{ fontSize: 'var(--tg-font-size-sm)' }}>
              {value}
            </Typography.Text>
          ) : (
            <Typography.Text type="secondary">—</Typography.Text>
          ),
      },
      {
        title: '操作',
        key: 'actions',
        width: 160,
        fixed: 'right',
        render: (_: unknown, record) => {
          const logCount = ((record.result as Record<string, unknown> | null)?.logs as unknown[] | undefined)?.length ?? 0;
          const canRetry = record.status === 'failed' || record.status === 'pending_confirmation';
          const canCancel =
            record.status === 'pending' ||
            record.status === 'running' ||
            record.status === 'pending_confirmation';
          return (
            <Space size={0}>
              <Tooltip
                title={logCount ? `展开看执行日志（${logCount} 条，执行中会实时追加）` : '还没有日志——任务开始执行后这里会实时刷新'}
              >
                <Button type="text" size="small" onClick={() => toggleExpanded(record.id)}>
                  日志{logCount ? ` ${logCount}` : ''}
                </Button>
              </Tooltip>
              <Tooltip title={canRetry ? '重新排队（attempts 归零）' : '只允许失败或等待确认的任务重试'}>
                <Button
                  type="text"
                  size="small"
                  icon={<RedoOutlined />}
                  disabled={!canRetry}
                  onClick={() => void handleRetry(record)}
                >
                  重试
                </Button>
              </Tooltip>
              <Tooltip title={canCancel ? '取消任务' : '只有待执行 / 等待确认 / 执行中的任务可以取消'}>
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<StopOutlined />}
                  disabled={!canCancel}
                  onClick={() => void handleCancel(record)}
                >
                  取消
                </Button>
              </Tooltip>
              <Button
                type="text"
                size="small"
                icon={<FileSearchOutlined />}
                onClick={() => setDetailId(record.id)}
              >
                详情
              </Button>
            </Space>
          );
        },
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIds, selectedOnPage, pageItems.length]);

  const expandable = useMemo(
    () => ({
      expandedRowKeys: expandedIds,
      onExpandedRowsChange: (keys: readonly React.Key[]) => setExpandedIds(keys.map(String)),
      expandedRowRender: (record: TaskOut) => (
        <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)', padding: 'var(--tg-space-md) 0' }}>
          {(() => {
            // 执行日志：任务跑的过程中每一步都写进 result.logs，
            // 批量任务（一号一条）就能看到「这一号做到哪了」
            const logs = ((record.result as Record<string, unknown> | null)?.logs as
              | { at: string; stage: string; detail: string }[]
              | undefined) ?? [];
            const progress = (record.result as Record<string, unknown> | null) ?? {};
            const summaryParts = ['sent', 'total', 'joined', 'fetched']
              .filter((key) => progress[key] !== undefined)
              .map((key) => `${key}=${progress[key]}`);
            if (!logs.length && !summaryParts.length) return null;
            return (
              <div className="tg-stack" style={{ gap: 'var(--tg-space-xs)' }}>
                <b style={{ fontSize: 'var(--tg-font-size-sm)' }}>
                  执行日志{summaryParts.length ? `（${summaryParts.join(' · ')}）` : ''}
                </b>
                {logs.length ? (
                  <div className="tg-stack" style={{ gap: 2, maxHeight: 220, overflowY: 'auto' }}>
                    {logs.map((item, index) => (
                      <div key={`${item.at}-${index}`} style={{ fontSize: 'var(--tg-font-size-sm)' }}>
                        <span className="tg-mono tg-muted">{item.at.slice(11, 19)}</span>{' '}
                        <span>{item.detail || item.stage}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className="tg-muted" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
                    （这一步还没产生日志；批量任务执行时这里会逐步刷新）
                  </span>
                )}
              </div>
            );
          })()}
          <JsonBlock title="入队参数（payload）" value={record.payload} maxHeight={200} />
          <JsonBlock
            title="执行结果（result）"
            value={record.result ?? null}
            emptyText="（还没有结果）"
            maxHeight={200}
          />
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 'var(--tg-space-xl)',
              color: 'var(--tg-color-text-tertiary)',
              fontSize: 'var(--tg-font-size-sm)',
            }}
          >
            <span>任务 ID：{record.id}</span>
            {record.created_by_name ? <span>发起人：{record.created_by_name}</span> : null}
            <span>下次执行：{formatTime(record.next_run_at)}</span>
            {record.dialog_id ? <span>会话：{record.dialog_id}</span> : null}
          </div>
        </div>
      ),
      rowExpandable: (record: TaskOut) => Boolean(stringifyDetail(record.payload)),
    }),
    [],
  );

  const activeFilters = buildActiveFilters([
    {
      key: 'status',
      label: '状态',
      display: q.filters.status
        ? TASK_STATUS_OPTIONS.find((item) => item.value === q.filters.status)?.label ?? q.filters.status
        : '',
      clear: () => q.setFilter('status', ''),
    },
    {
      key: 'type',
      label: '类型',
      display: q.filters.type
        ? TASK_TYPE_OPTIONS.find((item) => item.value === q.filters.type)?.label ?? q.filters.type
        : '',
      clear: () => q.setFilter('type', ''),
    },
    {
      key: 'account_id',
      label: '账号',
      display: q.filters.account_id
        ? accounts.data?.items.find((item) => item.id === q.filters.account_id)?.phone_masked ?? q.filters.account_id
        : '',
      clear: () => q.setFilter('account_id', null),
    },
    {
      key: 'bot_id',
      label: 'Bot',
      display: q.filters.bot_id
        ? bots.data?.find((item) => item.id === q.filters.bot_id)?.bot_username ?? q.filters.bot_id
        : '',
      clear: () => q.setFilter('bot_id', null),
    },
    {
      key: 'only_failed',
      label: '只看失败',
      display: q.filters.only_failed ? '开启' : '',
      clear: () => q.setFilter('only_failed', false),
    },
  ]);

  const chipStatus = (status: TaskStatus) => {
    const isActive = q.filters.status === status;
    const count = counts[status] ?? 0;
    return (
      <button
        key={status}
        type="button"
        className={[
          'tg-task-chip',
          STATUS_CHIP_TONE[status] ?? 'is-neutral',
          isActive ? 'is-active' : '',
          count > 0 ? 'has-count' : 'is-zero',
        ]
          .filter(Boolean)
          .join(' ')}
        onClick={() => q.setFilter('status', isActive ? '' : status)}
        title={isActive ? '点击取消该状态筛选' : `只看「${TASK_STATUS_OPTIONS.find((item) => item.value === status)?.label ?? status}」`}
      >
        <span className="tg-task-chip-count">{count}</span>
        {TASK_STATUS_OPTIONS.find((item) => item.value === status)?.label ?? status}
      </button>
    );
  };

  return (
    <PageContainer
      title="任务中心"
      description="所有异步任务的队列视图：待执行、等待确认、执行中、失败都可在这里看到；失败任务可直接重试，执行中的可取消。"
    >
      <div className="tg-task-summary" style={{ marginBottom: 'var(--tg-space-lg)' }}>
        {STATUS_CHIP_ORDER.slice(0, 3).map(chipStatus)}
        <span className="tg-task-summary-sep" aria-hidden />
        {STATUS_CHIP_ORDER.slice(3).map(chipStatus)}
        <span className="tg-task-summary-sep" aria-hidden />
        <Tooltip title="来自工作台口径：已超过预计执行时间、仍待执行的任务数">
          <span className="tg-task-chip is-static is-overdue">
            <span className="dot" />
            <span className="tg-task-chip-count">{dashboard.data?.tasks_overdue ?? 0}</span>
            超时
          </span>
        </Tooltip>
        <Tooltip title="来自工作台口径：长时间无进展、疑似卡死的执行中任务数">
          <span className="tg-task-chip is-static is-stuck">
            <span className="dot" />
            <span className="tg-task-chip-count">{dashboard.data?.tasks_stuck ?? 0}</span>
            卡死
          </span>
        </Tooltip>
        <span className="tg-task-summary-actions">
          {failedCount > 0 ? (
            <Button
              danger
              size="small"
              icon={<RedoOutlined />}
              loading={batchRetrying}
              onClick={() => void retryAllFailed()}
            >
              重试全部失败（{failedCount}）
            </Button>
          ) : null}
          <span className="tg-task-summary-total">共 {tasks.data?.total ?? 0} 条</span>
        </span>
      </div>

      <FilterBar
        collapsible
        onReset={q.reset}
        onSearch={() => void tasks.reload()}
        loading={tasks.loading}
        activeFilters={activeFilters}
        extra={
          <Space size={4}>
            <span style={{ color: 'var(--tg-color-text-secondary)', fontSize: 'var(--tg-font-size-sm)' }}>
              自动刷新（10 秒）
            </span>
            <Switch size="small" checked={autoRefresh} onChange={setAutoRefresh} />
          </Space>
        }
      >
        <Select
          allowClear
          placeholder="状态"
          style={{ width: 140 }}
          value={q.filters.status || undefined}
          onChange={(value) => q.setFilter('status', (value as TaskStatus) ?? '')}
          options={TASK_STATUS_OPTIONS}
        />
        <Select
          allowClear
          placeholder="类型"
          style={{ width: 170 }}
          value={q.filters.type || undefined}
          onChange={(value) => q.setFilter('type', (value as TaskType) ?? '')}
          options={TASK_TYPE_OPTIONS}
        />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="账号"
          style={{ width: 200 }}
          value={q.filters.account_id ?? undefined}
          onChange={(value) => q.setFilter('account_id', value ?? null)}
          options={(accounts.data?.items ?? []).map((item) => ({
            value: item.id,
            label: `${item.phone_masked}${item.remark ? `（${item.remark}）` : ''}`,
          }))}
        />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="Bot"
          style={{ width: 170 }}
          value={q.filters.bot_id ?? undefined}
          onChange={(value) => q.setFilter('bot_id', value ?? null)}
          options={(bots.data ?? []).map((item) => ({
            value: item.id,
            label: item.bot_username ? `@${item.bot_username}` : item.name,
          }))}
        />
        <Space size={4}>
          <span>只看失败</span>
          <Switch
            size="small"
            checked={q.filters.only_failed}
            onChange={(checked) => q.setFilter('only_failed', checked)}
          />
        </Space>
      </FilterBar>

      <DataTable<TaskOut>
        rowKey="id"
        columns={columns}
        dataSource={pageItems}
        total={tasks.data?.total}
        page={q.page}
        pageSize={q.pageSize}
        onPageChange={q.setPage}
        loading={tasks.loading}
        error={tasks.error}
        onRetry={() => void tasks.reload()}
        sortableColumns={{
          type: 'type',
          status: 'status',
          attempts: 'attempts',
          created_at: 'created_at',
          started_at: 'started_at',
          completed_at: 'completed_at',
        }}
        sortField={q.sort}
        sortOrder={q.order}
        onSortChange={q.setSort}
        columnSettingsKey="tasks"
        scrollX={1500}
        expandable={expandable}
        onExport={handleExport}
        toolbar={
          <Space size={4}>
            <Button
              type="primary"
              ghost
              size="small"
              icon={<RedoOutlined />}
              loading={batchRetrying}
              disabled={!selectedIds.length}
              onClick={() => void handleBatchRetry()}
            >
              批量重试{selectedIds.length ? `（${selectedIds.length}）` : ''}
            </Button>
            {selectedIds.length ? (
              <Button type="link" size="small" onClick={() => setSelectedIds([])}>
                清空选择
              </Button>
            ) : null}
          </Space>
        }
        empty={{
          art: 'task',
          title: '没有符合条件的任务',
          description: '换个筛选条件，或点「重置」看全部任务。',
        }}
      />

      <TaskDetailDrawer
        taskId={detailId}
        onClose={() => setDetailId(null)}
        onRetry={(task) => void handleRetry(task)}
        onCancel={(task) => void handleCancel(task)}
      />
    </PageContainer>
  );
}

function SoftTagBot({ label }: { label: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '0 var(--tg-space-sm)',
        borderRadius: 'var(--tg-radius-sm)',
        background: 'var(--tg-color-bg-sunken)',
        border: '1px solid var(--tg-color-border-subtle)',
        color: 'var(--tg-color-text-secondary)',
        fontSize: 'var(--tg-font-size-sm)',
      }}
    >
      @{label}
    </span>
  );
}
