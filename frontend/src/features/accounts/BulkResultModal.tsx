/**
 * BulkResultModal —— 批量账号操作结果弹窗（逐条展示成功/失败/跳过）。
 *
 * 输入是 /api/accounts/bulk/* 的统一响应 BulkResultOut；
 * 命中上限截断（truncated）时在顶部给黄色提示，引导缩小范围。
 */
import { Modal, Alert, Table, Tag, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { Link } from 'react-router-dom';
import type { BulkItemResult, BulkResultOut } from '../../api/types';

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
      width: 340,
      ellipsis: { showTitle: false },
      render: (value: string) => (
        <Tooltip title={value || ''} placement="topLeft">
          <span className="tg-clamp-cell">{value || '—'}</span>
        </Tooltip>
      ),
    },
    {
      title: '关联任务',
      dataIndex: 'task_id',
      width: 160,
      render: (value: string | null) =>
        value ? (
          <Link className="tg-mono" to={`/tasks?account_id=${value}`} style={{ fontSize: 'var(--tg-font-size-xs)' }}>
            任务 {value.slice(0, 6)}
          </Link>
        ) : (
          <span className="tg-muted">—</span>
        ),
    },
  ];

  // 只有确实带检测结果的批次才显示这一列，避免整列全是「—」占位
  const columnsWithCheck = items.some((item) => item.status_label)
    ? [
        ...columns.slice(0, 3),
        {
          title: '检测状态',
          dataIndex: 'status_label',
          width: 110,
          render: (value?: string) => (value ? <Tag>{value}</Tag> : <span className="tg-muted">—</span>),
        },
        ...columns.slice(3),
      ]
    : columns;

  return (
    <Modal open={open} title="批量操作结果" onCancel={onClose} onOk={onClose} okText="知道了" cancelText="关闭" width={760}>
      {result ? (
        <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
          {/* 统计块：每个数字独立成块，配色区分「成了几个 / 挂了几个 / 跳了几个」 */}
          <div className="tg-flex" style={{ gap: 'var(--tg-space-sm)', flexWrap: 'wrap' }}>
            <span className="tg-result-stat is-total">
              命中 <b>{result.requested}</b>
            </span>
            {result.succeeded ? (
              <span className="tg-result-stat is-ok">
                成功 <b>{result.succeeded}</b>
              </span>
            ) : null}
            {result.failed ? (
              <span className="tg-result-stat is-fail">
                失败 <b>{result.failed}</b>
              </span>
            ) : null}
            {result.skipped ? (
              <span className="tg-result-stat is-skip">
                跳过 <b>{result.skipped}</b>
              </span>
            ) : null}
            {result.task_ids.length ? (
              <span className="tg-result-stat is-task">
                入队任务 <b>{result.task_ids.length}</b>
              </span>
            ) : null}
          </div>
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
            columns={columnsWithCheck}
            dataSource={items}
            pagination={{ pageSize: 10, showSizeChanger: false, size: 'small', showTotal: (total) => `共 ${total} 条` }}
          />
        </div>
      ) : null}
    </Modal>
  );
}
