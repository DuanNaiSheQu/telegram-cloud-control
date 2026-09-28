import { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, TeamOutlined } from '@ant-design/icons';
import { accountApi, groupApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { formatTime } from '../utils/format';
import { notifySuccess } from '../utils/feedback';
import AccountPickerModal from '../components/AccountPickerModal';
import type { GroupOut } from '../api/types';

interface GroupForm {
  name: string;
  description?: string;
}

export default function Groups() {
  const groups = useAsyncData(() => groupApi.list(), []);
  // 用于算「哪些号已经在这个分组里」，account_id → group_id
  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }), []);

  const [editing, setEditing] = useState<GroupOut | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [memberGroup, setMemberGroup] = useState<GroupOut | null>(null);
  const [savingMembers, setSavingMembers] = useState(false);

  const allAccounts = useMemo(() => accounts.data?.items ?? [], [accounts.data]);

  const memberIds = useMemo(() => {
    if (!memberGroup) return [];
    return allAccounts.filter((item) => item.group_id === memberGroup.id).map((item) => item.id);
  }, [allAccounts, memberGroup]);

  const columns: ColumnsType<GroupOut> = [
    { title: '分组名', dataIndex: 'name', width: 180, render: (v: string) => <Tag color="blue">{v}</Tag> },
    {
      title: '说明',
      dataIndex: 'description',
      render: (v: string) => v || <Typography.Text type="secondary">—</Typography.Text>,
    },
    { title: '账号数', dataIndex: 'account_count', width: 100 },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (v: string | null) => formatTime(v),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_: unknown, record) => (
        <Space>
          <Button size="small" icon={<TeamOutlined />} onClick={() => setMemberGroup(record)}>
            管理账号
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(record)}>
            编辑
          </Button>
          <Popconfirm
            title="删除这个分组？"
            description="账号本身不会被删除，只是不再属于该分组。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              try {
                const res = await groupApi.remove(record.id);
                notifySuccess(res.message || '分组已删除');
                void groups.reload();
                void accounts.reload();
              } catch {
                /* client 已统一提示 */
              }
            }}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

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
        notifySuccess(res.message || `已加入 ${added.length} 个账号`);
      }
      if (removed.length) {
        const res = await groupApi.removeAccounts(memberGroup.id, removed);
        notifySuccess(res.message || `已移出 ${removed.length} 个账号`);
      }
      if (!added.length && !removed.length) notifySuccess('分组没有变化');
      setMemberGroup(null);
      void groups.reload();
      void accounts.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setSavingMembers(false);
    }
  };

  return (
    <div>
      <Card
        title="账号分组"
        extra={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                void groups.reload();
                void accounts.reload();
              }}
              loading={groups.loading}
            >
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建分组
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="分组是内部标签，用来把号分给同事；一个号同一时间只属于一个分组。"
        />
        {groups.error ? (
          <Alert type="error" showIcon message={`分组加载失败：${groups.error}`} style={{ marginBottom: 12 }} />
        ) : null}
        <Table<GroupOut>
          size="small"
          rowKey="id"
          loading={groups.loading}
          dataSource={groups.data ?? []}
          columns={columns}
          pagination={false}
          locale={{ emptyText: <Empty description="还没有分组，先新建一个" /> }}
        />
      </Card>

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

      <AccountPickerModal
        open={Boolean(memberGroup)}
        title={`管理分组账号：${memberGroup?.name ?? ''}`}
        hint="勾选 = 加入该分组，取消勾选 = 移出该分组；保存时只提交变化的部分。"
        value={memberIds}
        confirmLoading={savingMembers}
        onCancel={() => setMemberGroup(null)}
        onSubmit={handleSaveMembers}
      />
    </div>
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
        notifySuccess('分组已更新');
      } else {
        await groupApi.create({ name: values.name.trim(), description: values.description ?? '' });
        notifySuccess('分组已创建');
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
          rules={[{ required: true, message: '请输入分组名' }, { max: 64, message: '最多 64 个字符' }]}
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
