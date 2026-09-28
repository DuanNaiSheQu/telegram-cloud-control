/**
 * 营销中心：素材库 + 批量私信 / 群发 / 素材群发 / 加群 / 退群 / 强拉 / 批量改资料 / 吵群 / 拟人发言 + 批次进度。
 *
 * 每个动作都是「账号范围 + 动作参数」表单，提交后后端按「一 号一任务」入队，
 * 结果弹窗复用 BulkResultModal；执行进度看「批次进度」或任务中心。
 */
import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DeleteOutlined, InboxOutlined, PlusOutlined, ReloadOutlined, RocketOutlined } from '@ant-design/icons';
import BulkResultModal from '../features/accounts/BulkResultModal';
import { PageContainer, StatusBadge } from '../components';
import { campaignApi, groupApi, materialApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { notifySuccess, toast } from '../utils/feedback';
import { formatNumber, formatTime } from '../utils/format';
import type {
  AccountStatus,
  BulkPmRequest,
  BulkResultOut,
  CampaignBatchItem,
  CampaignBatchOut,
  ForceAddRequest,
  GroupBroadcastRequest,
  JoinGroupRequest,
  LeaveGroupRequest,
  MaterialKind,
  MaterialOut,
  MaterialSendRequest,
  PersonaRequest,
  ProfileBulkRequest,
  StormRequest,
  UUID,
} from '../api/types';

type ScopeValue = 'all' | 'group';

interface ScopeState {
  scope: ScopeValue;
  groupId?: UUID | null;
  limit: number;
}

const KIND_COLORS: Record<MaterialKind, string> = {
  text: 'blue',
  photo: 'green',
  video: 'purple',
  document: 'orange',
};

/** 账号范围选择器：all / group:<id>；limit 默认 200 */
function ScopeFields({ value, onChange }: { value: ScopeState; onChange: (next: ScopeState) => void }) {
  const groups = useAsyncData(() => groupApi.list(), [], { immediate: false });
  useEffect(() => {
    void groups.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <Space wrap>
      <Segmented<ScopeValue>
        value={value.scope}
        onChange={(scope) => onChange({ ...value, scope })}
        options={[
          { label: '全部可见账号', value: 'all' },
          { label: '按分组', value: 'group' },
        ]}
      />
      {value.scope === 'group' ? (
        <Select
          style={{ width: 200 }}
          placeholder="选择账号分组"
          value={value.groupId ?? undefined}
          loading={groups.loading}
          onChange={(groupId) => onChange({ ...value, groupId })}
          options={(groups.data ?? []).map((group) => ({ label: group.name, value: group.id }))}
        />
      ) : null}
      <InputNumber
        min={1}
        max={500}
        value={value.limit}
        onChange={(limit) => onChange({ ...value, limit: limit ?? 200 })}
        addonBefore="最多处理"
        addonAfter="个号"
      />
    </Space>
  );
}

function scopePayload(scope: ScopeState): Record<string, unknown> {
  if (scope.scope === 'group' && scope.groupId) {
    return { scope: `group:${scope.groupId}`, account_ids: null, limit: scope.limit };
  }
  return { scope: 'all', account_ids: null, limit: scope.limit };
}

function splitField(value?: unknown): string[] {
  return String(value ?? '')
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

// ---------------------------------------------------------------- 素材库

function MaterialsTab() {
  const materials = useAsyncData(() => materialApi.list({ page: 1, page_size: 100 }), []);
  const [name, setName] = useState('');
  const [text, setText] = useState('');
  const [creating, setCreating] = useState(false);

  const createText = async () => {
    if (!name.trim()) {
      toast.warning('先给素材起个名字');
      return;
    }
    setCreating(true);
    try {
      await materialApi.create({ name: name.trim(), text });
      notifySuccess('文字素材已保存');
      setName('');
      setText('');
      void materials.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setCreating(false);
    }
  };

  const remove = async (material: MaterialOut) => {
    await materialApi.remove(material.id);
    notifySuccess('素材已删除');
    void materials.reload();
  };

  const columns: ColumnsType<MaterialOut> = [
    { title: '名称', dataIndex: 'name', width: 180 },
    {
      title: '类型',
      dataIndex: 'kind',
      width: 90,
      render: (kind: MaterialKind, record) => <Tag color={KIND_COLORS[kind]}>{record.kind_label}</Tag>,
    },
    {
      title: '内容',
      dataIndex: 'text',
      ellipsis: true,
      render: (value: string, record) => value || record.original_name || <span className="tg-muted">—</span>,
    },
    {
      title: '大小',
      dataIndex: 'size_bytes',
      width: 90,
      render: (value: number) => (value ? formatNumber(value) : <span className="tg-muted">—</span>),
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: (value: string) => formatTime(value) },
    {
      title: '操作',
      width: 130,
      render: (_, record) => (
        <Space>
          {record.kind !== 'text' ? (
            <a href={materialApi.downloadUrl(record.id)} target="_blank" rel="noreferrer">
              下载
            </a>
          ) : null}
          <Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => void remove(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
      <Card size="small" title="新建文字素材">
        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder="素材名（内部识别用）"
            value={name}
            onChange={(event) => setName(event.target.value)}
            style={{ width: 240 }}
          />
          <Input.TextArea
            placeholder="要发送的文字（批量私信 / 群发 / 吵群都会用到）"
            value={text}
            onChange={(event) => setText(event.target.value)}
            autoSize={{ minRows: 2, maxRows: 4 }}
          />
          <Button type="primary" icon={<PlusOutlined />} loading={creating} onClick={() => void createText()}>
            保存
          </Button>
        </Space.Compact>
      </Card>
      <Card size="small" title="上传媒体素材（图片 / 视频 / 文件，最大 20MB）">
        <Upload.Dragger
          multiple={false}
          showUploadList={false}
          customRequest={async (options) => {
            const file = options.file as File;
            const baseName = file.name.replace(/\.[^.]+$/, '');
            try {
              await materialApi.upload(baseName, file);
              notifySuccess(`「${baseName}」已上传`);
              void materials.reload();
            } catch {
              /* client 已统一提示 */
            }
          }}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽文件到这里上传</p>
          <p className="ant-upload-hint">素材名取文件名；发送时可在素材群发里配说明文字</p>
        </Upload.Dragger>
      </Card>
      <Table<MaterialOut>
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={materials.data?.items ?? []}
        loading={materials.loading}
        pagination={false}
      />
    </div>
  );
}

// ---------------------------------------------------------------- 素材下拉

function MaterialSelect(props: { value?: string; onChange?: (value: string) => void }) {
  const materials = useAsyncData(() => materialApi.list({ page: 1, page_size: 100 }), []);
  return (
    <Select
      {...props}
      placeholder="选择素材"
      loading={materials.loading}
      options={(materials.data?.items ?? []).map((item) => ({
        label: `${item.name}（${item.kind_label}）`,
        value: item.id,
      }))}
    />
  );
}

// ---------------------------------------------------------------- 批次进度

function BatchesTab() {
  const batches = useAsyncData(() => campaignApi.batches({ page: 1, page_size: 50 }), []);
  const [detail, setDetail] = useState<CampaignBatchOut | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const openDetail = async (batchId: UUID) => {
    setDetailLoading(true);
    try {
      setDetail(await campaignApi.batch(batchId));
    } catch {
      /* client 已统一提示 */
    } finally {
      setDetailLoading(false);
    }
  };

  const cancel = async (batchId: UUID) => {
    const res = await campaignApi.cancelBatch(batchId);
    notifySuccess(res.message);
    void batches.reload();
    await openDetail(batchId);
  };

  const itemColumns: ColumnsType<CampaignBatchItem> = [
    { title: '账号', dataIndex: 'account_label', width: 140 },
    { title: '任务类型', dataIndex: 'type_label', width: 110 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string, record) => (
        <StatusBadge status={value as AccountStatus} label={record.status_label} size="sm" />
      ),
    },
    { title: '尝试', dataIndex: 'attempts', width: 60 },
    {
      title: '失败原因',
      dataIndex: 'error',
      ellipsis: true,
      render: (value: string) => value || <span className="tg-muted">—</span>,
    },
  ];

  const columns: ColumnsType<CampaignBatchOut> = [
    {
      title: '批次',
      dataIndex: 'batch_id',
      width: 220,
      render: (value: UUID) => <span className="tg-mono">{value.slice(0, 8)}…</span>,
    },
    { title: '提交时间', dataIndex: 'created_at', width: 170, render: (value: string) => formatTime(value) },
    { title: '任务数', dataIndex: 'total', width: 80 },
    {
      title: '状态分布',
      dataIndex: 'counts',
      render: (counts: Record<string, number>) => {
        const parts = Object.entries(counts ?? {})
          .filter(([, count]) => count > 0)
          .map(([key, count]) => `${key}=${count}`);
        return parts.length ? (
          <span className="tg-mono tg-muted">{parts.join('  ')}</span>
        ) : (
          <span className="tg-muted">—</span>
        );
      },
    },
    {
      title: '操作',
      width: 160,
      render: (_, record) => (
        <Space>
          <Button size="small" loading={detailLoading} onClick={() => void openDetail(record.batch_id)}>
            详情
          </Button>
          <Button size="small" danger onClick={() => void cancel(record.batch_id)}>
            取消
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
      <Space>
        <Button icon={<ReloadOutlined />} onClick={() => void batches.reload()}>
          刷新
        </Button>
        <Typography.Text type="secondary">执行中的吵群 / 拟人任务会随每轮发言实时更新进度</Typography.Text>
      </Space>
      <Table<CampaignBatchOut>
        size="small"
        rowKey="batch_id"
        columns={columns}
        dataSource={batches.data?.items ?? []}
        loading={batches.loading}
        pagination={{ pageSize: 20, size: 'small', showTotal: (total) => `共 ${total} 批` }}
      />
      {detail ? (
        <Card
          size="small"
          title={`批次 ${detail.batch_id} · ${formatTime(detail.created_at ?? '')} · 共 ${detail.total} 条任务`}
          extra={
            <Button size="small" danger onClick={() => void cancel(detail.batch_id)}>
              取消未完成任务
            </Button>
          }
        >
          <Table<CampaignBatchItem>
            size="small"
            rowKey="task_id"
            columns={itemColumns}
            dataSource={detail.items}
            pagination={{ pageSize: 10, size: 'small' }}
          />
        </Card>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- 动作表单

interface ActionFormProps {
  title: string;
  description: string;
  submit: (payload: Record<string, unknown>) => Promise<BulkResultOut>;
  buildPayload: (scope: ScopeState, values: Record<string, unknown>) => Record<string, unknown>;
  children: React.ReactNode;
}

function ActionTab({ title, description, submit, buildPayload, children }: ActionFormProps) {
  const [scope, setScope] = useState<ScopeState>({ scope: 'all', limit: 200 });
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<BulkResultOut | null>(null);

  const onFinish = async (values: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      setResult(await submit(buildPayload(scope, values)));
    } catch {
      /* client 已统一提示 */
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
      <Alert type="info" showIcon message={title} description={description} />
      <Form form={form} layout="vertical" onFinish={(values) => void onFinish(values)}>
        {children}
        <Form.Item label="账号范围">
          <ScopeFields value={scope} onChange={setScope} />
        </Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" icon={<RocketOutlined />} loading={submitting}>
            提交任务
          </Button>
          <Typography.Text type="secondary">提交后按「一 号一任务」错峰入队，由 Worker 执行</Typography.Text>
        </Space>
      </Form>
      <BulkResultModal open={!!result} result={result} onClose={() => setResult(null)} />
    </div>
  );
}

// ---------------------------------------------------------------- 页面

export default function Campaigns() {
  const tabs = [
    { key: 'materials', label: '素材库', children: <MaterialsTab /> },
    {
      key: 'bulk-pm',
      label: '批量私信',
      children: (
        <ActionTab
          title="批量私信"
          description="一批号各向目标逐个发消息；文本池给多条时按账号顺序分配给不同号，说的话不重样。目标支持 @用户名、手机号或数字用户 ID，一行一个或逗号分隔。"
          buildPayload={(scope, values) => ({
            ...scopePayload(scope),
            targets: splitField(values.targets),
            text: String(values.text ?? '').trim() || null,
            texts: splitField(values.texts).length ? splitField(values.texts) : null,
            naturalize: Boolean(values.naturalize),
            min_interval: Number(values.min_interval ?? 3),
            max_interval: Number(values.max_interval ?? 8),
          })}
          submit={(payload) => campaignApi.bulkPm(payload as unknown as BulkPmRequest)}
        >
          <Form.Item label="私信目标" name="targets" rules={[{ required: true, message: '至少一个目标' }]}>
            <Input.TextArea placeholder="@user1\n@user2\n+8613800138000" autoSize={{ minRows: 3, maxRows: 6 }} />
          </Form.Item>
          <Form.Item label="文本（所有号同一句）" name="text">
            <Input.TextArea placeholder="填了统一文本就忽略文本池" autoSize={{ minRows: 2, maxRows: 4 }} />
          </Form.Item>
          <Form.Item label="文本池（按账号取模分配，每行一条）" name="texts">
            <Input.TextArea placeholder="第一号发这句\n第二号发这句\n…" autoSize={{ minRows: 3, maxRows: 6 }} />
          </Form.Item>
          <Space wrap>
            <Form.Item label="目标间最小间隔（秒）" name="min_interval" initialValue={3}>
              <InputNumber min={1} max={60} />
            </Form.Item>
            <Form.Item label="最大间隔（秒）" name="max_interval" initialValue={8}>
              <InputNumber min={1} max={120} />
            </Form.Item>
            <Form.Item label="口语化微调" name="naturalize" valuePropName="checked" initialValue={false}>
              <Switch />
            </Form.Item>
          </Space>
        </ActionTab>
      ),
    },
    {
      key: 'broadcast',
      label: '群发',
      children: (
        <ActionTab
          title="批量群发"
          description="一批号各向指定群发一条。目标群支持 @用户名、数字群 ID 或已同步的会话 ID。"
          buildPayload={(scope, values) => ({
            ...scopePayload(scope),
            target_group: String(values.target_group ?? '').trim(),
            text: String(values.text ?? '').trim() || null,
            texts: splitField(values.texts).length ? splitField(values.texts) : null,
            naturalize: Boolean(values.naturalize),
          })}
          submit={(payload) => campaignApi.groupBroadcast(payload as unknown as GroupBroadcastRequest)}
        >
          <Form.Item label="目标群" name="target_group" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="@用户名 / 群 ID / 会话 ID" />
          </Form.Item>
          <Form.Item label="文本（所有号同一句）" name="text">
            <Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} />
          </Form.Item>
          <Form.Item label="文本池（按账号取模分配，每行一条）" name="texts">
            <Input.TextArea autoSize={{ minRows: 3, maxRows: 6 }} />
          </Form.Item>
          <Form.Item label="口语化微调" name="naturalize" valuePropName="checked" initialValue={false}>
            <Switch />
          </Form.Item>
        </ActionTab>
      ),
    },
    {
      key: 'material-send',
      label: '素材群发',
      children: (
        <ActionTab
          title="素材群发"
          description="把素材库里的文字或媒体发给目标：填目标群就发到群里；填私信目标则逐个私信。"
          buildPayload={(scope, values) => ({
            ...scopePayload(scope),
            material_id: String(values.material_id ?? ''),
            target_group: String(values.target_group ?? '').trim() || null,
            targets: splitField(values.targets).length ? splitField(values.targets) : null,
            min_interval: Number(values.min_interval ?? 3),
            max_interval: Number(values.max_interval ?? 8),
          })}
          submit={(payload) => campaignApi.materialSend(payload as unknown as MaterialSendRequest)}
        >
          <Form.Item label="素材" name="material_id" rules={[{ required: true, message: '先到素材库建一条' }]}>
            <MaterialSelect />
          </Form.Item>
          <Form.Item label="目标群（二选一）" name="target_group">
            <Input placeholder="@用户名 / 群 ID / 会话 ID" />
          </Form.Item>
          <Form.Item label="私信目标（二选一，每行一个）" name="targets">
            <Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} />
          </Form.Item>
          <Space wrap>
            <Form.Item label="最小间隔（秒）" name="min_interval" initialValue={3}>
              <InputNumber min={1} max={60} />
            </Form.Item>
            <Form.Item label="最大间隔（秒）" name="max_interval" initialValue={8}>
              <InputNumber min={1} max={120} />
            </Form.Item>
          </Space>
        </ActionTab>
      ),
    },
    {
      key: 'join',
      label: '加群',
      children: (
        <ActionTab
          title="批量加群"
          description="一批号加入同一个群：邀请链接（t.me/+...）或 @公开群用户名。已加入的号自动跳过。"
          buildPayload={(scope, values) => ({
            ...scopePayload(scope),
            target: String(values.target ?? '').trim(),
          })}
          submit={(payload) => campaignApi.joinGroup(payload as unknown as JoinGroupRequest)}
        >
          <Form.Item label="邀请链接或公开群" name="target" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="邀请链接 t.me/+xxxx 或 @公开群用户名" />
          </Form.Item>
        </ActionTab>
      ),
    },
    {
      key: 'leave',
      label: '退群',
      children: (
        <ActionTab
          title="批量退群"
          description="一批号退出同一个群。支持 @用户名、数字群 ID 或会话 ID。"
          buildPayload={(scope, values) => ({
            ...scopePayload(scope),
            target: String(values.target ?? '').trim(),
            delete_history: values.delete_history !== false,
          })}
          submit={(payload) => campaignApi.leaveGroup(payload as unknown as LeaveGroupRequest)}
        >
          <Form.Item label="要退的群" name="target" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="@用户名 / 群 ID / 会话 ID" />
          </Form.Item>
          <Form.Item label="退出后删除该会话记录" name="delete_history" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </ActionTab>
      ),
    },
    {
      key: 'force-add',
      label: '强拉进群',
      children: (
        <ActionTab
          title="强拉进群"
          description="把成员拉进目标群。执行号必须是该群管理员（普通群需成员为执行号的联系人）。成员：@用户名、手机号或数字用户 ID，每行一个，最多 50。"
          buildPayload={(scope, values) => ({
            ...scopePayload(scope),
            group: String(values.group ?? '').trim(),
            members: splitField(values.members),
          })}
          submit={(payload) => campaignApi.forceAdd(payload as unknown as ForceAddRequest)}
        >
          <Form.Item label="目标群" name="group" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="@用户名 / 群 ID / 会话 ID" />
          </Form.Item>
          <Form.Item label="要拉进的成员（每行一个）" name="members" rules={[{ required: true, message: '至少一个成员' }]}>
            <Input.TextArea placeholder="@user1\n@user2" autoSize={{ minRows: 3, maxRows: 8 }} />
          </Form.Item>
        </ActionTab>
      ),
    },
    {
      key: 'profile',
      label: '批量改资料',
      children: (
        <ActionTab
          title="批量改资料"
          description="一批号统一改名 / 简介 / 用户名 / 头像。留空的字段不改。"
          buildPayload={(scope, values) => ({
            ...scopePayload(scope),
            profile: {
              first_name: String(values.first_name ?? '').trim() || null,
              last_name: String(values.last_name ?? '').trim() || null,
              bio: String(values.bio ?? '').trim() || null,
              username: String(values.username ?? '').trim() || null,
              photo_url: String(values.photo_url ?? '').trim() || null,
            },
          })}
          submit={(payload) => campaignApi.profileUpdate(payload as unknown as ProfileBulkRequest)}
        >
          <Space wrap>
            <Form.Item label="名字" name="first_name">
              <Input placeholder="First name" />
            </Form.Item>
            <Form.Item label="姓氏" name="last_name">
              <Input placeholder="Last name" />
            </Form.Item>
            <Form.Item label="用户名（@ 后面部分）" name="username">
              <Input placeholder="用户名（不含 @）" />
            </Form.Item>
          </Space>
          <Form.Item label="简介" name="bio">
            <Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} />
          </Form.Item>
          <Form.Item label="头像图片地址" name="photo_url">
            <Input placeholder="https://…/avatar.jpg" />
          </Form.Item>
        </ActionTab>
      ),
    },
    {
      key: 'storm',
      label: '吵群',
      children: (
        <ActionTab
          title="吵群"
          description="一批号在同一个群里按随机间隔轮流发文本池里的话（每轮随机挑一句），可配置每轮回复群内最近消息的概率。总时长 = 轮数 × 最大间隔，不能超过 25 分钟。"
          buildPayload={(scope, values) => ({
            ...scopePayload(scope),
            group: String(values.group ?? '').trim() || null,
            rounds: Number(values.rounds ?? 5),
            min_interval: Number(values.min_interval ?? 8),
            max_interval: Number(values.max_interval ?? 30),
            texts: splitField(values.texts),
            reply_probability: Number(values.reply_probability ?? 0),
          })}
          submit={(payload) => campaignApi.storm(payload as unknown as StormRequest)}
        >
          <Form.Item label="目标群" name="group" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="@用户名 或 群 ID" />
          </Form.Item>
          <Form.Item label="文本池（每轮随机挑一句，每行一条）" name="texts" rules={[{ required: true, message: '至少一句' }]}>
            <Input.TextArea placeholder="这句不错\n顶一下\n有道理" autoSize={{ minRows: 4, maxRows: 8 }} />
          </Form.Item>
          <Space wrap>
            <Form.Item label="每个号发几轮" name="rounds" initialValue={5}>
              <InputNumber min={1} max={20} />
            </Form.Item>
            <Form.Item label="最小间隔（秒）" name="min_interval" initialValue={8}>
              <InputNumber min={3} max={120} />
            </Form.Item>
            <Form.Item label="最大间隔（秒）" name="max_interval" initialValue={30}>
              <InputNumber min={3} max={120} />
            </Form.Item>
            <Form.Item label="回复群内最近消息的概率" name="reply_probability" initialValue={0}>
              <InputNumber min={0} max={1} step={0.1} />
            </Form.Item>
          </Space>
        </ActionTab>
      ),
    },
    {
      key: 'persona',
      label: '拟人发言',
      children: (
        <ActionTab
          title="拟人发言"
          description="一批号按人设连续发言：每轮看群里最近消息，用 AI 生成符合人设的话；AI 未配置或失败时自动退回备用文本池。"
          buildPayload={(scope, values) => ({
            ...scopePayload(scope),
            group: String(values.group ?? '').trim() || null,
            persona: String(values.persona ?? '').trim(),
            topic: String(values.topic ?? '').trim() || null,
            use_ai: values.use_ai !== false,
            texts: splitField(values.texts).length ? splitField(values.texts) : null,
            rounds: Number(values.rounds ?? 5),
            min_interval: Number(values.min_interval ?? 10),
            max_interval: Number(values.max_interval ?? 40),
          })}
          submit={(payload) => campaignApi.persona(payload as unknown as PersonaRequest)}
        >
          <Form.Item label="目标群" name="group" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="@用户名 或 群 ID" />
          </Form.Item>
          <Form.Item label="人设（给 AI 的角色设定）" name="persona" rules={[{ required: true, message: '必填' }]}>
            <Input.TextArea
              placeholder="例：你是 25 岁的数码爱好者，说话随意、爱用短句和网络词，偶尔吐槽。"
              autoSize={{ minRows: 2, maxRows: 4 }}
            />
          </Form.Item>
          <Form.Item label="话题（可选）" name="topic">
            <Input placeholder="不给就看群里在聊什么" />
          </Form.Item>
          <Form.Item label="AI 不可用时的备用文本池（每行一条）" name="texts">
            <Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} />
          </Form.Item>
          <Space wrap>
            <Form.Item label="使用 AI 生成" name="use_ai" valuePropName="checked" initialValue={true}>
              <Switch />
            </Form.Item>
            <Form.Item label="每个号发几轮" name="rounds" initialValue={5}>
              <InputNumber min={1} max={20} />
            </Form.Item>
            <Form.Item label="最小间隔（秒）" name="min_interval" initialValue={10}>
              <InputNumber min={3} max={120} />
            </Form.Item>
            <Form.Item label="最大间隔（秒）" name="max_interval" initialValue={40}>
              <InputNumber min={3} max={120} />
            </Form.Item>
          </Space>
        </ActionTab>
      ),
    },
    { key: 'batches', label: '批次进度', children: <BatchesTab /> },
  ];

  return (
    <PageContainer
      title="营销中心"
      description="批量私信 / 群发 / 素材群发 / 加群退群 / 强拉 / 批量改资料 / 吵群 / 拟人发言。任务按「一 号一任务」入队，进度在批次页查看。"
    >
      <Tabs defaultActiveKey="materials" items={tabs} />
    </PageContainer>
  );
}
