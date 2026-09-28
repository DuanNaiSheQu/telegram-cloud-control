import { useMemo, useState } from 'react';
import { Button, Checkbox, Dropdown, Input, Select, Space, Tooltip, Typography } from 'antd';
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
} from '@ant-design/icons';
import { accountApi, exportApi, groupApi, proxyApi, userApi } from '../api/endpoints';
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
  const [wizardAccount, setWizardAccount] = useState<AccountOut | null>(null);
  const [editAccount, setEditAccount] = useState<AccountOut | null>(null);
  const [profileAccount, setProfileAccount] = useState<AccountOut | null>(null);
  const [deleteAccount, setDeleteAccount] = useState<AccountOut | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [bulkAction, setBulkAction] = useState<BulkAction | null>(null);
  const [bulkResult, setBulkResult] = useState<BulkResultOut | null>(null);

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

  const columns: ColumnsType<AccountOut> = [selectColumn, ...baseColumns];

  const bulkMenuItems = [
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
      description="状态、分组、心跳、当前任务；异常口径与工作台一致（非 healthy 且非 pending）。"
      actions={
        <Space>
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
        <StatCard title="正常" value={summary?.healthy ?? 0} tone="success" icon={<SafetyCertificateOutlined />} hint="healthy" onClick={() => q.setFilter('status', 'healthy')} />
        <StatCard title="异常" value={summary?.abnormal ?? 0} tone={summary?.abnormal ? 'danger' : 'success'} icon={<ThunderboltOutlined />} hint="needs_code / frozen / invalid / dead / disabled" />
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
              menu={{ items: bulkMenuItems, onClick: ({ key }) => setBulkAction(key as BulkAction) }}
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

      <AccountDetailDrawer accountId={detailId} handlers={handlers} onClose={() => setDetailId(null)} />
    </PageContainer>
  );
}
