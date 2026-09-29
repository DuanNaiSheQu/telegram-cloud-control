import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Segmented, Space, Switch, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  FieldTimeOutlined,
  GlobalOutlined,
  MessageOutlined,
  ReloadOutlined,
  LoginOutlined,
  RiseOutlined,
  SafetyCertificateOutlined,
  ScheduleOutlined,
  SendOutlined,
  ThunderboltOutlined,
  UserOutlined,
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
import type { Tone } from '../constants';
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

const QUICK_LINKS: { path: string; label: string; desc: string; icon: ReactNode; tone: Tone }[] = [
  { path: '/accounts', label: '账号管理', desc: '状态、分组、心跳', icon: <UserOutlined />, tone: 'primary' },
  { path: '/detection', label: '账号检测', desc: '连得上 / 要验证码 / 失效', icon: <SafetyCertificateOutlined />, tone: 'success' },
  { path: '/network', label: '网络', desc: '代理与出站地址', icon: <GlobalOutlined />, tone: 'info' },
  { path: '/tasks', label: '任务中心', desc: '队列进度与失败重试', icon: <ScheduleOutlined />, tone: 'warning' },
  { path: '/campaigns', label: '营销中心', desc: '批量私信 / 群发 / 加退群', icon: <SendOutlined />, tone: 'danger' },
  { path: '/dialogs', label: '会话', desc: '私信与群聊', icon: <MessageOutlined />, tone: 'primary' },
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
    { key: 'pending', label: '待执行', value: data?.tasks_pending ?? 0, tone: 'info' as const, icon: <ClockCircleOutlined /> },
    { key: 'running', label: '执行中', value: data?.tasks_running ?? 0, tone: 'primary' as const, icon: <RiseOutlined /> },
    { key: 'overdue', label: '到期未领', value: data?.tasks_overdue ?? 0, tone: 'warning' as const, icon: <FieldTimeOutlined /> },
    { key: 'stuck', label: '卡住', value: data?.tasks_stuck ?? 0, tone: 'danger' as const, icon: <ExclamationCircleOutlined /> },
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

      {data && data.telegram_ready === false ? (
        <Alert
          type="warning"
          showIcon
          message="未配置 Telegram API 凭据，Worker 空转中：不会连接 Telegram，任务也不会执行"
          description={
            <span className="tg-stack" style={{ gap: 'var(--tg-space-xs)' }}>
              <span>
                这不是本系统的限制，而是 Telegram 的机制：任何第三方客户端（包括本系统、各类云控面板）都必须用自己申请的
                <code> api_id / api_hash </code>才能连接。申请免费，几分钟就好：
              </span>
              <span>
                1. 打开 <a href="https://my.telegram.org" target="_blank" rel="noreferrer">my.telegram.org</a> →
                用你的手机号登录（收到的验证码填进去）；
              </span>
              <span>2. 进 <b>API development tools</b> → 随便填个应用名（App title / Short name）→ 创建；</span>
              <span>
                3. 把页面上的 <code>api_id</code>（数字）与 <code>api_hash</code>（32 位字符串）填进
                <code> backend/.env </code>，然后 <code>make stack-down && make stack-up</code> 重启。
              </span>
              <span className="tg-muted" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
                提示：一套凭据可以给多个号用；号多时建议分几套，避免一套被限流牵连全部账号。
                不要用网上公开的 api_id，那会被封。
              </span>
            </span>
          }
          style={{ marginBottom: 'var(--tg-layout-page-gap)' }}
        />
      ) : null}
          <span className="tg-muted" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
            自动刷新（15 秒） <Switch size="small" checked={autoRefresh} onChange={setAutoRefresh} />
          </span>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void reload()}>
            刷新
          </Button>
        </Space>
      }
    >
      {data && !loading && (data.total_accounts ?? 0) === 0 ? (
        <Alert
          type="info"
          showIcon
          icon={<LoginOutlined />}
          message="还没有接入任何 Telegram 账号"
          description="账号是整套系统的起点：先用一个自己的号通过验证码登录，系统才能同步会话、接收消息并按你的指令发送。登录后建议顺手做一次「账号检测」确认号在线。"
          action={
            <Space direction={isCompact ? 'vertical' : 'horizontal'}>
              <Button type="primary" onClick={() => navigate('/accounts?wizard=1')}>
                登录第一个账号
              </Button>
              <Button onClick={() => navigate('/accounts')}>进入账号管理</Button>
            </Space>
          }
        />
      ) : null}

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
          hint="要验证码 / 冻结 / 失效 / 永久双向 / 停用"
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

      <SectionCard title="快捷入口" subtitle="常用页面一键跳转">
        <div className="tg-quick-grid">
          {QUICK_LINKS.map((item) => (
            <button
              key={item.path}
              type="button"
              className="tg-quick-link"
              onClick={() => navigate(item.path)}
            >
              <span className={`tg-quick-link-icon is-${item.tone}`}>{item.icon}</span>
              <span className="tg-stack" style={{ gap: 'var(--tg-space-xxs)', minWidth: 0 }}>
                <span className="tg-quick-link-label">{item.label}</span>
                <span className="tg-quick-link-desc tg-ellipsis">{item.desc}</span>
              </span>
            </button>
          ))}
        </div>
      </SectionCard>

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
            empty={
              !loading && !error && !(data?.workers?.length)
                ? { art: 'network', title: '还没有 Worker 上报心跳', description: '启动 Worker 后这里会出现心跳记录。' }
                : false
            }
          >
            {staleWorkers.length ? (
              <Alert
                type="warning"
                showIcon
                style={{ margin: 'var(--tg-space-lg) var(--tg-space-lg) 0' }}
                message={`${staleWorkers.length} 个 Worker 超过 60 秒无心跳`}
                description="处置：到部署机确认 Worker 进程是否存活（看进程列表与日志），必要时重启；Worker 死后租约到期会被重新认领，账号数据不受影响。"
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
            <div className="tg-queue-grid">
              {queueItems.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className="tg-queue-tile"
                  onClick={() => navigate(`/tasks?status=${item.key}`)}
                >
                  <span className={`tg-queue-tile-icon is-${item.tone}`}>{item.icon}</span>
                  <span className="tg-queue-tile-label">{item.label}</span>
                  <span className="tg-queue-tile-value tg-num">{item.value}</span>
                </button>
              ))}
            </div>
            <Typography.Paragraph type="secondary" style={{ marginTop: 'var(--tg-space-lg)', marginBottom: 0, fontSize: 'var(--tg-font-size-sm)' }}>
              到期未领：已过计划执行时间、仍没有被 Worker 认领；卡住：执行中超时未完成，需要优先人工介入。
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
                ? { art: 'inbox', compact: true, title: '没有未读通知', description: '一切正常；异常发生时这里会出现提醒。' }
                : false
            }
            bodyPadding="none"
          >
            <div className="tg-stack" style={{ gap: 'var(--tg-space-xs)' }}>
              {(notifications.data?.items ?? []).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="tg-notify-item"
                  onClick={() => void markRead(item)}
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

        </div>
      </div>
    </PageContainer>
  );
}
