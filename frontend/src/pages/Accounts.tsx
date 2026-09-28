import { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Dropdown,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CloudSyncOutlined,
  DownOutlined,
  EditOutlined,
  KeyOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
  ThunderboltOutlined,
  UserSwitchOutlined,
} from '@ant-design/icons';
import { accountApi, groupApi, proxyApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { ACCOUNT_STATUS_OPTIONS, CURRENT_TASK_OPTIONS } from '../constants';
import { formatAccountAge, formatFromNow, formatTime, isHeartbeatStale } from '../utils/format';
import { notifyError, notifySuccess } from '../utils/feedback';
import { ApiError } from '../api/client';
import StatusBadge from '../components/StatusBadge';
import { CurrentTaskTag } from '../components/TaskStatusTag';
import AccountLoginWizard from '../components/AccountLoginWizard';
import type {
  AccountListQuery,
  AccountOut,
  AccountStatus,
  GroupOut,
  ProxyOut,
} from '../api/types';

const PAGE_SIZE = 20;

interface CreateForm {
  phone: string;
  group_id?: string;
  proxy_id?: string;
  remark?: string;
}

interface EditForm {
  group_id?: string | null;
  proxy_id?: string | null;
  remark?: string;
}

interface ProfileForm {
  first_name?: string;
  last_name?: string;
  bio?: string;
  username?: string;
  photo_url?: string;
}

export default function Accounts() {
  const [query, setQuery] = useState<AccountListQuery>({ page: 1, page_size: PAGE_SIZE });
  const [createOpen, setCreateOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardAccount, setWizardAccount] = useState<AccountOut | null>(null);
  const [editAccount, setEditAccount] = useState<AccountOut | null>(null);
  const [profileAccount, setProfileAccount] = useState<AccountOut | null>(null);

  const accounts = useAsyncData(() => accountApi.list(query), [query]);
  const groups = useAsyncData(() => groupApi.list(), []);
  const proxies = useAsyncData(() => proxyApi.list(), []);

  const items = accounts.data?.items ?? [];
  const summary = accounts.data?.summary ?? null;

  const patchQuery = (patch: Partial<AccountListQuery>, resetPage = true) => {
    setQuery((prev) => ({ ...prev, ...patch, page: resetPage ? 1 : prev.page }));
  };

  const runAccountAction = async (
    account: AccountOut,
    action: () => Promise<{ ok: boolean; message: string }>,
    successText: string,
  ) => {
    try {
      const res = await action();
      notifySuccess(res?.message || successText);
      void accounts.reload();
      void proxies.reload();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        notifyError(err.detail || `${account.phone_masked} 当前状态不允许该操作`);
      }
    }
  };

  const columns: ColumnsType<AccountOut> = useMemo(
    () => [
      {
        title: '手机号',
        dataIndex: 'phone_masked',
        width: 140,
        fixed: 'left',
        render: (value: string, record) =>
          record.display_name ? (
            <Tooltip title={`本号资料名称：${record.display_name}`}>
              <span>{value}</span>
            </Tooltip>
          ) : (
            value
          ),
      },
      {
        title: '用户名',
        dataIndex: 'username',
        width: 130,
        render: (value: string | null) => value || '—',
      },
      {
        title: '用户 ID',
        dataIndex: 'tg_user_id',
        width: 120,
        render: (value: number | null) => (value ? String(value) : '—'),
      },
      {
        title: '号龄',
        dataIndex: 'age_days',
        width: 90,
        render: (value: number | null) => formatAccountAge(value),
      },
      { title: '群数量', dataIndex: 'group_count', width: 80 },
      {
        title: '分组',
        dataIndex: 'group_name',
        width: 120,
        render: (value: string | null) => (value ? <Tag color="blue">{value}</Tag> : <Tag>未分组</Tag>),
      },
      {
        title: '代理',
        dataIndex: 'proxy_endpoint',
        width: 180,
        render: (value: string | null) => (value ? <Typography.Text code>{value}</Typography.Text> : '直连'),
      },
      {
        title: '状态',
        dataIndex: 'status',
        width: 110,
        render: (_: unknown, record) => (
          <StatusBadge
            status={record.status}
            label={record.status_label}
            reason={record.status_reason || record.last_error}
          />
        ),
      },
      {
        title: '当前任务',
        dataIndex: 'current_task',
        width: 130,
        render: (_: unknown, record) => (
          <CurrentTaskTag task={record.current_task} label={record.current_task_label} />
        ),
      },
      {
        title: '最后心跳',
        dataIndex: 'last_heartbeat',
        width: 150,
        render: (value: string | null) => {
          const stale = isHeartbeatStale(value);
          return (
            <Tooltip title={formatTime(value)}>
              <span style={stale ? { color: '#cf1322' } : undefined}>{formatFromNow(value)}</span>
            </Tooltip>
          );
        },
      },
      {
        title: '操作',
        key: 'actions',
        width: 130,
        fixed: 'right',
        render: (_: unknown, record) => {
          const disabled = record.status === 'disabled';
          return (
            <Dropdown
              trigger={['click']}
              menu={{
                items: [
                  { key: 'login', icon: <KeyOutlined />, label: '登录向导 / 重新登录' },
                  { key: 'check', icon: <SafetyCertificateOutlined />, label: '单号检测' },
                  { key: 'sync', icon: <CloudSyncOutlined />, label: '同步会话' },
                  { type: 'divider' },
                  { key: 'edit', icon: <EditOutlined />, label: '修改分组 / 代理' },
                  { key: 'profile', icon: <UserSwitchOutlined />, label: '修改本号资料' },
                  { key: 'release', icon: <ThunderboltOutlined />, label: '清除租约' },
                  { type: 'divider' },
                  disabled
                    ? { key: 'enable', icon: <ThunderboltOutlined />, label: '启用' }
                    : { key: 'disable', icon: <StopOutlined />, label: '停用', danger: true },
                ],
                onClick: ({ key }) => {
                  if (key === 'login') {
                    setWizardAccount(record);
                    setWizardOpen(true);
                  }
                  if (key === 'check') {
                    void (async () => {
                      try {
                        const res = await accountApi.check(record.id);
                        if (res.reachable) notifySuccess(`${res.phone_masked}：${res.message || '连得上'}`);
                        else notifyError(`${res.phone_masked}：${res.message || res.status_label || '连不上'}`);
                        void accounts.reload();
                      } catch {
                        /* client 已统一提示 */
                      }
                    })();
                  }
                  if (key === 'sync') {
                    void (async () => {
                      try {
                        const res = await accountApi.syncDialogs(record.id);
                        notifySuccess(res.message || '已提交同步会话任务');
                        void accounts.reload();
                      } catch {
                        /* client 已统一提示 */
                      }
                    })();
                  }
                  if (key === 'edit') setEditAccount(record);
                  if (key === 'profile') setProfileAccount(record);
                  if (key === 'release') {
                    void runAccountAction(record, () => accountApi.releaseLease(record.id), '租约已清除');
                  }
                  if (key === 'disable') {
                    void runAccountAction(record, () => accountApi.disable(record.id), '账号已停用');
                  }
                  if (key === 'enable') {
                    void runAccountAction(record, () => accountApi.enable(record.id), '账号已启用');
                  }
                },
              }}
            >
              <Button size="small">
                操作 <DownOutlined />
              </Button>
            </Dropdown>
          );
        },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [accounts.reload, proxies.reload],
  );

  return (
    <div>
      <Row gutter={16} className="stat-row">
        <Col xs={12} xl={6}>
          <Card>
            <Statistic title="账号总数" value={summary?.total ?? accounts.data?.total ?? 0} />
          </Card>
        </Col>
        <Col xs={12} xl={6}>
          <Card>
            <Statistic title="正常" value={summary?.healthy ?? 0} valueStyle={{ color: '#3f8600' }} />
          </Card>
        </Col>
        <Col xs={12} xl={6}>
          <Card>
            <Statistic
              title="异常"
              value={summary?.abnormal ?? 0}
              valueStyle={{ color: (summary?.abnormal ?? 0) > 0 ? '#cf1322' : undefined }}
            />
          </Card>
        </Col>
        <Col xs={12} xl={6}>
          <Card>
            <Statistic title="本周新增" value={summary?.new_this_week ?? 0} />
          </Card>
        </Col>
      </Row>

      <Card>
        <div className="page-toolbar">
          <Select
            allowClear
            placeholder="分组"
            style={{ width: 160 }}
            value={query.group_id ?? undefined}
            onChange={(value) => patchQuery({ group_id: value ?? null })}
            options={(groups.data ?? []).map((g) => ({ value: g.id, label: `${g.name}（${g.account_count}）` }))}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 140 }}
            value={query.status || undefined}
            onChange={(value) => patchQuery({ status: (value as AccountStatus) ?? '' })}
            options={ACCOUNT_STATUS_OPTIONS}
          />
          <Select
            allowClear
            placeholder="当前任务"
            style={{ width: 160 }}
            value={query.current_task || undefined}
            onChange={(value) => patchQuery({ current_task: value ?? '' })}
            options={CURRENT_TASK_OPTIONS}
          />
          <Input.Search
            allowClear
            placeholder="手机号 / 用户名 / 备注"
            style={{ width: 220 }}
            defaultValue={query.phone}
            onSearch={(value) => patchQuery({ phone: value.trim(), keyword: value.trim() })}
          />
          <Space className="page-toolbar-right">
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                void accounts.reload();
                void groups.reload();
                void proxies.reload();
              }}
              loading={accounts.loading}
            >
              刷新
            </Button>
            <Button
              icon={<KeyOutlined />}
              onClick={() => {
                setWizardAccount(null);
                setWizardOpen(true);
              }}
            >
              登录向导
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建账号
            </Button>
          </Space>
        </div>

        {accounts.error ? (
          <Alert type="error" showIcon message={`账号列表加载失败：${accounts.error}`} style={{ marginBottom: 12 }} />
        ) : null}

        <Table<AccountOut>
          size="small"
          rowKey="id"
          loading={accounts.loading}
          dataSource={items}
          columns={columns}
          scroll={{ x: 1500 }}
          locale={{ emptyText: <Empty description="没有符合条件的账号" /> }}
          pagination={{
            current: query.page ?? 1,
            pageSize: query.page_size ?? PAGE_SIZE,
            total: accounts.data?.total ?? 0,
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            showTotal: (total) => `共 ${total} 个账号`,
            onChange: (page, pageSize) => setQuery((prev) => ({ ...prev, page, page_size: pageSize })),
          }}
        />
      </Card>

      <CreateAccountModal
        open={createOpen}
        groups={groups.data ?? []}
        proxies={proxies.data ?? []}
        onCancel={() => setCreateOpen(false)}
        onSuccess={() => {
          setCreateOpen(false);
          void accounts.reload();
          void groups.reload();
        }}
      />

      <AccountLoginWizard
        open={wizardOpen}
        account={wizardAccount}
        groups={groups.data ?? []}
        proxies={proxies.data ?? []}
        onCancel={() => setWizardOpen(false)}
        onDone={() => {
          void accounts.reload();
          void groups.reload();
        }}
      />

      <EditAccountModal
        account={editAccount}
        groups={groups.data ?? []}
        proxies={proxies.data ?? []}
        onCancel={() => setEditAccount(null)}
        onSuccess={() => {
          setEditAccount(null);
          void accounts.reload();
          void proxies.reload();
        }}
      />

      <ProfileModal
        account={profileAccount}
        onCancel={() => setProfileAccount(null)}
        onSuccess={() => {
          setProfileAccount(null);
          void accounts.reload();
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------- 子弹窗

function CreateAccountModal({
  open,
  groups,
  proxies,
  onCancel,
  onSuccess,
}: {
  open: boolean;
  groups: GroupOut[];
  proxies: ProxyOut[];
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<CreateForm>();
  const [submitting, setSubmitting] = useState(false);

  const handleFinish = async (values: CreateForm) => {
    setSubmitting(true);
    try {
      await accountApi.create({
        phone: values.phone.trim(),
        group_id: values.group_id || null,
        proxy_id: values.proxy_id || null,
        remark: values.remark ?? '',
      });
      notifySuccess('账号已建档，接着用「登录向导」发验证码');
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
      title="新建账号"
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
      onOk={() => form.submit()}
      okText="建档"
      cancelText="取消"
      confirmLoading={submitting}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="建档不自动登录；会话由该号自己的验证码拿到。"
      />
      <Form form={form} layout="vertical" onFinish={handleFinish} autoComplete="off">
        <Form.Item
          label="手机号（带国家码）"
          name="phone"
          rules={[{ required: true, message: '请输入手机号' }]}
        >
          <Input placeholder="+8613800000000" allowClear />
        </Form.Item>
        <Form.Item label="分组（可选）" name="group_id">
          <Select
            allowClear
            placeholder="不选则不分组"
            options={groups.map((g) => ({ value: g.id, label: g.name }))}
          />
        </Form.Item>
        <Form.Item label="代理（可选）" name="proxy_id">
          <Select
            allowClear
            placeholder="不选则直连"
            options={proxies.map((p) => ({ value: p.id, label: `${p.name}（${p.endpoint}）` }))}
          />
        </Form.Item>
        <Form.Item label="备注" name="remark">
          <Input.TextArea rows={2} placeholder="备注（可选）" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

function EditAccountModal({
  account,
  groups,
  proxies,
  onCancel,
  onSuccess,
}: {
  account: AccountOut | null;
  groups: GroupOut[];
  proxies: ProxyOut[];
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<EditForm>();
  const [submitting, setSubmitting] = useState(false);

  const handleFinish = async (values: EditForm) => {
    if (!account) return;
    setSubmitting(true);
    try {
      await accountApi.update(account.id, {
        group_id: values.group_id ?? null,
        proxy_id: values.proxy_id ?? null,
        remark: values.remark ?? '',
      });
      notifySuccess('已保存');
      onSuccess();
    } catch {
      /* client 已统一提示 */
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={Boolean(account)}
      title={`修改分组 / 代理：${account?.phone_masked ?? ''}`}
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
        initialValues={{
          group_id: account?.group_id ?? undefined,
          proxy_id: account?.proxy_id ?? undefined,
          remark: account?.remark ?? '',
        }}
        key={account?.id}
      >
        <Form.Item label="分组" name="group_id">
          <Select
            allowClear
            placeholder="清空 = 移出分组"
            options={groups.map((g) => ({ value: g.id, label: g.name }))}
          />
        </Form.Item>
        <Form.Item label="代理" name="proxy_id">
          <Select
            allowClear
            placeholder="清空 = 直连（不绑定代理）"
            options={proxies.map((p) => ({ value: p.id, label: `${p.name}（${p.endpoint}）` }))}
          />
        </Form.Item>
        <Form.Item label="备注" name="remark">
          <Input.TextArea rows={2} />
        </Form.Item>
        <Typography.Text type="secondary">
          分组是内部标签，代理是这个号固定的出站地址，Worker 认领时读取。
        </Typography.Text>
      </Form>
    </Modal>
  );
}

function ProfileModal({
  account,
  onCancel,
  onSuccess,
}: {
  account: AccountOut | null;
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<ProfileForm>();
  const [submitting, setSubmitting] = useState(false);

  const handleFinish = async (values: ProfileForm) => {
    if (!account) return;
    // 只提交真正填了的字段：契约里这些字段都可选，回空串有清空 Telegram 资料的风险
    const payload: {
      first_name?: string;
      last_name?: string;
      bio?: string;
      username?: string;
      photo_url?: string;
    } = {};
    (['first_name', 'last_name', 'bio', 'username', 'photo_url'] as const).forEach((key) => {
      const value = values[key]?.trim();
      if (value) payload[key] = value;
    });
    if (!Object.keys(payload).length) {
      notifyError('请至少填一项要修改的资料');
      return;
    }
    setSubmitting(true);
    try {
      const res = await accountApi.profile(account.id, payload);
      notifySuccess(res.message || '已提交改资料任务，等 Worker 执行');
      onSuccess();
    } catch {
      /* client 已统一提示 */
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={Boolean(account)}
      title={`修改本号资料：${account?.phone_masked ?? ''}`}
      onCancel={onCancel}
      onOk={() => form.submit()}
      okText="提交修改"
      cancelText="取消"
      confirmLoading={submitting}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="改的是这个号自己在 Telegram 上的名称和头像，由持有租约的 Worker 执行。"
      />
      <Form
        form={form}
        layout="vertical"
        onFinish={handleFinish}
        key={account?.id}
        initialValues={{ first_name: account?.display_name ?? '' }}
      >
        <Form.Item label="名称 first_name" name="first_name">
          <Input placeholder="名称" allowClear />
        </Form.Item>
        <Form.Item label="姓氏 last_name" name="last_name">
          <Input placeholder="姓氏（可选）" allowClear />
        </Form.Item>
        <Form.Item label="简介 bio" name="bio">
          <Input.TextArea rows={2} placeholder="简介（可选）" />
        </Form.Item>
        <Form.Item label="用户名 username" name="username">
          <Input placeholder="不带 @ 的用户名（可选）" allowClear />
        </Form.Item>
        <Form.Item label="头像 URL photo_url" name="photo_url">
          <Input placeholder="https://…（可选）" allowClear />
        </Form.Item>
      </Form>
    </Modal>
  );
}
