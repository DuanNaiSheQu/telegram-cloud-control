/**
 * BotFormModal —— 新建 / 编辑 Bot。
 * - 新建时 Token 必填，编辑时留空 = 不改；
 * - 假 Token / 被撤销 Token：后端 400 中文原因（「Telegram 拒绝了该 Token（401）…」）
 *   展示在表单内 Alert，弹窗不关、页面不崩；
 * - Token 安全提示：加密保存、只回掩码、只在服务端解密。
 */
import { useState } from 'react';
import { Alert, Form, Input, InputNumber, Modal, Select, Space, Switch } from 'antd';
import { botApi } from '../../api/endpoints';
import { ApiError } from '../../api/client';
import { RELAY_TARGET_KIND_OPTIONS } from '../../constants';
import { notifySuccess } from '../../utils/feedback';
import type { BotCreate, BotOut, RelayTargetKind } from '../../api/types';
import { setBotHealthCache } from './useBotHealth';

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

export function BotFormModal({
  open,
  bot,
  onCancel,
  onSuccess,
}: {
  open: boolean;
  bot: BotOut | null;
  onCancel: () => void;
  onSuccess: (botId?: string) => void;
}) {
  const [form] = Form.useForm<BotForm>();
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const handleFinish = async (values: BotForm) => {
    setSubmitting(true);
    setFormError(null);
    try {
      if (bot) {
        const updated = await botApi.update(bot.id, {
          name: values.name.trim(),
          // Token 留空 = 不改
          ...(values.token?.trim() ? { token: values.token.trim() } : {}),
          relay_enabled: values.relay_enabled,
          relay_target_chat_id: values.relay_target_chat_id ?? null,
          relay_target_kind: values.relay_target_kind,
          auto_reply_enabled: values.auto_reply_enabled,
          persona_text: values.persona_text ?? '',
          remark: values.remark ?? '',
        });
        setBotHealthCache(bot.id, 'ok');
        notifySuccess('Bot 已更新');
        onSuccess(updated.id);
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
        const created = await botApi.create(payload);
        setBotHealthCache(created.id, 'ok');
        notifySuccess('Bot 已创建（Webhook 已尝试注册）');
        onSuccess(created.id);
      }
    } catch (err) {
      // 后端 400/409 的中文原因直接展示在表单里，弹窗保持打开
      setFormError(err instanceof ApiError ? err.friendlyMessage : '保存失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={bot ? `编辑 Bot：${bot.name}` : '新建 Bot'}
      onCancel={onCancel}
      okText={bot ? '保存' : '创建'}
      cancelText="取消"
      confirmLoading={submitting}
      width={600}
      onOk={() => form.submit()}
    >
      {formError ? (
        <Alert
          type="error"
          showIcon
          closable
          onClose={() => setFormError(null)}
          message="保存失败"
          description={formError}
          style={{ marginBottom: 'var(--tg-space-xl)' }}
        />
      ) : null}

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 'var(--tg-space-xl)' }}
        message="Token 安全提示"
        description="Token 用 BotFather 给的那串，加密保存后接口只回掩码；解密只在服务端进行，前端拿不到明文。新建时会先 getMe 校验，再尝试注册 Webhook。"
      />

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
          extra="形如 123456789:AA...；换 Token 会重新 getMe 校验，失败原因直接显示在本弹窗。"
        >
          <Input.Password placeholder="123456789:AA..." autoComplete="new-password" />
        </Form.Item>
        <Form.Item label="转发到员工群" name="relay_enabled" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Space size="middle" style={{ display: 'flex', width: '100%' }} align="start">
          <Form.Item label="目标类型" name="relay_target_kind" style={{ flex: '0 0 160px' }}>
            <Select options={RELAY_TARGET_KIND_OPTIONS} />
          </Form.Item>
          <Form.Item label="员工群 chat_id" name="relay_target_chat_id" style={{ flex: 1 }}>
            <InputNumber style={{ width: '100%' }} placeholder="-1001234567890" />
          </Form.Item>
        </Space>
        <Form.Item
          label="自动回复"
          name="auto_reply_enabled"
          valuePropName="checked"
          extra="开启后 Bot 私聊按 persona 资料自动回复；资料可在列表「自动回复资料」里编辑。"
        >
          <Switch />
        </Form.Item>
        <Form.Item label="自动回复资料 persona_text" name="persona_text">
          <Input.TextArea rows={4} maxLength={2000} showCount placeholder="这个 Bot 的身份和说话方式，自动回复时喂给模型（选填）。" />
        </Form.Item>
        <Form.Item label="备注" name="remark">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
