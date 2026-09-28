import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 开发环境把 /api 反代到本机后端（含 WebSocket 升级），生产用 nginx.conf 做同样的事。
// 版本号真源在仓库根的 VERSION（与后端 /health 返回的同一个值）
const appVersion = (() => {
  try {
    return readFileSync(resolve(__dirname, '..', 'VERSION'), 'utf8').trim() || '0.0.0';
  } catch {
    return '0.0.0';
  }
})();

export default defineConfig({
  define: { __APP_VERSION__: JSON.stringify(appVersion) },
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
    // 本地用 npm run preview 验证构建产物时，同样把 /api 反代到后端
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // antd 自身（CSS-in-JS + 各组件）单独成 vendor chunk，方便浏览器长期缓存；
    // 单包压缩后约 1.1MB（gzip 约 350KB），属于 antd 正常体量，这里把告警阈值放到 1200。
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // 显式分组：react 运行时 / antd 组件 / antd 图标各占一块，避免主包过大且便于长期缓存
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          antd: ['antd'],
          'antd-icons': ['@ant-design/icons'],
        },
      },
    },
  },
});
