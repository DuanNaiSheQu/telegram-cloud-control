/**
 * ConfirmModal —— 统一二次确认（危险操作 / 批量操作 / 不可撤销动作）。
 *
 * props 契约：
 * ┌──────────────────┬──────────────────────────────────────────────────────────┐
 * │ open             │ boolean                                                  │
 * │ title            │ ReactNode  一句话说清要做什么（「停用 3 个账号？」）        │
 * │ content          │ ReactNode  影响范围说明（会列出账号 / 条数）               │
 * │ description      │ ReactNode  灰色补充说明（后果、可否恢复）                  │
 * │ okText/cancelText│ string  默认「确定」/「取消」                             │
 * │ danger           │ boolean  危险按钮（红色），默认 false                     │
 * │ loading          │ boolean  外部提交中                                      │
 * │ onOk             │ () => void | Promise<void>  返回 Promise 时自动 loading    │
 * │ onCancel         │ () => void                                               │
 * │ confirmPhrase    │ string  高危操作：必须原样输入这段文字才能确认             │
 * │ confirmPhraseHint│ ReactNode  输入框下方提示                                │
 * │ extra            │ ReactNode  额外内容（Checkbox「我已知晓」等）              │
 * │ width            │ number  默认 420                                         │
 * └──────────────────┴──────────────────────────────────────────────────────────┘
 * 用法：
 *   <ConfirmModal open={open} danger title="停用这 3 个账号？"
 *                 content={<ul>…</ul>} description="停用后不再认领任务，可随时启用。"
 *                 okText="停用" onOk={handleDisable} onCancel={() => setOpen(false)} />
 */
import { useEffect, useState, type ReactNode } from 'react';
import { Alert, Button, Input, Modal, Typography } from 'antd';
import { ExclamationCircleFilled } from '@ant-design/icons';

export interface ConfirmModalProps {
  open: boolean;
  title: ReactNode;
  content?: ReactNode;
  description?: ReactNode;
  okText?: string;
  cancelText?: string;
  danger?: boolean;
  loading?: boolean;
  onOk: () => void | Promise<void>;
  onCancel: () => void;
  confirmPhrase?: string;
  confirmPhraseHint?: ReactNode;
  extra?: ReactNode;
  width?: number;
}

export function ConfirmModal({
  open,
  title,
  content,
  description,
  okText = '确定',
  cancelText = '取消',
  danger = false,
  loading = false,
  onOk,
  onCancel,
  confirmPhrase,
  confirmPhraseHint,
  extra,
  width = 420,
}: ConfirmModalProps) {
  const [submitting, setSubmitting] = useState(false);
  const [phrase, setPhrase] = useState('');

  useEffect(() => {
    if (!open) {
      setPhrase('');
      setSubmitting(false);
    }
  }, [open]);

  const phraseOk = !confirmPhrase || phrase.trim() === confirmPhrase;

  const handleOk = async () => {
    if (!phraseOk) return;
    try {
      const result = onOk();
      if (result && typeof (result as Promise<void>).then === 'function') {
        setSubmitting(true);
        await result;
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--tg-space-md)' }}>
          {danger ? <ExclamationCircleFilled style={{ color: 'var(--tg-color-warning)' }} /> : null}
          {title}
        </span>
      }
      onCancel={onCancel}
      width={width}
      maskClosable={false}
      confirmLoading={loading || submitting}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          {cancelText}
        </Button>,
        <Button
          key="ok"
          type="primary"
          danger={danger}
          loading={loading || submitting}
          disabled={!phraseOk}
          onClick={handleOk}
        >
          {okText}
        </Button>,
      ]}
    >
      <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
        {content}
        {description ? (
          <Typography.Text type="secondary" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
            {description}
          </Typography.Text>
        ) : null}
        {confirmPhrase ? (
          <div>
            <Alert
              type="warning"
              showIcon
              message={`这是不可撤销的操作，请输入「${confirmPhrase}」确认`}
              style={{ marginBottom: 'var(--tg-space-md)' }}
            />
            <Input
              value={phrase}
              onChange={(event) => setPhrase(event.target.value)}
              placeholder={confirmPhrase}
              autoComplete="off"
            />
            {confirmPhraseHint ? (
              <Typography.Text type="secondary" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
                {confirmPhraseHint}
              </Typography.Text>
            ) : null}
          </div>
        ) : null}
        {extra}
      </div>
    </Modal>
  );
}

export default ConfirmModal;
