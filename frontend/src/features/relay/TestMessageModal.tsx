/**
 * TestMessageModal —— 用 Bot 向目标 chat 发一条测试消息。
 * 用于 Relay 页面：规则行内「测试」与新建/编辑表单里的「用 Bot 发一条测试消息」。
 * 失败时把后端中文原因（ApiError.friendlyMessage）展示在弹窗内，页面不崩。
 */
import { useEffect, useState } from 'react';
import { Alert, Button, Input, Modal, Space, Typography } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import { api, ApiError } from '../../api/client';
import type { RelayTestResponse } from './types';

export interface TestMessageModalProps {
  open: boolean;
  /** Bot 显示名（测试目标提示用） */
  botLabel?: string;
  botId?: string | null;
  chatId?: number | null;
  onClose: () => void;
}

const DEFAULT_TEXT = '这是一条测试消息（来自 Telegram 云控）';

export function TestMessageModal({ open, botLabel, botId, chatId, onClose }: TestMessageModalProps) {
  const [text, setText] = useState(DEFAULT_TEXT);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<RelayTestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setText(DEFAULT_TEXT);
    setResult(null);
    setError(null);
  }, [open]);

  const canSend = Boolean(botId && chatId) && text.trim().length > 0 && !sending;

  const handleSend = async () => {
    if (!canSend) return;
    setSending(true);
    setResult(null);
    setError(null);
    try {
      const res = await api.post<RelayTestResponse>('/api/relays/test', {
        bot_id: botId,
        chat_id: chatId,
        text: text.trim(),
      });
      setResult(res);
    } catch (err) {
      // ApiError.friendlyMessage 已是中文原因（Telegram 拒绝 / Token 无法解密 / 网络失败）
      setError(err instanceof ApiError ? err.friendlyMessage : '发送失败，请稍后重试');
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal
      open={open}
      title="用 Bot 发一条测试消息"
      onCancel={onClose}
      width={520}
      footer={
        <Space>
          <Button onClick={onClose}>关闭</Button>
          <Button type="primary" icon={<SendOutlined />} loading={sending} disabled={!canSend} onClick={handleSend}>
            {sending ? '发送中…' : '发送测试消息'}
          </Button>
        </Space>
      }
    >
      {botId && chatId ? (
        <Typography.Paragraph type="secondary" style={{ marginBottom: 'var(--tg-space-lg)' }}>
          将用 {botLabel || '所选 Bot'} 向 chat_id <Typography.Text code>{chatId}</Typography.Text>{' '}
          发送下面这条消息；对方会真实收到，请谨慎使用。
        </Typography.Paragraph>
      ) : (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 'var(--tg-space-lg)' }}
          message="请先在表单里选择 Bot 并填写员工群 chat_id，再发测试消息。"
        />
      )}

      <Input.TextArea
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="测试消息内容"
        maxLength={2000}
        showCount
      />

      {result?.ok ? (
        <Alert
          type="success"
          showIcon
          style={{ marginTop: 'var(--tg-space-xl)' }}
          message="测试消息已发出"
          description={result.detail || result.message || `员工群消息 ID：${result.staff_message_id ?? '—'}`}
        />
      ) : null}

      {error ? (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 'var(--tg-space-xl)' }}
          message="发送失败"
          description={error}
        />
      ) : null}
    </Modal>
  );
}
