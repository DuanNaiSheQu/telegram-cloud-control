/**
 * JsonBlock —— 详情里的格式化 JSON 块（等宽字体 + 复制按钮 + 超长滚动）。
 * 任务详情（payload/result）与审计详情（detail JSON）共用。
 */
import { useState, type CSSProperties, type ReactNode } from 'react';
import { Button, Tooltip } from 'antd';
import { CheckOutlined, CopyOutlined } from '@ant-design/icons';
import { copyText } from '../../utils/download';
import { stringifyDetail } from '../../utils/format';
import { toast } from '../../utils/feedback';

interface JsonBlockProps {
  title?: ReactNode;
  value: unknown;
  emptyText?: string;
  maxHeight?: number;
  style?: CSSProperties;
  className?: string;
}

export function JsonBlock({
  title,
  value,
  emptyText = '（无）',
  maxHeight = 320,
  style,
  className,
}: JsonBlockProps) {
  const [copied, setCopied] = useState(false);
  const text = stringifyDetail(value);

  const handleCopy = async () => {
    if (!text) return;
    const ok = await copyText(text);
    if (ok) {
      setCopied(true);
      toast.success('已复制');
      window.setTimeout(() => setCopied(false), 1600);
    } else {
      toast.error('复制失败，请手动选中复制');
    }
  };

  return (
    <div className={['tg-json-block', className].filter(Boolean).join(' ')} style={style}>
      <div className="tg-json-block-head">
        {title ? <span className="tg-json-block-title">{title}</span> : null}
        {text ? (
          <Tooltip title="复制完整内容">
            <Button
              type="text"
              size="small"
              icon={copied ? <CheckOutlined style={{ color: 'var(--tg-color-success)' }} /> : <CopyOutlined />}
              onClick={() => void handleCopy()}
              aria-label={title ? `复制${title}` : '复制'}
            />
          </Tooltip>
        ) : null}
      </div>
      <pre className="tg-json-block-body" style={{ maxHeight }}>
        {text || emptyText}
      </pre>
    </div>
  );
}
