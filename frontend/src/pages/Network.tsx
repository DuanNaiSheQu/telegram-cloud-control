import { useMemo, useState } from 'react';
import { Alert, Button, Form, Input, InputNumber, Modal, Select, Space, Switch, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ApiOutlined, DeleteOutlined, EditOutlined, LinkOutlined, PlusOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { accountApi, proxyApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { PROXY_SCHEME_OPTIONS } from '../constants';
import { isAbnormalStatus } from '../constants';
import { formatTime } from '../utils/format';
import { toast } from '../utils/feedback';
import AccountPickerModal from '../components/AccountPickerModal';
import { ConfirmModal, CopyableText, DataTable, PageContainer, SoftTag, StatusDot } from '../components';
import { hostError, normalizeHost, parseEndpoint } from '../features/network/proxyNormalize';
import type { ProxyCreate, ProxyOut, ProxyScheme } from '../api/types';

export default function Network() {
  const proxies = useAsyncData(() => proxyApi.list(), []);
  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }), []);

  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<ProxyOut | null>(null);
  const [deleting, setDeleting] = useState<ProxyOut | null>(null);
  const [removing, setRemoving] = useState(false);
  const [bindProxy, setBindProxy] = useState<ProxyOut | null>(null);
  const [saving, setSaving] = useState(false);

  const allAccounts = useMemo(() => accounts.data?.items ?? [], [accounts.data]);

  /** proxy_id → 绑定账号的状态分布（健康提示用） */
  const healthOf = useMemo(() => {
    const map = new Map<string, { healthy: number; abnormal: number; pending: number }>();
    allAccounts.forEach((item) => {
      if (!item.proxy_id) return;
      const entry = map.get(item.proxy_id) ?? { healthy: 0, abnormal: 0, pending: 0 };
      if (item.status === 'healthy') entry.healthy += 1;
      else if (item.status === 'pending') entry.pending += 1;
      else if (isAbnormalStatus(item.status)) entry.abnormal += 1;
      map.set(item.proxy_id, entry);
    });
    return map;
  }, [allAccounts]);

  const boundIds = useMemo(() => {
    if (!bindProxy) return [];
    return allAccounts.filter((item) => item.proxy_id === bindProxy.id).map((item) => item.id);
  }, [allAccounts, bindProxy]);

  const handleDelete = async () => {
    if (!deleting) return;
    setRemoving(true);
    try {
      const res = await proxyApi.remove(deleting.id);
      toast.success(res.message || '代理已删除');
      setDeleting(null);
      void proxies.reload();
      void accounts.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setRemoving(false);
    }
  };

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
        toast.success(res.message || `已绑定 ${added.length} 个账号`);
      }
      // 契约只提供代理 → 账号的绑定接口，解绑走账号侧 PATCH proxy_id=null（显式传 null = 直连）
      for (const accountId of removed) {
        await accountApi.update(accountId, { proxy_id: null });
      }
      if (removed.length) toast.success(`已解绑 ${removed.length} 个账号（改为直连）`);
      if (!added.length && !removed.length) toast.info('绑定关系没有变化');
      setBindProxy(null);
      void proxies.reload();
      void accounts.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnsType<ProxyOut> = [
    { title: '名称', dataIndex: 'name', width: 140, render: (value: string) => <span style={{ fontWeight: 'var(--tg-font-weight-medium)' }}>{value}</span> },
    {
      title: '协议',
      dataIndex: 'scheme',
      width: 100,
      render: (value: string) => <SoftTag tone="info" size="sm">{value.toUpperCase()}</SoftTag>,
    },
    {
      title: '出口',
      dataIndex: 'endpoint',
      render: (value: string) => <CopyableText value={value} mono maxLength={40} truncate="middle" />,
    },
    {
      title: '账号口令',
      dataIndex: 'has_auth',
      width: 100,
      render: (value: boolean) => (value ? <SoftTag tone="success" size="sm">已配置</SoftTag> : <SoftTag tone="neutral" size="sm">无</SoftTag>),
    },
    {
      title: '绑定账号',
      key: 'binding',
      width: 210,
      render: (_: unknown, record) => {
        const health = healthOf.get(record.id);
        return (
          <span className="tg-flex" style={{ alignItems: 'center', gap: 'var(--tg-space-sm)' }}>
            <span className="tg-num">{record.account_count} 个</span>
            {health && health.abnormal > 0 ? (
              <Tooltip title="绑定账号里有异常状态（needs_code / frozen / invalid / dead / disabled），建议排查账号或换代理">
                <SoftTag tone="danger" size="sm">
                  <ThunderboltOutlined /> {health.abnormal} 个异常
                </SoftTag>
              </Tooltip>
            ) : record.account_count > 0 ? (
              <SoftTag tone="success" size="sm">全部正常</SoftTag>
            ) : (
              <SoftTag tone="neutral" size="sm">未绑定</SoftTag>
            )}
          </span>
        );
      },
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 80,
      render: (value: boolean, record) => (
        <Switch
          size="small"
          checked={value}
          onChange={async (checked) => {
            try {
              await proxyApi.update(record.id, { enabled: checked });
              toast.success(checked ? '代理已启用' : '代理已停用');
              void proxies.reload();
            } catch {
              /* client 已统一提示 */
            }
          }}
        />
      ),
    },
    { title: '备注', dataIndex: 'remark', width: 140, render: (value: string) => value || <span className="tg-muted">—</span> },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (value: string | null) => formatTime(value) },
    {
      title: '操作',
      key: 'actions',
      width: 250,
      render: (_: unknown, record) => (
        <Space>
          <Button size="small" icon={<LinkOutlined />} onClick={() => setBindProxy(record)}>
            绑定账号
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
      title="网络"
      description="代理是这个号固定的出站地址，Worker 认领时读取；用户名/密码加密保存，接口只回是否已配置。"
      actions={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            loading={proxies.loading}
            onClick={() => {
              void proxies.reload();
              void accounts.reload();
            }}
          >
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建代理
          </Button>
        </Space>
      }
    >
      <DataTable<ProxyOut>
        rowKey="id"
        columns={columns}
        dataSource={proxies.data ?? []}
        loading={proxies.loading}
        error={proxies.error}
        onRetry={() => {
          void proxies.reload();
          void accounts.reload();
        }}
        showDensity={false}
        scrollX={1300}
        empty={{
          art: 'network',
          title: '还没有代理',
          description: '新建代理后，把账号批量绑定过来即可走固定出口。',
          action: <Button type="primary" onClick={() => setCreateOpen(true)}>新建代理</Button>,
        }}
      />
      <Typography.Paragraph type="secondary" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
        <StatusDot status="healthy" kind="account" size={8} /> 健康提示按绑定账号的状态统计；有异常号时建议先修号，必要时换更稳的出口。
      </Typography.Paragraph>

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

      <ConfirmModal
        open={Boolean(deleting)}
        danger
        title={`删除代理「${deleting?.name ?? ''}」？`}
        content={<Typography.Text>已绑定的账号不会删除，但会失去出站地址（页面会引导重新绑定）。</Typography.Text>}
        okText="删除"
        loading={removing}
        onOk={() => void handleDelete()}
        onCancel={() => setDeleting(null)}
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
    </PageContainer>
  );
}

// ---------------------------------------------------------------- 代理表单（含出口规范化）

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
  const [endpoint, setEndpoint] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);

  const applyParse = () => {
    const parsed = parseEndpoint(endpoint);
    if (!parsed.host) {
      setParseError('解析不出主机，请检查出口写法（如 socks5://user:pass@1.2.3.4:1080）');
      return;
    }
    setParseError(null);
    const patch: Record<string, unknown> = {};
    if (parsed.scheme) patch.scheme = parsed.scheme;
    if (parsed.host) patch.host = parsed.host;
    if (parsed.port) patch.port = parsed.port;
    if (parsed.username) patch.username = parsed.username;
    if (parsed.password) patch.password = parsed.password;
    form.setFieldsValue(patch as never);
    toast.success('已解析出口并填入下方字段，核对后保存');
  };

  const handleFinish = async (values: ProxyForm) => {
    setSubmitting(true);
    const payload: ProxyCreate = {
      name: values.name.trim(),
      scheme: values.scheme,
      host: normalizeHost(values.host),
      port: values.port,
      enabled: values.enabled,
      remark: values.remark ?? '',
    };
    // 只有填了才提交账号密码，留空 = 不改动
    if (values.username?.trim()) payload.username = values.username.trim();
    if (values.password) payload.password = values.password;

    try {
      if (proxy) {
        await proxyApi.update(proxy.id, payload);
        toast.success('代理已更新');
      } else {
        await proxyApi.create(payload);
        toast.success('代理已创建');
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
      onCancel={() => {
        setEndpoint('');
        setParseError(null);
        onCancel();
      }}
      onOk={() => form.submit()}
      okText="保存"
      cancelText="取消"
      confirmLoading={submitting}
      width={560}
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
        {!proxy ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="粘贴完整出口可一键解析（socks5://user:pass@1.2.3.4:1080），也可以直接填下面的字段。"
          />
        ) : null}
        {!proxy ? (
          <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
            <Input
              prefix={<ApiOutlined />}
              placeholder="粘贴出口：socks5://user:pass@1.2.3.4:1080"
              value={endpoint}
              onChange={(e) => {
                setEndpoint(e.target.value);
                setParseError(null);
              }}
              onPressEnter={applyParse}
            />
            <Button onClick={applyParse}>解析出口</Button>
          </Space.Compact>
        ) : null}
        {parseError ? (
          <Typography.Text type="danger" style={{ display: 'block', marginBottom: 12, fontSize: 'var(--tg-font-size-sm)' }}>
            {parseError}
          </Typography.Text>
        ) : null}

        <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入名称' }, { max: 64, message: '最多 64 个字符' }]}>
          <Input placeholder="例如：HK-01" allowClear />
        </Form.Item>

        <div className="tg-flex" style={{ gap: 'var(--tg-space-md)', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <Form.Item label="协议" name="scheme" rules={[{ required: true, message: '请选择协议' }]}>
            <Select style={{ width: 140 }} options={PROXY_SCHEME_OPTIONS} />
          </Form.Item>
          <Form.Item
            label="主机"
            name="host"
            style={{ minWidth: 220 }}
            rules={[{ validator: (_rule, value: string) => (hostError(value ?? '') ? Promise.reject(new Error(hostError(value ?? '') ?? '')) : Promise.resolve()) }]}
            normalize={(value: string) => normalizeHost(value ?? '')}
          >
            <Input placeholder="1.2.3.4 或 host.example.com" allowClear prefix={<ApiOutlined />} />
          </Form.Item>
          <Form.Item label="端口" name="port" rules={[{ required: true, message: '请输入端口' }]}>
            <InputNumber min={1} max={65535} precision={0} style={{ width: 110 }} />
          </Form.Item>
        </div>

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
