/**
 * NotFound —— 404 兜底页（在外壳里渲染，不会白屏，也不会把人甩回登录页）。
 *
 * props 契约：{ pathname?: string; onBack?: () => void }
 */
import { Button } from 'antd';
import { useLocation, useNavigate } from 'react-router-dom';
import { HomeOutlined } from '@ant-design/icons';
import EmptyState from './EmptyState';

export interface NotFoundProps {
  pathname?: string;
  onBack?: () => void;
}

export function NotFound({ pathname, onBack }: NotFoundProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const current = pathname ?? location.pathname;
  return (
    <div className="tg-page">
      <div className="tg-card" style={{ padding: 'var(--tg-space-xl)' }}>
        <EmptyState
          art="search"
          title="页面不存在"
          description={
            <>
              没有找到 <code className="tg-mono">{current}</code> 对应的页面。
              可能是链接过期，或侧栏里已经改了入口。
            </>
          }
          action={
            <Button
              type="primary"
              icon={<HomeOutlined />}
              onClick={() => {
                if (onBack) onBack();
                else navigate('/');
              }}
            >
              回到工作台
            </Button>
          }
        />
      </div>
    </div>
  );
}

export default NotFound;
