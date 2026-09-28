import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Dropdown,
  Empty,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CloseCircleOutlined,
  DownOutlined,
  ReloadOutlined,
  RedoOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { accountApi, taskApi } from '../api/endpoints';
import { useAsyncData, useInterval } from '../hooks/useAsyncData';
import { TASK_STATUS_OPTIONS, TASK_TYPE_OPTIONS } from '../constants';
import { formatTime, stringifyDetail } from '../utils/format';
import { notifySuccess } from '../utils/feedback';
import { TaskStatusTag, TaskTypeTag } from '../components/TaskStatusTag';
import type { TaskListQuery, TaskOut, TaskStatus, TaskType } from '../api/types';

const REFRESH_MS = 10_000;

export default function Tasks() {
  const [searchParams] = useSearchParams();

  const [filters, setFilters] = useState<Omit<TaskListQuery, 'page' | 'page_size'>>(() => ({
    status: (searchParams.get('status') as TaskStatus | null) ?? '',
    type: (searchParams.get('type') as TaskType | null) ?? '',
    account_id: searchParams.get('account_id'),
    only_failed: searchParams.get('only_failed') === 'true',
  }));
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const query: TaskListQuery = { ...filters, page, page_size: pageSize };
  const tasks = useAsyncData(() => taskApi.list(query), [JSON.stringify(query)]);
  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }), []);

  useInterval(() => {
    void tasks.reload();
  }, autoRefresh ? REFRESH_MS : null);

  const patchFilters = (patch: Partial<Omit<TaskListQuery, 'page' | 'page_size'>>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
    setPage(1);
  };

  const counts = tasks.data?.counts ?? {};

  const handleRetry = async (task: TaskOut) => {
    try {
      const res = await taskApi.retry(task.id);
      notifySuccess(res.message || '已重新排队');
      void tasks.reload();
    } catch {
      /* client 已统一提示 */
    }
  };

  const handleCancel = async (task: TaskOut) => {
    try {
      const res = await taskApi.cancel(task.id);
      notifySuccess(res.message || '任务已取消');
      void tasks.reload();
    } catch {
      /* client 已统一提示 */
    }
  };

  const columns: ColumnsType<TaskOut> = [
    {
      title: '类型',
      dataIndex: 'type',
      width: 150,
      render: (_: unknown, record) => <TaskTypeTag type={record.type} label={record.type_label} />,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (_: unknown, record) => <TaskStatusTag status={record.status} label={record.status_label} />,
    },
    {
      title: '账号',
      dataIndex: 'account_label',
      width: 140,
      render: (value: string | null, record) =>
        value ? (
          <Tooltip title={record.account_id}>{value}</Tooltip>
        ) : record.bot_label ? (
          <Tag color="purple">{record.bot_label}</Tag>
        ) : (
          '—'
        ),
    },
    {
      title: '错误原因',
      dataIndex: 'error',
      render: (value: string) =>
        value ? (
          <Tooltip title={<div style={{ maxWidth: 520, whiteSpace: 'pre-wrap' }}>{value}</div>}>
            <span className="ellipsis" style={{ display: 'inline-block', maxWidth: 320 }}>
              {value}
            </span>
          </Tooltip>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
    {
      title: '重试次数',
      dataIndex: 'attempts',
      width: 100,
      render: (value: number, record) => (
        <Tag color={value >= record.max_attempts ? 'red' : 'default'}>
          {value}/{record.max_attempts}
        </Tag>
      ),
    },
    { title: '创建时间', dataIndex: 'created_at', width: 165, render: (v: string | null) => formatTime(v) },
    { title: '开始时间', dataIndex: 'started_at', width: 165, render: (v: string | null) => formatTime(v) },
    { title: '完成时间', dataIndex: 'completed_at', width: 165, render: (v: string | null) => formatTime(v) },
    {
      title: 'Worker',
      dataIndex: 'worker_id',
      width: 130,
      render: (value: string | null) => value || <Typography.Text type="secondary">—</Typography.Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      fixed: 'right',
      render: (_: unknown, record) => {
        const canRetry = record.status === 'failed' || record.status === 'pending_confirmation';
        const canCancel =
          record.status === 'pending' ||
          record.status === 'running' ||
          record.status === 'pending_confirmation';
        return (
          <Dropdown
            trigger={['click']}
            menu={{
              items: [
                { key: 'retry', icon: <RedoOutlined />, label: '重试', disabled: !canRetry },
                { key: 'cancel', icon: <StopOutlined />, label: '取消', danger: true, disabled: !canCancel },
              ],
              onClick: ({ key }) => {
                if (key === 'retry') void handleRetry(record);
                if (key === 'cancel') void handleCancel(record);
              },
            }}
          >
            <Button size="small">
              操作 <DownOutlined />
            </Button>
          </Dropdown>
        );
      },
    },
  ];

  return (
    <div>
      <Card className="section-card">
        <div className="page-toolbar">
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 140 }}
            value={filters.status || undefined}
            onChange={(value) => patchFilters({ status: (value as TaskStatus) ?? '' })}
            options={TASK_STATUS_OPTIONS}
          />
          <Select
            allowClear
            placeholder="类型"
            style={{ width: 170 }}
            value={filters.type || undefined}
            onChange={(value) => patchFilters({ type: (value as TaskType) ?? '' })}
            options={TASK_TYPE_OPTIONS}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="账号"
            style={{ width: 200 }}
            value={filters.account_id ?? undefined}
            onChange={(value) => patchFilters({ account_id: value ?? null })}
            options={(accounts.data?.items ?? []).map((item) => ({
              value: item.id,
              label: `${item.phone_masked}${item.username ? ` / ${item.username}` : ''}`,
            }))}
          />
          <Space size={4}>
            <span>只看失败</span>
            <Switch
              size="small"
              checked={Boolean(filters.only_failed)}
              onChange={(checked) => patchFilters({ only_failed: checked })}
            />
          </Space>
          <Space className="page-toolbar-right">
            <span>
              自动刷新（10 秒） <Switch size="small" checked={autoRefresh} onChange={setAutoRefresh} />
            </span>
            <Button
              icon={<ReloadOutlined />}
              loading={tasks.loading}
              onClick={() => void tasks.reload()}
            >
              刷新
            </Button>
          </Space>
        </div>

        <Space wrap size="small" style={{ marginBottom: 12 }}>
          <Tag>待执行 {counts.pending ?? 0}</Tag>
          <Tag color="gold">等待确认 {counts.pending_confirmation ?? 0}</Tag>
          <Tag color="processing">执行中 {counts.running ?? 0}</Tag>
          <Tag color="green">已完成 {counts.completed ?? 0}</Tag>
          <Tag color="red">失败 {counts.failed ?? 0}</Tag>
          <Tag>已取消 {counts.cancelled ?? 0}</Tag>
          <Typography.Text type="secondary">共 {tasks.data?.total ?? 0} 条</Typography.Text>
        </Space>

        {filters.account_id ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="当前按账号筛选"
            action={
              <Button size="small" icon={<CloseCircleOutlined />} onClick={() => patchFilters({ account_id: null })}>
                清除
              </Button>
            }
          />
        ) : null}

        <Table<TaskOut>
          size="small"
          rowKey="id"
          loading={tasks.loading}
          dataSource={tasks.data?.items ?? []}
          columns={columns}
          scroll={{ x: 1600 }}
          locale={{ emptyText: <Empty description="没有符合条件的任务" /> }}
          expandable={{
            expandedRowRender: (record) => (
              <Space direction="vertical" size={6} style={{ width: '100%' }}>
                <Typography.Text strong>失败原因 / 详情</Typography.Text>
                <pre className="code-block">{record.error || '（无）'}</pre>
                <Typography.Text strong>payload</Typography.Text>
                <pre className="code-block">{stringifyDetail(record.payload)}</pre>
                {record.result ? (
                  <>
                    <Typography.Text strong>result</Typography.Text>
                    <pre className="code-block">{stringifyDetail(record.result)}</pre>
                  </>
                ) : null}
                <Space wrap>
                  <Typography.Text type="secondary">任务 ID：{record.id}</Typography.Text>
                  {record.account_id ? (
                    <Typography.Text type="secondary">账号 ID：{record.account_id}</Typography.Text>
                  ) : null}
                  {record.created_by_name ? (
                    <Typography.Text type="secondary">发起人：{record.created_by_name}</Typography.Text>
                  ) : null}
                  <Typography.Text type="secondary">下次执行：{formatTime(record.next_run_at)}</Typography.Text>
                </Space>
              </Space>
            ),
          }}
          pagination={{
            current: page,
            pageSize,
            total: tasks.data?.total ?? 0,
            showSizeChanger: true,
            pageSizeOptions: ['20', '50', '100'],
            showTotal: (total) => `共 ${total} 条任务`,
            onChange: (nextPage, nextSize) => {
              setPage(nextPage);
              setPageSize(nextSize);
            },
          }}
        />
      </Card>
    </div>
  );
}
