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
