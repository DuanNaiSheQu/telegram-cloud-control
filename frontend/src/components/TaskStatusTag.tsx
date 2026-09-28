import { Tag } from 'antd';
import {
  CURRENT_TASK_LABELS,
  TASK_STATUS_COLORS,
  TASK_STATUS_LABELS,
  TASK_TYPE_LABELS,
} from '../constants';
import type { CurrentTask, MessageStatus, TaskStatus, TaskType } from '../api/types';

/** 任务状态：待执行 / 等待确认 / 执行中 / 已完成 / 失败 / 已取消 */
export function TaskStatusTag({ status, label }: { status?: TaskStatus | null; label?: string | null }) {
  if (!status) return <Tag>未知</Tag>;
  return (
    <Tag color={TASK_STATUS_COLORS[status] ?? 'default'}>{label || TASK_STATUS_LABELS[status] || status}</Tag>
  );
}

/** 任务类型：同步会话 / 单条发送 / 转发到员工群 … */
export function TaskTypeTag({ type, label }: { type?: TaskType | string | null; label?: string | null }) {
  if (!type) return <Tag>—</Tag>;
  return <Tag color="geekblue">{label || TASK_TYPE_LABELS[type as TaskType] || type}</Tag>;
}

/** 账号当前任务：空闲 / 同步会话 / 等待确认发送 / 转发到员工群 */
export function CurrentTaskTag({
  task,
  label,
}: {
  task?: CurrentTask | null;
  label?: string | null;
}) {
  if (!task) return <span>—</span>;
  const text = label || CURRENT_TASK_LABELS[task] || task;
  if (task === 'idle') return <Tag>{text}</Tag>;
  return <Tag color={task === 'awaiting_confirm' ? 'gold' : 'processing'}>{text}</Tag>;
}

const MESSAGE_STATUS_COLORS: Record<MessageStatus, string> = {
  received: 'default',
  pending: 'gold',
  sent: 'green',
  failed: 'red',
};

export function MessageStatusTag({ status, label }: { status?: MessageStatus | null; label?: string | null }) {
  if (!status) return null;
  return <Tag color={MESSAGE_STATUS_COLORS[status] ?? 'default'}>{label || status}</Tag>;
}

export default TaskStatusTag;
