import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Form, Input, Typography } from 'antd';
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { useAuth } from '../auth/AuthContext';
import { ApiError } from '../api/client';

interface LoginForm {
  username: string;
  password: string;
}

export default function Login() {
  const { login, user, ready } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const from = (location.state as { from?: string } | null)?.from ?? '/';

  if (ready && user) return <Navigate to={from} replace />;

  const handleFinish = async (values: LoginForm) => {
    setSubmitting(true);
    setError(null);
    try {
      await login(values.username, values.password);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? err.detail || '用户名或口令不正确' : err.message);
      } else {
        setError('登录失败，请稍后重试');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="app-center" style={{ background: '#f0f2f5' }}>
      <Card style={{ width: 380 }} styles={{ body: { padding: 28 } }}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <Typography.Title level={4} style={{ marginBottom: 4 }}>
            Telegram 云控
          </Typography.Title>
          <Typography.Text type="secondary">内部运维控制台，请用员工账号登录</Typography.Text>
        </div>

        {error ? (
          <Alert
            type="error"
            showIcon
            message={error}
            style={{ marginBottom: 16 }}
            closable
            onClose={() => setError(null)}
          />
        ) : null}

        <Form<LoginForm> layout="vertical" onFinish={handleFinish} autoComplete="off" requiredMark={false}>
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" size="large" autoComplete="username" autoFocus />
          </Form.Item>
          <Form.Item
            label="口令"
            name="password"
            rules={[{ required: true, message: '请输入口令' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="口令"
              size="large"
              autoComplete="current-password"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" size="large" block loading={submitting}>
              登录
            </Button>
          </Form.Item>
        </Form>

        <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0, fontSize: 12 }}>
          登录状态保存在本机浏览器（tgcc_token），换人使用请先退出登录。
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
