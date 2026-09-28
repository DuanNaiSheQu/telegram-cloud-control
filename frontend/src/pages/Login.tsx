/**
 * 登录页（企业 SaaS 流程）：
 *   左侧品牌叙事（窄屏收起）→ 右侧登录卡：欢迎语、环境标识、首次使用引导（默认折叠）、
 *   账号口令表单、CapsLock 提醒、记住用户名、内联错误提示、全宽主按钮、安全说明。
 *
 * 交互细节：
 * - 回车提交、自动聚焦用户名、口令可切换可见（antd 自带）；
 * - 登录中按钮 loading 并禁用表单，避免重复提交；
 * - 错误提示内联展示（后端 detail 已是中文），登录成功后回到离开前的页面；
 * - 「记住用户名」写 localStorage，只记账号不记口令。
 */
import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Alert, Button, Checkbox, Form, Input, Typography } from 'antd';
import { ExclamationCircleOutlined, LockOutlined, QuestionCircleOutlined, UserOutlined } from '@ant-design/icons';
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

const ENV_LABEL: Record<string, string> = {
  development: '本地开发环境',
  production: '生产环境',
};

export default function Login() {
  const { login, user, ready } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { isNarrow } = useBreakpoint();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hintOpen, setHintOpen] = useState(false);
  const [hintDismissed, setHintDismissed] = useState(() => isLoginHintDismissed());
  const [capsLock, setCapsLock] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? '/';
  const envMode = import.meta.env.MODE;
  const remembered = readRememberedUsername();

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
        // 401 账号或口令不对、403 员工被停用：后端 detail 已是中文
        setError(err.detail || err.friendlyMessage || '登录失败，请稍后重试');
      } else {
        setError('登录失败，请稍后重试');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-shell">
      {!isNarrow ? <BrandPanel /> : null}

      <main className="login-panel">
        <div className="login-card">
          <div className="login-mini-brand">
            <span className="login-mini-mark">TG</span>
            <span>
              <span className="login-brand-point-title" style={{ color: 'var(--tg-color-text-primary)' }}>
                Telegram 云控
              </span>
              <span className="login-brand-point-desc">Telegram 运营控制台</span>
            </span>
          </div>

          {envMode !== 'production' ? <div className="login-env-tag">{ENV_LABEL[envMode] ?? envMode}</div> : null}

          <div className="login-card-head">
            <h1 className="login-title">欢迎回来</h1>
            <p className="login-subtitle">使用你的账号登录，登录后可查看你被分配的账号与会话。</p>
          </div>

          {!hintDismissed ? (
            <div className="login-hint">
              {hintOpen ? (
                <Alert
                  type="info"
                  showIcon
                  closable
                  onClose={() => {
                    setHintOpen(false);
                    setHintDismissed(true);
                    dismissLoginHint();
                  }}
                  message="首次部署怎么登录？"
                  description="用部署时 BOOTSTRAP_ADMIN_PASSWORD 创建的管理员账号登录；本地开发默认是 admin / admin12345。登录后请到「员工分配」给同事开账号。"
                />
              ) : (
                <button type="button" className="login-hint-toggle" onClick={() => setHintOpen(true)}>
                  <QuestionCircleOutlined /> 首次部署？看看初始账号怎么拿
                </button>
              )}
            </div>
          ) : null}

          {error ? (
            <Alert
              type="error"
              showIcon
              closable
              className="login-hint"
              message="登录失败"
              description={error}
              onClose={() => setError(null)}
            />
          ) : null}

          <Form<LoginForm>
            className="login-form"
            layout="vertical"
            onFinish={handleFinish}
            autoComplete="off"
            requiredMark={false}
            disabled={submitting}
            initialValues={{ username: remembered ?? '', remember: Boolean(remembered) }}
          >
            <Form.Item
              label="用户名"
              name="username"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder="例如 admin"
                size="large"
                autoComplete="username"
                autoFocus
              />
            </Form.Item>

            <Form.Item label="口令" name="password" rules={[{ required: true, message: '请输入口令' }]}>
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="登录口令"
                size="large"
                autoComplete="current-password"
                onKeyUp={(event) => setCapsLock(event.getModifierState?.('CapsLock') ?? false)}
                onBlur={() => setCapsLock(false)}
              />
            </Form.Item>

            {capsLock ? (
              <div className="login-capslock">
                <ExclamationCircleOutlined /> 大写锁定已打开，口令可能输错大小写
              </div>
            ) : null}

            <div className="login-row">
              <Form.Item name="remember" valuePropName="checked" noStyle>
                <Checkbox>记住用户名</Checkbox>
              </Form.Item>
              <Typography.Text className="login-row-note">口令忘了？联系管理员重置</Typography.Text>
            </div>

            <Button type="primary" htmlType="submit" size="large" block loading={submitting}>
              {submitting ? '正在登录…' : '登录控制台'}
            </Button>
          </Form>

          <p className="login-foot">
            登录状态保存在本机浏览器（<strong>tgcc_token</strong>），换人使用请先退出登录。
            <br />
            账号由管理员在「员工分配」里创建与停用。
          </p>
        </div>
      </main>
    </div>
  );
}
