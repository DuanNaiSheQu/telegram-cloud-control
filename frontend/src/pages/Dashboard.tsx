import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Row,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { dashboardApi } from '../api/endpoints';
import { useAsyncData, useInterval } from '../hooks/useAsyncData';
import { formatFromNow, formatTime, isHeartbeatStale } from '../utils/format';
import { optionLabel, TASK_TYPE_LABELS } from '../constants';
import type { FailedTaskOut, WorkerStatus } from '../api/types';

const REFRESH_MS = 15_000;

export default function Dashboard() {
  const navigate = useNavigate();
  const [autoRefresh, setAutoRefresh] = useState(true);
  const { data, loading, reload } = useAsyncData(() => dashboardApi.get(), []);

  useInterval(() => {
    void reload();
  }, autoRefresh ? REFRESH_MS : null);

  const workerColumns: ColumnsType<WorkerStatus> = [
    {
      title: 'Worker',
      dataIndex: 'worker_id',
      render: (value: string, record) => {
        const stale = record.stale || isHeartbeatStale(record.last_heartbeat);
        return (
          <Space>
            <span style={stale ? { color: '#cf1322', fontWeight: 600 } : undefined}>{value || '—'}</span>
            {stale ? <Tag color="red">超 60 秒无心跳</Tag> : <Tag color="green">心跳正常</Tag>}
          </Space>
        );
      },
    },
    {
      title: '最后心跳',
      dataIndex: 'last_heartbeat',
      render: (value: string | null, record) => {
        const stale = record.stale || isHeartbeatStale(value);
        return (
          <Tooltip title={formatTime(value)}>
            <span style={stale ? { color: '#cf1322' } : undefined}>{formatFromNow(value)}</span>
          </Tooltip>
        );
      },
    },
    { title: '在线号数', dataIndex: 'online_accounts', width: 100 },
    { title: '持租约号数', dataIndex: 'leased_accounts', width: 110 },
    {
      title: '来源',
      dataIndex: 'source',
      width: 100,
      render: (value: string) => <Tag>{value === 'redis' ? 'Redis 心跳' : value || '—'}</Tag>,
    },
  ];

  const failureColumns: ColumnsType<FailedTaskOut> = [
    {
      title: '任务类型',
      dataIndex: 'type_label',
      width: 130,
      render: (value: string, record) => value || optionLabel(TASK_TYPE_LABELS, record.type),
    },
    {
      title: '账号',
      dataIndex: 'account_label',
      width: 140,
      render: (value: string | null) => value || '—',
    },
    {
      title: '失败原因',
      dataIndex: 'error',
      render: (value: string) =>
        value ? (
          <Tooltip
            title={
              <div style={{ maxWidth: 460, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{value}</div>
            }
          >
            <span className="ellipsis" style={{ display: 'inline-block', maxWidth: 420 }}>
              {value}
            </span>
          </Tooltip>
        ) : (
          '—'
        ),
    },
    {
      title: '重试',
      dataIndex: 'attempts',
      width: 90,
      render: (value: number, record) => `${value}/${record.max_attempts}`,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value: string | null) => formatTime(value),
    },
  ];

  return (
    <div>
      <div className="page-toolbar">
        <Typography.Text type="secondary">
          {data?.generated_at ? `数据生成于 ${formatTime(data.generated_at)}` : '正在加载工作台数据…'}
        </Typography.Text>
        <Space className="page-toolbar-right">
          <span>
            自动刷新（15 秒） <Switch size="small" checked={autoRefresh} onChange={setAutoRefresh} />
          </span>
          <Button icon={<ReloadOutlined />} onClick={() => void reload()} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      <Row gutter={16} className="stat-row">
        <Col xs={24} sm={12} xl={6}>
          <Card>
            <Statistic
              title="在线数"
              value={data?.online_accounts ?? 0}
              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
              suffix={<Typography.Text type="secondary" style={{ fontSize: 12 }}>/ 共 {data?.total_accounts ?? 0} 个号</Typography.Text>}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card>
            <Statistic
              title="异常数"
              value={data?.abnormal_accounts ?? 0}
              valueStyle={{ color: (data?.abnormal_accounts ?? 0) > 0 ? '#cf1322' : undefined }}
              prefix={<ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card>
            <Statistic
              title="失败任务"
              value={data?.tasks_failed ?? 0}
              valueStyle={{ color: (data?.tasks_failed ?? 0) > 0 ? '#cf1322' : undefined }}
              prefix={<WarningOutlined style={{ color: '#faad14' }} />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card>
            <Statistic title="账号总数" value={data?.total_accounts ?? 0} />
          </Card>
        </Col>
      </Row>

      <Card
        className="section-card"
        title="Worker 心跳"
        extra={<Typography.Text type="secondary">超过 60 秒没有心跳标红，值班时先看这里</Typography.Text>}
      >
        <Table<WorkerStatus>
          size="small"
          rowKey="worker_id"
          loading={loading}
          dataSource={data?.workers ?? []}
          columns={workerColumns}
          pagination={false}
          locale={{ emptyText: <Empty description="还没有 Worker 上报心跳" /> }}
        />
      </Card>

      <Row gutter={16}>
        <Col xs={24} xl={14}>
          <Card
            title="最近失败任务"
            className="section-card"
            extra={
              <Button type="link" onClick={() => navigate('/tasks?only_failed=true')}>
                去任务中心
              </Button>
            }
          >
            <Table<FailedTaskOut>
              size="small"
              rowKey="id"
              loading={loading}
              dataSource={data?.recent_failures ?? []}
              columns={failureColumns}
              pagination={false}
              locale={{ emptyText: <Empty description="最近没有失败任务" /> }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card title="队列积压" className="section-card">
            <Row gutter={16}>
              <Col span={12}>
                <Statistic title="待执行 pending" value={data?.tasks_pending ?? 0} prefix={<SyncOutlined />} />
              </Col>
              <Col span={12}>
                <Statistic title="执行中 running" value={data?.tasks_running ?? 0} />
              </Col>
            </Row>
            <Row gutter={16} style={{ marginTop: 16 }}>
              <Col span={12}>
                <Statistic
                  title="到期未执行 overdue"
                  value={data?.tasks_overdue ?? 0}
                  valueStyle={{ color: (data?.tasks_overdue ?? 0) > 0 ? '#faad14' : undefined }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="卡住 stuck"
                  value={data?.tasks_stuck ?? 0}
                  valueStyle={{ color: (data?.tasks_stuck ?? 0) > 0 ? '#cf1322' : undefined }}
                />
              </Col>
            </Row>
            <Space direction="vertical" size={4} style={{ marginTop: 16 }}>
              <Typography.Text type="secondary">
                会话 {data?.total_dialogs ?? 0} 个，其中未读 {data?.unread_dialogs ?? 0} 个；Bot {data?.total_bots ?? 0} 个。
              </Typography.Text>
              <Typography.Text type="secondary">
                <Badge status="processing" /> 在线数按租约心跳统计，Redis 心跳丢了会重新认领。
              </Typography.Text>
            </Space>
          </Card>
        </Col>
      </Row>

      {(data?.tasks_stuck ?? 0) > 0 ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 8 }}
          message="有任务卡住（running 超过阈值未完成）"
          description="去任务中心筛「执行中」查看 worker_id 和开始时间；必要时重试或取消。"
          action={
            <Button size="small" onClick={() => navigate('/tasks?status=running')}>
              查看
            </Button>
          }
        />
      ) : null}
    </div>
  );
}
