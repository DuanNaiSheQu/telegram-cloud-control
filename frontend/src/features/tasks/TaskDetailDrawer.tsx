/**
 * 任务详情抽屉：基本信息 + 时间线 + payload / result / error（格式化 JSON 可复制）。
 * 打开时用 taskApi.get 拉最新一条，footer 提供重试 / 取消。
 */
import { useEffect, useMemo } from 'react';
import { Button, Space, Typography } from 'antd';
import { RedoOutlined, StopOutlined } from '@ant-design/icons';
import {
  CopyableText,
  DetailDrawer,
  RelativeTime,
  TaskStatusTag,
  TaskTypeTag,
  type DetailSection,
} from '../../components';
import { taskApi } from '../../api/endpoints';
import { useAsyncData, useInterval } from '../../hooks/useAsyncData';
import { useWsEvent } from '../../hooks/useWebSocket';
import { formatTime } from '../../utils/format';
import type { TaskOut } from '../../api/types';
import { JsonBlock } from './JsonBlock';

interface TaskDetailDrawerProps {
  taskId: string | null;
  onClose: () => void;
  onRetry: (task: TaskOut) => void;
  onCancel: (task: TaskOut) => void;
}

/** 没有日志时按状态给一句人话——留白会让人以为功能坏了 */
const EMPTY_LOG_HINT: Record<string, string> = {
  pending: '排队中：等 Worker 认领这个号之后开始执行，日志会写在这里',
  running: '执行中：正在跑，日志马上出来（抽屉开着会自动刷新）',
  failed: '已失败，但没有留下执行日志——可以点下面的「重试」重新排队',
  completed: '已完成，但没有产生日志条目（该任务类型可能不上报步骤）',
  cancelled: '已取消',
  pending_confirmation: '等待确认后才开始执行，日志会在执行时写入',
};

export function TaskDetailDrawer({ taskId, onClose, onRetry, onCancel }: TaskDetailDrawerProps) {
  const detail = useAsyncData<TaskOut>(() => taskApi.get(taskId as string), [taskId], {
    immediate: false,
    silentError: true,
  });

  useEffect(() => {
    if (taskId) {
      detail.setData(null);
      void detail.reload();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  const task = detail.data;

  // 实时：任务事件一到就刷（WS 推的是「状态变了」；逐条追加的日志仍靠下面的轮询兜底）
  useWsEvent(
    'task',
    (event) => {
      if (taskId && event.task_id === taskId) void detail.reload();
    },
    Boolean(taskId),
  );

  // 兜底轮询：任务还在排队 / 执行中时每 3 秒拉一次，抽屉开着就能看到日志往上长
  useInterval(() => {
    if (!taskId) return;
    if (task?.status === 'pending' || task?.status === 'running') void detail.reload();
  }, 3000);

  // 执行日志：与列表页展开的那份同源（result.logs）
  const logs = useMemo(() => {
    const raw = (task?.result as Record<string, unknown> | null)?.logs;
    return Array.isArray(raw) ? (raw as { at: string; stage: string; detail: string }[]) : [];
  }, [task]);

  const canRetry = task?.status === 'failed' || task?.status === 'pending_confirmation';
  const canCancel =
    task?.status === 'pending' ||
    task?.status === 'running' ||
    task?.status === 'pending_confirmation';

  const sections: DetailSection[] = task
    ? [
        {
          title: '执行日志',
          content: logs.length ? (
            <div className="tg-stack" style={{ gap: 2, maxHeight: 340, overflowY: 'auto' }}>
              {logs.map((entry, index) => {
                const tone = stageTone(entry.stage);
                const isLatest = index === logs.length - 1;
                return (
                  <div
                    key={`${entry.at}-${index}`}
                    style={{
                      display: 'flex',
                      gap: 'var(--tg-space-md)',
                      alignItems: 'baseline',
                      padding: '3px var(--tg-space-sm)',
                      borderRadius: 4,
                      // 最新一条加底纹：一眼看到「现在卡在哪一步」
                      background: isLatest ? 'var(--tg-color-primary-bg)' : undefined,
                    }}
                  >
                    <span
                      style={{
                        flex: 'none',
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: isLatest ? tone.color : 'transparent',
                        border: `2px solid ${tone.color}`,
                      }}
                    />
                    <span
                      style={{
                        flex: 'none',
                        color: 'var(--tg-color-text-tertiary)',
                        fontSize: 'var(--tg-font-size-xs)',
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {formatTime(entry.at)}
                    </span>
                    <span
                      style={{
                        flex: 'none',
                        minWidth: 56,
                        fontSize: 'var(--tg-font-size-xs)',
                        color: tone.color,
                        fontWeight: 'var(--tg-font-weight-medium)',
                      }}
                    >
                      {tone.label}
                    </span>
                    <span style={{ color: 'var(--tg-color-text-primary)' }}>{entry.detail}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <Typography.Text type="secondary">
              {EMPTY_LOG_HINT[task.status] ?? '这个任务还没有日志。'}
            </Typography.Text>
          ),
        },
        {
          title: '基本信息',
          items: [
            {
              label: '任务类型',
              value: <TaskTypeTag type={task.type} label={task.type_label} />,
            },
            {
              label: '状态',
              value: <TaskStatusTag status={task.status} label={task.status_label} />,
            },
            {
              label: '任务 ID',
              value: <CopyableText value={task.id} mono />,
            },
            { label: '尝试次数', value: `${task.attempts} / ${task.max_attempts}` },
            { label: '优先级', value: task.priority },
            {
              label: 'Worker',
              value: task.worker_id ? <CopyableText value={task.worker_id} mono /> : undefined,
            },
            { label: '发起人', value: task.created_by_name || undefined },
            { label: '下次执行', value: formatTime(task.next_run_at) },
          ],
        },
        {
          title: '时间线',
          content: (
            <div className="tg-stack" style={{ gap: 'var(--tg-space-md)' }}>
              <TimelineRow label="创建" value={task.created_at} />
              <TimelineRow label="开始执行" value={task.started_at} />
              <TimelineRow label="完成" value={task.completed_at} />
              <TimelineRow label="下次执行" value={task.next_run_at} />
            </div>
          ),
        },
      ]
    : [];

  return (
    <DetailDrawer
      open={Boolean(taskId)}
      onClose={onClose}
      title={task ? (task.type_label || task.type) : '任务详情'}
      subtitle={
        task ? (
          <Space size={8}>
            <span>
              {task.account_label || task.bot_label || '系统任务'}
            </span>
            {task.created_at ? <RelativeTime value={task.created_at} refreshMs={0} /> : null}
          </Space>
        ) : undefined
      }
      width={680}
      loading={detail.loading}
      error={detail.error}
      onRetry={() => void detail.reload()}
      sections={sections}
      footer={
        task ? (
          <Space>
            <Button
              icon={<RedoOutlined />}
              disabled={!canRetry}
              title={canRetry ? undefined : '只允许失败或等待确认的任务重试'}
              onClick={() => onRetry(task)}
            >
              重试
            </Button>
            <Button
              danger
              icon={<StopOutlined />}
              disabled={!canCancel}
              title={canCancel ? undefined : '只有待执行 / 等待确认 / 执行中的任务可以取消'}
              onClick={() => onCancel(task)}
            >
              取消
            </Button>
          </Space>
        ) : null
      }
    >
      {task ? (
        <div className="tg-stack" style={{ gap: 'var(--tg-space-xl)' }}>
          {task.error ? (
            <div>
              <Typography.Text strong>错误原因</Typography.Text>
              <div style={{ marginTop: 'var(--tg-space-md)' }}>
                <JsonBlock value={task.error} emptyText="（无）" />
              </div>
            </div>
          ) : null}
          <JsonBlock title="入队参数（payload）" value={task.payload} />
          {task.result !== null && task.result !== undefined ? (
            <JsonBlock title="执行结果（result）" value={task.result} />
          ) : (
            <JsonBlock title="执行结果（result）" value={null} emptyText="（还没有结果：任务未完成或未写入）" />
          )}
        </div>
      ) : null}
    </DetailDrawer>
  );
}

/** 日志分级：把 stage 翻成中文短标签 + 配色，一眼看出「在干嘛 / 卡哪了」 */
const STAGE_LABELS: Record<string, string> = {
  start: '开始',
  scanning: '扫描中',
  searching: '搜索中',
  sending: '发送中',
  progress: '进行中',
  online: '上线',
  done: '完成',
  error: '出错',
  failed: '失败',
};

function stageTone(stage: string): { label: string; color: string } {
  const key = (stage || '').toLowerCase();
  const label = STAGE_LABELS[key] ?? stage ?? '进行中';
  if (key.includes('error') || key.includes('fail')) return { label, color: 'var(--tg-color-danger)' };
  if (key.includes('done') || key.includes('complete') || key === 'ok') {
    return { label, color: 'var(--tg-color-success)' };
  }
  if (key.includes('start')) return { label, color: 'var(--tg-color-primary)' };
  return { label, color: 'var(--tg-color-text-secondary)' };
}

function TimelineRow({ label, value }: { label: string; value?: string | null }) {  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--tg-space-lg)',
        fontSize: 'var(--tg-font-size-sm)',
      }}
    >
      <span style={{ color: 'var(--tg-color-text-tertiary)', width: 64, flex: 'none' }}>{label}</span>
      <span style={{ color: 'var(--tg-color-text-primary)' }}>{formatTime(value)}</span>
    </div>
  );
}
