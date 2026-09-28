import { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ApiOutlined,
  DeleteOutlined,
  EditOutlined,
  LinkOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { accountApi, proxyApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { PROXY_SCHEME_OPTIONS } from '../constants';
import { formatTime } from '../utils/format';
import { notifySuccess } from '../utils/feedback';
import AccountPickerModal from '../components/AccountPickerModal';
import type { ProxyCreate, ProxyOut, ProxyScheme } from '../api/types';

export default function Network() {
  const proxies = useAsyncData(() => proxyApi.list(), []);
  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }), []);

  const [editing, setEditing] = useState<ProxyOut | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [bindProxy, setBindProxy] = useState<ProxyOut | null>(null);
  const [saving, setSaving] = useState(false);

  const allAccounts = useMemo(() => accounts.data?.items ?? [], [accounts.data]);

  const boundIds = useMemo(() => {
    if (!bindProxy) return [];
    return allAccounts.filter((item) => item.proxy_id === bindProxy.id).map((item) => item.id);
  }, [allAccounts, bindProxy]);

  const columns: ColumnsType<ProxyOut> = [
    { title: '名称', dataIndex: 'name', width: 150 },
    {
      title: '协议',
      dataIndex: 'scheme',
      width: 110,
      render: (value: string) => <Tag color="geekblue">{value.toUpperCase()}</Tag>,
    },
    {
      title: '地址',
      dataIndex: 'endpoint',
      render: (value: string) => <Typography.Text code>{value}</Typography.Text>,
    },
    {
      title: '账号密码',
      dataIndex: 'has_auth',
      width: 110,
      render: (value: boolean) => (value ? <Tag color="green">已配置</Tag> : <Tag>无</Tag>),
    },
    {
      title: '绑定账号数',
      dataIndex: 'account_count',
      width: 110,
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 90,
      render: (value: boolean, record) => (
        <Switch
          size="small"
          checked={value}
          onChange={async (checked) => {
            try {
              await proxyApi.update(record.id, { enabled: checked });
              notifySuccess(checked ? '代理已启用' : '代理已停用');
              void proxies.reload();
            } catch {
              /* client 已统一提示 */
            }
          }}
        />
      ),
    },
    {
      title: '备注',
      dataIndex: 'remark',
      width: 150,
      render: (value: string) => value || '—',
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
      width: 260,
      render: (_: unknown, record) => (
        <Space>
          <Button size="small" icon={<LinkOutlined />} onClick={() => setBindProxy(record)}>
            绑定账号
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(record)}>
            编辑
          </Button>
          <Popconfirm
            title="删除这个代理？"
            description="已绑定的账号需要重新指定出站地址。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              try {
                const res = await proxyApi.remove(record.id);
                notifySuccess(res.message || '代理已删除');
                void proxies.reload();
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

  const handleBind = async (selectedIds: string[]) => {
    if (!bindProxy) return;
    const current = new Set(boundIds);
    const next = new Set(selectedIds);
    const added = selectedIds.filter((id) => !current.has(id));
    const removed = boundIds.filter((id) => !next.has(id));
    setSaving(true);
    try {
      if (added.length) {
        const res = await proxyApi.bindAccounts(bindProxy.id, added);
        notifySuccess(res.message || `已绑定 ${added.length} 个账号`);
      }
      // 契约只提供代理 → 账号的绑定接口，解绑走账号侧 PATCH proxy_id=null
      for (const accountId of removed) {
        await accountApi.update(accountId, { proxy_id: null });
      }
      if (removed.length) notifySuccess(`已解绑 ${removed.length} 个账号（改为直连）`);
      if (!added.length && !removed.length) notifySuccess('绑定关系没有变化');
      setBindProxy(null);
      void proxies.reload();
      void accounts.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <Card
        title="网络 / 代理"
        extra={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                void proxies.reload();
                void accounts.reload();
              }}
              loading={proxies.loading}
            >
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建代理
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="代理是这个号固定的出站地址，Worker 认领时读取；用户名/密码加密保存，接口只回是否已配置。"
        />
        {proxies.error ? (
          <Alert type="error" showIcon message={`代理加载失败：${proxies.error}`} style={{ marginBottom: 12 }} />
        ) : null}
        <Table<ProxyOut>
          size="small"
          rowKey="id"
          loading={proxies.loading}
          dataSource={proxies.data ?? []}
          columns={columns}
          pagination={false}
          scroll={{ x: 1300 }}
          locale={{ emptyText: <Empty description="还没有代理，先新建一个" /> }}
        />
      </Card>

      <ProxyFormModal
        open={createOpen || Boolean(editing)}
        proxy={editing}
        onCancel={() => {
          setCreateOpen(false);
          setEditing(null);
        }}
        onSuccess={() => {
          setCreateOpen(false);
          setEditing(null);
          void proxies.reload();
          void accounts.reload();
        }}
      />

      <AccountPickerModal
        open={Boolean(bindProxy)}
        title={`把账号绑定到代理：${bindProxy?.name ?? ''}`}
        hint="勾选 = 走这个代理，取消勾选 = 解绑改为直连。"
        value={boundIds}
        confirmLoading={saving}
        onCancel={() => setBindProxy(null)}
        onSubmit={handleBind}
      />
    </div>
  );
}

interface ProxyForm {
  name: string;
  scheme: ProxyScheme;
  host: string;
  port: number;
  username?: string;
  password?: string;
  enabled: boolean;
  remark?: string;
}

function ProxyFormModal({
  open,
  proxy,
  onCancel,
  onSuccess,
}: {
  open: boolean;
  proxy: ProxyOut | null;
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<ProxyForm>();
  const [submitting, setSubmitting] = useState(false);

  const handleFinish = async (values: ProxyForm) => {
    setSubmitting(true);
    const payload: ProxyCreate = {
      name: values.name.trim(),
      scheme: values.scheme,
      host: values.host.trim(),
      port: values.port,
      enabled: values.enabled,
      remark: values.remark ?? '',
    };
    // 只有填了才提交账号密码，留空 = 不改动
    if (values.username) payload.username = values.username;
    if (values.password) payload.password = values.password;

    try {
      if (proxy) {
        await proxyApi.update(proxy.id, payload);
        notifySuccess('代理已更新');
      } else {
        await proxyApi.create(payload);
        notifySuccess('代理已创建');
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
      title={proxy ? `编辑代理：${proxy.name}` : '新建代理'}
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
        key={proxy?.id ?? 'new'}
        initialValues={{
          name: proxy?.name ?? '',
          scheme: (proxy?.scheme as ProxyScheme) ?? 'socks5',
          host: proxy?.host ?? '',
          port: proxy?.port ?? 1080,
          enabled: proxy?.enabled ?? true,
          remark: proxy?.remark ?? '',
        }}
      >
        <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入名称' }]}>
          <Input placeholder="例如：HK-01" allowClear />
        </Form.Item>
        <Space size="middle" style={{ display: 'flex' }} align="start">
          <Form.Item label="协议" name="scheme" rules={[{ required: true, message: '请选择协议' }]}>
            <Select style={{ width: 140 }} options={PROXY_SCHEME_OPTIONS} />
          </Form.Item>
          <Form.Item
            label="主机"
            name="host"
            rules={[{ required: true, message: '请输入主机' }]}
            style={{ minWidth: 220 }}
          >
            <Input placeholder="1.2.3.4 或 host.example.com" allowClear prefix={<ApiOutlined />} />
          </Form.Item>
          <Form.Item label="端口" name="port" rules={[{ required: true, message: '请输入端口' }]}>
            <InputNumber min={1} max={65535} style={{ width: 110 }} />
          </Form.Item>
        </Space>
        <Form.Item label="用户名（留空表示不修改）" name="username">
          <Input placeholder="可选" allowClear autoComplete="off" />
        </Form.Item>
        <Form.Item label="密码（留空表示不修改）" name="password">
          <Input.Password placeholder="可选" autoComplete="new-password" />
        </Form.Item>
        <Form.Item label="启用" name="enabled" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item label="备注" name="remark">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
