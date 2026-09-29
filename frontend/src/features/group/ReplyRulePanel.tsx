/**
 * ReplyRulePanel —— 账号自动回复规则。
 *
 * 与「关键词监听」的分工：监听只记录给人看，这个面板里的规则**会真的发消息**。
 * 所以每行都明确标出「范围 / 冷却」，新建时也把这些摆在明面上——
 * 运营必须清楚「我现在是在让账号自动回话」，而不是以为只是加了个提醒。
 */
import { Button, Card, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tag, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { toast } from '../../utils/feedback';
import { useAsyncData } from '../../hooks/useAsyncData';
import { groupIntelApi } from '../../api/endpoints';
import type { ReplyRuleOut } from '../../api/types';

const SCOPE_LABEL: Record<string, string> = { private: '仅私信', group: '仅群聊', both: '私信+群聊' };

export default function ReplyRulePanel() {
  const rules = useAsyncData(() => groupIntelApi.replyRules(), []);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const create = async () => {
    const values = await form.validateFields();
    const keywords = String(values.keywords ?? '')
      .split(/[,\n，]/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (!keywords.length) {
      toast.warning('至少填一个关键词');
      return;
    }
    setSaving(true);
    try {
      const res = await groupIntelApi.createReplyRule({
        name: String(values.name ?? '').trim(),
        keywords,
        reply_text: String(values.reply_text ?? ''),
        match_mode: values.match_mode ?? 'contains',
        scope: values.scope ?? 'private',
        cooldown_seconds: Number(values.cooldown_seconds ?? 300),
      });
      toast.success(res.message || '已启用自动回复');
      setOpen(false);
      form.resetFields();
      void rules.reload();
    } catch {
      /* client 已提示 */
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (row: ReplyRuleOut, enabled: boolean) => {
    try {
      await groupIntelApi.updateReplyRule(row.id, { enabled });
      toast.success(enabled ? '已启用（命中会自动回）' : '已停用');
      void rules.reload();
    } catch {
      /* client 已提示 */
    }
  };

  const remove = async (row: ReplyRuleOut) => {
    Modal.confirm({
      title: `删除规则「${row.name || row.keywords.join('、')}」？`,
      content: '已发出的回复会留在会话记录里，只删除规则本身。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await groupIntelApi.deleteReplyRule(row.id);
          toast.success('规则已删除');
          void rules.reload();
        } catch {
          /* client 已提示 */
        }
      },
    });
  };

  return (
    <Card
      title="自动回复规则"
      size="small"
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} size="small" onClick={() => void rules.reload()} loading={rules.loading}>
            刷新
          </Button>
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
            新建规则
          </Button>
        </Space>
      }
      style={{ marginTop: 'var(--tg-space-lg)' }}
    >
      <Typography.Text type="secondary" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
        命中关键词会**自动发消息**（不是只记录）。同一会话在冷却时间内只回一次，
        且发出的每条都计入该号的发送额度——不会绕过节流与每日配额。
      </Typography.Text>

      <Table<ReplyRuleOut>
        size="small"
        rowKey="id"
        style={{ marginTop: 'var(--tg-space-sm)' }}
        dataSource={rules.data?.items ?? []}
        loading={rules.loading}
        pagination={false}
        locale={{ emptyText: '还没有规则：点右上角「新建规则」，例如 多少钱 → 自动回报价' }}
        columns={[
          { title: '规则', dataIndex: 'name', width: 150 },
          {
            title: '命中词',
            dataIndex: 'keywords',
            render: (list: string[]) => (
              <Space size={4} wrap>
                {(list ?? []).map((word) => (
                  <Tag key={word}>{word}</Tag>
                ))}
              </Space>
            ),
          },
          {
            title: '回复内容',
            dataIndex: 'reply_text',
            ellipsis: true,
            render: (value: string) => <span className="tg-muted">{value}</span>,
          },
          { title: '范围', dataIndex: 'scope', width: 100, render: (v: string) => <Tag>{SCOPE_LABEL[v] ?? v}</Tag> },
          { title: '冷却', dataIndex: 'cooldown_seconds', width: 90, render: (v: number) => `${v}s` },
          { title: '命中', dataIndex: 'hit_count', width: 70 },
          {
            title: '状态',
            dataIndex: 'enabled',
            width: 80,
            render: (enabled: boolean, row) => (
              <Switch size="small" checked={enabled} onChange={(next) => void toggle(row, next)} />
            ),
          },
          {
            title: '操作',
            width: 70,
            render: (_: unknown, row) => (
              <Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => void remove(row)} />
            ),
          },
        ]}
      />

      <Modal
        open={open}
        title="新建自动回复规则"
        okText="启用"
        cancelText="取消"
        confirmLoading={saving}
        onCancel={() => setOpen(false)}
        onOk={() => void create()}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ match_mode: 'contains', scope: 'private', cooldown_seconds: 300 }}
        >
          <Form.Item label="规则名（可选）" name="name">
            <Input placeholder="例如 价格咨询（留空自动取前几个词）" allowClear />
          </Form.Item>
          <Form.Item
            label="命中关键词"
            name="keywords"
            rules={[{ required: true, message: '请至少填一个关键词' }]}
            tooltip="逗号或换行分隔，命中任意一个就回"
          >
            <Input.TextArea rows={2} placeholder={'多少钱\n价格\n费率'} />
          </Form.Item>
          <Form.Item
            label="回复内容"
            name="reply_text"
            rules={[{ required: true, message: '请填写要自动回复的内容' }]}
          >
            <Input.TextArea rows={3} placeholder="您好，报价与开卡方式已私发～" />
          </Form.Item>
          <Space size="large" wrap>
            <Form.Item label="匹配方式" name="match_mode">
              <Select
                style={{ width: 130 }}
                options={[
                  { value: 'contains', label: '包含' },
                  { value: 'exact', label: '完全相等' },
                  { value: 'regex', label: '正则' },
                ]}
              />
            </Form.Item>
            <Form.Item label="生效范围" name="scope">
              <Select
                style={{ width: 130 }}
                options={[
                  { value: 'private', label: '仅私信' },
                  { value: 'group', label: '仅群聊' },
                  { value: 'both', label: '私信+群聊' },
                ]}
              />
            </Form.Item>
            <Form.Item label="冷却（秒）" name="cooldown_seconds" tooltip="同一会话多久内只回一次，防止刷屏">
              <InputNumber min={0} max={86400} style={{ width: 120 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </Card>
  );
}
