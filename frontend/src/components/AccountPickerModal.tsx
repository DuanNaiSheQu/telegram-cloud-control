import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Empty, Input, Modal, Select, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { accountApi, groupApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { formatTime } from '../utils/format';
import StatusBadge from './StatusBadge';
import type { AccountOut } from '../api/types';

export interface AccountPickerModalProps {
  open: boolean;
  title: React.ReactNode;
  hint?: React.ReactNode;
  /** 已选账号 id */
  value: string[];
  confirmLoading?: boolean;
  okText?: string;
  onCancel: () => void;
  onSubmit: (ids: string[]) => void | Promise<void>;
  /** 只允许选择这些账号（不传=全部） */
  restrictTo?: string[] | null;
}

/** 通用「挑账号」弹窗：分组 + 关键词筛选，多选，供分组 / 代理 / 员工分配复用。 */
export function AccountPickerModal({
  open,
  title,
  hint,
  value,
  confirmLoading,
  okText = '保存',
  onCancel,
  onSubmit,
  restrictTo = null,
}: AccountPickerModalProps) {
  const [keyword, setKeyword] = useState('');
  const [groupId, setGroupId] = useState<string | undefined>(undefined);
  const [selectedIds, setSelectedIds] = useState<string[]>(value);

  const groups = useAsyncData(() => groupApi.list(), [], { immediate: false });
  const accounts = useAsyncData(
    () =>
      accountApi.list({
        page: 1,
        page_size: 200,
        keyword: keyword || undefined,
        group_id: groupId || undefined,
      }),
    [open, keyword, groupId],
    { immediate: false },
  );

  useEffect(() => {
    if (!open) return;
    setSelectedIds(value);
    void groups.reload();
    void accounts.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, value]);

  useEffect(() => {
    if (!open) return;
    void accounts.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keyword, groupId]);

  const items = useMemo(() => {
    const list = accounts.data?.items ?? [];
    if (!restrictTo) return list;
    const allow = new Set(restrictTo);
    return list.filter((item) => allow.has(item.id));
  }, [accounts.data, restrictTo]);

  const columns: ColumnsType<AccountOut> = [
    { title: '手机号', dataIndex: 'phone_masked', width: 140 },
    {
      title: '用户名',
      dataIndex: 'username',
      width: 140,
      render: (v: string | null) => v || '—',
    },
    {
      title: '分组',
      dataIndex: 'group_name',
      width: 120,
      render: (v: string | null) => v || <Tag>未分组</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (_: unknown, record: AccountOut) => (
        <StatusBadge status={record.status} label={record.status_label} reason={record.status_reason} />
      ),
    },
    {
      title: '最后心跳',
      dataIndex: 'last_heartbeat',
      width: 170,
      render: (v: string | null) => formatTime(v),
    },
  ];

  const handleOk = useCallback(async () => {
    await onSubmit(selectedIds);
  }, [onSubmit, selectedIds]);

  return (
    <Modal
      open={open}
      title={title}
      onCancel={onCancel}
      onOk={handleOk}
      okText={okText}
      cancelText="取消"
      confirmLoading={confirmLoading}
      width={860}
    >
      <Space direction="vertical" size="small" style={{ width: '100%' }}>
        {hint ? <Alert type="info" showIcon message={hint} /> : null}
        <Space wrap>
          <Select
            allowClear
            placeholder="按分组筛选"
            style={{ width: 180 }}
            value={groupId}
            onChange={(v) => setGroupId(v)}
            options={(groups.data ?? []).map((g) => ({ value: g.id, label: `${g.name}（${g.account_count}）` }))}
          />
          <Input.Search
            allowClear
            placeholder="手机号 / 用户名关键词"
            style={{ width: 240 }}
            onSearch={(v) => setKeyword(v.trim())}
          />
          <Typography.Text type="secondary">已选 {selectedIds.length} 个</Typography.Text>
        </Space>
        <Table<AccountOut>
          size="small"
          rowKey="id"
          loading={accounts.loading}
          dataSource={items}
          columns={columns}
          locale={{ emptyText: <Empty description="没有符合条件的账号" /> }}
          pagination={{ pageSize: 10, showSizeChanger: false, size: 'small' }}
          scroll={{ y: 320 }}
          rowSelection={{
            preserveSelectedRowKeys: true,
            selectedRowKeys: selectedIds,
            onChange: (keys) => setSelectedIds(keys.map((k) => String(k))),
          }}
        />
        <Typography.Text type="secondary">
          共 {items.length} 个可选账号；勾选状态会被保留，切页/搜索不会丢。
        </Typography.Text>
      </Space>
    </Modal>
  );
}

export default AccountPickerModal;
