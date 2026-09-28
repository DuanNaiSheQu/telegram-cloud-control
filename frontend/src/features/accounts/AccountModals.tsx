/**
 * 账号管理页面私有弹窗（新建 / 改分组代理 / 改资料 / 批量操作参数）。
 * 只被 pages/Accounts.tsx 使用；通用交互走 components/ 的 ConfirmModal、AccountLoginWizard 等。
 */
import { useEffect, useState } from 'react';
import { Alert, Form, Input, Modal, Radio, Select, Space, Typography } from 'antd';
import { accountBulkApi, accountApi } from '../../api/endpoints';
import { toast } from '../../utils/feedback';
import type {
  AccountOut,
  BulkAccountRequest,
  BulkAction,
  BulkResultOut,
  GroupOut,
  ProxyOut,
  UserOut,
} from '../../api/types';

// ---------------------------------------------------------------- 新建账号

interface CreateForm {
  phone: string;
  group_id?: string;
  proxy_id?: string;
  remark?: string;
}

export function CreateAccountModal({
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
      toast.success('账号已建档，接着用「登录向导」发验证码');
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
          <Select allowClear placeholder="不选则不分组" options={groups.map((g) => ({ value: g.id, label: g.name }))} />
        </Form.Item>
        <Form.Item label="代理（可选）" name="proxy_id">
          <Select allowClear placeholder="不选则直连" options={proxies.map((p) => ({ value: p.id, label: `${p.name}（${p.endpoint}）` }))} />
        </Form.Item>
        <Form.Item label="备注" name="remark">
          <Input.TextArea rows={2} placeholder="备注（可选）" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

// ---------------------------------------------------------------- 改分组 / 代理

export function EditAccountModal({
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
  const [form] = Form.useForm<{ group_id?: string | null; proxy_id?: string | null; remark?: string }>();
  const [submitting, setSubmitting] = useState(false);

  const handleFinish = async (values: { group_id?: string | null; proxy_id?: string | null; remark?: string }) => {
    if (!account) return;
    setSubmitting(true);
    try {
      await accountApi.update(account.id, {
        group_id: values.group_id ?? null,
        proxy_id: values.proxy_id ?? null,
        remark: values.remark ?? '',
      });
      toast.success('已保存');
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
          <Select allowClear placeholder="清空 = 移出分组" options={groups.map((g) => ({ value: g.id, label: g.name }))} />
        </Form.Item>
        <Form.Item label="代理" name="proxy_id">
          <Select allowClear placeholder="清空 = 直连（不绑定代理）" options={proxies.map((p) => ({ value: p.id, label: `${p.name}（${p.endpoint}）` }))} />
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

// ---------------------------------------------------------------- 改资料

export function ProfileModal({
  account,
  onCancel,
  onSuccess,
}: {
  account: AccountOut | null;
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<{
    first_name?: string;
    last_name?: string;
    bio?: string;
    username?: string;
    photo_url?: string;
  }>();
  const [submitting, setSubmitting] = useState(false);

  const handleFinish = async (values: {
    first_name?: string;
    last_name?: string;
    bio?: string;
    username?: string;
    photo_url?: string;
  }) => {
    if (!account) return;
    // 只提交真正填了的字段：契约里这些字段都可选，回空串有清空 Telegram 资料的风险
    const payload: Record<string, string> = {};
    (['first_name', 'last_name', 'bio', 'username', 'photo_url'] as const).forEach((key) => {
      const value = values[key]?.trim();
      if (value) payload[key] = value;
    });
    if (!Object.keys(payload).length) {
      toast.error('请至少填一项要修改的资料');
      return;
    }
    setSubmitting(true);
    try {
      const res = await accountApi.profile(account.id, payload);
      toast.success(res.message || '已提交改资料任务，等 Worker 执行');
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

// ---------------------------------------------------------------- 批量操作

export interface BulkActionModalProps {
  open: boolean;
  /** 要执行的批量动作；null 时不渲染 */
  action: BulkAction | null;
  /** 当前勾选的账号（scope=selected 时用） */
  selectedIds: string[];
  /** 当前筛选条件（scope=all 时后端会按同条件收敛，仅作提示） */
  filteredTotal: number;
  groups: GroupOut[];
  proxies: ProxyOut[];
  users: UserOut[];
  onCancel: () => void;
  onDone: (result: BulkResultOut | null) => void;
}

const ACTION_LABELS: Record<BulkAction, string> = {
  check: '批量检测',
  'sync-dialogs': '批量同步会话',
  assign: '批量分配',
  group: '批量改分组',
  proxy: '批量改代理',
  status: '批量启停',
  disable: '批量停用',
  enable: '批量启用',
  'release-lease': '批量清除租约',
};

/** 需要额外参数的批量动作 */
const PARAM_ACTIONS: BulkAction[] = ['assign', 'group', 'proxy'];

export function BulkActionModal({
  open,
  action,
  selectedIds,
  filteredTotal,
  groups,
  proxies,
  users,
  onCancel,
  onDone,
}: BulkActionModalProps) {
  const [scope, setScope] = useState<'selected' | 'all'>('selected');
  const [groupId, setGroupId] = useState<string | null>(null);
  const [proxyId, setProxyId] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [mode, setMode] = useState<'assign' | 'unassign'>('assign');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setScope(selectedIds.length ? 'selected' : 'all');
      setGroupId(null);
      setProxyId(null);
      setUserId(null);
      setMode('assign');
    }
  }, [open, selectedIds.length]);

  if (!action) return null;

  const needsParam = PARAM_ACTIONS.includes(action);
  const paramReady = !needsParam || (action === 'group') || (action === 'proxy') || (action === 'assign' && userId);
  const ready = paramReady && (scope === 'selected' ? selectedIds.length > 0 : filteredTotal > 0);

  const handleOk = async () => {
    const payload: BulkAccountRequest = {
      scope,
      account_ids: scope === 'selected' ? selectedIds : null,
    };
    if (action === 'group') payload.group_id = groupId;
    if (action === 'proxy') payload.proxy_id = proxyId;
    if (action === 'assign') {
      payload.user_id = userId ?? undefined;
      payload.mode = mode;
    }
    setSubmitting(true);
    try {
      const result = await accountBulkApi.run(action, payload);
      onDone(result);
    } catch {
      onDone(null);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={ACTION_LABELS[action]}
      onCancel={onCancel}
      onOk={() => void handleOk()}
      okText="执行"
      cancelText="取消"
      confirmLoading={submitting}
      okButtonProps={{ disabled: !ready }}
    >
      <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
        <Form layout="vertical">
          <Form.Item label="作用范围">
            <Radio.Group value={scope} onChange={(event) => setScope(event.target.value)}>
              <Space direction="vertical">
                <Radio value="selected" disabled={!selectedIds.length}>
                  选中的 {selectedIds.length} 个账号
                </Radio>
                <Radio value="all" disabled={!filteredTotal}>
                  当前筛选下的全部账号（约 {filteredTotal} 个）
                </Radio>
              </Space>
            </Radio.Group>
          </Form.Item>

          {action === 'group' ? (
            <Form.Item label="目标分组（清空 = 移出分组）">
              <Select
                allowClear
                placeholder="不选 = 移出分组"
                style={{ width: '100%' }}
                value={groupId ?? undefined}
                onChange={(value) => setGroupId(value ?? null)}
                options={groups.map((g) => ({ value: g.id, label: `${g.name}（${g.account_count}）` }))}
              />
            </Form.Item>
          ) : null}

          {action === 'proxy' ? (
            <Form.Item label="目标代理（清空 = 改为直连）">
              <Select
                allowClear
                placeholder="不选 = 解绑改为直连"
                style={{ width: '100%' }}
                value={proxyId ?? undefined}
                onChange={(value) => setProxyId(value ?? null)}
                options={proxies.map((p) => ({ value: p.id, label: `${p.name}（${p.endpoint}）` }))}
              />
            </Form.Item>
          ) : null}

          {action === 'assign' ? (
            <>
              <Form.Item label="员工" required>
                <Select
                  placeholder="选择要分配给的员工"
                  style={{ width: '100%' }}
                  value={userId ?? undefined}
                  onChange={(value) => setUserId(value ?? null)}
                  options={users.map((u) => ({ value: u.id, label: `${u.display_name || u.username}（${u.username}）` }))}
                />
              </Form.Item>
              <Form.Item label="模式">
                <Radio.Group value={mode} onChange={(event) => setMode(event.target.value)}>
                  <Radio value="assign">分配</Radio>
                  <Radio value="unassign">取消分配</Radio>
                </Radio.Group>
              </Form.Item>
            </>
          ) : null}
        </Form>

        {!ready ? (
          <Alert
            type="warning"
            showIcon
            message={scope === 'selected' ? '请先在列表里勾选账号' : '当前筛选条件下没有账号'}
          />
        ) : null}
        <Typography.Text type="secondary">
          {action === 'check' || action === 'sync-dialogs'
            ? '会为每个账号写一条任务，Worker 认领后执行；单次上限 200，超出会截断。'
            : action === 'disable'
              ? '停用会清掉这些号的租约，Worker 会断开它们；可随时启用恢复。'
              : action === 'release-lease'
                ? '只清租约、不改状态，Worker 会在下轮重新认领。'
                : '结果会逐条返回，执行完成后弹窗展示。'}
        </Typography.Text>
      </div>
    </Modal>
  );
}
