/**
 * ErrorState —— 统一失败态（绝不白屏）。
 *
 * props 契约：
 * ┌─────────────┬───────────────────────────────────────────────────────────┐
 * │ title       │ ReactNode  默认「加载失败」                                │
 * │ description │ ReactNode  默认「后端接口没有返回数据，请重试…」             │
 * │ error       │ string|null 具体错误（ApiError.message，已是中文）           │
 * │ onRetry     │ () => void 传了就显示「重试」按钮                           │
 * │ extra       │ ReactNode  额外操作（如「返回工作台」）                      │
 * │ compact     │ boolean    卡片内嵌小尺寸                                   │
 * │ className   │ string                                                      │
 * └─────────────┴───────────────────────────────────────────────────────────┘
 */
import type { CSSProperties, ReactNode } from 'react';
import { Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import EmptyState from './EmptyState';

export interface ErrorStateProps {
  title?: ReactNode;
  description?: ReactNode;
  error?: string | null;
  onRetry?: () => void;
  retryText?: string;
  extra?: ReactNode;
  compact?: boolean;
  className?: string;
  style?: CSSProperties;
}

export function ErrorState({
  title = '加载失败',
  description,
  error,
  onRetry,
  retryText = '重试',
  extra,
  compact = false,
  className,
  style,
}: ErrorStateProps) {
  return (
    <div className={['tg-error-state', className].filter(Boolean).join(' ')} style={style}>
      <EmptyState
        art="error"
        compact={compact}
        title={title}
        description={
          description ?? (
            <span>
              后端接口没有正常返回，请稍后再试。
              {error ? <span className="tg-break">（{error}）</span> : null}
            </span>
          )
        }
        action={
          onRetry ? (
            <Button icon={<ReloadOutlined />} onClick={onRetry}>
              {retryText}
            </Button>
          ) : undefined
        }
        secondaryAction={extra}
      />
    </div>
  );
}

export default ErrorState;
