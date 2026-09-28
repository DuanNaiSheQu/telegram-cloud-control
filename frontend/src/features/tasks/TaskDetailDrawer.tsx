/**
 * 任务详情抽屉：基本信息 + 时间线 + payload / result / error（格式化 JSON 可复制）。
 * 打开时用 taskApi.get 拉最新一条，footer 提供重试 / 取消。
 */
import { useEffect } from 'react';
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
import { useAsyncData } from '../../hooks/useAsyncData';
import { formatTime } from '../../utils/format';
import type { TaskOut } from '../../api/types';
import { JsonBlock } from './JsonBlock';

interface TaskDetailDrawerProps {
  taskId: string | null;
  onClose: () => void;
  onRetry: (task: TaskOut) => void;
  onCancel: (task: TaskOut) => void;
}

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

  const canRetry = task?.status === 'failed' || task?.status === 'pending_confirmation';
  const canCancel =
    task?.status === 'pending' ||
    task?.status === 'running' ||
    task?.status === 'pending_confirmation';

  const sections: DetailSection[] = task
    ? [
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
          <JsonBlock title="payload（入队参数）" value={task.payload} />
          {task.result !== null && task.result !== undefined ? (
            <JsonBlock title="result（执行结果）" value={task.result} />
          ) : (
            <JsonBlock title="result（执行结果）" value={null} emptyText="（还没有结果：任务未完成或未写入）" />
          )}
        </div>
      ) : null}
    </DetailDrawer>
  );
}

function TimelineRow({ label, value }: { label: string; value?: string | null }) {
  return (
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
