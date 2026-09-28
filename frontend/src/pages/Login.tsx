/**
 * 登录页：品牌区（左侧，窄屏隐藏）+ 登录表单（右侧）。
 * 功能：用户名/口令、显示口令、记住用户名、中文错误提示、加载态、回车提交、
 * 首次进入的 BOOTSTRAP_ADMIN_PASSWORD 引导。全部颜色/间距走 var(--tg-*)，深浅色自适应。
 */
import { useState, type CSSProperties } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Alert, Button, Checkbox, Form, Input } from 'antd';
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { useAuth } from '../auth/AuthContext';
import { ApiError } from '../api/client';
import { useBreakpoint } from '../hooks/useMediaQuery';
import BrandPanel from '../features/auth/BrandPanel';
import {
  dismissLoginHint,
  isLoginHintDismissed,
  readRememberedUsername,
  writeRememberedUsername,
} from '../features/auth/rememberUsername';

interface LoginForm {
  username: string;
  password: string;
  remember: boolean;
}

export default function Login() {
  const { login, user, ready } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { isNarrow } = useBreakpoint();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hintVisible, setHintVisible] = useState(() => !isLoginHintDismissed());

  const from = (location.state as { from?: string } | null)?.from ?? '/';

  if (ready && user) return <Navigate to={from} replace />;

  const handleFinish = async (values: LoginForm) => {
    setSubmitting(true);
    setError(null);
    try {
      await login(values.username, values.password);
      writeRememberedUsername(values.remember ? values.username.trim() : null);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        // 401 用户名/密码错误、403 员工被停用：后端 detail 已是中文
        setError(err.detail || err.friendlyMessage || '登录失败，请稍后重试');
      } else {
        setError('登录失败，请稍后重试');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const root: CSSProperties = {
    minHeight: '100vh',
    display: 'flex',
    background: 'var(--tg-color-bg-app)',
  };
  const panel: CSSProperties = {
    flex: 1,
    minWidth: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 'var(--tg-space-xxxl)',
  };
  const card: CSSProperties = {
    width: 400,
    maxWidth: '100%',
    background: 'var(--tg-color-bg-card)',
    border: '1px solid var(--tg-color-border-subtle)',
    borderRadius: 'var(--tg-radius-card-lg)',
    boxShadow: 'var(--tg-shadow-lg)',
    padding: 'var(--tg-space-huge)',
  };
  const header: CSSProperties = {
    textAlign: 'center',
    marginBottom: 'var(--tg-space-xxl)',
  };
  const title: CSSProperties = {
    fontSize: 'var(--tg-font-size-title)',
    fontWeight: 'var(--tg-font-weight-semibold)',
    color: 'var(--tg-color-text-primary)',
    margin: 0,
  };
  const sub: CSSProperties = {
    color: 'var(--tg-color-text-tertiary)',
    fontSize: 'var(--tg-font-size)',
    marginTop: 'var(--tg-space-md)',
    marginBottom: 0,
  };
  const footer: CSSProperties = {
    color: 'var(--tg-color-text-tertiary)',
    fontSize: 'var(--tg-font-size-sm)',
    marginTop: 'var(--tg-space-xl)',
    marginBottom: 0,
    textAlign: 'center',
    lineHeight: 'var(--tg-font-line-normal)',
  };
  const badge: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 'var(--tg-space-md)',
    marginBottom: 'var(--tg-space-xl)',
    width: '100%',
  };

  return (
    <div style={root}>
      {!isNarrow ? <BrandPanel /> : null}
      <div style={panel}>
        <div style={card}>
          <div style={header}>
            <h1 style={title}>登录控制台</h1>
            <p style={sub}>请使用员工账号登录 Telegram 云控</p>
          </div>

          {hintVisible ? (
            <Alert
              type="info"
              showIcon
              closable
              style={badge}
              onClose={() => {
                setHintVisible(false);
                dismissLoginHint();
              }}
              message="首次进入？"
              description="请使用部署时用 BOOTSTRAP_ADMIN_PASSWORD 创建的管理员账号登录（本地开发默认 admin / admin12345）。"
            />
          ) : null}

          {error ? (
            <Alert
              type="error"
              showIcon
              message={error}
              style={{ marginBottom: 'var(--tg-space-xl)' }}
              closable
              onClose={() => setError(null)}
            />
          ) : null}

          <Form<LoginForm>
            layout="vertical"
            onFinish={handleFinish}
            autoComplete="off"
            requiredMark={false}
            initialValues={{
              username: readRememberedUsername(),
              remember: Boolean(readRememberedUsername()),
            }}
          >
            <Form.Item
              label="用户名"
              name="username"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder="用户名"
                size="large"
                autoComplete="username"
                autoFocus
              />
            </Form.Item>
            <Form.Item label="口令" name="password" rules={[{ required: true, message: '请输入口令' }]}>
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="口令"
                size="large"
                autoComplete="current-password"
              />
            </Form.Item>
            <Form.Item name="remember" valuePropName="checked" style={{ marginBottom: 'var(--tg-space-xl)' }}>
              <Checkbox>记住用户名</Checkbox>
            </Form.Item>
            <Form.Item style={{ marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" size="large" block loading={submitting}>
                {submitting ? '登录中…' : '登录'}
              </Button>
            </Form.Item>
          </Form>

          <p style={footer}>登录状态保存在本机浏览器（tgcc_token），换人使用请先退出登录。</p>
        </div>
      </div>
    </div>
  );
}
