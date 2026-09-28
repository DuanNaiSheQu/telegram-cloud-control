import { useState } from 'react';
import { Alert, Button, Card, Empty, Select, Space, Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined } from '@ant-design/icons';
import { accountApi, auditApi, userApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { AUDIT_ACTION_LABELS, AUDIT_ACTION_OPTIONS } from '../constants';
import { formatTime, stringifyDetail } from '../utils/format';
import type { AuditListQuery, AuditOut } from '../api/types';

export default function Audit() {
  const [filters, setFilters] = useState<AuditListQuery>({ page: 1, page_size: 20 });
  const audit = useAsyncData(() => auditApi.list(filters), [JSON.stringify(filters)]);
  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }), []);
  const users = useAsyncData(() => userApi.list(), []);

  const patch = (value: Partial<AuditListQuery>) => setFilters((prev) => ({ ...prev, ...value, page: 1 }));

  const columns: ColumnsType<AuditOut> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string | null) => formatTime(value),
    },
    {
      title: '谁',
      dataIndex: 'user_name',
      width: 150,
      render: (value: string | null) => value || '系统',
    },
    {
      title: '动作',
      dataIndex: 'action',
      width: 190,
      render: (_: unknown, record) => (
        <Space direction="vertical" size={0}>
          <span>{record.action_label || AUDIT_ACTION_LABELS[record.action] || record.action}</span>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {record.action}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '账号',
      dataIndex: 'account_label',
      width: 150,
      render: (value: string | null, record) =>
        value ? (
          <Tooltip title={record.account_id}>{value}</Tooltip>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
    {
      title: '对象',
      key: 'target',
      width: 220,
      render: (_: unknown, record) =>
        record.target_type || record.target_id ? (
          <Typography.Text code style={{ fontSize: 12 }}>
            {record.target_type || '—'}
            {record.target_id ? ` / ${record.target_id}` : ''}
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
    {
      title: '详情',
      dataIndex: 'detail',
      render: (value: unknown) => {
        const text = stringifyDetail(value);
        if (!text) return <Typography.Text type="secondary">—</Typography.Text>;
        const flat = text.replace(/\s+/g, ' ');
        return (
          <Tooltip title={<div style={{ maxWidth: 520, whiteSpace: 'pre-wrap' }}>{text}</div>}>
            <span className="ellipsis" style={{ display: 'inline-block', maxWidth: 260 }}>
              {flat.length > 60 ? `${flat.slice(0, 60)}…` : flat}
            </span>
          </Tooltip>
        );
      },
    },
    {
      title: '来源 IP',
      dataIndex: 'client_ip',
      width: 140,
      render: (value: string) => value || '—',
    },
  ];

  return (
    <div>
      <Card
        title="操作记录"
        extra={
          <Space>
            <Tag>审计只增不改</Tag>
            <Button icon={<ReloadOutlined />} loading={audit.loading} onClick={() => void audit.reload()}>
              刷新
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="谁在什么时间对哪个号做了什么，都记在这里；发送类动作会记到具体是人点的还是 AI 草稿带出去的。"
        />
        <div className="page-toolbar">
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="动作"
            style={{ width: 240 }}
            value={filters.action || undefined}
            onChange={(value) => patch({ action: value ?? '' })}
            options={AUDIT_ACTION_OPTIONS}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="账号"
            style={{ width: 200 }}
            value={filters.account_id ?? undefined}
            onChange={(value) => patch({ account_id: value ?? null })}
            options={(accounts.data?.items ?? []).map((item) => ({
              value: item.id,
              label: item.phone_masked,
            }))}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="员工"
            style={{ width: 180 }}
            value={filters.user_id ?? undefined}
            onChange={(value) => patch({ user_id: value ?? null })}
            options={(users.data ?? []).map((item) => ({
              value: item.id,
              label: `${item.display_name || item.username}（${item.username}）`,
            }))}
          />
        </div>

        {audit.error ? (
          <Alert type="error" showIcon message={`操作记录加载失败：${audit.error}`} style={{ marginBottom: 12 }} />
        ) : null}

        <Table<AuditOut>
          size="small"
          rowKey="id"
          loading={audit.loading}
          dataSource={audit.data?.items ?? []}
          columns={columns}
          scroll={{ x: 1300 }}
          locale={{ emptyText: <Empty description="没有符合条件的操作记录" /> }}
          expandable={{
            expandedRowRender: (record) => (
              <pre className="code-block">{stringifyDetail(record.detail) || '（无详情）'}</pre>
            ),
          }}
          pagination={{
            current: filters.page,
            pageSize: filters.page_size,
            total: audit.data?.total ?? 0,
            showSizeChanger: true,
            pageSizeOptions: ['20', '50', '100'],
            showTotal: (total) => `共 ${total} 条`,
            onChange: (page, pageSize) => setFilters((prev) => ({ ...prev, page, page_size: pageSize })),
          }}
        />
      </Card>
    </div>
  );
}
