/**
 * BulkResultModal —— 批量账号操作结果弹窗（逐条展示成功/失败/跳过）。
 *
 * 输入是 /api/accounts/bulk/* 的统一响应 BulkResultOut；
 * 命中上限截断（truncated）时在顶部给黄色提示，引导缩小范围。
 */
import { Modal, Alert, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { Link } from 'react-router-dom';
import type { BulkItemResult, BulkResultOut } from '../../api/types';
import { StatusBadge } from '../../components';

interface Props {
  open: boolean;
  result: BulkResultOut | null;
  onClose: () => void;
}

export default function BulkResultModal({ open, result, onClose }: Props) {
  const items = result?.items ?? [];

  const columns: ColumnsType<BulkItemResult> = [
    { title: '账号', dataIndex: 'account_label', width: 140 },
    {
      title: '结果',
      dataIndex: 'ok',
      width: 90,
      render: (value: boolean, record) =>
        value ? (
          <span style={{ color: 'var(--tg-color-success)' }}>成功</span>
        ) : record.message && record.status === 'disabled' ? (
          <span className="tg-muted">跳过</span>
        ) : (
          <span style={{ color: 'var(--tg-color-danger)' }}>失败</span>
        ),
    },
    {
      title: '说明',
      dataIndex: 'message',
      render: (value: string) => value || <span className="tg-muted">—</span>,
    },
    {
      title: '检测状态',
      dataIndex: 'status',
      width: 120,
      render: (_: unknown, record) =>
        record.status ? <StatusBadge status={record.status} label={record.status_label} size="sm" /> : <span className="tg-muted">—</span>,
    },
    {
      title: '关联任务',
      dataIndex: 'task_id',
      width: 160,
      render: (value: string | null) =>
        value ? (
          <Link className="tg-mono" to={`/tasks?account_id=${value}`} style={{ fontSize: 'var(--tg-font-size-xs)' }}>
            {value.slice(0, 8)}…
          </Link>
        ) : (
          <span className="tg-muted">—</span>
        ),
    },
  ];

  return (
    <Modal open={open} title="批量操作结果" onCancel={onClose} onOk={onClose} okText="知道了" cancelText="关闭" width={760}>
      {result ? (
        <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
          <Typography.Text>
            共命中 <span className="tg-num">{result.requested}</span> 个账号：
            <span style={{ color: 'var(--tg-color-success)' }}> 成功 {result.succeeded}</span>
            {result.failed ? <span style={{ color: 'var(--tg-color-danger)' }}> · 失败 {result.failed}</span> : null}
            {result.skipped ? <span className="tg-muted"> · 跳过 {result.skipped}</span> : null}
            {result.task_ids.length ? <span className="tg-muted"> · 入队任务 {result.task_ids.length} 个</span> : null}
          </Typography.Text>
          {result.truncated ? (
            <Alert
              type="warning"
              showIcon
              message="命中数量超过单次上限，只处理了前一部分"
              description="请缩小范围（按分组 / 状态筛选或多选点名）后分批执行。"
            />
          ) : null}
          <Table<BulkItemResult>
            size="small"
            rowKey={(record) => record.account_id}
            columns={columns}
            dataSource={items}
            pagination={{ pageSize: 10, showSizeChanger: false, size: 'small', showTotal: (total) => `共 ${total} 条` }}
          />
        </div>
      ) : null}
    </Modal>
  );
}
