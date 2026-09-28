import { useState } from 'react';
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
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { botApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { RELAY_TARGET_KIND_OPTIONS } from '../constants';
import { formatTime } from '../utils/format';
import { notifySuccess } from '../utils/feedback';
import type { BotCreate, BotOut, RelayTargetKind } from '../api/types';

/**
 * Bot 管理独立成页（不在 Bot 转发页做 Tab）：Token 掩码、Webhook 状态、
 * 自动回复开关和 persona 都在这里维护，转发规则在「Bot 转发」页。
 */
export default function Bots() {
  const bots = useAsyncData(() => botApi.list(), []);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<BotOut | null>(null);
  const [personaBot, setPersonaBot] = useState<BotOut | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const handleWebhook = async (bot: BotOut, enable: boolean) => {
    setBusyId(bot.id);
    try {
      const res = await botApi.webhook(bot.id, enable);
      notifySuccess(res.message || res.detail || (enable ? 'Webhook 已注册' : 'Webhook 已删除'));
      void bots.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setBusyId(null);
    }
  };

  const handleCheck = async (bot: BotOut) => {
    setBusyId(bot.id);
    try {
      const res = await botApi.check(bot.id);
      notifySuccess(`校验通过：${res.bot_username ? `@${res.bot_username}` : res.name}`);
      void bots.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setBusyId(null);
    }
  };

  const columns: ColumnsType<BotOut> = [
    {
      title: '名称',
      dataIndex: 'name',
      width: 150,
      render: (value: string, record) => (
        <Space direction="vertical" size={0}>
          <span>{value}</span>
          {record.bot_tg_id ? (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              ID {record.bot_tg_id}
            </Typography.Text>
          ) : null}
        </Space>
      ),
    },
    {
      title: '@username',
      dataIndex: 'bot_username',
      width: 160,
      render: (value: string | null) =>
        value ? (
          <Typography.Text code>@{value}</Typography.Text>
        ) : (
          <Tooltip title="Token 校验成功后由 getMe 回填">
            <Tag>未校验</Tag>
          </Tooltip>
        ),
    },
    {
      title: 'Token',
      dataIndex: 'token_masked',
      width: 170,
      render: (value: string) => <Typography.Text code>{value || '—'}</Typography.Text>,
    },
    {
      title: 'Webhook',
      key: 'webhook',
      width: 220,
      render: (_: unknown, record) => (
        <Space direction="vertical" size={2}>
          <Tag color={record.webhook_enabled ? 'green' : 'default'}>
            {record.webhook_enabled ? '已注册' : '未注册'}
          </Tag>
          {record.webhook_url ? (
            <Tooltip title={record.webhook_url}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }} className="ellipsis">
                {record.webhook_url}
              </Typography.Text>
            </Tooltip>
          ) : null}
          {record.webhook_set_at ? (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              设置于 {formatTime(record.webhook_set_at)}
            </Typography.Text>
          ) : null}
        </Space>
      ),
    },
    {
      title: '自动回复',
      dataIndex: 'auto_reply_enabled',
      width: 110,
      render: (value: boolean, record) => (
        <Switch
          size="small"
          checked={value}
          onChange={async (checked) => {
            try {
              await botApi.update(record.id, { auto_reply_enabled: checked });
              notifySuccess(checked ? '自动回复已开启' : '自动回复已关闭');
              void bots.reload();
            } catch {
              /* client 已统一提示 */
            }
          }}
        />
      ),
    },
    {
      title: '转发到员工群',
      dataIndex: 'relay_enabled',
      width: 130,
      render: (value: boolean, record) =>
        value ? (
          <Tooltip title={`chat_id ${record.relay_target_chat_id ?? '未设置'}`}>
            <Tag color="blue">已开启</Tag>
          </Tooltip>
        ) : (
          <Tag>未开启</Tag>
        ),
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
      width: 340,
      render: (_: unknown, record) => (
        <Space wrap>
          <Button
            size="small"
            icon={<SyncOutlined />}
            loading={busyId === record.id}
            onClick={() => void handleCheck(record)}
          >
            重新校验
          </Button>
          {record.webhook_enabled ? (
            <Button
              size="small"
              icon={<CheckCircleOutlined />}
              loading={busyId === record.id}
              onClick={() => void handleWebhook(record, false)}
            >
              删除 Webhook
            </Button>
          ) : (
            <Button
              size="small"
              icon={<CheckCircleOutlined />}
              loading={busyId === record.id}
              onClick={() => void handleWebhook(record, true)}
            >
              注册 Webhook
            </Button>
          )}
          <Button size="small" onClick={() => setPersonaBot(record)}>
            自动回复资料
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(record)}>
            编辑
          </Button>
          <Popconfirm
            title="删除这个 Bot？"
            description="删除后它的转发规则和自动回复都会失效。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              try {
                const res = await botApi.remove(record.id);
                notifySuccess(res.message || 'Bot 已删除');
                void bots.reload();
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

  return (
    <div>
      <Card
        title="Bot 管理"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} loading={bots.loading} onClick={() => void bots.reload()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建 Bot
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="Token 用 BotFather 给的那串，加密保存后只回掩码（123456...abcd）；新建时会调 getMe 校验并注册 Webhook。"
        />
        {bots.error ? (
          <Alert type="error" showIcon message={`Bot 列表加载失败：${bots.error}`} style={{ marginBottom: 12 }} />
        ) : null}
        <Table<BotOut>
          size="small"
          rowKey="id"
          loading={bots.loading}
          dataSource={bots.data ?? []}
          columns={columns}
          pagination={false}
          scroll={{ x: 1700 }}
          locale={{ emptyText: <Empty description="还没有 Bot，先用 Token 建一个" /> }}
        />
      </Card>

      <BotFormModal
        open={createOpen || Boolean(editing)}
        bot={editing}
        onCancel={() => {
          setCreateOpen(false);
          setEditing(null);
        }}
        onSuccess={() => {
          setCreateOpen(false);
          setEditing(null);
          void bots.reload();
        }}
      />

      <PersonaModal
        bot={personaBot}
        onCancel={() => setPersonaBot(null)}
        onSuccess={() => {
          setPersonaBot(null);
          void bots.reload();
        }}
      />
    </div>
  );
}

interface BotForm {
  name: string;
  token?: string;
  relay_enabled: boolean;
  relay_target_chat_id?: number | null;
  relay_target_kind: RelayTargetKind;
  auto_reply_enabled: boolean;
  persona_text?: string;
  remark?: string;
}

function BotFormModal({
  open,
  bot,
  onCancel,
  onSuccess,
}: {
  open: boolean;
  bot: BotOut | null;
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<BotForm>();
  const [submitting, setSubmitting] = useState(false);

  const handleFinish = async (values: BotForm) => {
    setSubmitting(true);
    try {
      if (bot) {
        await botApi.update(bot.id, {
          name: values.name.trim(),
          // Token 留空 = 不改
          ...(values.token ? { token: values.token.trim() } : {}),
          relay_enabled: values.relay_enabled,
          relay_target_chat_id: values.relay_target_chat_id ?? null,
          relay_target_kind: values.relay_target_kind,
          auto_reply_enabled: values.auto_reply_enabled,
          persona_text: values.persona_text ?? '',
          remark: values.remark ?? '',
        });
        notifySuccess('Bot 已更新');
      } else {
        const payload: BotCreate = {
          name: values.name.trim(),
          token: (values.token ?? '').trim(),
          relay_enabled: values.relay_enabled,
          relay_target_chat_id: values.relay_target_chat_id ?? null,
          relay_target_kind: values.relay_target_kind,
          auto_reply_enabled: values.auto_reply_enabled,
          persona_text: values.persona_text ?? '',
          remark: values.remark ?? '',
        };
        await botApi.create(payload);
        notifySuccess('Bot 已创建，Webhook 已尝试注册');
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
      title={bot ? `编辑 Bot：${bot.name}` : '新建 Bot'}
      onCancel={onCancel}
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
        key={bot?.id ?? 'new'}
        initialValues={{
          name: bot?.name ?? '',
          relay_enabled: bot?.relay_enabled ?? false,
          relay_target_chat_id: bot?.relay_target_chat_id ?? null,
          relay_target_kind: bot?.relay_target_kind ?? 'group',
          auto_reply_enabled: bot?.auto_reply_enabled ?? false,
          persona_text: bot?.persona_text ?? '',
          remark: bot?.remark ?? '',
        }}
      >
        <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入名称' }]}>
          <Input placeholder="例如：客服Bot" allowClear />
        </Form.Item>
        <Form.Item
          label={bot ? 'Token（留空表示不修改）' : 'Token'}
          name="token"
          rules={bot ? [] : [{ required: true, message: '请输入 BotFather 给的 Token' }]}
          extra="形如 123456789:AA...；不会回显明文，只显示掩码。"
        >
          <Input.Password placeholder="123456789:AA..." autoComplete="new-password" />
        </Form.Item>
        <Space size="middle" style={{ display: 'flex' }} align="start">
          <Form.Item label="转发到员工群" name="relay_enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item label="目标类型" name="relay_target_kind">
            <Select style={{ width: 140 }} options={RELAY_TARGET_KIND_OPTIONS} />
          </Form.Item>
          <Form.Item label="员工群 chat_id" name="relay_target_chat_id">
            <InputNumber style={{ width: 200 }} placeholder="-1001234567890" />
          </Form.Item>
        </Space>
        <Form.Item label="自动回复" name="auto_reply_enabled" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item label="自动回复资料 persona_text" name="persona_text">
          <Input.TextArea rows={4} placeholder="这个 Bot 的身份和说话方式，自动回复时喂给模型。" />
        </Form.Item>
        <Form.Item label="备注" name="remark">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

function PersonaModal({
  bot,
  onCancel,
  onSuccess,
}: {
  bot: BotOut | null;
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<{ persona_text: string; auto_reply_enabled: boolean }>();
  const [submitting, setSubmitting] = useState(false);

  const handleFinish = async (values: { persona_text: string; auto_reply_enabled: boolean }) => {
    if (!bot) return;
    setSubmitting(true);
    try {
      await botApi.update(bot.id, {
        persona_text: values.persona_text,
        auto_reply_enabled: values.auto_reply_enabled,
      });
      notifySuccess('自动回复资料已保存');
      onSuccess();
    } catch {
      /* client 已统一提示 */
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={Boolean(bot)}
      title={`自动回复资料：${bot?.name ?? ''}`}
      onCancel={onCancel}
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
        key={bot?.id}
        initialValues={{
          persona_text: bot?.persona_text ?? '',
          auto_reply_enabled: bot?.auto_reply_enabled ?? false,
        }}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="官方 Bot 按这份资料自动回复，对方看到的是 Bot 身份；资料和调用记录分开存放。"
        />
        <Form.Item label="开启自动回复" name="auto_reply_enabled" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item label="资料 persona_text" name="persona_text">
          <Input.TextArea rows={8} placeholder="例如：你是某某公司的客服 Bot，只回答营业时间和地址，其它问题请对方留言。" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
