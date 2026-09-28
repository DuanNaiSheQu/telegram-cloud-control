/**
 * ErrorBoundary —— 渲染期异常兜底：任何一个页面崩了都不白屏。
 *
 * props 契约：
 *   <ErrorBoundary>            <App/></ErrorBoundary>                     全局兜底
 *   <ErrorBoundary compact onReset={fn}>…</ErrorBoundary>                局部兜底（卡片内）
 *
 * 说明：
 *  - 只在 class 组件里能捕获渲染异常，因此这里是 class；
 *  - 路由级兜底建议用 <RouteErrorBoundary/>（App.tsx 内部按 pathname 自动重置）；
 *  - 捕获到的错误会 console.error 一份，便于排查；同时展示给用户「重试 / 刷新」两条出路。
 */
import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import ErrorState from './ErrorState';

export interface ErrorBoundaryProps {
  children: ReactNode;
  /** 自定义标题 */
  title?: ReactNode;
  /** 自定义说明 */
  description?: ReactNode;
  /** 点击「重试」时额外做的清理（例如回首页） */
  onReset?: () => void;
  compact?: boolean;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 保留控制台堆栈：值班同事截图时能看到组件栈
    console.error('[ErrorBoundary] 页面渲染异常：', error, info.componentStack);
  }

  private reset = () => {
    this.setState({ error: null });
    this.props.onReset?.();
  };

  render(): ReactNode {
    const { error } = this.state;
    const { children, title, description, compact } = this.props;
    if (!error) return children;
    return (
      <ErrorState
        compact={compact}
        title={title ?? '页面出错了'}
        description={
          description ?? (
            <span>
              这个区块渲染时抛出异常，其它部分仍可正常使用。可以点「重试」重新渲染，或刷新整个页面。
              <br />
              <span className="tg-mono tg-break">{error.message || String(error)}</span>
            </span>
          )
        }
        onRetry={this.reset}
        retryText="重试"
        extra={
          <Button type="text" icon={<ReloadOutlined />} onClick={() => window.location.reload()}>
            刷新页面
          </Button>
        }
      />
    );
  }
}

export default ErrorBoundary;
