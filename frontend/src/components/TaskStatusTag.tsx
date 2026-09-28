/**
 * TaskStatusTag / TaskTypeTag / CurrentTaskTag / MessageStatusTag
 * —— 任务与会话相关的中文标签，全部按 token 上色（不再用 antd 预设色名）。
 *
 * props 契约：
 *   <TaskStatusTag status={task.status} label={task.status_label} />
 *   <TaskTypeTag   type={task.type}     label={task.type_label} />
 *   <CurrentTaskTag task={account.current_task} label={account.current_task_label} />
 *   <MessageStatusTag status={message.status} label={message.status_label} />
 * 通用可选 props：size?: 'sm'|'md'、showDot?: boolean、className?、style?
 * 颜色：--tg-color-task-<status>-{fg,bg,border,dot}
 */
import type { CSSProperties } from 'react';
import { Tooltip } from 'antd';
import {
  CURRENT_TASK_LABELS,
  MESSAGE_STATUS_LABELS,
  MESSAGE_STATUS_TONE,
  TASK_STATUS_LABELS,
  TASK_TYPE_LABELS,
  type Tone,
} from '../constants';
import type { CurrentTask, MessageStatus, TaskStatus, TaskType } from '../api/types';

interface TagBaseProps {
  size?: 'sm' | 'md';
  showDot?: boolean;
  className?: string;
  style?: CSSProperties;
  tooltip?: string;
}

/** 通用语义标签：tone → CSS 变量 */
export function SoftTag({
  tone,
  children,
  size = 'md',
  showDot = false,
  className,
  style,
  tooltip,
}: TagBaseProps & { tone: Tone; children: React.ReactNode }) {
  const tag = (
    <span
      className={['tg-status-badge', className].filter(Boolean).join(' ')}
      style={{
        height: size === 'sm' ? 20 : 24,
        fontSize: size === 'sm' ? 'var(--tg-font-size-xs)' : 'var(--tg-font-size-sm)',
        color: `var(--tg-color-${tone})`,
        background: `var(--tg-color-${tone}-bg)`,
        borderColor: `var(--tg-color-${tone}-border)`,
        ...style,
      }}
    >
      {showDot ? (
        <span
          className="tg-status-dot"
          style={{ width: 6, height: 6, background: `var(--tg-color-${tone})` }}
          aria-hidden
        />
      ) : null}
      {children}
    </span>
  );
  return tooltip ? <Tooltip title={tooltip}>{tag}</Tooltip> : tag;
}

/** 任务状态：待执行 / 等待确认 / 执行中 / 已完成 / 失败 / 已取消 */
export function TaskStatusTag({
  status,
  label,
  size = 'md',
  showDot = true,
  className,
  style,
}: TagBaseProps & { status?: TaskStatus | null; label?: string | null }) {
  if (!status) return <SoftTag tone="neutral" size={size}>{label || '未知'}</SoftTag>;
  const key = status;
  const text = label || TASK_STATUS_LABELS[status] || status;
  const tag = (
    <span
      className={['tg-status-badge', className].filter(Boolean).join(' ')}
      style={{
        height: size === 'sm' ? 20 : 24,
        fontSize: size === 'sm' ? 'var(--tg-font-size-xs)' : 'var(--tg-font-size-sm)',
        color: `var(--tg-color-task-${key}-fg)`,
        background: `var(--tg-color-task-${key}-bg)`,
        borderColor: `var(--tg-color-task-${key}-border)`,
        ...style,
      }}
    >
      {showDot ? (
        <span
          className={['tg-status-dot', status === 'running' ? 'is-pulse' : ''].filter(Boolean).join(' ')}
          style={{
            width: 6,
            height: 6,
            background: `var(--tg-color-task-${key}-dot)`,
            color: `var(--tg-color-task-${key}-dot)`,
          }}
          aria-hidden
        />
      ) : null}
      {text}
    </span>
  );
  return tag;
}

/** 任务类型：同步会话 / 单条发送 / 转发到员工群 … */
export function TaskTypeTag({
  type,
  label,
  size = 'md',
  className,
  style,
}: TagBaseProps & { type?: TaskType | string | null; label?: string | null }) {
  if (!type) return <span className="tg-muted">—</span>;
  const text = label || TASK_TYPE_LABELS[type as TaskType] || type;
  return (
    <SoftTag
      tone="info"
      size={size}
      className={className}
      style={{ background: 'var(--tg-color-bg-sunken)', borderColor: 'var(--tg-color-border-subtle)', color: 'var(--tg-color-text-secondary)', ...style }}
    >
      {text}
    </SoftTag>
  );
}

/** 账号当前任务：空闲 / 同步会话 / 等待确认发送 / 转发到员工群 */
export function CurrentTaskTag({
  task,
  label,
  size = 'md',
  className,
  style,
}: TagBaseProps & { task?: CurrentTask | null; label?: string | null }) {
  if (!task) return <span className="tg-muted">—</span>;
  const text = label || CURRENT_TASK_LABELS[task] || task;
  if (task === 'idle') {
    return (
      <SoftTag tone="neutral" size={size} className={className} style={style}>
        {text}
      </SoftTag>
    );
  }
  return (
    <SoftTag tone={task === 'awaiting_confirm' ? 'warning' : 'primary'} size={size} showDot className={className} style={style}>
      {text}
    </SoftTag>
  );
}

/** 消息状态：已接收 / 待发送 / 已发送 / 发送失败 */
export function MessageStatusTag({
  status,
  label,
  size = 'md',
  className,
  style,
}: TagBaseProps & { status?: MessageStatus | null; label?: string | null }) {
  if (!status) return null;
  const text = label || MESSAGE_STATUS_LABELS[status] || status;
  return (
    <SoftTag tone={MESSAGE_STATUS_TONE[status]} size={size} showDot className={className} style={style}>
      {text}
    </SoftTag>
  );
}

export default TaskStatusTag;
