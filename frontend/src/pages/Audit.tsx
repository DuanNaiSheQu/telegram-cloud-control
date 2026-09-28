/**
 * 操作记录：审计表（时间、谁、动作中文标签、账号、Bot、目标、详情、IP）+
 * 筛选（动作/员工/账号/时间范围 from/to）+ 分页 + 服务端排序 + 导出 CSV +
 * 详情抽屉（detail JSON 格式化、可复制）。
 */
import { useMemo, useState } from 'react';
import { Button, DatePicker, Select, Tooltip, Typography } from 'antd';
import type { TableColumnsType } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import { CopyableText, DataTable, FilterBar, PageContainer, RelativeTime } from '../components';
import { accountApi, auditApi, exportApi, userApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { useTableQuery, buildActiveFilters } from '../hooks/useTableQuery';
import { downloadBlob } from '../utils/download';
import { formatTime, stringifyDetail } from '../utils/format';
import { toast } from '../utils/feedback';
import { AUDIT_ACTION_OPTIONS } from '../constants';
import type { AuditListQuery, AuditOut } from '../api/types';
import { AuditDetailDrawer } from '../features/audit/AuditDetailDrawer';
import '../features/tasks/tasks.css';

export default function Audit() {
  const q = useTableQuery({
    filters: {
      action: '' as string,
      user_id: null as string | null,
      account_id: null as string | null,
      from: null as string | null,
      to: null as string | null,
    },
    pageSize: 20,
  });

  const audit = useAsyncData(
    () => {
      // 后端 GET /api/audit 支持 from/to（ISO8601，闭区间）；类型未含这两个字段，走局部扩展
      const query = {
        ...q.params,
        action: q.filters.action || undefined,
        user_id: q.filters.user_id ?? undefined,
        account_id: q.filters.account_id ?? undefined,
        from: q.filters.from ?? undefined,
        to: q.filters.to ?? undefined,
        sort: q.sort ?? undefined,
        order: q.order ?? undefined,
      } as AuditListQuery;
      return auditApi.list(query);
    },
    [q.paramsKey, q.sort, q.order],
  );

  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }, { silent: true }), []);
  const users = useAsyncData(() => userApi.list(), []);

  const [detail, setDetail] = useState<AuditOut | null>(null);
  const [rangeValue, setRangeValue] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [range, setRange] = useState<[string, string] | null>(null);

  const applyRange = (values: [Dayjs | null, Dayjs | null] | null) => {
    if (!values?.[0] || !values[1]) {
      setRangeValue(null);
      setRange(null);
      q.patchFilters({ from: null, to: null });
      return;
    }
    const [from, to] = values;
    if (from.isAfter(to)) {
      toast.warning('时间范围不合法：开始时间不能晚于结束时间');
      return;
    }
    setRangeValue([from, to]);
    setRange([from.toISOString(), to.toISOString()]);
    q.patchFilters({ from: from.toISOString(), to: to.toISOString() });
  };

  const handleReset = () => {
    q.reset();
    setRangeValue(null);
    setRange(null);
  };

  const handleExport = async () => {
    const res = await exportApi.audit({
      ...q.params,
      action: q.filters.action || undefined,
      user_id: q.filters.user_id ?? undefined,
      account_id: q.filters.account_id ?? undefined,
      from: q.filters.from ?? undefined,
      to: q.filters.to ?? undefined,
      sort: q.sort ?? undefined,
      order: q.order ?? undefined,
    } as AuditListQuery);
    downloadBlob(res.blob, res.filename);
  };

  const columns = useMemo<TableColumnsType<AuditOut>>(
    () => [
      {
        title: '时间',
        key: 'created_at',
        width: 150,
        render: (_: unknown, record) => <RelativeTime value={record.created_at} />,
      },
      {
        title: '谁',
        key: 'user_name',
        width: 120,
        render: (_: unknown, record) => (
          <span>{record.user_name ?? <Typography.Text type="secondary">系统</Typography.Text>}</span>
        ),
      },
      {
        title: '动作',
        key: 'action',
        width: 180,
        render: (_: unknown, record) => (
          <span className="tg-stack" style={{ gap: 0 }}>
            <span>{record.action_label || record.action}</span>
            <Typography.Text type="secondary" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
              {record.action}
            </Typography.Text>
          </span>
        ),
      },
      {
        title: '账号',
        key: 'account',
        width: 140,
        render: (_: unknown, record) =>
          record.account_label ? (
            <Tooltip title={`账号 ID ${record.account_id ?? '—'}`}>
              <span>{record.account_label}</span>
            </Tooltip>
          ) : (
            <Typography.Text type="secondary">—</Typography.Text>
          ),
      },
      {
        title: 'Bot',
        key: 'bot',
        width: 130,
        render: (_: unknown, record) =>
          record.bot_id ? (
            <CopyableText value={record.bot_id} mono maxLength={14} />
          ) : (
            <Typography.Text type="secondary">—</Typography.Text>
          ),
      },
      {
        title: '目标',
        key: 'target',
        width: 220,
        render: (_: unknown, record) =>
          record.target_type || record.target_id ? (
            <span style={{ display: 'inline-flex', gap: 'var(--tg-space-xs)', alignItems: 'center' }}>
              <span>{record.target_type || '—'}</span>
              {record.target_id ? <CopyableText value={record.target_id} mono maxLength={16} /> : null}
            </span>
          ) : (
            <Typography.Text type="secondary">—</Typography.Text>
          ),
      },
      {
        title: '详情',
        key: 'detail',
        render: (_: unknown, record) => {
          const text = stringifyDetail(record.detail);
          if (!text) return <Typography.Text type="secondary">—</Typography.Text>;
          const flat = text.replace(/\s+/g, ' ');
          return (
            <Tooltip title={<div style={{ maxWidth: 520, whiteSpace: 'pre-wrap' }}>{text}</div>}>
              <span className="ellipsis" style={{ display: 'inline-block', maxWidth: 260 }}>
                {flat.length > 64 ? `${flat.slice(0, 64)}…` : flat}
              </span>
            </Tooltip>
          );
        },
      },
      {
        title: '来源 IP',
        key: 'client_ip',
        dataIndex: 'client_ip',
        width: 130,
        render: (value: string) => value || <Typography.Text type="secondary">—</Typography.Text>,
      },
      {
        title: '',
        key: 'view',
        width: 60,
        fixed: 'right',
        render: (_: unknown, record) => (
          <Button type="link" size="small" onClick={() => setDetail(record)}>
            查看
          </Button>
        ),
      },
    ],
    [],
  );

  const activeFilters = buildActiveFilters([
    {
      key: 'action',
      label: '动作',
      display: q.filters.action
        ? AUDIT_ACTION_OPTIONS.find((item) => item.value === q.filters.action)?.label ?? q.filters.action
        : '',
      clear: () => q.setFilter('action', ''),
    },
    {
      key: 'user_id',
      label: '员工',
      display: q.filters.user_id
        ? users.data?.find((item) => item.id === q.filters.user_id)?.display_name ?? q.filters.user_id
        : '',
      clear: () => q.setFilter('user_id', null),
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
      key: 'range',
      label: '时间范围',
      display: range ? `${formatTime(range[0])} ~ ${formatTime(range[1])}` : '',
      clear: () => {
        setRange(null);
        q.patchFilters({ from: null, to: null });
      },
    },
  ]);

  return (
    <PageContainer
      title="操作记录"
      description="谁在什么时间对哪个号做了什么，都记在这里（只增不改）；发送类动作会记到具体是人点的还是 AI 草稿带出去的。"
      actions={
        <Button icon={<ReloadOutlined />} onClick={() => void audit.reload()}>
          刷新
        </Button>
      }
    >
      <FilterBar
        collapsible
        onReset={handleReset}
        onSearch={() => void audit.reload()}
        loading={audit.loading}
        activeFilters={activeFilters}
      >
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="动作"
          style={{ width: 240 }}
          value={q.filters.action || undefined}
          onChange={(value) => q.setFilter('action', value ?? '')}
          options={AUDIT_ACTION_OPTIONS}
        />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="员工"
          style={{ width: 180 }}
          value={q.filters.user_id ?? undefined}
          onChange={(value) => q.setFilter('user_id', value ?? null)}
          options={(users.data ?? []).map((item) => ({
            value: item.id,
            label: `${item.display_name || item.username}（${item.username}）`,
          }))}
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
            label: item.phone_masked,
          }))}
        />
        <DatePicker.RangePicker
          showTime
          value={rangeValue}
          placeholder={['开始时间', '结束时间']}
          onChange={(values) => applyRange(values)}
        />
      </FilterBar>

      <DataTable<AuditOut>
        rowKey="id"
        columns={columns}
        dataSource={audit.data?.items ?? []}
        total={audit.data?.total}
        page={q.page}
        pageSize={q.pageSize}
        onPageChange={q.setPage}
        loading={audit.loading}
        error={audit.error}
        onRetry={() => void audit.reload()}
        sortableColumns={{ created_at: 'created_at', action: 'action' }}
        sortField={q.sort}
        sortOrder={q.order}
        onSortChange={q.setSort}
        columnSettingsKey="audit"
        scrollX={1300}
        onExport={handleExport}
        onRow={(record) => ({
          onClick: () => setDetail(record),
          style: { cursor: 'pointer' },
        })}
        empty={{
          art: 'list',
          title: '没有符合条件的操作记录',
          description: '换个筛选条件，或清空时间范围看看。',
        }}
      />

      <AuditDetailDrawer record={detail} onClose={() => setDetail(null)} />
    </PageContainer>
  );
}
