/**
 * 前端启动入口。
 * 主题变量由 ThemeProvider 从 theme/tokens.ts 注入（<html> 内联样式）；
 * styles.css 里有一份同名兜底，供 JS 执行前的首屏使用（index.html 的引导脚本负责设 data-theme）。
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';
import 'antd/dist/reset.css';
import './styles.css';
import App from './App';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

const container = document.getElementById('root');
if (!container) throw new Error('找不到 #root 挂载点');

ReactDOM.createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
