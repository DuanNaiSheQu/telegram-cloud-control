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
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DeleteOutlined, KeyOutlined, PlusOutlined, ReloadOutlined, TeamOutlined } from '@ant-design/icons';
import { assignmentApi, userApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { USER_ROLE_LABELS, USER_ROLE_OPTIONS } from '../constants';
import { formatTime } from '../utils/format';
import { notifySuccess } from '../utils/feedback';
import { useAuth } from '../auth/AuthContext';
import AccountPickerModal from '../components/AccountPickerModal';
import type { UserOut, UserRole } from '../api/types';

export default function Assignments() {
  const { isAdmin } = useAuth();
  const users = useAsyncData(() => userApi.list(), []);
  const assignments = useAsyncData(() => assignmentApi.list(), []);

  const [createOpen, setCreateOpen] = useState(false);
  const [pwdUser, setPwdUser] = useState<UserOut | null>(null);
  const [assignUser, setAssignUser] = useState<UserOut | null>(null);
  const [saving, setSaving] = useState(false);

  const assignedIds = useMemo(() => {
    if (!assignUser) return [];
    return assignments.data?.find((item) => item.user_id === assignUser.id)?.account_ids ?? [];
  }, [assignments.data, assignUser]);

  const handleAssign = async (selectedIds: string[]) => {
    if (!assignUser) return;
    const current = new Set(assignedIds);
    const next = new Set(selectedIds);
    const added = selectedIds.filter((id) => !current.has(id));
    const removed = assignedIds.filter((id) => !next.has(id));
    setSaving(true);
    try {
      if (added.length) {
        await assignmentApi.create(assignUser.id, added);
        notifySuccess(`已给 ${assignUser.username} 分配 ${added.length} 个账号`);
      }
      if (removed.length) {
        await assignmentApi.remove(assignUser.id, removed);
        notifySuccess(`已取消 ${removed.length} 个账号的分配`);
      }
      if (!added.length && !removed.length) notifySuccess('分配关系没有变化');
      setAssignUser(null);
      void users.reload();
      void assignments.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnsType<UserOut> = [
    { title: '用户名', dataIndex: 'username', width: 160 },
    {
      title: '显示名',
      dataIndex: 'display_name',
      width: 160,
      render: (value: string) => value || '—',
    },
    {
      title: '角色',
      dataIndex: 'role',
      width: 110,
      render: (value: UserRole) => (
        <Tag color={value === 'admin' ? 'gold' : 'blue'}>{USER_ROLE_LABELS[value] ?? value}</Tag>
      ),
    },
    {
      title: '已分配账号数',
      dataIndex: 'account_count',
      width: 130,
      render: (value: number, record) => (
        <Space>
          <Tag color={value > 0 ? 'blue' : 'default'}>{value}</Tag>
          {record.role === 'admin' ? (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              管理员看全部
            </Typography.Text>
          ) : null}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 100,
      render: (value: boolean) => (value ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
    },
    {
      title: '最后登录',
      dataIndex: 'last_login_at',
      width: 170,
      render: (value: string | null) => formatTime(value),
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
      width: 300,
      render: (_: unknown, record) => (
        <Space wrap>
          <Button
            size="small"
            icon={<TeamOutlined />}
            disabled={!isAdmin}
            onClick={() => setAssignUser(record)}
          >
            分配账号
          </Button>
          <Button size="small" icon={<KeyOutlined />} disabled={!isAdmin} onClick={() => setPwdUser(record)}>
            改口令
          </Button>
          <Button
            size="small"
            disabled={!isAdmin}
            onClick={async () => {
              try {
                await userApi.update(record.id, { is_active: !record.is_active });
                notifySuccess(record.is_active ? '员工已停用' : '员工已启用');
                void users.reload();
              } catch {
                /* client 已统一提示 */
              }
            }}
          >
            {record.is_active ? '停用' : '启用'}
          </Button>
          <Popconfirm
            title="删除这个员工？"
            description="删除后他用这个账号登录不了控制台。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            disabled={!isAdmin}
            onConfirm={async () => {
              try {
                const res = await userApi.remove(record.id);
                notifySuccess(res.message || '员工已删除');
                void users.reload();
                void assignments.reload();
              } catch {
                /* client 已统一提示 */
              }
            }}
          >
            <Button size="small" danger icon={<DeleteOutlined />} disabled={!isAdmin}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card
        title="员工分配"
        extra={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              loading={users.loading}
              onClick={() => {
                void users.reload();
                void assignments.reload();
              }}
            >
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} disabled={!isAdmin} onClick={() => setCreateOpen(true)}>
              新建员工
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="操作员只能看/操作被分配到的账号；管理员看全部账号。分组是标签，分配才是权限。"
        />
        {!isAdmin ? (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            message="当前登录的不是管理员，员工管理和分配按钮不可用（后端会回 403）。"
          />
        ) : null}
        <Table<UserOut>
          size="small"
          rowKey="id"
          loading={users.loading}
          dataSource={users.data ?? []}
          columns={columns}
          pagination={false}
          scroll={{ x: 1300 }}
          locale={{ emptyText: <Empty description="还没有员工账号" /> }}
        />
      </Card>

      <UserFormModal
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onSuccess={() => {
          setCreateOpen(false);
          void users.reload();
        }}
      />

      <PasswordModal
        user={pwdUser}
        onCancel={() => setPwdUser(null)}
        onSuccess={() => setPwdUser(null)}
      />

      <AccountPickerModal
        open={Boolean(assignUser)}
        title={`分配账号给：${assignUser?.display_name || assignUser?.username || ''}`}
        hint="勾选 = 分配，取消勾选 = 收回；保存时只提交变化的部分。"
        value={assignedIds}
        confirmLoading={saving}
        onCancel={() => setAssignUser(null)}
        onSubmit={handleAssign}
      />
    </div>
  );
}

interface UserForm {
  username: string;
  password: string;
  display_name?: string;
  role: UserRole;
}

function UserFormModal({
  open,
  onCancel,
  onSuccess,
}: {
  open: boolean;
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<UserForm>();
  const [submitting, setSubmitting] = useState(false);

  const handleFinish = async (values: UserForm) => {
    setSubmitting(true);
    try {
      await userApi.create({
        username: values.username.trim(),
        password: values.password,
        display_name: values.display_name ?? '',
        role: values.role,
      });
      notifySuccess('员工已创建');
      form.resetFields();
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
      title="新建员工"
      onCancel={onCancel}
      onOk={() => form.submit()}
      okText="创建"
      cancelText="取消"
      confirmLoading={submitting}
    >
      <Form form={form} layout="vertical" onFinish={handleFinish} initialValues={{ role: 'operator' }}>
        <Form.Item
          label="用户名"
          name="username"
          rules={[{ required: true, message: '请输入用户名' }, { min: 2, message: '至少 2 个字符' }]}
        >
          <Input placeholder="登录用户名" allowClear autoComplete="off" />
        </Form.Item>
        <Form.Item
          label="口令"
          name="password"
          rules={[{ required: true, message: '请输入口令' }, { min: 6, message: '至少 6 位' }]}
        >
          <Input.Password placeholder="至少 6 位" autoComplete="new-password" />
        </Form.Item>
        <Form.Item label="显示名" name="display_name">
          <Input placeholder="例如：值班-小王" allowClear />
        </Form.Item>
        <Form.Item label="角色" name="role" rules={[{ required: true, message: '请选择角色' }]}>
          <Select options={USER_ROLE_OPTIONS} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

function PasswordModal({
  user,
  onCancel,
  onSuccess,
}: {
  user: UserOut | null;
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<{ password: string }>();
  const [submitting, setSubmitting] = useState(false);

  const handleFinish = async (values: { password: string }) => {
    if (!user) return;
    setSubmitting(true);
    try {
      await userApi.update(user.id, { password: values.password });
      notifySuccess('口令已更新');
      form.resetFields();
      onSuccess();
    } catch {
      /* client 已统一提示 */
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={Boolean(user)}
      title={`修改口令：${user?.username ?? ''}`}
      onCancel={onCancel}
      onOk={() => form.submit()}
      okText="保存"
      cancelText="取消"
      confirmLoading={submitting}
    >
      <Form form={form} layout="vertical" onFinish={handleFinish}>
        <Form.Item
          label="新口令"
          name="password"
          rules={[{ required: true, message: '请输入新口令' }, { min: 6, message: '至少 6 位' }]}
        >
          <Input.Password placeholder="至少 6 位" autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
