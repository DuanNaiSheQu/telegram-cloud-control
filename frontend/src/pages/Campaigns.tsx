/**
 * 营销中心：素材库 + 批量私信 / 群发 / 素材群发 / 加群 / 退群 / 强拉 / 批量改资料 / 吵群 / 拟人发言 + 批次进度。
 *
 * 每个动作都是「账号范围 + 动作参数」表单，提交后后端按「一 号一任务」入队，
 * 结果弹窗复用 BulkResultModal；执行进度看「批次进度」或任务中心。
 */
import { useEffect, useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
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
  Tag,
  Typography,
  Upload,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  DeleteOutlined,
  InboxOutlined,
  PlusOutlined,
  ReloadOutlined,
  RocketOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import BulkResultModal from '../features/accounts/BulkResultModal';
import AccountPickerModal from '../components/AccountPickerModal';
import MaterialThumb from '../features/materials/MaterialThumb';
import MaterialPicker from '../features/materials/MaterialSelect';
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

type ScopeValue = 'all' | 'group' | 'selected';

interface ScopeState {
  scope: ScopeValue;
  groupId?: UUID | null;
  /** scope=selected 时手动勾选的账号 id */
  ids?: string[];
  limit: number;
}

const KIND_COLORS: Record<MaterialKind, string> = {
  text: 'blue',
  photo: 'green',
  video: 'purple',
  document: 'orange',
};

/** 账号范围选择器：all / group:<id>；limit 默认 200
 *
 * 注意：提交时后端只保留「能承接营销动作」的号 —— 冻结 / 失效 / 停用的号会被自动滤掉
 *（它们写操作必被 Telegram 拒绝），所以勾了 10 个可能只排出 9 条任务。
 */
function ScopeFields({ value, onChange }: { value: ScopeState; onChange: (next: ScopeState) => void }) {
  const groups = useAsyncData(() => groupApi.list(), [], { immediate: false });
  const [pickerOpen, setPickerOpen] = useState(false);
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
          { label: '手动选择', value: 'selected' },
        ]}
      />
      {value.scope === 'selected' ? (
        <>
          <Button size="middle" icon={<TeamOutlined />} onClick={() => setPickerOpen(true)}>
            选择账号{value.ids?.length ? `（已选 ${value.ids.length}）` : ''}
          </Button>
          <AccountPickerModal
            open={pickerOpen}
            title="选择要执行本次任务的账号"
            value={value.ids ?? []}
            onCancel={() => setPickerOpen(false)}
            onSubmit={async (ids) => {
              onChange({ ...value, ids });
              setPickerOpen(false);
            }}
          />
        </>
      ) : null}
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

/** 可选素材选择：把素材库里的图片/视频/文档配在文本一起发（批量私信 / 群发共用） */
function MaterialPickField({ value, onChange }: { value?: string | null; onChange?: (next: string | null) => void }) {
  const materials = useAsyncData(() => materialApi.list({ page: 1, page_size: 100 }), [], { immediate: false });
  useEffect(() => {
    void materials.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <Form.Item
      label="附带素材（可选）"
      tooltip="选了素材就按素材发：图片/视频/文档带配文，文本作为配文一起发；留空则只发文本"
    >
      <Select
        allowClear
        style={{ width: 320 }}
        placeholder="不附带素材，只发文本"
        value={value ?? undefined}
        loading={materials.loading}
        onChange={(next) => onChange?.(next ?? null)}
        options={(materials.data?.items ?? []).map((item) => ({
          value: item.id,
          label: `[${item.kind_label ?? item.kind}] ${item.name}`,
        }))}
      />
    </Form.Item>
  );
}

function scopePayload(scope: ScopeState): Record<string, unknown> {
  if (scope.scope === 'group' && scope.groupId) {
    return { scope: `group:${scope.groupId}`, account_ids: null, limit: scope.limit };
  }
  if (scope.scope === 'selected') {
    // 手动挑号：直接把 id 列表交给后端（后端按 scope=selected 校验可见性）
    return { scope: 'selected', account_ids: scope.ids ?? [], limit: scope.limit };
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
    {
      title: '预览',
      dataIndex: 'id',
      width: 72,
      render: (_: string, record) => (
        <MaterialThumb materialId={record.id} kind={record.kind} alt={record.name} />
      ),
    },
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
            placeholder="素材名（便于识别，例如：八月活动话术）"
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
      <Form form={form} layout="vertical" className="tg-action-form" onFinish={(values) => void onFinish(values)}>
        {children}
        <Form.Item label="账号范围" className="tg-submit-bar">
        <Typography.Text type="secondary" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
          冻结 / 失效 / 停用的号会自动跳过（它们发不出去消息）；检测 / 申诉解封 / 官方养号不受此限制。
        </Typography.Text>
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
  const { section } = useParams<{ section: string }>();
  const sections = [
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
            dispatch: String(values.dispatch ?? 'each'),
            material_id: (values.material_id as string | undefined) ?? null,
          })}
          submit={(payload) => campaignApi.bulkPm(payload as unknown as BulkPmRequest)}
        >
          <div className="tg-form-group-title">内容：发什么、发给谁</div>
          <Form.Item label="私信目标" name="targets" rules={[{ required: true, message: '至少一个目标' }]}>
            <Input.TextArea placeholder="@user1\n@user2\n+12025550143" autoSize={{ minRows: 3, maxRows: 6 }} style={{ maxWidth: 820 }} />
          </Form.Item>
          <Form.Item label="文本（所有号同一句）" name="text">
            <Input.TextArea placeholder="填了统一文本就忽略文本池" autoSize={{ minRows: 2, maxRows: 4 }} style={{ maxWidth: 820 }} />
          </Form.Item>
          <Form.Item label="文本池（按账号取模分配，每行一条）" name="texts">
            <Input.TextArea placeholder="第一号发这句\n第二号发这句\n…" autoSize={{ minRows: 3, maxRows: 6 }} style={{ maxWidth: 820 }} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, next) => prev.material_id !== next.material_id}>
            {({ getFieldValue, setFieldValue }) => (
              <MaterialPickField
                value={getFieldValue('material_id')}
                onChange={(next) => setFieldValue('material_id', next)}
              />
            )}
          </Form.Item>
          {/* 节奏与配额：什么时候发、发多快、一天发多少 */}
          <div className="tg-form-group-title">节奏与配额</div>
          <div className="tg-form-grid">
            <Form.Item label="目标间最小间隔（秒）" name="min_interval" initialValue={3}>
              <InputNumber min={1} max={60} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="最大间隔（秒）" name="max_interval" initialValue={8}>
              <InputNumber min={1} max={120} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              label="发送时间窗（定时）"
              name="send_window"
              tooltip="只在这个时间段内发；不在窗内会自动顺延到窗口开始，不用手动掐点。留空 = 不限"
            >
              <Input placeholder="09:00-23:00（留空 = 不限）" allowClear />
            </Form.Item>
            <Form.Item
              label="每号每日配额（定量）"
              name="daily_quota"
              tooltip="每个号每天最多发多少条，超了自动顺延到次日。0 = 不限"
            >
              <InputNumber min={0} max={2000} style={{ width: '100%' }} placeholder="0 = 不限" />
            </Form.Item>
            <Form.Item
              label="口语化微调"
              name="naturalize"
              valuePropName="checked"
              initialValue={false}
              tooltip="在文本里做轻微改写（同义替换、标点变化），让不同号发出去的话不完全一样"
            >
              <Switch />
            </Form.Item>
          </div>
          <div className="tg-form-group-title">执行方式</div>
          <div className="tg-form-grid">
            <Form.Item
              label="分发方式"
              name="dispatch"
              initialValue="each"
            tooltip="轮询分配：目标按账号轮流切分，一个目标只由一个号处理——多号并行分摊，互不重复打扰"
          >
            <Segmented
              options={[
                { label: '每个号都发一遍', value: 'each' },
                { label: '按账号轮询分配目标', value: 'round_robin' },
              ]}
            />
            </Form.Item>
            <Form.Item
              label="无号时自动补号"
              name="auto_supply"
              valuePropName="checked"
              tooltip="可用的号不够承担这批目标时，自动从号池补状态正常的号；补进来的号同样受配额与节流约束"
            >
              <Switch />
            </Form.Item>
          </div>
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
            dispatch: String(values.dispatch ?? 'each'),
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
          <Form.Item
            label="分发方式"
            name="dispatch"
            initialValue="each"
            tooltip="轮询分配：目标列表按账号轮流切分，多号并行分摊，互不重复"
          >
            <Segmented
              options={[
                { label: '每个号都发一遍', value: 'each' },
                { label: '按账号轮询分配目标', value: 'round_robin' },
              ]}
            />
          </Form.Item>
        </ActionTab>
      ),
    },
    {
      key: 'join',
      label: '加群',
      children: (
        <ActionTab
          title="批量加群"
          description="一批号加入一个或多个群：邀请链接（t.me/+...）或 @公开群用户名，一行一个。已加入的自动跳过；群多时可选「按账号轮询分配」，让每个号分头进不同的群。"
          buildPayload={(scope, values) => ({
            ...scopePayload(scope),
            targets: splitField(values.targets),
            dispatch: String(values.dispatch ?? 'each'),
          })}
          submit={(payload) => campaignApi.joinGroup(payload as unknown as JoinGroupRequest)}
        >
          <Form.Item
            label="邀请链接或公开群（一行一个，可批量）"
            name="targets"
            rules={[{ required: true, message: '至少填一个群' }]}
          >
            <Input.TextArea
              placeholder={'t.me/+AbCdEfGh1234\n@public_group\nt.me/another_group'}
              autoSize={{ minRows: 3, maxRows: 10 }}
            />
          </Form.Item>
          <Form.Item
            label="分发方式"
            name="dispatch"
            initialValue="each"
            tooltip="轮询分配：群按账号轮流切分，一个群只由一个号去加——避免所有号同时挤进同一个群"
          >
            <Segmented
              options={[
                { label: '每个号都加全部群', value: 'each' },
                { label: '按账号轮询分配群', value: 'round_robin' },
              ]}
            />
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
          description="一批号退出一个或多个群，一行一个。支持 @用户名、数字群 ID 或会话 ID；群多时可选「按账号轮询分配」，让每个号分头退不同的群。"
          buildPayload={(scope, values) => ({
            ...scopePayload(scope),
            targets: splitField(values.targets),
            delete_history: values.delete_history !== false,
            dispatch: String(values.dispatch ?? 'each'),
          })}
          submit={(payload) => campaignApi.leaveGroup(payload as unknown as LeaveGroupRequest)}
        >
          <Form.Item label="要退的群（一行一个，可批量）" name="targets" rules={[{ required: true, message: '至少一个群' }]}>
            <Input.TextArea placeholder={'@group_a\n-1001234567890\nt.me/group_c'} autoSize={{ minRows: 3, maxRows: 10 }} />
          </Form.Item>
          <Form.Item
            label="分发方式"
            name="dispatch"
            initialValue="each"
            tooltip="轮询分配：群按账号轮流切分，一个群只由一个号去退"
          >
            <Segmented
              options={[
                { label: '每个号都退全部群', value: 'each' },
                { label: '按账号轮询分配群', value: 'round_robin' },
              ]}
            />
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
          description="把成员拉进一个或多个目标群。执行号必须是这些群的管理员（普通群需成员为执行号的联系人）。成员：@用户名、手机号或数字用户 ID，每行一个，最多 50。"
          buildPayload={(scope, values) => ({
            ...scopePayload(scope),
            groups: splitField(values.groups),
            members: splitField(values.members),
            dispatch: String(values.dispatch ?? 'each'),
          })}
          submit={(payload) => campaignApi.forceAdd(payload as unknown as ForceAddRequest)}
        >
          <Form.Item label="目标群（一行一个，可批量）" name="groups" rules={[{ required: true, message: '至少一个群' }]}>
            <Input.TextArea placeholder={'@group_a\n-1001234567890'} autoSize={{ minRows: 2, maxRows: 8 }} />
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
          description="一批号改名 / 简介 / 用户名 / 头像。文字框里写一行=所有号统一改成它，写多行=当成候选池，每个号拿不同的值（避免一批号资料完全一样）。留空的字段不改。"
          buildPayload={(scope, values) => {
            // 一行 = 统一值；多行 = 候选池（按号顺序轮流取 或 随机取）
            const nameLines = splitField(values.first_name);
            const lastLines = splitField(values.last_name);
            const bioLines = splitField(values.bio);
            const one = (lines: string[]) => (lines.length === 1 ? lines[0] : null);
            return {
              ...scopePayload(scope),
              profile: {
                first_name: one(nameLines),
                last_name: one(lastLines),
                bio: one(bioLines),
                username: String(values.username ?? '').trim() || null,
                photo_url: String(values.photo_url ?? '').trim() || null,
                photo_material_id: (values.photo_material_id as string | undefined) ?? null,
              },
              first_name_pool: nameLines.length > 1 ? nameLines : null,
              last_name_pool: lastLines.length > 1 ? lastLines : null,
              bio_pool: bioLines.length > 1 ? bioLines : null,
              username_prefix: String(values.username_prefix ?? '').trim() || null,
              username_random_digits: Number(values.username_random_digits ?? 4),
              assign_mode: String(values.assign_mode ?? 'sequence'),
            };
          }}
          submit={(payload) => campaignApi.profileUpdate(payload as unknown as ProfileBulkRequest)}
        >
          <Space wrap align="start">
            <Form.Item label="名字（多行=候选池）" name="first_name">
              <Input.TextArea placeholder={'David\nAlex\n小林'} autoSize={{ minRows: 2, maxRows: 6 }} style={{ width: 200 }} />
            </Form.Item>
            <Form.Item label="姓氏（多行=候选池）" name="last_name">
              <Input.TextArea placeholder={'Chen\nWang\nLi'} autoSize={{ minRows: 2, maxRows: 6 }} style={{ width: 200 }} />
            </Form.Item>
            <Form.Item
              label="固定用户名（@ 后面部分）"
              name="username"
              tooltip="直接填用户名即可；带 @ 或 t.me 链接会被自动清洗。规则：5-32 位，字母/数字/下划线，以字母开头"
            >
              <Input placeholder="例如 woieduanai（@ 会自动去掉）" style={{ width: 240 }} />
            </Form.Item>
          </Space>
          <Form.Item label="简介（多行=候选池）" name="bio">
            <Input.TextArea
              placeholder={'第一句简介\n第二句简介\n第三句简介'}
              autoSize={{ minRows: 3, maxRows: 8 }}
            />
          </Form.Item>
          <Space wrap align="start">
            <Form.Item
              label="用户名前缀（推荐）"
              name="username_prefix"
              tooltip="用户名全局唯一，批量时用「前缀 + 随机数字」，每个号自动生成不撞名"
            >
              <Input placeholder="例如 user_" style={{ width: 160 }} />
            </Form.Item>
            <Form.Item label="随机数字位数" name="username_random_digits" initialValue={4}>
              <InputNumber min={2} max={8} style={{ width: 120 }} />
            </Form.Item>
            <Form.Item
              label="池化取值方式"
              name="assign_mode"
              initialValue="sequence"
              tooltip="按号顺序：同批号轮流取池里的值，互不重复；随机：每个号随机取一个"
            >
              <Segmented
                options={[
                  { label: '按号顺序', value: 'sequence' },
                  { label: '随机', value: 'random' },
                ]}
              />
            </Form.Item>
          </Space>
          <Form.Item
            label="头像（推荐从素材库选）"
            name="photo_material_id"
            tooltip="直接选素材库里的图片；也可以改下面的地址字段，二选一"
          >
            <MaterialPicker kinds={['photo']} placeholder="从素材库选一张图片（可选）" />
          </Form.Item>
          <Form.Item label="或填头像图片地址" name="photo_url">
            <Input placeholder="https://…/avatar.jpg" style={{ maxWidth: 420 }} />
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

  const navigate = useNavigate();
  const current = sections.find((item) => item.key === section);
  if (section && !current) return <Navigate to="/campaigns/materials" replace />;
  const active = current ?? sections[0];

  return (
    <PageContainer
      title={active.label}
      description="批量运营：提交后按「一 号一任务」错峰入队，由 Worker 执行；进度与取消在「批次进度」页。左侧「营销中心」子菜单可切换功能。"
      actions={
        <Select
          size="small"
          style={{ width: 176 }}
          value={active.key}
          onChange={(key) => navigate(`/campaigns/${key}`)}
          options={sections.map((item) => ({ value: item.key, label: item.label }))}
          aria-label="切换营销中心功能"
        />
      }
    >
      {active.children}
    </PageContainer>
  );
}
