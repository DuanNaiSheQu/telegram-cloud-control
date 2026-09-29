import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Checkbox, Input, Select, Space, Switch } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined, SafetyCertificateOutlined, SyncOutlined } from '@ant-design/icons';
import { accountApi, groupApi } from '../api/endpoints';
import { useAsyncData, useInterval } from '../hooks/useAsyncData';
import { useTableQuery, buildActiveFilters } from '../hooks/useTableQuery';
import { formatTime } from '../utils/format';
import { toast } from '../utils/feedback';
import {
  DataTable,
  FilterBar,
  PageContainer,
  RelativeTime,
  SoftTag,
  StatusBadge,
  StatusDot,
} from '../components';
import { useRowSelection } from '../features/accounts/useRowSelection';
import type { AccountOut, CheckRequest, CheckResultOut } from '../api/types';

interface CheckRow extends CheckResultOut {
  checked_at: string;
}

const POLL_MS = 10_000;

/** 筛选条件字段类型 */
interface DetectionFilters extends Record<string, unknown> {
  group_id: string | null;
  keyword: string;
}

export default function Detection() {
  const [draftKeyword, setDraftKeyword] = useState('');
  const selection = useRowSelection();
  const [rows, setRows] = useState<CheckRow[]>([]);
  const [checking, setChecking] = useState(false);
  const [lastScope, setLastScope] = useState<CheckRequest | null>(null);
  const [lastLabel, setLastLabel] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(false);

  const q = useTableQuery<DetectionFilters>({ filters: { group_id: null, keyword: '' }, pageSize: 10 });

  const accounts = useAsyncData(
    () =>
      accountApi.list({
        page: 1,
        page_size: 200,
        group_id: (q.filters.group_id as string | null) ?? undefined,
        keyword: (q.filters.keyword as string) || undefined,
      }),
    [q.paramsKey],
  );
  const groups = useAsyncData(() => groupApi.list(), []);

  const runCheck = async (payload: CheckRequest, label: string) => {
    setChecking(true);
    try {
      const res = await accountApi.checkBatch(payload);
      const list = Array.isArray(res) ? res : ((res as unknown as { items?: CheckResultOut[] }).items ?? []);
      const checkedAt = new Date().toISOString();
      setRows(list.map((item) => ({ ...item, checked_at: checkedAt })));
      setLastScope(payload);
      setLastLabel(label);
      toast.success(`${label}：返回 ${list.length} 条结果，Worker 写回后再次刷新可看最新状态`);
      void accounts.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setChecking(false);
    }
  };

  // 轮询刷新：重跑最近一次检测范围，拿最新结果
  useInterval(() => {
    if (lastScope && !checking) void runCheck(lastScope, lastLabel || '重新检测');
  }, autoRefresh ? POLL_MS : null);

  const failedRows = useMemo(() => rows.filter((row) => !row.reachable), [rows]);

  const retryFailed = () => {
    if (!failedRows.length) return;
    void runCheck({ account_ids: failedRows.map((row) => row.account_id), scope: 'selected' }, `重试 ${failedRows.length} 个失败项`);
  };

  // 封号 / 停用 / 失效的号不该挂在检测页占位置——默认只列还能检测的号，
  // 需要时用开关把它们调出来（检测本身对失效号没意义：它连不上）。
  const [showDead, setShowDead] = useState(false);
  const visibleAccounts = useMemo(() => {
    const items = accounts.data?.items ?? [];
    if (showDead) return items;
    return items.filter((item) => item.status !== 'disabled' && item.status !== 'dead' && item.status !== 'invalid');
  }, [accounts.data, showDead]);
  const hiddenCount = (accounts.data?.items?.length ?? 0) - visibleAccounts.length;

  const deadToggle = (
    <Checkbox checked={showDead} onChange={(e) => setShowDead(e.target.checked)}>
      显示已停用 / 失效的号{hiddenCount > 0 ? `（已隐藏 ${hiddenCount} 个）` : ''}
    </Checkbox>
  );

  const pageIds = useMemo(() => (accounts.data?.items ?? []).map((item) => item.id), [accounts.data]);

  const accountColumns: ColumnsType<AccountOut> = [
    {
      title: (
        <Checkbox
          checked={selection.pageAllSelected(pageIds)}
          indeterminate={selection.pageSomeSelected(pageIds) && !selection.pageAllSelected(pageIds)}
          onChange={(event) => selection.togglePage(pageIds, event.target.checked)}
          aria-label="选择本页全部账号"
        />
      ),
      key: 'select',
      width: 44,
      render: (_: unknown, record) => (
        <Checkbox
          checked={selection.isSelected(record.id)}
          onChange={(event) => selection.toggleOne(record.id, event.target.checked)}
          aria-label={`选择账号 ${record.phone_masked}`}
        />
      ),
    },
    {
      title: '账号',
      dataIndex: 'phone_masked',
      width: 150,
      render: (value: string, record: AccountOut) => (
        <span className="tg-mono">{record.display_label || value}</span>
      ),
    },
    { title: '用户名', dataIndex: 'username', width: 120, render: (value: string | null) => value || <span className="tg-muted">—</span> },
    {
      title: '分组',
      dataIndex: 'group_name',
      width: 110,
      render: (value: string | null) => (value ? <SoftTag tone="primary" size="sm">{value}</SoftTag> : <SoftTag tone="neutral" size="sm">未分组</SoftTag>),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (_: unknown, record) => <StatusBadge status={record.status} label={record.status_label} reason={record.status_reason} size="sm" />,
    },
    { title: '最后检测', dataIndex: 'last_checked_at', width: 150, render: (value: string | null) => <RelativeTime value={value} /> },
    { title: '最后心跳', dataIndex: 'last_heartbeat', width: 150, render: (value: string | null) => <RelativeTime value={value} /> },
  ];

  const resultColumns: ColumnsType<CheckRow> = [
    {
      title: '账号',
      dataIndex: 'phone_masked',
      width: 150,
      render: (value: string, record: { account_label?: string | null; phone_masked?: string }) => (
        <span className="tg-mono">{record.account_label || value}</span>
      ),
    },
    {
      title: '连得上',
      dataIndex: 'reachable',
      width: 100,
      render: (value: boolean) =>
        value ? (
          <span className="tg-flex" style={{ gap: 'var(--tg-space-sm)', alignItems: 'center', color: 'var(--tg-color-success)' }}>
            <StatusDot status="healthy" kind="account" size={8} /> 是
          </span>
        ) : (
          <span className="tg-flex" style={{ gap: 'var(--tg-space-sm)', alignItems: 'center', color: 'var(--tg-color-danger)' }}>
            <StatusDot status="frozen" kind="account" size={8} /> 否
          </span>
        ),
    },
    {
      title: '要验证码',
      dataIndex: 'status',
      width: 100,
      render: (_: unknown, record) =>
        record.status === 'needs_code' ? (
          <SoftTag tone="warning" size="sm">要验证码</SoftTag>
        ) : (
          <span className="tg-muted">—</span>
        ),
    },
    {
      title: '会话失效',
      dataIndex: 'status',
      width: 100,
      render: (_: unknown, record) =>
        record.status === 'invalid' || record.status === 'dead' ? (
          <SoftTag tone="danger" size="sm">会话失效</SoftTag>
        ) : (
          <span className="tg-muted">—</span>
        ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (_: unknown, record) => <StatusBadge status={record.status} label={record.status_label} size="sm" />,
    },
    { title: '说明', dataIndex: 'message', render: (value: string) => value || <span className="tg-muted">—</span> },
    {
      title: '关联任务',
      dataIndex: 'task_id',
      width: 140,
      render: (value: string | null, record) =>
        value ? (
          <Link className="tg-mono" to={`/tasks?account_id=${record.account_id}`} style={{ fontSize: 'var(--tg-font-size-xs)' }}>
            {value.slice(0, 8)}…
          </Link>
        ) : (
          <span className="tg-muted">—</span>
        ),
    },
    { title: '最近检测时间', dataIndex: 'checked_at', width: 160, render: (value: string) => formatTime(value) },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: unknown, record) => (
        <Button size="small" icon={<ReloadOutlined />} onClick={() => void runCheck({ account_ids: [record.account_id], scope: 'selected' }, `重试 ${record.phone_masked}`)}>
          重试
        </Button>
      ),
    },
  ];

  const currentGroup = groups.data?.find((g) => g.id === q.filters.group_id);

  return (
    <PageContainer
      title="账号检测"
      description="检测会写一条账号检测任务，Worker 读到后回写状态；结果为「连得上 / 要验证码 / 会话失效」。"
      actions={
        <Space wrap>
        {deadToggle}
          <Button
            icon={<SafetyCertificateOutlined />}
            disabled={!selection.count}
            loading={checking}
            onClick={() => void runCheck({ account_ids: selection.selectedIds, scope: 'selected' }, `检测选中 ${selection.count} 个`)}
          >
            检测选中（{selection.count}）
          </Button>
          {currentGroup ? (
            <Button
              loading={checking}
              onClick={() => void runCheck({ account_ids: null, scope: `group:${currentGroup.id}` }, `检测分组「${currentGroup.name}」`)}
            >
              检测当前分组
            </Button>
          ) : null}
          <Button
            type="primary"
            loading={checking}
            onClick={() => void runCheck({ account_ids: null, scope: 'all' }, '检测全部')}
          >
            全部检测
          </Button>
        </Space>
      }
    >
      <FilterBar
        collapsible
        onReset={() => {
          q.reset();
          setDraftKeyword('');
        }}
        onSearch={() => q.setFilter('keyword', draftKeyword.trim())}
        loading={accounts.loading}
        activeFilters={buildActiveFilters([
          {
            key: 'group_id',
            label: '分组',
            display: currentGroup?.name,
            clear: () => q.setFilter('group_id', null),
          },
          { key: 'keyword', label: '关键词', display: q.filters.keyword as string, clear: () => { setDraftKeyword(''); q.setFilter('keyword', ''); } },
        ])}
      >
        <Select
          allowClear
          placeholder="按分组筛选"
          style={{ width: 180 }}
          value={(q.filters.group_id as string | null) ?? undefined}
          onChange={(value) => {
            q.setFilter('group_id', value ?? null);
            selection.clear();
          }}
          options={(groups.data ?? []).map((g) => ({ value: g.id, label: `${g.name}（${g.account_count}）` }))}
        />
        <Input allowClear placeholder="手机号 / 用户名关键词" style={{ width: 220 }} value={draftKeyword} onChange={(e) => setDraftKeyword(e.target.value)} />
      </FilterBar>

      <DataTable<AccountOut>
        rowKey="id"
        columns={accountColumns}
        dataSource={visibleAccounts}
        loading={accounts.loading}
        error={accounts.error}
        onRetry={() => void accounts.reload()}
        showDensity={false}
        title={
          selection.count ? (
            <span className="tg-flex" style={{ alignItems: 'center', gap: 'var(--tg-space-sm)' }}>
              <span style={{ color: 'var(--tg-color-primary)' }}>已选 {selection.count} 个</span>
              <Button type="link" size="small" onClick={selection.clear}>
                取消选择
              </Button>
            </span>
          ) : undefined
        }
        empty={{
          art: 'accounts',
          title: '没有符合条件的账号',
          description: '先到账号管理建档，再来这里检测。',
        }}
      />

      <DataTable<CheckRow>
        rowKey={(record) => `${record.account_id}-${record.checked_at}`}
        columns={resultColumns}
        dataSource={rows}
        loading={checking}
        showDensity={false}
        onRetry={() => lastScope && void runCheck(lastScope, lastLabel || '重新检测')}
        title={
          <span className="tg-flex" style={{ alignItems: 'center', gap: 'var(--tg-space-sm)' }}>
            检测结果
            {lastLabel ? <SoftTag tone="info" size="sm">{lastLabel}</SoftTag> : null}
          </span>
        }
        toolbar={
          <>
            {failedRows.length ? (
              <Button size="small" icon={<SyncOutlined />} onClick={retryFailed}>
                重试失败项（{failedRows.length}）
              </Button>
            ) : null}
          </>
        }
        extra={
          <span className="tg-muted" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
            自动刷新（10 秒） <Switch size="small" checked={autoRefresh} onChange={setAutoRefresh} />
          </span>
        }
        empty={{
          art: 'search',
          title: '还没有发起检测',
          description: '点右上角「检测选中 / 检测当前分组 / 全部检测」查看结果。',
        }}
      />
    </PageContainer>
  );
}
