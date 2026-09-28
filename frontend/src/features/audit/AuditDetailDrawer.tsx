/**
 * 审计详情抽屉：谁 / 何时 / 什么动作 / 目标 / IP + detail JSON（格式化、可复制）。
 * 数据直接用列表行（auditApi.list 已返回 detail），无需二次请求。
 */
import { Button, Space } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { CopyableText, DetailDrawer, RelativeTime } from '../../components';
import { copyText } from '../../utils/download';
import { formatTime, stringifyDetail } from '../../utils/format';
import { toast } from '../../utils/feedback';
import type { AuditOut } from '../../api/types';
import { JsonBlock } from '../tasks/JsonBlock';
import '../tasks/tasks.css';

interface AuditDetailDrawerProps {
  record: AuditOut | null;
  onClose: () => void;
}

export function AuditDetailDrawer({ record, onClose }: AuditDetailDrawerProps) {

  const handleCopyAll = async () => {
    if (!record) return;
    const payload = stringifyDetail({
      时间: record.created_at,
      操作人: record.user_name ?? '系统',
      动作: record.action_label || record.action,
      账号: record.account_label ?? null,
      Bot: record.bot_id ?? null,
      目标类型: record.target_type,
      目标ID: record.target_id,
      来源IP: record.client_ip,
      详情: record.detail ?? null,
    });
    const ok = await copyText(payload);
    if (ok) toast.success('已复制完整审计记录');
    else toast.error('复制失败，请手动选中复制');
  };

  return (
    <DetailDrawer
      open={Boolean(record)}
      onClose={onClose}
      title={record ? (record.action_label || record.action) : '审计详情'}
      subtitle={
        record ? (
          <Space size={8}>
            <span>{record.user_name ?? '系统'}</span>
            {record.created_at ? <RelativeTime value={record.created_at} refreshMs={0} /> : null}
          </Space>
        ) : undefined
      }
      width={640}
      sections={
        record
          ? [
              {
                title: '记录信息',
                items: [
                  { label: '时间', value: formatTime(record.created_at) },
                  { label: '动作名', value: <CopyableText value={record.action} mono /> },
                  { label: '操作人', value: record.user_name || '系统' },
                  { label: '账号', value: record.account_label || undefined },
                  {
                    label: 'Bot',
                    value: record.bot_id ? <CopyableText value={record.bot_id} mono maxLength={20} /> : undefined,
                  },
                  { label: '目标类型', value: record.target_type || undefined },
                  {
                    label: '目标 ID',
                    value: record.target_id ? <CopyableText value={record.target_id} mono /> : undefined,
                  },
                  { label: '来源 IP', value: record.client_ip || undefined },
                ],
              },
            ]
          : []
      }
      extra={
        record ? (
          <Button size="small" icon={<CopyOutlined />} onClick={() => void handleCopyAll()}>
            复制全部
          </Button>
        ) : null
      }
    >
      {record ? (
        <JsonBlock title="详情 JSON（detail）" value={record.detail ?? null} emptyText="（无详情）" />
      ) : null}
    </DetailDrawer>
  );
}
