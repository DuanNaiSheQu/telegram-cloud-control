/**
 * KeywordWatchPanel —— 关键词监听：规则管理 + 命中流水。
 *
 * 这是「别人找我」的能力：私信/群发是我们主动找人，监听则是在有人聊到
 * 「开卡 / 费率」这类词时第一时间记下来——比事后翻聊天记录有用得多。
 * 命中写进入退群同一条事件流水，这里只做展示与规则维护。
 */
import { Button, Card, Form, Input, Modal, Space, Switch, Table, Tag, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { toast } from '../../utils/feedback';
import { useAsyncData } from '../../hooks/useAsyncData';
import { groupIntelApi } from '../../api/endpoints';
import { RelativeTime } from '../../components';
import type { KeywordHitOut, KeywordWatchOut } from '../../api/types';

export default function KeywordWatchPanel() {
  const watches = useAsyncData(() => groupIntelApi.keywordWatches(), []);
  const hits = useAsyncData(() => groupIntelApi.keywordHits(50), []);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const reload = () => {
    void watches.reload();
    void hits.reload();
  };

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
      const res = await groupIntelApi.createKeywordWatch({
        name: String(values.name ?? '').trim(),
        keywords,
        notify: Boolean(values.notify),
      });
      toast.success(res.message || '已开始监听');
      setOpen(false);
      form.resetFields();
      reload();
    } catch {
      /* client 已提示 */
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (row: KeywordWatchOut, enabled: boolean) => {
    try {
      await groupIntelApi.updateKeywordWatch(row.id, { enabled });
      toast.success(enabled ? '已启用' : '已停用');
      void watches.reload();
    } catch {
      /* client 已提示 */
    }
  };

  const remove = async (row: KeywordWatchOut) => {
    Modal.confirm({
      title: `删除规则「${row.name || row.keywords.join('、')}」？`,
      content: '已记录的历史命中会保留，只删除规则本身。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await groupIntelApi.deleteKeywordWatch(row.id);
          toast.success('规则已删除');
          reload();
        } catch {
          /* client 已提示 */
        }
      },
    });
  };

  return (
    <Card
      title="关键词监听"
      size="small"
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} size="small" onClick={reload} loading={watches.loading}>
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
        群里有人聊到这些词就会记一条命中（写进入退群同一条时间线）。规则改动最多 60 秒后在 Worker 生效。
      </Typography.Text>

      <Table<KeywordWatchOut>
        size="small"
        rowKey="id"
        style={{ marginTop: 'var(--tg-space-sm)' }}
        dataSource={watches.data?.items ?? []}
        loading={watches.loading}
        pagination={false}
        locale={{ emptyText: '还没有监听规则：点右上角「新建规则」，例如 开卡 / 费率 / USDT' }}
        columns={[
          { title: '规则', dataIndex: 'name', width: 160 },
          {
            title: '关键词',
            dataIndex: 'keywords',
            render: (list: string[]) => (
              <Space size={4} wrap>
                {(list ?? []).map((word) => (
                  <Tag key={word}>{word}</Tag>
                ))}
              </Space>
            ),
          },
          { title: '命中', dataIndex: 'hit_count', width: 80 },
          {
            title: '状态',
            dataIndex: 'enabled',
            width: 90,
            render: (enabled: boolean, row) => (
              <Switch size="small" checked={enabled} onChange={(next) => void toggle(row, next)} />
            ),
          },
          {
            title: '操作',
            width: 80,
            render: (_: unknown, row) => (
              <Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => void remove(row)} />
            ),
          },
        ]}
      />

      <div className="tg-form-group-title" style={{ marginTop: 'var(--tg-space-lg)' }}>
        最近命中
      </div>
      <Table<KeywordHitOut>
        size="small"
        rowKey="id"
        dataSource={hits.data?.items ?? []}
        loading={hits.loading}
        pagination={{ pageSize: 5, size: 'small', hideOnSinglePage: true }}
        locale={{ emptyText: '还没有命中记录' }}
        columns={[
          { title: '时间', dataIndex: 'occurred_at', width: 110, render: (value: string) => <RelativeTime value={value} /> },
          { title: '规则', dataIndex: 'rule_name', width: 110 },
          { title: '关键词', dataIndex: 'keyword', width: 100, render: (value: string) => <Tag color="orange">{value}</Tag> },
          { title: '发送者', dataIndex: 'sender', width: 140 },
          { title: '内容', dataIndex: 'text', ellipsis: true },
        ]}
      />

      <Modal
        open={open}
        title="新建关键词监听规则"
        okText="开始监听"
        cancelText="取消"
        confirmLoading={saving}
        onCancel={() => setOpen(false)}
        onOk={() => void create()}
      >
        <Form form={form} layout="vertical" initialValues={{ notify: true }}>
          <Form.Item label="规则名（可选）" name="name">
            <Input placeholder="例如 开卡咨询（留空自动取前几个词）" allowClear />
          </Form.Item>
          <Form.Item
            label="关键词"
            name="keywords"
            rules={[{ required: true, message: '请至少填一个关键词' }]}
            tooltip="逗号或换行分隔，命中任意一个就记录"
          >
            <Input.TextArea rows={3} placeholder={'开卡\n费率\nUSDT'} />
          </Form.Item>
          <Form.Item label="命中时推通知" name="notify" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
