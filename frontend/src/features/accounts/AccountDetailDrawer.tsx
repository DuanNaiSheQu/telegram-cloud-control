/**
 * AccountDetailDrawer —— 账号详情抽屉（/api/accounts/{id}/overview 一次拿全）。
 *
 * 分区：基本信息 / 状态与租约 / 统计 / 最近会话 / 最近消息 / 最近任务 / 最近审计；
 * 底部操作条由页面传入 handler（返回 Promise 时抽屉自动重新加载概览）。
 */
import { Button, Space, Tooltip } from 'antd';
import {
  CloudSyncOutlined,
  DeleteOutlined,
  EditOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
  ThunderboltOutlined,
  UserSwitchOutlined,
} from '@ant-design/icons';
import { accountApi } from '../../api/endpoints';
import { useAsyncData } from '../../hooks/useAsyncData';
import { formatAccountAge, formatTime, previewText } from '../../utils/format';
import {
  CurrentTaskTag,
  DetailDrawer,
  MessageStatusTag,
  RelativeTime,
  StatusBadge,
  TaskStatusTag,
  TaskTypeTag,
} from '../../components';
import type { AccountOut, AccountOverviewOut } from '../../api/types';

export interface AccountDetailHandlers {
  onCheck: (account: AccountOut) => Promise<void> | void;
  onSync: (account: AccountOut) => Promise<void> | void;
  onEdit: (account: AccountOut) => void;
  onProfile: (account: AccountOut) => void;
  onReleaseLease: (account: AccountOut) => Promise<void> | void;
  onToggleEnabled: (account: AccountOut) => Promise<void> | void;
  onRemove: (account: AccountOut) => Promise<void> | void;
}

interface Props {
  accountId: string | null;
  handlers: AccountDetailHandlers;
  onClose: () => void;
}

function StatCell({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div
      style={{
        background: 'var(--tg-color-bg-sunken)',
        border: '1px solid var(--tg-color-border-subtle)',
        borderRadius: 'var(--tg-radius-md)',
        padding: 'var(--tg-space-md) var(--tg-space-lg)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--tg-space-xxs)',
      }}
    >
      <span className="tg-muted" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
        {label}
      </span>
      <span className="tg-num" style={{ fontSize: 'var(--tg-font-size-lg)', fontWeight: 'var(--tg-font-weight-semibold)', color: `var(--tg-color-${tone})` }}>
        {value}
      </span>
    </div>
  );
}

export default function AccountDetailDrawer({ accountId, handlers, onClose }: Props) {
  const { data, loading, error, reload } = useAsyncData(
    () => (accountId ? accountApi.overview(accountId) : Promise.resolve(null)),
    [accountId],
  );

  const overview: AccountOverviewOut | null = data;
  const account = overview?.account ?? null;

  const run = async (fn: (account: AccountOut) => Promise<void> | void) => {
    if (!account) return;
    await fn(account);
    void reload();
  };

  return (
    <DetailDrawer
      open={Boolean(accountId)}
      onClose={onClose}
      width={680}
      title={account?.phone_masked ?? '账号详情'}
      subtitle={
        account ? (
          <span className="tg-flex" style={{ gap: 'var(--tg-space-md)', alignItems: 'center' }}>
            {account.username ? `@${account.username}` : null}
            <StatusBadge status={account.status} label={account.status_label} reason={account.status_reason || account.last_error} size="sm" />
          </span>
        ) : null
      }
      loading={loading}
      error={error}
      onRetry={() => void reload()}
      sections={
        account
          ? [
              {
                title: '基本信息',
                items: [
                  { label: '手机号（脱敏）', value: account.phone_masked, mono: true },
                  { label: '用户名', value: account.username || '—' },
                  { label: '用户 ID', value: account.tg_user_id ? String(account.tg_user_id) : '—', mono: true },
                  { label: '资料名称', value: account.display_name || '—' },
                  { label: '号龄', value: formatAccountAge(account.age_days) },
                  { label: '群数量', value: account.group_count },
                  { label: '分组', value: account.group_name || '未分组' },
                  { label: '代理', value: account.proxy_endpoint || '直连', mono: true },
                  { label: '备注', value: account.remark || '—', span: 'full' },
                  { label: '建档时间', value: formatTime(account.created_at), span: 'full' },
                ],
              },
              {
                title: '状态与租约',
                items: [
                  {
                    label: '当前任务',
                    value: <CurrentTaskTag task={account.current_task} label={account.current_task_label} size="sm" />,
                  },
                  { label: '最后心跳', value: <RelativeTime value={account.last_heartbeat} /> },
                  {
                    label: '租约 Worker',
                    value: overview?.lease?.worker_id ?? '—',
                    mono: true,
                  },
                  {
                    label: '租约到期',
                    value: overview?.lease?.lease_until ? <RelativeTime value={overview.lease.lease_until} /> : '—',
                  },
                  { label: '租约状态', value: overview?.lease?.active ? '持有中' : '未持有' },
                  { label: '最近检测', value: formatTime(account.last_checked_at) },
                  {
                    label: '最近错误',
                    span: 'full',
                    value: account.last_error ? (
                      <Tooltip title={account.last_error} placement="topLeft">
                        <span className="tg-clamp-cell tg-text-danger">{account.last_error}</span>
                      </Tooltip>
                    ) : (
                      '—'
                    ),
                  },
                ],
              },
            ]
          : []
      }
      footer={
        account ? (
          <Space wrap>
            <Button size="small" icon={<SafetyCertificateOutlined />} onClick={() => void run(handlers.onCheck)}>
              检测
            </Button>
            <Button size="small" icon={<CloudSyncOutlined />} onClick={() => void run(handlers.onSync)}>
              同步会话
            </Button>
            <Button size="small" icon={<EditOutlined />} onClick={() => handlers.onEdit(account)}>
              改分组 / 代理
            </Button>
            <Button size="small" icon={<UserSwitchOutlined />} onClick={() => handlers.onProfile(account)}>
              改资料
            </Button>
            <Button size="small" icon={<ThunderboltOutlined />} onClick={() => void run(handlers.onReleaseLease)}>
              清除租约
            </Button>
            <Button
              size="small"
              icon={<StopOutlined />}
              danger={account.status !== 'disabled'}
              onClick={() => void run(handlers.onToggleEnabled)}
            >
              {account.status === 'disabled' ? '启用' : '停用'}
            </Button>
            <Button size="small" danger icon={<DeleteOutlined />} onClick={() => void run(handlers.onRemove)}>
              删除
            </Button>
          </Space>
        ) : null
      }
    >
      {overview ? (
        <div className="tg-stack" style={{ gap: 'var(--tg-space-xl)' }}>
          <section className="tg-detail-section">
            <div className="tg-detail-section-title">统计</div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
                gap: 'var(--tg-space-md)',
              }}
            >
              <StatCell label="会话总数" value={overview.dialog_stats.total} tone="primary" />
              <StatCell label="群聊 / 私信" value={overview.dialog_stats.group} tone="info" />
              <StatCell label="未读会话" value={overview.dialog_stats.unread} tone="warning" />
              <StatCell label="失败任务" value={overview.task_stats.failed} tone="danger" />
            </div>
            <div
              className="tg-muted"
              style={{
                marginTop: 'var(--tg-space-md)',
                fontSize: 'var(--tg-font-size-xs)',
                display: 'flex',
                flexWrap: 'wrap',
                gap: 'var(--tg-space-lg)',
              }}
            >
              <span>任务：待执行 {overview.task_stats.pending} · 执行中 {overview.task_stats.running} · 已完成 {overview.task_stats.completed}</span>
              <span>等待确认 {overview.task_stats.pending_confirmation} · 已取消 {overview.task_stats.cancelled}</span>
            </div>
          </section>

          <section className="tg-detail-section">
            <div className="tg-detail-section-title">最近会话</div>
            {overview.recent_dialogs.length ? (
              <div className="tg-stack" style={{ gap: 'var(--tg-space-sm)' }}>
                {overview.recent_dialogs.map((dialog) => (
                  <div
                    key={dialog.id}
                    style={{
                      background: 'var(--tg-color-bg-sunken)',
                      border: '1px solid var(--tg-color-border-subtle)',
                      borderRadius: 'var(--tg-radius-md)',
                      padding: 'var(--tg-space-md) var(--tg-space-lg)',
                      display: 'flex',
                      justifyContent: 'space-between',
                      gap: 'var(--tg-space-md)',
                    }}
                  >
                    <span className="tg-ellipsis">{dialog.title || dialog.peer_display}</span>
                    <span className="tg-muted tg-nowrap" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
                      {dialog.kind_label} · 未读 {dialog.unread_count}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="tg-muted">还没有同步到会话。</div>
            )}
          </section>

          <section className="tg-detail-section">
            <div className="tg-detail-section-title">最近消息</div>
            {overview.recent_messages.length ? (
              <div className="tg-stack" style={{ gap: 'var(--tg-space-sm)' }}>
                {overview.recent_messages.map((message) => (
                  <div
                    key={message.id}
                    style={{
                      background: 'var(--tg-color-bg-sunken)',
                      border: '1px solid var(--tg-color-border-subtle)',
                      borderRadius: 'var(--tg-radius-md)',
                      padding: 'var(--tg-space-md) var(--tg-space-lg)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 'var(--tg-space-xxs)',
                    }}
                  >
                    <span className="tg-flex-between" style={{ gap: 'var(--tg-space-md)' }}>
                      <span className="tg-muted" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
                        {message.direction_label} · {message.sender_name}
                      </span>
                      <span style={{ fontSize: 'var(--tg-font-size-xs)' }}>
                        <MessageStatusTag status={message.status} label={message.status_label} size="sm" />
                      </span>
                    </span>
                    <span className="tg-clamp-2" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
                      {previewText(message.body, 120)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="tg-muted">最近没有消息。</div>
            )}
          </section>

          <section className="tg-detail-section">
            <div className="tg-detail-section-title">最近任务</div>
            {overview.recent_tasks.length ? (
              <div className="tg-stack" style={{ gap: 'var(--tg-space-sm)' }}>
                {overview.recent_tasks.map((task) => (
                  <div
                    key={task.id}
                    style={{
                      background: 'var(--tg-color-bg-sunken)',
                      border: '1px solid var(--tg-color-border-subtle)',
                      borderRadius: 'var(--tg-radius-md)',
                      padding: 'var(--tg-space-md) var(--tg-space-lg)',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 'var(--tg-space-md)',
                    }}
                  >
                    <TaskTypeTag type={task.type} label={task.type_label} size="sm" />
                    <TaskStatusTag status={task.status} label={task.status_label} size="sm" />
                    <span className="tg-muted tg-nowrap" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
                      <RelativeTime value={task.created_at} />
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="tg-muted">最近没有任务。</div>
            )}
          </section>

          <section className="tg-detail-section">
            <div className="tg-detail-section-title">最近审计</div>
            {overview.recent_audit.length ? (
              <div className="tg-stack" style={{ gap: 'var(--tg-space-sm)' }}>
                {overview.recent_audit.map((entry) => (
                  <div
                    key={entry.id}
                    style={{
                      background: 'var(--tg-color-bg-sunken)',
                      border: '1px solid var(--tg-color-border-subtle)',
                      borderRadius: 'var(--tg-radius-md)',
                      padding: 'var(--tg-space-md) var(--tg-space-lg)',
                      display: 'flex',
                      justifyContent: 'space-between',
                      gap: 'var(--tg-space-md)',
                    }}
                  >
                    <span className="tg-ellipsis" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
                      {entry.action_label} · {entry.user_name ?? '—'}
                    </span>
                    <span className="tg-muted tg-nowrap" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
                      <RelativeTime value={entry.created_at} />
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="tg-muted">最近没有操作记录。</div>
            )}
          </section>
        </div>
      ) : null}
    </DetailDrawer>
  );
}
