import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Segmented, Space, Switch, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  FieldTimeOutlined,
  ReloadOutlined,
  RiseOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { dashboardApi, metricsApi, notificationApi } from '../api/endpoints';
import { useAsyncData, useInterval } from '../hooks/useAsyncData';
import { useBreakpoint } from '../hooks/useMediaQuery';
import { formatTime, isHeartbeatStale } from '../utils/format';
import { toast } from '../utils/feedback';
import {
  DataTable,
  PageContainer,
  RelativeTime,
  SectionCard,
  SoftTag,
  StatCard,
  StatGrid,
  TaskTypeTag,
} from '../components';
import type { FailedTaskOut, MetricsWindow, NotificationOut, WorkerStatus } from '../api/types';
import TrendChart from '../features/dashboard/TrendChart';

const REFRESH_MS = 15_000;

/** 从趋势序列里算「环比」：最后一个点相对上一个点的变化百分比 */
function deltaOf(points: { v: number }[]): number | null {
  if (points.length < 2) return null;
  const prev = points[points.length - 2].v;
  const last = points[points.length - 1].v;
  if (!prev) return last > 0 ? 100 : 0;
  return Math.round(((last - prev) / prev) * 100);
}

const QUICK_LINKS: { path: string; label: string; desc: string }[] = [
  { path: '/accounts', label: '账号管理', desc: '状态、分组、心跳' },
  { path: '/detection', label: '账号检测', desc: '连得上 / 要验证码 / 失效' },
  { path: '/network', label: '网络', desc: '代理与出站地址' },
  { path: '/tasks', label: '任务中心', desc: '队列与失败重试' },
  { path: '/dialogs', label: '会话', desc: '私信与群聊' },
  { path: '/audit', label: '操作记录', desc: '谁在什么时候做了什么' },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const { isCompact } = useBreakpoint();
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [window, setWindow] = useState<MetricsWindow>('24h');
  const [marking, setMarking] = useState(false);

  const { data, loading, error, reload } = useAsyncData(() => dashboardApi.get(), []);
  const trends = useAsyncData(() => metricsApi.trends(window), [window]);
  const notifications = useAsyncData(
    () => notificationApi.list({ unread_only: true, page: 1, page_size: 8 }),
    [],
  );

  useInterval(() => {
    void reload();
    void trends.reload();
    void notifications.reload();
  }, autoRefresh ? REFRESH_MS : null);

  const trendByKey = useMemo(() => {
    const map = new Map<string, { v: number }[]>();
    (trends.data?.series ?? []).forEach((series) => map.set(series.key, series.points));
    return map;
  }, [trends.data]);

  const onlineDelta = deltaOf(trendByKey.get('online_accounts') ?? []);
  const abnormalDelta = deltaOf(trendByKey.get('abnormal_accounts') ?? []);
  const failedDelta = deltaOf(trendByKey.get('tasks_failed') ?? []);

  const staleWorkers = useMemo(
    () => (data?.workers ?? []).filter((worker) => worker.stale || isHeartbeatStale(worker.last_heartbeat)),
    [data],
  );

  const workerColumns: ColumnsType<WorkerStatus> = [
    {
      title: 'Worker',
      dataIndex: 'worker_id',
      render: (value: string, record) => {
        const stale = record.stale || isHeartbeatStale(record.last_heartbeat);
        return (
          <span className="tg-flex" style={{ alignItems: 'center', gap: 'var(--tg-space-sm)' }}>
            <span className="tg-mono" style={stale ? { color: 'var(--tg-color-danger)', fontWeight: 'var(--tg-font-weight-semibold)' } : undefined}>
              {value || '—'}
            </span>
            {stale ? <SoftTag tone="danger" size="sm">超 60 秒无心跳</SoftTag> : <SoftTag tone="success" size="sm">心跳正常</SoftTag>}
          </span>
        );
      },
    },
    {
      title: '最后心跳',
      dataIndex: 'last_heartbeat',
      width: 150,
      render: (value: string | null, record) => {
        const stale = record.stale || isHeartbeatStale(value);
        return (
          <span style={stale ? { color: 'var(--tg-color-danger)' } : undefined}>
            <RelativeTime value={value} />
          </span>
        );
      },
    },
    { title: '在线号数', dataIndex: 'online_accounts', width: 100, render: (value: number) => <span className="tg-num">{value}</span> },
    { title: '持租约号数', dataIndex: 'leased_accounts', width: 110, render: (value: number) => <span className="tg-num">{value}</span> },
    {
      title: '来源',
      dataIndex: 'source',
      width: 110,
      render: (value: string) => <SoftTag tone="neutral" size="sm">{value === 'redis' ? 'Redis 心跳' : value || '—'}</SoftTag>,
    },
  ];

  const failureColumns: ColumnsType<FailedTaskOut> = [
    {
      title: '任务类型',
      dataIndex: 'type',
      width: 130,
      render: (_: unknown, record) => <TaskTypeTag type={record.type} label={record.type_label} size="sm" />,
    },
    {
      title: '账号',
      dataIndex: 'account_label',
      width: 130,
      render: (value: string | null) => value || <span className="tg-muted">—</span>,
    },
    {
      title: '失败原因',
      dataIndex: 'error',
      render: (value: string) =>
        value ? (
          <Tooltip title={<div style={{ maxWidth: 460, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{value}</div>}>
            <span className="tg-ellipsis" style={{ display: 'inline-block', maxWidth: 360 }}>
              {value}
            </span>
          </Tooltip>
        ) : (
          <span className="tg-muted">—</span>
        ),
    },
    {
      title: '重试',
      dataIndex: 'attempts',
      width: 90,
      render: (value: number, record) => (
        <span className="tg-num" style={value >= record.max_attempts ? { color: 'var(--tg-color-danger)' } : undefined}>
          {value}/{record.max_attempts}
        </span>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 160,
      render: (value: string | null) => <RelativeTime value={value} />,
    },
  ];

  const markRead = async (item: NotificationOut) => {
    setMarking(true);
    try {
      await notificationApi.markRead(item.id);
      void notifications.reload();
      if (item.link) navigate(item.link);
    } catch {
      /* client 已统一提示 */
    } finally {
      setMarking(false);
    }
  };

  const markAllRead = async () => {
    setMarking(true);
    try {
      const res = await notificationApi.markAllRead();
      toast.success(res.message || '已全部标记为已读');
      void notifications.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setMarking(false);
    }
  };

  const queueItems = [
    { key: 'pending', label: '待执行 pending', value: data?.tasks_pending ?? 0, tone: 'info' as const, icon: <ClockCircleOutlined /> },
    { key: 'running', label: '执行中 running', value: data?.tasks_running ?? 0, tone: 'primary' as const, icon: <RiseOutlined /> },
    { key: 'overdue', label: '到期未执行 overdue', value: data?.tasks_overdue ?? 0, tone: 'warning' as const, icon: <FieldTimeOutlined /> },
    { key: 'stuck', label: '卡住 stuck', value: data?.tasks_stuck ?? 0, tone: 'danger' as const, icon: <ExclamationCircleOutlined /> },
  ];

  return (
    <PageContainer
      title="工作台"
      description={
        data?.generated_at
          ? `数据生成于 ${formatTime(data.generated_at)}；在线数按租约心跳统计，Redis 心跳丢了会重新认领。`
          : '在线数、异常数、Worker 心跳与任务积压。'
      }
      actions={
        <Space>
          <span className="tg-muted" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
            自动刷新（15 秒） <Switch size="small" checked={autoRefresh} onChange={setAutoRefresh} />
          </span>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void reload()}>
            刷新
          </Button>
        </Space>
      }
    >
      <StatGrid>
        <StatCard
          title="在线数"
          value={data?.online_accounts ?? 0}
          unit={<span className="tg-muted">/ 共 {data?.total_accounts ?? 0} 个号</span>}
          tone="success"
          icon={<CheckCircleOutlined />}
          delta={onlineDelta === null ? undefined : { value: onlineDelta, goodWhen: 'up' }}
          trend={trendByKey.get('online_accounts')}
          hint={`持租约 ${data?.leased_accounts ?? 0} 个号`}
          onClick={() => navigate('/accounts')}
        />
        <StatCard
          title="异常数"
          value={data?.abnormal_accounts ?? 0}
          tone={data?.abnormal_accounts ? 'danger' : 'success'}
          icon={<WarningOutlined />}
          delta={abnormalDelta === null ? undefined : { value: abnormalDelta, goodWhen: 'down' }}
          trend={trendByKey.get('abnormal_accounts')}
          hint="needs_code / frozen / invalid / dead / disabled"
          onClick={() => navigate('/accounts?status=abnormal')}
        />
        <StatCard
          title="失败任务"
          value={data?.tasks_failed ?? 0}
          tone={data?.tasks_failed ? 'danger' : 'success'}
          icon={<ExclamationCircleOutlined />}
          delta={failedDelta === null ? undefined : { value: failedDelta, goodWhen: 'down' }}
          trend={trendByKey.get('tasks_failed')}
          hint="24 小时内失败总数"
          onClick={() => navigate('/tasks?only_failed=true')}
        />
        <StatCard
          title="账号总数"
          value={data?.total_accounts ?? 0}
          tone="primary"
          icon={<ThunderboltOutlined />}
          hint={`会话 ${data?.total_dialogs ?? 0} · 未读 ${data?.unread_dialogs ?? 0} · Bot ${data?.total_bots ?? 0}`}
          onClick={() => navigate('/accounts')}
        />
      </StatGrid>

      <SectionCard
        title="在线趋势"
        subtitle="在线账号 / 异常账号 / 任务成功 / 任务失败，按小时（7d、30d 为按天）聚合"
        extra={
          <Segmented
            size="small"
            value={window}
            onChange={(value) => setWindow(value as MetricsWindow)}
            options={[
              { value: '24h', label: '24 小时' },
              { value: '7d', label: '7 天' },
              { value: '30d', label: '30 天' },
            ]}
          />
        }
        loading={trends.initialLoading}
        error={trends.error}
        onRetry={() => void trends.reload()}
      >
        <TrendChart series={trends.data?.series ?? []} height={280} />
      </SectionCard>

      <div
        style={{
          display: 'grid',
          gap: 'var(--tg-layout-page-gap)',
          gridTemplateColumns: isCompact ? 'minmax(0, 1fr)' : 'minmax(0, 3fr) minmax(0, 2fr)',
        }}
      >
        <div className="tg-stack" style={{ gap: 'var(--tg-layout-page-gap)' }}>
          <SectionCard
            title="Worker 心跳"
            subtitle="超过 60 秒没有心跳标红，值班时先看这里"
            loading={loading && !data}
            error={error}
            onRetry={() => void reload()}
            bodyPadding="none"
            empty={!loading && !error && !(data?.workers?.length)}
          >
            {staleWorkers.length ? (
              <Alert
                type="warning"
                showIcon
                style={{ margin: 'var(--tg-space-lg) var(--tg-space-lg) 0' }}
                message={`${staleWorkers.length} 个 Worker 超过 60 秒无心跳`}
                description="处置：到部署机确认 worker 进程是否存活（看进程列表与日志），必要时重启；Worker 死后租约到期会被重新认领，账号数据不受影响。"
              />
            ) : null}
            <DataTable<WorkerStatus>
              rowKey="worker_id"
              columns={workerColumns}
              dataSource={data?.workers ?? []}
              loading={loading}
              showDensity={false}
              skeletonRows={3}
              empty={{ art: 'network', title: '还没有 Worker 上报心跳', description: '启动 Worker 后这里会出现心跳记录。' }}
            />
          </SectionCard>

          <SectionCard
            title="最近失败任务"
            subtitle="按创建时间倒序，最近 10 条"
            extra={
              <Button type="link" size="small" onClick={() => navigate('/tasks?only_failed=true')}>
                去任务中心
              </Button>
            }
            loading={loading && !data}
            error={error}
            onRetry={() => void reload()}
            bodyPadding="none"
          >
            <DataTable<FailedTaskOut>
              rowKey="id"
              columns={failureColumns}
              dataSource={data?.recent_failures ?? []}
              loading={loading}
              showDensity={false}
              skeletonRows={3}
              empty={{ art: 'task', title: '最近没有失败任务', description: '任务失败后会出现在这里。' }}
            />
          </SectionCard>
        </div>

        <div className="tg-stack" style={{ gap: 'var(--tg-layout-page-gap)' }}>
          <SectionCard
            title="任务队列积压"
            subtitle="点击数字去任务中心看明细"
            loading={loading && !data}
            error={error}
            onRetry={() => void reload()}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                gap: 'var(--tg-space-lg)',
              }}
            >
              {queueItems.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => navigate(`/tasks?status=${item.key}`)}
                  style={{
                    cursor: 'pointer',
                    textAlign: 'left',
                    background: 'var(--tg-color-bg-sunken)',
                    border: '1px solid var(--tg-color-border-subtle)',
                    borderRadius: 'var(--tg-radius-lg)',
                    padding: 'var(--tg-space-lg) var(--tg-space-xl)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 'var(--tg-space-xs)',
                  }}
                >
                  <span
                    className="tg-flex"
                    style={{ alignItems: 'center', gap: 'var(--tg-space-sm)', color: `var(--tg-color-${item.tone})`, fontSize: 'var(--tg-font-size-sm)' }}
                  >
                    {item.icon}
                    {item.label}
                  </span>
                  <span className="tg-num" style={{ fontSize: 'var(--tg-font-size-title)', fontWeight: 'var(--tg-font-weight-semibold)' }}>
                    {item.value}
                  </span>
                </button>
              ))}
            </div>
            <Typography.Paragraph type="secondary" style={{ marginTop: 'var(--tg-space-lg)', marginBottom: 0, fontSize: 'var(--tg-font-size-sm)' }}>
              overdue = 过了 next_run_at 还没被认领；stuck = running 超过阈值未完成，优先人工介入。
            </Typography.Paragraph>
          </SectionCard>

          <SectionCard
            title="未读通知"
            subtitle={notifications.data ? `${notifications.data.unread} 条未读异常` : '任务失败 / Worker 掉线 / 账号异常 / 备份失败'}
            extra={
              <Button type="link" size="small" loading={marking} disabled={!(notifications.data?.unread)} onClick={() => void markAllRead()}>
                全部已读
              </Button>
            }
            loading={notifications.initialLoading}
            error={notifications.error}
            onRetry={() => void notifications.reload()}
            empty={
              notifications.data && !notifications.loading
                ? { art: 'inbox', title: '没有未读通知', description: '一切正常；异常发生时这里会出现提醒。' }
                : false
            }
            bodyPadding="none"
          >
            <div className="tg-stack" style={{ gap: 'var(--tg-space-xs)' }}>
              {(notifications.data?.items ?? []).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => void markRead(item)}
                  style={{
                    cursor: 'pointer',
                    textAlign: 'left',
                    background: 'transparent',
                    border: 'none',
                    borderBottom: '1px solid var(--tg-color-divider)',
                    padding: 'var(--tg-space-lg) var(--tg-space-xl)',
                    width: '100%',
                    display: 'flex',
                    gap: 'var(--tg-space-lg)',
                    alignItems: 'flex-start',
                  }}
                >
                  <span
                    aria-hidden
                    style={{
                      flex: 'none',
                      width: 8,
                      height: 8,
                      marginTop: 6,
                      borderRadius: 'var(--tg-radius-pill)',
                      background: `var(--tg-color-${item.level === 'error' ? 'danger' : item.level === 'warning' ? 'warning' : 'info'})`,
                    }}
                  />
                  <span className="tg-stack" style={{ gap: 'var(--tg-space-xxs)' }}>
                    <span className="tg-flex-between" style={{ gap: 'var(--tg-space-md)' }}>
                      <span style={{ fontWeight: 'var(--tg-font-weight-medium)' }}>{item.title}</span>
                      <span className="tg-muted tg-nowrap" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
                        <RelativeTime value={item.created_at} />
                      </span>
                    </span>
                    <span className="tg-muted tg-clamp-2" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
                      {item.body}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="快捷入口" subtitle="常用页面一键跳转">
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                gap: 'var(--tg-space-md)',
              }}
            >
              {QUICK_LINKS.map((item) => (
                <button
                  key={item.path}
                  type="button"
                  onClick={() => navigate(item.path)}
                  style={{
                    cursor: 'pointer',
                    textAlign: 'left',
                    background: 'var(--tg-color-bg-sunken)',
                    border: '1px solid var(--tg-color-border-subtle)',
                    borderRadius: 'var(--tg-radius-md)',
                    padding: 'var(--tg-space-md) var(--tg-space-lg)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 'var(--tg-space-xxs)',
                  }}
                >
                  <span style={{ color: 'var(--tg-color-text-link)', fontWeight: 'var(--tg-font-weight-medium)', fontSize: 'var(--tg-font-size-sm)' }}>
                    {item.label}
                  </span>
                  <span className="tg-muted tg-ellipsis" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
                    {item.desc}
                  </span>
                </button>
              ))}
            </div>
          </SectionCard>
        </div>
      </div>
    </PageContainer>
  );
}
