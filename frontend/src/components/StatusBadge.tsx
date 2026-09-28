import { Tag, Tooltip } from 'antd';
import { ACCOUNT_STATUS_COLORS, ACCOUNT_STATUS_LABELS } from '../constants';
import type { AccountStatus } from '../api/types';

interface StatusBadgeProps {
  status?: AccountStatus | null;
  /** 后端回的 status_label 优先 */
  label?: string | null;
  /** status_reason / last_error，鼠标悬浮看原因 */
  reason?: string | null;
}

/** 账号状态标签：正常 / 冻结 / 失效 / 永久双向 / 停用 … */
export function StatusBadge({ status, label, reason }: StatusBadgeProps) {
  if (!status) return <Tag>未知</Tag>;
  const text = label || ACCOUNT_STATUS_LABELS[status] || status;
  const color = ACCOUNT_STATUS_COLORS[status] ?? 'default';
  const tag = <Tag color={color}>{text}</Tag>;
  return reason ? (
    <Tooltip title={reason}>
      <span style={{ cursor: 'help' }}>{tag}</span>
    </Tooltip>
  ) : (
    tag
  );
}

export default StatusBadge;
