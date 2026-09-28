import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Alert, Button, Checkbox, Dropdown, Form, Input, InputNumber, Modal, Select, Space, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CloudSyncOutlined,
  DownOutlined,
  EditOutlined,
  ExportOutlined,
  KeyOutlined,
  MoreOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
  ThunderboltOutlined,
  UserSwitchOutlined,
  ImportOutlined,
} from '@ant-design/icons';
import { accountApi, accountBulkApiExtra, exportApi, groupApi, proxyApi, userApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { useTableQuery, buildActiveFilters } from '../hooks/useTableQuery';
import { useAuth } from '../auth/AuthContext';
import { ACCOUNT_STATUS_OPTIONS, CURRENT_TASK_OPTIONS } from '../constants';
import { downloadBlob } from '../utils/download';
import { formatAccountAge } from '../utils/format';
import { toast } from '../utils/feedback';
import {
  ConfirmModal,
  CurrentTaskTag,
  DataTable,
  FilterBar,
  PageContainer,
  RelativeTime,
  SoftTag,
  StatCard,
  StatGrid,
  StatusBadge,
} from '../components';
import AccountLoginWizard from '../components/AccountLoginWizard';
import AccountDetailDrawer, { type AccountDetailHandlers } from '../features/accounts/AccountDetailDrawer';
import { BulkActionModal, CreateAccountModal, EditAccountModal, ProfileModal } from '../features/accounts/AccountModals';
import BulkResultModal from '../features/accounts/BulkResultModal';
import AccountImportModal from '../features/accounts/AccountImportModal';
import { useRowSelection } from '../features/accounts/useRowSelection';
import type { AccountOut, AccountStatus, BulkAction, BulkResultOut, CurrentTask } from '../api/types';

/** 筛选条件的字段类型（group_id 可为 null，便于 useTableQuery 泛型推导） */
interface AccountFilters extends Record<string, unknown> {
  group_id: string | null;
  status: string;
  current_task: string;
  phone: string;
  keyword: string;
}

export default function Accounts() {
  const { isAdmin } = useAuth();
  const [draftPhone, setDraftPhone] = useState('');
  const [draftKeyword, setDraftKeyword] = useState('');
  const selection = useRowSelection();
  const [createOpen, setCreateOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  // 从工作台/引导条带 ?wizard=1 进来时直接开登录向导，参数用完即清（避免刷新又弹）
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    if (searchParams.get('wizard') !== '1') return;
    setWizardAccount(null);
    setWizardOpen(true);
    const next = new URLSearchParams(searchParams);
    next.delete('wizard');
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);
  const [wizardAccount, setWizardAccount] = useState<AccountOut | null>(null);
  const [editAccount, setEditAccount] = useState<AccountOut | null>(null);
  const [profileAccount, setProfileAccount] = useState<AccountOut | null>(null);
  const [deleteAccount, setDeleteAccount] = useState<AccountOut | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [bulkAction, setBulkAction] = useState<BulkAction | null>(null);
  const [bulkResult, setBulkResult] = useState<BulkResultOut | null>(null);
  // 账号矩阵入口：导入向导、深度验活、节流设置
  const [importOpen, setImportOpen] = useState(false);
  const [warmupOpen, setWarmupOpen] = useState(false);
  const [warmupBusy, setWarmupBusy] = useState(false);
  const [warmupForm] = Form.useForm();
  const [probeOpen, setProbeOpen] = useState(false);
  const [probeWrite, setProbeWrite] = useState(false);
  const [probeBusy, setProbeBusy] = useState(false);
  const [throttleOpen, setThrottleOpen] = useState(false);
  const [throttleBusy, setThrottleBusy] = useState(false);
  const [throttleForm] = Form.useForm();

  const q = useTableQuery<AccountFilters>({
    filters: { group_id: null, status: '', current_task: '', phone: '', keyword: '' },
    pageSize: 20,
  });

  const accounts = useAsyncData(
    () =>
      accountApi.list({
        ...q.params,
        group_id: (q.filters.group_id as string | null) ?? undefined,
        status: (q.filters.status as AccountStatus) || undefined,
        current_task: (q.filters.current_task as CurrentTask) || undefined,
        phone: (q.filters.phone as string) || undefined,
        keyword: (q.filters.keyword as string) || undefined,
        sort: q.sort ?? undefined,
        order: q.order ?? undefined,
      }),
    [q.paramsKey, q.sort, q.order],
  );
  const groups = useAsyncData(() => groupApi.list(), []);
  const proxies = useAsyncData(() => proxyApi.list(), []);
  const users = useAsyncData(() => (isAdmin ? userApi.list() : Promise.resolve([])), [isAdmin]);

  const summary = accounts.data?.summary ?? null;

  const commitTextFilters = () => {
    q.setFilter('phone', draftPhone.trim());
    q.setFilter('keyword', draftKeyword.trim());
  };

  const reloadAll = () => {
    void accounts.reload();
    void groups.reload();
    void proxies.reload();
  };

  // ---------------------------------------------------------------- 行内动作

  const handleCheck = async (account: AccountOut) => {
    const res = await accountApi.check(account.id);
    if (res.reachable) toast.success(`${res.phone_masked}：${res.message || '连得上'}`);
    else toast.error(`${res.phone_masked}：${res.message || res.status_label || '连不上'}`);
    void accounts.reload();
  };

  const handleSync = async (account: AccountOut) => {
    const res = await accountApi.syncDialogs(account.id);
    toast.success(res.message || '已提交同步会话任务');
    void accounts.reload();
  };

  const handleReleaseLease = async (account: AccountOut) => {
    const res = await accountApi.releaseLease(account.id);
    toast.success(res.message || '租约已清除');
    void accounts.reload();
  };

  const handleToggleEnabled = async (account: AccountOut) => {
    const res =
      account.status === 'disabled'
        ? await accountApi.enable(account.id)
        : await accountApi.disable(account.id);
    toast.success(res.message || (account.status === 'disabled' ? '账号已启用' : '账号已停用'));
    void accounts.reload();
  };

  const handleDelete = async () => {
    if (!deleteAccount) return;
    setDeleting(true);
    try {
      const res = await accountApi.remove(deleteAccount.id);
      toast.success(res.message || '账号已删除');
      setDeleteAccount(null);
      reloadAll();
    } catch {
      /* client 已统一提示 */
    } finally {
      setDeleting(false);
    }
  };

  const handlers: AccountDetailHandlers = {
    onCheck: handleCheck,
    onSync: handleSync,
    onEdit: setEditAccount,
    onProfile: setProfileAccount,
    onLogin: (account) => {
      setWizardAccount(account);
      setWizardOpen(true);
    },
    onReleaseLease: handleReleaseLease,
    onToggleEnabled: handleToggleEnabled,
    onRemove: (account) => setDeleteAccount(account),
  };

  const handleExport = async () => {
    const result = await exportApi.accounts({
      group_id: (q.filters.group_id as string | null) ?? undefined,
      status: (q.filters.status as AccountStatus) || undefined,
      current_task: (q.filters.current_task as CurrentTask) || undefined,
      phone: (q.filters.phone as string) || undefined,
      keyword: (q.filters.keyword as string) || undefined,
      sort: q.sort ?? undefined,
      order: q.order ?? undefined,
    });
    downloadBlob(result.blob, result.filename);
    if (result.truncated) toast.warning('导出超过 5 万行已截断，请缩小筛选范围');
    else toast.success(`已导出 ${result.total ?? '全部'} 行 → ${result.filename}`);
  };

  // ---------------------------------------------------------------- 表格列

  const pageIds = useMemo(() => (accounts.data?.items ?? []).map((item) => item.id), [accounts.data]);

  const baseColumns: ColumnsType<AccountOut> = useMemo(
    () => [
      {
        title: '手机号',
        dataIndex: 'phone_masked',
        key: 'phone_masked',
        width: 130,
        fixed: 'left',
        render: (value: string, record) => (
          <Tooltip title={record.display_name ? `本号资料名称：${record.display_name}` : undefined}>
            <span className="tg-mono">{value}</span>
          </Tooltip>
        ),
      },
      { title: '用户名', dataIndex: 'username', key: 'username', width: 120, render: (value: string | null) => value || <span className="tg-muted">—</span> },
      {
        title: '用户 ID',
        dataIndex: 'tg_user_id',
        key: 'tg_user_id',
        width: 110,
        render: (value: number | null) => (value ? <span className="tg-mono">{String(value)}</span> : <span className="tg-muted">—</span>),
      },
      { title: '号龄', dataIndex: 'age_days', key: 'age_days', width: 90, render: (value: number | null) => formatAccountAge(value) },
      { title: '群数量', dataIndex: 'group_count', key: 'group_count', width: 80, render: (value: number) => <span className="tg-num">{value}</span> },
      {
        title: '分组',
        dataIndex: 'group_name',
        key: 'group_name',
        width: 110,
        render: (value: string | null) => (value ? <SoftTag tone="primary" size="sm">{value}</SoftTag> : <SoftTag tone="neutral" size="sm">未分组</SoftTag>),
      },
      {
        title: '代理',
        dataIndex: 'proxy_endpoint',
        key: 'proxy_endpoint',
        width: 170,
        render: (value: string | null) =>
          value ? <span className="tg-mono tg-ellipsis" style={{ display: 'inline-block', maxWidth: 150 }}>{value}</span> : <span className="tg-muted">直连</span>,
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 110,
        render: (_: unknown, record) => (
          <StatusBadge status={record.status} label={record.status_label} reason={record.status_reason || record.last_error} size="sm" />
        ),
      },
      {
        title: '当前任务',
        dataIndex: 'current_task',
        key: 'current_task',
        width: 120,
        render: (_: unknown, record) => <CurrentTaskTag task={record.current_task} label={record.current_task_label} size="sm" />,
      },
      {
        title: '最后心跳',
        dataIndex: 'last_heartbeat',
        key: 'last_heartbeat',
        width: 150,
        render: (value: string | null) => <RelativeTime value={value} />,
      },
      {
        title: '操作',
        key: 'actions',
        width: 90,
        fixed: 'right',
        render: (_: unknown, record) => (
          <span onClick={(event) => event.stopPropagation()}>
            <Dropdown
              trigger={['click']}
              menu={{
                items: [
                  { key: 'check', icon: <SafetyCertificateOutlined />, label: '单号检测' },
                  { key: 'sync', icon: <CloudSyncOutlined />, label: '同步会话' },
                  { key: 'edit', icon: <EditOutlined />, label: '改分组 / 代理' },
                  { key: 'profile', icon: <UserSwitchOutlined />, label: '改资料' },
                  { key: 'login', icon: <KeyOutlined />, label: '重新登录（登录向导）' },
                  { key: 'release', icon: <ThunderboltOutlined />, label: '清除租约' },
                  { type: 'divider' },
                  record.status === 'disabled'
                    ? { key: 'enable', icon: <StopOutlined />, label: '启用' }
                    : { key: 'disable', icon: <StopOutlined />, label: '停用', danger: true },
                  { type: 'divider' },
                  { key: 'delete', label: '删除', danger: true },
                ],
                onClick: ({ key }) => {
                  if (key === 'check') void handleCheck(record);
                  if (key === 'sync') void handleSync(record);
                  if (key === 'edit') setEditAccount(record);
                  if (key === 'profile') setProfileAccount(record);
                  if (key === 'login') {
                    setWizardAccount(record);
                    setWizardOpen(true);
                  }
                  if (key === 'release') void handleReleaseLease(record);
                  if (key === 'disable' || key === 'enable') void handleToggleEnabled(record);
                  if (key === 'delete') setDeleteAccount(record);
                },
              }}
            >
              <Button size="small" type="text" icon={<MoreOutlined />} aria-label={`账号 ${record.phone_masked} 操作`} />
            </Dropdown>
          </span>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const selectColumn: ColumnsType<AccountOut>[number] = {
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
    fixed: 'left',
    render: (_: unknown, record) => (
      <span onClick={(event) => event.stopPropagation()}>
        <Checkbox
          checked={selection.isSelected(record.id)}
          onChange={(event) => selection.toggleOne(record.id, event.target.checked)}
          aria-label={`选择账号 ${record.phone_masked}`}
        />
      </span>
    ),
  };

  // 官方机制养号：上线/翻会话/下线，不发消息
  const runWarmup = async () => {
    if (!selection.count) {
      toast.warning('先在列表里勾选要养号的账号');
      return;
    }
    const values = warmupForm.getFieldsValue() as {
      rounds?: number;
      online_min_seconds?: number;
      online_max_seconds?: number;
      read_inbox?: boolean;
      typing?: boolean;
      sync_limits?: boolean;
    };
    setWarmupBusy(true);
    try {
      const res = await accountBulkApiExtra.warmup({
        scope: 'selected',
        account_ids: selection.selectedIds,
        rounds: values.rounds ?? 1,
        online_min_seconds: values.online_min_seconds ?? 60,
        online_max_seconds: values.online_max_seconds ?? 300,
        read_inbox: Boolean(values.read_inbox),
        typing: Boolean(values.typing),
        sync_limits: values.sync_limits !== false,
      });
      setWarmupOpen(false);
      setBulkResult(res);
      reloadAll();
    } catch {
      /* client 已统一提示 */
    } finally {
      setWarmupBusy(false);
    }
  };

  // 深度验活：排队执行，结果写回健康分
  const runProbe = async () => {
    if (!selection.count) {
      toast.warning('先在列表里勾选要验活的账号');
      return;
    }
    setProbeBusy(true);
    try {
      const res = await accountBulkApiExtra.probe({
        scope: 'selected',
        account_ids: selection.selectedIds,
        write_probe: probeWrite,
      });
      setProbeOpen(false);
      setBulkResult(res);
      reloadAll();
    } catch {
      /* client 已统一提示 */
    } finally {
      setProbeBusy(false);
    }
  };

  // 节流设置：留空不改，填 0 回到自动阶梯
  const runThrottle = async () => {
    if (!selection.count) {
      toast.warning('先在列表里勾选要设置节流的账号');
      return;
    }
    const values = throttleForm.getFieldsValue() as {
      daily?: number;
      interval?: number;
      resetFlood?: boolean;
      warmupNow?: boolean;
    };
    setThrottleBusy(true);
    try {
      const res = await accountBulkApiExtra.throttle({
        scope: 'selected',
        account_ids: selection.selectedIds,
        daily_message_limit: values.daily ?? undefined,
        min_action_seconds: values.interval ?? undefined,
        reset_flood: Boolean(values.resetFlood),
        start_warmup_now: Boolean(values.warmupNow),
      });
      setThrottleOpen(false);
      setBulkResult(res);
      reloadAll();
    } catch {
      /* client 已统一提示 */
    } finally {
      setThrottleBusy(false);
    }
  };

  // 健康分列：验活结果的直观呈现（绿 ≥80 / 黄 ≥50 / 红 <50）
  // 官方身份列：显示对齐的客户端平台（导入时从官方发布版本表里取）
  const clientColumn: ColumnsType<AccountOut>[number] = {
    title: '客户端',
    dataIndex: 'client_kind',
    width: 110,
    render: (value: string) => {
      const label = value === 'android' ? 'Android' : value === 'ios' ? 'iOS' : value === 'tdesktop' ? 'Desktop' : '未对齐';
      return <SoftTag tone={value ? 'neutral' : 'warning'} size="sm">{label}</SoftTag>;
    },
  };

  const healthColumn: ColumnsType<AccountOut>[number] = {
    title: '健康',
    dataIndex: 'health_score',
    width: 88,
    render: (value: number, record) => {
      const score = Number(value ?? 0);
      const tone = score >= 80 ? 'success' : score >= 50 ? 'warning' : 'danger';
      const color = `var(--tg-color-${tone === 'success' ? 'success' : tone === 'warning' ? 'warning' : 'danger'})`;
      return (
        <Tooltip title={record.health_checked_at ? '深度验活结果' : '还没验活过：选「深度验活」跑一次'}>
          <span className="tg-num" style={{ color, fontWeight: 'var(--tg-font-weight-medium)' }}>
            {score}
          </span>
        </Tooltip>
      );
    },
  };

  const columns: ColumnsType<AccountOut> = [selectColumn, clientColumn, healthColumn, ...baseColumns];

  const bulkMenuItems = [
    { key: 'warmup', label: '官方养号（上线/翻会话）' },
    { key: 'probe', label: '深度验活（健康分）' },
    { key: 'throttle', label: '设置发送节流（防封）' },
    { type: 'divider' as const },
    { key: 'check', label: '批量检测' },
    { key: 'sync-dialogs', label: '批量同步会话' },
    { key: 'group', label: '批量改分组 / 移出分组' },
    { key: 'proxy', label: '批量改代理 / 解绑直连' },
    ...(isAdmin ? [{ key: 'assign', label: '批量分配 / 取消分配' }] : []),
    { type: 'divider' as const },
    { key: 'disable', label: '批量停用', danger: true },
    { key: 'enable', label: '批量启用' },
    { key: 'release-lease', label: '批量清除租约' },
  ];

  return (
    <PageContainer
      title="账号管理"
      description="状态、分组、心跳、当前任务；异常口径与工作台一致（不等于「正常」，也不是「待登录」）。"
      actions={
        <Space>
          <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>
            批量导入
          </Button>
          <Button icon={<KeyOutlined />} onClick={() => { setWizardAccount(null); setWizardOpen(true); }}>
            登录向导
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建账号
          </Button>
        </Space>
      }
    >
      <StatGrid>
        <StatCard title="账号总数" value={summary?.total ?? accounts.data?.total ?? 0} tone="primary" icon={<UserSwitchOutlined />} hint="含停用与待登录" onClick={() => q.reset()} />
        <StatCard title="正常" value={summary?.healthy ?? 0} tone="success" icon={<SafetyCertificateOutlined />} hint="租约有效、心跳正常" onClick={() => q.setFilter('status', 'healthy')} />
        <StatCard title="异常" value={summary?.abnormal ?? 0} tone={summary?.abnormal ? 'danger' : 'success'} icon={<ThunderboltOutlined />} hint="要验证码 / 冻结 / 失效 / 永久双向 / 停用" />
        <StatCard
          title="本周新增"
          value={summary?.new_this_week ?? 0}
          tone="info"
          icon={<PlusOutlined />}
          hint={`在线 ${summary?.online ?? 0} · 持租约 ${summary?.leased ?? 0}`}
        />
      </StatGrid>

      <FilterBar
        collapsible
        onReset={() => {
          q.reset();
          setDraftPhone('');
          setDraftKeyword('');
        }}
        onSearch={commitTextFilters}
        loading={accounts.loading}
        activeFilters={buildActiveFilters([
          {
            key: 'group_id',
            label: '分组',
            display: groups.data?.find((g) => g.id === q.filters.group_id)?.name,
            clear: () => q.setFilter('group_id', null),
          },
          {
            key: 'status',
            label: '状态',
            display: ACCOUNT_STATUS_OPTIONS.find((o) => o.value === q.filters.status)?.label,
            clear: () => q.setFilter('status', ''),
          },
          {
            key: 'current_task',
            label: '当前任务',
            display: CURRENT_TASK_OPTIONS.find((o) => o.value === q.filters.current_task)?.label,
            clear: () => q.setFilter('current_task', ''),
          },
          { key: 'phone', label: '手机号', display: q.filters.phone as string, clear: () => { setDraftPhone(''); q.setFilter('phone', ''); } },
          { key: 'keyword', label: '关键词', display: q.filters.keyword as string, clear: () => { setDraftKeyword(''); q.setFilter('keyword', ''); } },
        ])}
      >
        <Select
          allowClear
          placeholder="分组"
          style={{ width: 170 }}
          value={(q.filters.group_id as string | null) ?? undefined}
          onChange={(value) => q.setFilter('group_id', value ?? null)}
          options={(groups.data ?? []).map((g) => ({ value: g.id, label: `${g.name}（${g.account_count}）` }))}
        />
        <Select
          allowClear
          placeholder="状态"
          style={{ width: 130 }}
          value={(q.filters.status as string) || undefined}
          onChange={(value) => q.setFilter('status', (value as AccountStatus) ?? '')}
          options={ACCOUNT_STATUS_OPTIONS}
        />
        <Select
          allowClear
          placeholder="当前任务"
          style={{ width: 150 }}
          value={(q.filters.current_task as string) || undefined}
          onChange={(value) => q.setFilter('current_task', (value as CurrentTask) ?? '')}
          options={CURRENT_TASK_OPTIONS}
        />
        <Input allowClear placeholder="手机号" style={{ width: 150 }} value={draftPhone} onChange={(e) => setDraftPhone(e.target.value)} />
        <Input allowClear placeholder="用户名 / 备注 / 关键词" style={{ width: 200 }} value={draftKeyword} onChange={(e) => setDraftKeyword(e.target.value)} />
      </FilterBar>

      <DataTable<AccountOut>
        rowKey="id"
        columns={columns}
        dataSource={accounts.data?.items ?? []}
        total={accounts.data?.total}
        page={q.page}
        pageSize={q.pageSize}
        onPageChange={q.setPage}
        loading={accounts.loading}
        error={accounts.error}
        onRetry={() => void accounts.reload()}
        sortableColumns={{
          phone_masked: 'phone_masked',
          username: 'username',
          age_days: 'age_days',
          group_count: 'group_count',
          status: 'status',
          current_task: 'current_task',
          last_heartbeat: 'last_heartbeat',
        }}
        sortField={q.sort}
        sortOrder={q.order}
        onSortChange={q.setSort}
        columnSettingsKey="accounts"
        scrollX={1500}
        onExport={handleExport}
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
        toolbar={
          <span className="tg-flex" style={{ alignItems: 'center', gap: 'var(--tg-space-sm)' }}>
            <Dropdown
              menu={{
                items: bulkMenuItems,
                onClick: ({ key }) => {
                  if (key === 'probe') setProbeOpen(true);
                  else if (key === 'throttle') setThrottleOpen(true);
                  else setBulkAction(key as BulkAction);
                },
              }}
              trigger={['click']}
            >
              <Button icon={<ExportOutlined />} disabled={!accounts.data?.total}>
                批量操作 <DownOutlined />
              </Button>
            </Dropdown>
            <Button size="small" onClick={() => selection.togglePage(pageIds, true)}>
              选择本页
            </Button>
          </span>
        }
        onRow={(record) => ({
          onClick: () => setDetailId(record.id),
          style: { cursor: 'pointer' },
        })}
        empty={{
          art: 'accounts',
          title: '还没有账号',
          description: '先建档、再用「登录向导」发验证码拿到会话。',
          action: <Button type="primary" onClick={() => setCreateOpen(true)}>新建账号</Button>,
        }}
      />

      <CreateAccountModal
        open={createOpen}
        groups={groups.data ?? []}
        proxies={proxies.data ?? []}
        onCancel={() => setCreateOpen(false)}
        onSuccess={() => {
          setCreateOpen(false);
          reloadAll();
        }}
      />

      <AccountLoginWizard
        open={wizardOpen}
        account={wizardAccount}
        groups={groups.data ?? []}
        proxies={proxies.data ?? []}
        onCancel={() => setWizardOpen(false)}
        onDone={() => {
          void accounts.reload();
          void groups.reload();
        }}
      />

      <EditAccountModal
        account={editAccount}
        groups={groups.data ?? []}
        proxies={proxies.data ?? []}
        onCancel={() => setEditAccount(null)}
        onSuccess={() => {
          setEditAccount(null);
          reloadAll();
        }}
      />

      <ProfileModal
        account={profileAccount}
        onCancel={() => setProfileAccount(null)}
        onSuccess={() => {
          setProfileAccount(null);
          void accounts.reload();
        }}
      />

      <ConfirmModal
        open={Boolean(deleteAccount)}
        danger
        title={`删除账号 ${deleteAccount?.phone_masked ?? ''}？`}
        content={<Typography.Text>删除后本号与它的会话 / 消息记录都会一并清掉，不可恢复。</Typography.Text>}
        confirmPhrase={deleteAccount?.phone_masked ?? ''}
        confirmPhraseHint="这是高危操作，请输入该账号的脱敏手机号确认。"
        okText="删除"
        loading={deleting}
        onOk={() => void handleDelete()}
        onCancel={() => setDeleteAccount(null)}
      />

      <BulkActionModal
        open={Boolean(bulkAction)}
        action={bulkAction}
        selectedIds={selection.selectedIds}
        filteredTotal={accounts.data?.total ?? 0}
        groups={groups.data ?? []}
        proxies={proxies.data ?? []}
        users={users.data ?? []}
        onCancel={() => setBulkAction(null)}
        onDone={(result) => {
          setBulkAction(null);
          setBulkResult(result);
          reloadAll();
        }}
      />

      <BulkResultModal open={Boolean(bulkResult)} result={bulkResult} onClose={() => setBulkResult(null)} />

      <AccountImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => {
          reloadAll();
        }}
      />

      <Modal
        open={warmupOpen}
        title="官方机制养号"
        okText="排队养号"
        cancelText="取消"
        confirmLoading={warmupBusy}
        onCancel={() => setWarmupOpen(false)}
        onOk={() => void runWarmup()}
      >
        <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
          <Alert
            type="info"
            showIcon
            message={`将对选中的 ${selection.count} 个号排队官方节奏活动`}
            description="动作完全对齐官方客户端：上线 → 翻会话列表 → 下线。全程不发消息、不加群，只产生正常的读行为与在线状态。默认不同步已读与打字状态（那两项对方可见）。"
          />
          <Form
            form={warmupForm}
            layout="vertical"
            initialValues={{ rounds: 1, online_min_seconds: 60, online_max_seconds: 300, sync_limits: true }}
          >
            <Form.Item label="养号轮数" name="rounds">
              <InputNumber min={1} max={5} style={{ width: 140 }} />
            </Form.Item>
            <Space>
              <Form.Item label="单轮在线最短（秒）" name="online_min_seconds">
                <InputNumber min={10} max={1800} style={{ width: 160 }} />
              </Form.Item>
              <Form.Item label="最长（秒）" name="online_max_seconds">
                <InputNumber min={10} max={3600} style={{ width: 160 }} />
              </Form.Item>
            </Space>
            <Form.Item name="read_inbox" valuePropName="checked" style={{ marginBottom: 'var(--tg-space-sm)' }}>
              <Checkbox>标记已读（更像真人，但对方会看到「已读」）</Checkbox>
            </Form.Item>
            <Form.Item name="typing" valuePropName="checked" style={{ marginBottom: 'var(--tg-space-sm)' }}>
              <Checkbox>显示「正在输入」（对方可见，慎用）</Checkbox>
            </Form.Item>
            <Form.Item name="sync_limits" valuePropName="checked" style={{ marginBottom: 0 }}>
              <Checkbox>同时同步官方限制参数（服务端下发的 flood/上限，节流只收紧不放松）</Checkbox>
            </Form.Item>
          </Form>
        </div>
      </Modal>

      <Modal
        open={probeOpen}
        title="深度验活"
        okText="开始验活"
        cancelText="取消"
        confirmLoading={probeBusy}
        onCancel={() => setProbeOpen(false)}
        onOk={() => void runProbe()}
      >
        <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
          <Alert
            type="info"
            showIcon
            message={`将对选中的 ${selection.count} 个账号排队深度验活`}
            description="验活会读账号状态、会话列表与授权会话数，复算 0-100 的健康分；结果写回账号页的健康列。"
          />
          <Checkbox checked={probeWrite} onChange={(event) => setProbeWrite(event.target.checked)}>
            额外做一次写权限探测（往该号自己的收藏夹发一条「验活探测」）
          </Checkbox>
        </div>
      </Modal>

      <Modal
        open={throttleOpen}
        title="设置发送节流"
        okText="应用到选中账号"
        cancelText="取消"
        confirmLoading={throttleBusy}
        onCancel={() => setThrottleOpen(false)}
        onOk={() => void runThrottle()}
      >
        <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
          <Alert
            type="info"
            showIcon
            message={`将对选中的 ${selection.count} 个账号应用节流设置`}
            description="每日上限与最小间隔留空表示不修改；填 0 表示回到「按号龄自动阶梯」（新号 20 条/天起，老号最多 200 条/天）。"
          />
          <Form form={throttleForm} layout="vertical" initialValues={{ daily: undefined, interval: undefined }}>
            <Form.Item label="每日发送上限" name="daily">
              <InputNumber min={0} max={2000} style={{ width: 200 }} placeholder="留空不改；0 = 自动阶梯" />
            </Form.Item>
            <Form.Item label="最小动作间隔（秒）" name="interval">
              <InputNumber min={0} max={3600} style={{ width: 200 }} placeholder="留空不改；0 = 自动阶梯" />
            </Form.Item>
            <Form.Item name="resetFlood" valuePropName="checked" style={{ marginBottom: 'var(--tg-space-md)' }}>
              <Checkbox>同时解除熔断冷却与限流计数（确认账号已恢复再勾）</Checkbox>
            </Form.Item>
            <Form.Item name="warmupNow" valuePropName="checked" style={{ marginBottom: 0 }}>
              <Checkbox>把养号起点重置为今天（新导入的号从最严档开始）</Checkbox>
            </Form.Item>
          </Form>
        </div>
      </Modal>

      <AccountDetailDrawer accountId={detailId} handlers={handlers} onClose={() => setDetailId(null)} />
    </PageContainer>
  );
}
