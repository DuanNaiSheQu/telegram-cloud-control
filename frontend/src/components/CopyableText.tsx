/**
 * CopyableText —— 可复制文本（长 ID / 手机号 / Token / 链接）。
 *
 * props 契约：
 * ┌────────────┬────────────────────────────────────────────────────────────┐
 * │ value      │ string  要复制的原文（必填）                                 │
 * │ display    │ ReactNode  展示内容，默认按 value 截断                       │
 * │ mono       │ boolean  等宽字体（ID / Token 建议开启）                     │
 * │ maxLength  │ number   展示超长截断，默认 28（0 = 不截断）                  │
 * │ truncate   │ 'end'|'middle'  截断方式，默认 'middle'（ID 看头尾更有用）    │
 * │ tooltip    │ string   悬浮提示，默认显示完整值                             │
 * │ onCopied   │ () => void 复制成功回调（一般用来 toast）                     │
 * │ className  │ string                                                      │
 * └────────────┴────────────────────────────────────────────────────────────┘
 * 用法：<CopyableText value={account.tg_user_id} mono />  /  <CopyableText value={phone} />
 */
import { useState, type CSSProperties, type ReactNode } from 'react';
import { Tooltip } from 'antd';
import { CheckOutlined, CopyOutlined } from '@ant-design/icons';
import { copyText } from '../utils/download';
import { toast } from '../utils/feedback';
import { truncateMiddle } from '../utils/format';

export interface CopyableTextProps {
  value: string | number | null | undefined;
  display?: ReactNode;
  mono?: boolean;
  maxLength?: number;
  truncate?: 'end' | 'middle';
  tooltip?: string;
  onCopied?: () => void;
  className?: string;
  style?: CSSProperties;
  /** 复制失败的提示文案 */
  errorText?: string;
}

export function CopyableText({
  value,
  display,
  mono = false,
  maxLength = 28,
  truncate = 'middle',
  tooltip,
  onCopied,
  className,
  style,
  errorText = '复制失败，请手动选中复制',
}: CopyableTextProps) {
  const [copied, setCopied] = useState(false);
  const text = value === null || value === undefined ? '' : String(value);

  if (!text) return <span className="tg-muted">—</span>;

  const shown =
    display ??
    (maxLength > 0 && text.length > maxLength
      ? truncate === 'middle'
        ? truncateMiddle(text, Math.ceil(maxLength / 2), Math.floor(maxLength / 2))
        : `${text.slice(0, maxLength)}…`
      : text);

  const handleCopy = async (event: React.MouseEvent) => {
    event.stopPropagation();
    const ok = await copyText(text);
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
      onCopied?.();
      toast.success('已复制');
    } else {
      toast.error(errorText);
    }
  };

  return (
    <span className={['tg-copyable', className].filter(Boolean).join(' ')} style={style}>
      <Tooltip title={tooltip ?? text}>
        <span className={['tg-copyable-text', mono ? 'tg-mono' : ''].filter(Boolean).join(' ')}>{shown}</span>
      </Tooltip>
      <button
        type="button"
        className={['tg-copyable-button', copied ? 'is-copied' : ''].filter(Boolean).join(' ')}
        onClick={handleCopy}
        aria-label="复制"
      >
        {copied ? <CheckOutlined /> : <CopyOutlined />}
      </button>
    </span>
  );
}

export default CopyableText;
