import { useMemo, useState } from 'react';
import { Button, Form, Input, Modal, Space, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, TeamOutlined } from '@ant-design/icons';
import { accountApi, groupApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { formatTime } from '../utils/format';
import { toast } from '../utils/feedback';
import { isAbnormalStatus } from '../constants';
import AccountPickerModal from '../components/AccountPickerModal';
import { ConfirmModal, DataTable, PageContainer, SoftTag, StatusDot } from '../components';
import type { GroupOut } from '../api/types';

interface GroupForm {
  name: string;
  description?: string;
}

/** 每个分组的账号状态分布（基于当前加载到的账号列表） */
interface GroupDistribution {
  healthy: number;
  pending: number;
  abnormal: number;
  /** 是否只是部分统计（账号总数超过单次拉取上限） */
  partial: boolean;
}

export default function Groups() {
  const groups = useAsyncData(() => groupApi.list(), []);
  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }), []);

  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<GroupOut | null>(null);
  const [deleting, setDeleting] = useState<GroupOut | null>(null);
  const [removing, setRemoving] = useState(false);
  const [memberGroup, setMemberGroup] = useState<GroupOut | null>(null);
  const [savingMembers, setSavingMembers] = useState(false);

  const allAccounts = useMemo(() => accounts.data?.items ?? [], [accounts.data]);
  const accountsTotal = accounts.data?.total ?? 0;

  const distributionOf = useMemo(() => {
    const map = new Map<string, GroupDistribution>();
    (groups.data ?? []).forEach((group) => {
      const members = allAccounts.filter((item) => item.group_id === group.id);
      map.set(group.id, {
        healthy: members.filter((item) => item.status === 'healthy').length,
        pending: members.filter((item) => item.status === 'pending').length,
        abnormal: members.filter((item) => isAbnormalStatus(item.status)).length,
        partial: accountsTotal > 200,
      });
    });
    return map;
  }, [groups.data, allAccounts, accountsTotal]);

  const memberIds = useMemo(() => {
    if (!memberGroup) return [];
    return allAccounts.filter((item) => item.group_id === memberGroup.id).map((item) => item.id);
  }, [allAccounts, memberGroup]);

  const handleDelete = async () => {
    if (!deleting) return;
    setRemoving(true);
    try {
      const res = await groupApi.remove(deleting.id);
      toast.success(res.message || '分组已删除');
      setDeleting(null);
      void groups.reload();
      void accounts.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setRemoving(false);
    }
  };

  const handleSaveMembers = async (selectedIds: string[]) => {
    if (!memberGroup) return;
    const current = new Set(memberIds);
    const next = new Set(selectedIds);
    const added = selectedIds.filter((id) => !current.has(id));
    const removed = memberIds.filter((id) => !next.has(id));
    setSavingMembers(true);
    try {
      if (added.length) {
        const res = await groupApi.addAccounts(memberGroup.id, added);
        toast.success(res.message || `已加入 ${added.length} 个账号`);
      }
      if (removed.length) {
        const res = await groupApi.removeAccounts(memberGroup.id, removed);
        toast.success(res.message || `已移出 ${removed.length} 个账号`);
      }
      if (!added.length && !removed.length) toast.info('分组没有变化');
      setMemberGroup(null);
      void groups.reload();
      void accounts.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setSavingMembers(false);
    }
  };

  const columns: ColumnsType<GroupOut> = [
    {
      title: '分组名',
      dataIndex: 'name',
      width: 200,
      render: (value: string) => <SoftTag tone="primary">{value}</SoftTag>,
    },
    {
      title: '说明',
      dataIndex: 'description',
      render: (value: string) => value || <span className="tg-muted">—</span>,
    },
    { title: '账号数', dataIndex: 'account_count', width: 90, render: (value: number) => <span className="tg-num">{value}</span> },
    {
      title: '状态分布',
      key: 'distribution',
      width: 280,
      render: (_: unknown, record) => {
        const dist = distributionOf.get(record.id);
        if (!dist) return <span className="tg-muted">—</span>;
        const chips = [
          { label: '正常', count: dist.healthy, status: 'healthy' as const },
          { label: '待登录', count: dist.pending, status: 'pending' as const },
          { label: '异常', count: dist.abnormal, status: 'frozen' as const },
        ];
        return (
          <span className="tg-flex" style={{ gap: 'var(--tg-space-md)', flexWrap: 'wrap' }}>
            {chips.map((chip) => (
              <Tooltip key={chip.status} title={`${chip.label} ${chip.count} 个${dist.partial ? '（基于前 200 个账号）' : ''}`}>
                <span
                  className="tg-flex"
                  style={{
                    alignItems: 'center',
                    gap: 'var(--tg-space-sm)',
                    fontSize: 'var(--tg-font-size-sm)',
                    color: 'var(--tg-color-text-secondary)',
                  }}
                >
                  <StatusDot status={chip.status} kind="account" size={8} />
                  {chip.label} <span className="tg-num">{chip.count}</span>
                </span>
              </Tooltip>
            ))}
          </span>
        );
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value: string | null) => formatTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 250,
      render: (_: unknown, record) => (
        <Space>
          <Button size="small" icon={<TeamOutlined />} onClick={() => setMemberGroup(record)}>
            管理账号
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(record)}>
            编辑
          </Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => setDeleting(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <PageContainer
      title="账号分组"
      description="分组是内部标签，用来把号分给同事；一个号同一时间只属于一个分组。"
      actions={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            loading={groups.loading}
            onClick={() => {
              void groups.reload();
              void accounts.reload();
            }}
          >
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建分组
          </Button>
        </Space>
      }
    >
      <DataTable<GroupOut>
        rowKey="id"
        columns={columns}
        dataSource={groups.data ?? []}
        loading={groups.loading}
        error={groups.error}
        onRetry={() => {
          void groups.reload();
          void accounts.reload();
        }}
        showDensity={false}
        empty={{
          art: 'list',
          title: '还没有分组',
          description: '新建分组后，把账号批量移入即可按组分配。',
          action: <Button type="primary" onClick={() => setCreateOpen(true)}>新建分组</Button>,
        }}
      />
      <Typography.Paragraph type="secondary" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
        状态分布按当前加载的账号统计；账号超过 200 个时显示前 200 个的口径，账号数仍以后端为准。
      </Typography.Paragraph>

      <GroupFormModal
        open={createOpen || Boolean(editing)}
        group={editing}
        onCancel={() => {
          setCreateOpen(false);
          setEditing(null);
        }}
        onSuccess={() => {
          setCreateOpen(false);
          setEditing(null);
          void groups.reload();
          void accounts.reload();
        }}
      />

      <ConfirmModal
        open={Boolean(deleting)}
        danger
        title={`删除分组「${deleting?.name ?? ''}」？`}
        content={<Typography.Text>账号本身不会被删除，只是不再属于该分组（变为未分组）。</Typography.Text>}
        okText="删除"
        loading={removing}
        onOk={() => void handleDelete()}
        onCancel={() => setDeleting(null)}
      />

      <AccountPickerModal
        open={Boolean(memberGroup)}
        title={`管理分组账号：${memberGroup?.name ?? ''}`}
        hint="勾选 = 加入该分组，取消勾选 = 移出该分组；保存时只提交变化的部分。"
        value={memberIds}
        confirmLoading={savingMembers}
        onCancel={() => setMemberGroup(null)}
        onSubmit={handleSaveMembers}
      />
    </PageContainer>
  );
}

function GroupFormModal({
  open,
  group,
  onCancel,
  onSuccess,
}: {
  open: boolean;
  group: GroupOut | null;
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<GroupForm>();
  const [submitting, setSubmitting] = useState(false);
  const isEdit = Boolean(group);

  const handleFinish = async (values: GroupForm) => {
    setSubmitting(true);
    try {
      if (group) {
        await groupApi.update(group.id, { name: values.name.trim(), description: values.description ?? '' });
        toast.success('分组已更新');
      } else {
        await groupApi.create({ name: values.name.trim(), description: values.description ?? '' });
        toast.success('分组已创建');
      }
      onSuccess();
    } catch {
      /* client 已统一提示 */
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={isEdit ? `编辑分组：${group?.name}` : '新建分组'}
      onCancel={onCancel}
      onOk={() => form.submit()}
      okText="保存"
      cancelText="取消"
      confirmLoading={submitting}
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={handleFinish}
        key={group?.id ?? 'new'}
        initialValues={{ name: group?.name ?? '', description: group?.description ?? '' }}
      >
        <Form.Item
          label="分组名"
          name="name"
          rules={[
            { required: true, message: '请输入分组名' },
            { max: 64, message: '最多 64 个字符' },
          ]}
        >
          <Input placeholder="例如：一组 / 值班号" allowClear />
        </Form.Item>
        <Form.Item label="说明" name="description">
          <Input.TextArea rows={2} placeholder="说明（可选）" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
