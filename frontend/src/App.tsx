import { useEffect } from 'react';
import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { bindMessageApi } from './utils/feedback';
import Layout, { RequireAuth } from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Accounts from './pages/Accounts';
import Groups from './pages/Groups';
import Detection from './pages/Detection';
import Network from './pages/Network';
import Dialogs from './pages/Dialogs';
import Tasks from './pages/Tasks';
import Relay from './pages/Relay';
import Bots from './pages/Bots';
import Assignments from './pages/Assignments';
import Audit from './pages/Audit';

/** 把 antd 的 message 实例交给 fetch 封装，避免用静态方法丢失主题/上下文 */
function FeedbackBridge() {
  const { message } = AntdApp.useApp();
  useEffect(() => {
    bindMessageApi(message);
    return () => bindMessageApi(null);
  }, [message]);
  return null;
}

/**
 * 路由表（侧栏显示名 → 路径）：
 * 工作台 /、任务中心 /tasks、账号管理 /accounts、账号分组 /groups、账号检测 /detection、
 * 网络 /network、会话 /dialogs、Bot 转发 /relay、Bot 管理 /bots、员工分配 /assignments、
 * 操作记录 /audit；登录 /login。
 */
export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: { colorPrimary: '#229ed9', borderRadius: 6 },
      }}
    >
      <AntdApp>
        <FeedbackBridge />
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                element={
                  <RequireAuth>
                    <Layout />
                  </RequireAuth>
                }
              >
                <Route path="/" element={<Dashboard />} />
                <Route path="/tasks" element={<Tasks />} />
                <Route path="/accounts" element={<Accounts />} />
                <Route path="/groups" element={<Groups />} />
                <Route path="/detection" element={<Detection />} />
                <Route path="/network" element={<Network />} />
                <Route path="/dialogs" element={<Dialogs />} />
                <Route path="/relay" element={<Relay />} />
                <Route path="/bots" element={<Bots />} />
                <Route path="/assignments" element={<Assignments />} />
                <Route path="/audit" element={<Audit />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  );
}
