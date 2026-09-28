/**
 * AccountAssignModal —— 给某员工批量分配 / 取消分配账号。
 * - 搜索 / 分组筛选 / 多选；
 * - 「全部 / 已分配 / 未分配」视图：未分配 = 目前没有任何归属人的账号；
 * - 每行展示归属人（按账号反查归属），已勾选 = 分配给当前员工；
 * - 保存时只提交变化部分（新增走 create，收回走 remove）。
 */
import { useEffect, useMemo, useState } from 'react';
import { Alert, Input, Modal, Select, Segmented, Space, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { StatusBadge, SoftTag } from '../../components';
import { assignmentApi, groupApi } from '../../api/endpoints';
import { useAsyncData } from '../../hooks/useAsyncData';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { formatTime } from '../../utils/format';
import { notifySuccess } from '../../utils/feedback';
import { ApiError } from '../../api/client';
import type { AccountOut, AssignmentOut, UserOut } from '../../api/types';

export type AssignView = 'all' | 'assigned' | 'unassigned';

export function AccountAssignModal({
  open,
  user,
  assignments,
  accounts,
  onCancel,
  onSaved,
}: {
  open: boolean;
  user: UserOut | null;
  /** 全部员工的分配关系（用于「归属人」与「未分配」判定） */
  assignments: AssignmentOut[];
  accounts: AccountOut[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [keyword, setKeyword] = useState('');
  const [groupId, setGroupId] = useState<string | undefined>(undefined);
  const [view, setView] = useState<AssignView>('all');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const debouncedKeyword = useDebouncedValue(keyword, 300);
  const groups = useAsyncData(() => groupApi.list(), [], { immediate: false });

  useEffect(() => {
    if (!open) return;
    setKeyword('');
    setGroupId(undefined);
    setView('all');
    setError(null);
    void groups.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // 当前员工已分配
  useEffect(() => {
    if (!open || !user) return;
    setSelectedIds(assignments.find((item) => item.user_id === user.id)?.account_ids ?? []);
  }, [open, user, assignments]);

  /** 账号 → 归属人用户名（多个归属时取第一个，正常业务不会出现） */
  const ownerOf = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of assignments) {
      for (const id of item.account_ids) {
        if (!map.has(id)) map.set(id, item.username);
      }
    }
    return map;
  }, [assignments]);

  const currentIds = useMemo(
    () => (user ? assignments.find((item) => item.user_id === user.id)?.account_ids ?? [] : []),
    [assignments, user],
  );

  const rows = useMemo(() => {
    const kw = debouncedKeyword.trim().toLowerCase();
    return accounts.filter((item) => {
      if (groupId && item.group_id !== groupId) return false;
      const mine = currentIds.includes(item.id);
      const owned = ownerOf.has(item.id);
      if (view === 'assigned' && !mine) return false;
      if (view === 'unassigned' && owned) return false;
      if (kw) {
        const hay = `${item.phone_masked} ${item.username ?? ''} ${item.display_name} ${item.remark}`
          .toLowerCase();
        if (!hay.includes(kw)) return false;
      }
      return true;
    });
  }, [accounts, debouncedKeyword, groupId, view, currentIds, ownerOf]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const added = selectedIds.filter((id) => !currentIds.includes(id));
  const removed = currentIds.filter((id) => !selectedSet.has(id));

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
      render: (v: string | null) => v || <SoftTag tone="neutral">未分组</SoftTag>,
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
      title: '归属人',
      key: 'owner',
      width: 130,
      render: (_: unknown, record: AccountOut) => {
        const owner = ownerOf.get(record.id);
        const mine = currentIds.includes(record.id);
        if (owner) {
          return <SoftTag tone={mine ? 'primary' : 'neutral'}>{mine ? `${owner}（当前）` : owner}</SoftTag>;
        }
        return <SoftTag tone="warning">未分配</SoftTag>;
      },
    },
    {
      title: '最后心跳',
      dataIndex: 'last_heartbeat',
      width: 160,
      render: (v: string | null) => formatTime(v),
    },
  ];

  const handleSave = async () => {
    if (!user) return;
    setSaving(true);
    setError(null);
    try {
      if (added.length) {
        await assignmentApi.create(user.id, added);
        notifySuccess(`已给 ${user.username} 分配 ${added.length} 个账号`);
      }
      if (removed.length) {
        await assignmentApi.remove(user.id, removed);
        notifySuccess(`已取消 ${user.username} 名下 ${removed.length} 个账号的分配`);
      }
      if (!added.length && !removed.length) notifySuccess('分配关系没有变化');
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : '保存失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      title={`分配账号给：${user?.display_name || user?.username || ''}`}
      onCancel={onCancel}
      width={860}
      okText="保存变更"
      cancelText="取消"
      confirmLoading={saving}
      okButtonProps={{ disabled: !added.length && !removed.length }}
      onOk={() => void handleSave()}
      footer={(_, { OkBtn, CancelBtn }) => (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 'var(--tg-space-md)',
          }}
        >
          <Typography.Text type="secondary">
            {added.length || removed.length
              ? `将分配 ${added.length} 个、收回 ${removed.length} 个`
              : '没有变化，可直接关闭'}
          </Typography.Text>
          <Space>
            <CancelBtn />
            <OkBtn />
          </Space>
        </div>
      )}
    >
      <div
        style={{
          display: 'flex',
          gap: 'var(--tg-space-md)',
          alignItems: 'center',
          flexWrap: 'wrap',
          marginBottom: 'var(--tg-space-xl)',
        }}
      >
        <Input.Search
          allowClear
          placeholder="搜索手机号 / 用户名 / 备注"
          style={{ width: 260 }}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onSearch={(v) => setKeyword(v)}
        />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="全部账号分组"
          style={{ width: 180 }}
          value={groupId}
          onChange={(v) => setGroupId(v)}
          options={(groups.data ?? []).map((item) => ({ value: item.id, label: item.name }))}
        />
        <Segmented<AssignView>
          value={view}
          onChange={(v) => setView(v)}
          options={[
            { value: 'all', label: '全部' },
            { value: 'assigned', label: '已分配给该员工' },
            { value: 'unassigned', label: '未分配' },
          ]}
        />
      </div>

      {error ? (
        <Alert
          type="error"
          showIcon
          closable
          onClose={() => setError(null)}
          message="保存失败"
          description={error}
          style={{ marginBottom: 'var(--tg-space-lg)' }}
        />
      ) : null}

      <Table<AccountOut>
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={rows}
        scroll={{ y: 420, x: 820 }}
        rowSelection={{
          selectedRowKeys: selectedIds,
          onChange: (keys) => setSelectedIds(keys.map(String)),
          preserveSelectedRowKeys: true,
        }}
        pagination={false}
        locale={{ emptyText: '没有符合条件的账号' }}
      />
    </Modal>
  );
}
