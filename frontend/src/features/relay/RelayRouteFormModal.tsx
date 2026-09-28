/**
 * RelayRouteFormModal —— 新建 / 编辑转发规则。
 * 表单内带「用 Bot 发一条测试消息」按钮：先用当前填写的 bot_id + staff_chat_id
 * 打 POST /api/relays/test（无需先保存规则），失败原因在测试弹窗内中文展示。
 */
import { useState } from 'react';
import { Button, Form, Input, InputNumber, Modal, Select, Space, Switch } from 'antd';
import { ExperimentOutlined } from '@ant-design/icons';
import { relayApi } from '../../api/endpoints';
import { RELAY_TARGET_KIND_OPTIONS } from '../../constants';
import { notifySuccess } from '../../utils/feedback';
import type { RelayRouteCreate, RelayRouteOut, RelayTargetKind } from '../../api/types';
import { TestMessageModal } from './TestMessageModal';
import { botLabel } from './types';

export interface RouteOption {
  value: string;
  label: string;
  /** 显示名（测试弹窗提示用） */
  name?: string;
  username?: string;
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

export function RelayRouteFormModal({
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
  bots: RouteOption[];
  accounts: RouteOption[];
  dialogs: RouteOption[];
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<RouteForm>();
  const [submitting, setSubmitting] = useState(false);
  const [testParams, setTestParams] = useState<{
    botId?: string;
    chatId?: number;
    label?: string;
  } | null>(null);

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
        notifySuccess('转发规则已更新');
      } else {
        await relayApi.create(payload);
        notifySuccess('转发规则已创建');
      }
      onSuccess();
    } catch {
      /* client 已统一中文提示 */
    } finally {
      setSubmitting(false);
    }
  };

  const openTest = () => {
    const botId = form.getFieldValue('bot_id') as string | undefined;
    const chatId = form.getFieldValue('staff_chat_id') as number | undefined;
    const bot = bots.find((item) => item.value === botId);
    setTestParams({
      botId,
      chatId,
      label: bot ? botLabel(bot.name, bot.username) : route?.bot_name ?? undefined,
    });
  };

  return (
    <>
      <Modal
        open={open}
        title={route ? '编辑转发规则' : '新建转发规则'}
        onCancel={onCancel}
        width={600}
        okText={route ? '保存' : '创建'}
        cancelText="取消"
        confirmLoading={submitting}
        onOk={() => form.submit()}
        footer={(_, { OkBtn, CancelBtn }) => (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 'var(--tg-space-md)',
            }}
          >
            <Button icon={<ExperimentOutlined />} onClick={openTest}>
              用 Bot 发一条测试消息
            </Button>
            <Space>
              <CancelBtn />
              <OkBtn />
            </Space>
          </div>
        )}
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
          <Form.Item
            label="员工群 chat_id"
            name="staff_chat_id"
            rules={[{ required: true, message: '请填写员工群 chat_id' }]}
            extra="转发的消息由所选 Bot 发到这个 chat（群或私聊）。"
          >
            <InputNumber style={{ width: '100%' }} placeholder="-1001234567890" />
          </Form.Item>
          <Form.Item label="员工群名称（备注用）" name="staff_chat_title">
            <Input placeholder="例如：值班-客服群" allowClear />
          </Form.Item>
          <Form.Item label="目标类型" name="target_kind" rules={[{ required: true, message: '请选择目标类型' }]}>
            <Select options={RELAY_TARGET_KIND_OPTIONS} />
          </Form.Item>
          <Form.Item label="来源过滤：只转发哪个账号的消息" name="account_id">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="不选 = 全部账号"
              options={accounts}
            />
          </Form.Item>
          <Form.Item label="来源过滤：只转发哪个会话的消息" name="dialog_id">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="不选 = 全部会话"
              options={dialogs}
            />
          </Form.Item>
          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item label="备注" name="remark">
            <Input.TextArea rows={2} placeholder="这条规则是干什么用的（选填）" />
          </Form.Item>
        </Form>
      </Modal>

      <TestMessageModal
        open={Boolean(testParams)}
        botId={testParams?.botId ?? null}
        chatId={testParams?.chatId ?? null}
        botLabel={testParams?.label}
        onClose={() => setTestParams(null)}
      />
    </>
  );
}
