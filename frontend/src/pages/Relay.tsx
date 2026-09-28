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
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { accountApi, botApi, dialogApi, relayApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { RELAY_TARGET_KIND_OPTIONS } from '../constants';
import { formatTime, shortId } from '../utils/format';
import { notifySuccess } from '../utils/feedback';
import type {
  RelayLinkOut,
  RelayRouteCreate,
  RelayRouteOut,
  RelayTargetKind,
} from '../api/types';

export default function Relay() {
  const routes = useAsyncData(() => relayApi.list(), []);
  const bots = useAsyncData(() => botApi.list(), []);
  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }), []);
  const dialogs = useAsyncData(() => dialogApi.list({ page: 1, page_size: 200 }), []);

  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<RelayRouteOut | null>(null);
  const [linkRouteId, setLinkRouteId] = useState<string | null>(null);
  const [linkPage, setLinkPage] = useState(1);
  const [linkPageSize, setLinkPageSize] = useState(20);

  const links = useAsyncData(
    () => relayApi.links({ route_id: linkRouteId, page: linkPage, page_size: linkPageSize }),
    [linkRouteId, linkPage, linkPageSize],
  );

  const routeColumns: ColumnsType<RelayRouteOut> = [
    {
      title: '规则',
      dataIndex: 'name',
      width: 150,
      render: (value: string, record) => value || `规则 ${shortId(record.id, 6)}`,
    },
    {
      title: 'Bot',
      dataIndex: 'bot_name',
      width: 180,
      render: (value: string | null, record) => (
        <Space direction="vertical" size={0}>
          <span>{value || '—'}</span>
          {record.bot_username ? (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              @{record.bot_username}
            </Typography.Text>
          ) : null}
        </Space>
      ),
    },
    {
      title: '员工群 chat_id',
      dataIndex: 'staff_chat_id',
      width: 170,
      render: (value: number, record) => (
        <Space direction="vertical" size={0}>
          <Typography.Text code>{value}</Typography.Text>
          {record.staff_chat_title ? (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {record.staff_chat_title}
            </Typography.Text>
          ) : null}
        </Space>
      ),
    },
    {
      title: '目标类型',
      dataIndex: 'target_kind',
      width: 100,
      render: (value: RelayTargetKind) => (
        <Tag>{value === 'private' ? '私聊' : '群聊'}</Tag>
      ),
    },
    {
      title: '来源过滤',
      key: 'source',
      width: 220,
      render: (_: unknown, record) => (
        <Space direction="vertical" size={0}>
          <span>{record.account_label ? `账号 ${record.account_label}` : '全部账号'}</span>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {record.dialog_title ? `会话 ${record.dialog_title}` : '全部会话'}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '已转发',
      dataIndex: 'relayed_count',
      width: 90,
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
              await relayApi.update(record.id, { enabled: checked });
              notifySuccess(checked ? '规则已启用' : '规则已停用');
              void routes.reload();
            } catch {
              /* client 已统一提示 */
            }
          }}
        />
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
      width: 230,
      render: (_: unknown, record) => (
        <Space>
          <Button size="small" onClick={() => setLinkRouteId(record.id)}>
            看转发记录
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(record)}>
            编辑
          </Button>
          <Popconfirm
            title="删除这条转发规则？"
            description="已转发的记录会保留，但不再继续转发。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              try {
                const res = await relayApi.remove(record.id);
                notifySuccess(res.message || '规则已删除');
                void routes.reload();
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

  const linkColumns: ColumnsType<RelayLinkOut> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string | null) => formatTime(value),
    },
    {
      title: '原消息',
      dataIndex: 'message_id',
      render: (value: string) => (
        <Tooltip title={`原消息 ID：${value}`}>
          <Typography.Text code>{shortId(value, 8)}</Typography.Text>
        </Tooltip>
      ),
    },
    {
      title: '员工群那条',
      dataIndex: 'staff_message_id',
      width: 160,
      render: (value: number) => <Typography.Text code>{value}</Typography.Text>,
    },
    {
      title: '员工群 chat_id',
      dataIndex: 'staff_chat_id',
      width: 170,
      render: (value: number) => <Typography.Text code>{value}</Typography.Text>,
    },
    {
      title: 'Bot',
      dataIndex: 'bot_id',
      width: 130,
      render: (value: string) => <Typography.Text code>{shortId(value, 8)}</Typography.Text>,
    },
    {
      title: '规则',
      dataIndex: 'route_id',
      width: 130,
      render: (value: string | null) => (value ? <Typography.Text code>{shortId(value, 8)}</Typography.Text> : '—'),
    },
  ];

  return (
    <div>
      <Card
        className="section-card"
        title="Bot 转发规则"
        extra={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              loading={routes.loading}
              onClick={() => {
                void routes.reload();
                void bots.reload();
              }}
            >
              刷新
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              disabled={!(bots.data ?? []).length}
              onClick={() => setCreateOpen(true)}
            >
              新建规则
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="新消息入库后写一条 relay_to_staff 任务，用指定 Bot 发到员工群，并带上来源（哪个号、群还是私信、对方是谁）。"
        />
        {!(bots.data ?? []).length ? (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            message="还没有 Bot，先去「Bot 管理」用 BotFather 给的 Token 建一个。"
          />
        ) : null}
        <Table<RelayRouteOut>
          size="small"
          rowKey="id"
          loading={routes.loading}
          dataSource={routes.data ?? []}
          columns={routeColumns}
          pagination={false}
          scroll={{ x: 1500 }}
          locale={{ emptyText: <Empty description="还没有转发规则" /> }}
        />
      </Card>

      <Card
        title="已转发记录"
        extra={
          <Space>
            <Select
              allowClear
              size="small"
              placeholder="全部规则"
              style={{ width: 200 }}
              value={linkRouteId ?? undefined}
              onChange={(value) => {
                setLinkRouteId(value ?? null);
                setLinkPage(1);
              }}
              options={(routes.data ?? []).map((route) => ({
                value: route.id,
                label: route.name || `规则 ${shortId(route.id, 6)}`,
              }))}
            />
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={links.loading}
              onClick={() => void links.reload()}
            >
              刷新
            </Button>
          </Space>
        }
      >
        <Table<RelayLinkOut>
          size="small"
          rowKey="id"
          loading={links.loading}
          dataSource={links.data?.items ?? []}
          columns={linkColumns}
          scroll={{ x: 1100 }}
          locale={{ emptyText: <Empty description="还没有转发记录" /> }}
          pagination={{
            current: linkPage,
            pageSize: linkPageSize,
            total: links.data?.total ?? 0,
            showSizeChanger: true,
            pageSizeOptions: ['20', '50', '100'],
            showTotal: (total) => `共 ${total} 条`,
            onChange: (page, size) => {
              setLinkPage(page);
              setLinkPageSize(size);
            },
          }}
        />
      </Card>

      <RouteFormModal
        open={createOpen || Boolean(editing)}
        route={editing}
        bots={(bots.data ?? []).map((bot) => ({
          value: bot.id,
          label: `${bot.name}${bot.bot_username ? ` (@${bot.bot_username})` : ''}`,
        }))}
        accounts={(accounts.data?.items ?? []).map((item) => ({
          value: item.id,
          label: `${item.phone_masked}${item.username ? ` / ${item.username}` : ''}`,
        }))}
        dialogs={(dialogs.data?.items ?? []).map((item) => ({
          value: item.id,
          label: `${item.title || item.peer_display || item.tg_chat_id}（${
            item.channel === 'bot' ? 'Bot' : '用户号'
          }）`,
        }))}
        onCancel={() => {
          setCreateOpen(false);
          setEditing(null);
        }}
        onSuccess={() => {
          setCreateOpen(false);
          setEditing(null);
          void routes.reload();
        }}
      />
    </div>
  );
}

interface RouteForm {
  name?: string;
  bot_id: string;
  staff_chat_id: number;
  staff_chat_title?: string;
  target_kind: RelayTargetKind;
  account_id?: string | null;
  dialog_id?: string | null;
  enabled: boolean;
  remark?: string;
}

interface Option {
  value: string;
  label: string;
}

function RouteFormModal({
  open,
  route,
  bots,
  accounts,
  dialogs,
  onCancel,
  onSuccess,
}: {
  open: boolean;
  route: RelayRouteOut | null;
  bots: Option[];
  accounts: Option[];
  dialogs: Option[];
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<RouteForm>();
  const [submitting, setSubmitting] = useState(false);

  const handleFinish = async (values: RouteForm) => {
    setSubmitting(true);
    const payload: RelayRouteCreate = {
      name: values.name ?? '',
      bot_id: values.bot_id,
      staff_chat_id: Number(values.staff_chat_id),
      staff_chat_title: values.staff_chat_title ?? '',
      target_kind: values.target_kind,
      account_id: values.account_id || null,
      dialog_id: values.dialog_id || null,
      enabled: values.enabled,
      remark: values.remark ?? '',
    };
    try {
      if (route) {
        await relayApi.update(route.id, payload);
        notifySuccess('规则已更新');
      } else {
        await relayApi.create(payload);
        notifySuccess('规则已创建');
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
      title={route ? '编辑转发规则' : '新建转发规则'}
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
        key={route?.id ?? 'new'}
        initialValues={{
          name: route?.name ?? '',
          bot_id: route?.bot_id,
          staff_chat_id: route?.staff_chat_id,
          staff_chat_title: route?.staff_chat_title ?? '',
          target_kind: route?.target_kind ?? 'group',
          account_id: route?.account_id ?? null,
          dialog_id: route?.dialog_id ?? null,
          enabled: route?.enabled ?? true,
          remark: route?.remark ?? '',
        }}
      >
        <Form.Item label="规则名" name="name">
          <Input placeholder="例如：客服群转发" allowClear />
        </Form.Item>
        <Form.Item label="用哪个 Bot" name="bot_id" rules={[{ required: true, message: '请选择 Bot' }]}>
          <Select placeholder="选择 Bot" options={bots} showSearch optionFilterProp="label" />
        </Form.Item>
        <Space size="middle" style={{ display: 'flex' }} align="start">
          <Form.Item
            label="员工群 chat_id"
            name="staff_chat_id"
            rules={[{ required: true, message: '请填员工群 chat_id' }]}
          >
            <InputNumber style={{ width: 200 }} placeholder="-1001234567890" />
          </Form.Item>
          <Form.Item label="目标类型" name="target_kind">
            <Select style={{ width: 140 }} options={RELAY_TARGET_KIND_OPTIONS} />
          </Form.Item>
        </Space>
        <Form.Item label="员工群名称（备注用）" name="staff_chat_title">
          <Input placeholder="例如：值班-客服群" allowClear />
        </Form.Item>
        <Form.Item label="来源过滤：只转发哪个账号的消息" name="account_id">
          <Select allowClear showSearch optionFilterProp="label" placeholder="不选 = 全部账号" options={accounts} />
        </Form.Item>
        <Form.Item label="来源过滤：只转发哪个会话的消息" name="dialog_id">
          <Select allowClear showSearch optionFilterProp="label" placeholder="不选 = 全部会话" options={dialogs} />
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
