/**
 * 界面截图脚本：登录控制台后逐页截图，产出 README 与文档用的真实截图。
 *
 * 用法（先起栈，控制台在 http://127.0.0.1:5173）：
 *
 *     cd frontend && npm run screenshots                 # 深色主题，覆盖 README 引用的那批
 *     cd frontend && npm run screenshots -- --theme light  # 浅色主题
 *     cd frontend && npm run screenshots -- --only group-intel
 *
 * 说明：
 * - 复用本机已装的 Chrome（`channel: 'chrome'`），不下载 Chromium；
 * - 视口 1440×900、2 倍缩放，与 README 里标注的尺寸一致；
 * - 登录走 API 拿 token 再注入 localStorage，避免脚本里处理验证码/表单；
 * - 页面等 `networkidle` 后再等一小段时间，让图表与列表渲染完。
 */
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SHOT_DIR = join(ROOT, 'frontend', 'screenshots');
const BASE = process.env.SCREENSHOT_BASE || 'http://127.0.0.1:5173';
const API = process.env.SCREENSHOT_API || 'http://127.0.0.1:8000';
const USERNAME = process.env.SCREENSHOT_USER || 'admin';
const PASSWORD = process.env.SCREENSHOT_PASSWORD || 'admin12345';

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const THEME = flag('theme', 'dark');
const ONLY = flag('only', '').split(',').map((item) => item.trim()).filter(Boolean);

/** 页面清单：key 用于 --only 过滤，file 是实际落盘名（沿用 README 已引用的命名） */
const PAGES = [
  { key: 'dashboard', path: '/', file: 'uicore-dashboard-{theme}-1440.png', label: '工作台' },
  { key: 'dialogs', path: '/dialogs', file: 'uiinbox-dialogs-chat-{theme}.png', label: '会话收件箱' },
  { key: 'accounts', path: '/accounts', file: 'uicore-accounts-{theme}-1440.png', label: '账号管理' },
  { key: 'tasks', path: '/tasks', file: 'uiinbox-tasks-{theme}.png', label: '任务中心' },
  // 本次新增：触达中心与群情报
  { key: 'campaigns', path: '/campaigns/bulk-pm', file: 'uicore-campaigns-{theme}-1440.png', label: '触达中心' },
  { key: 'campaigns-materials', path: '/campaigns/materials', file: 'uicore-campaigns-materials-{theme}.png', label: '触达中心·素材' },
  { key: 'group-intel', path: '/group-intel', file: 'uicore-group-intel-{theme}-1440.png', label: '群情报' },
  { key: 'detection', path: '/detection', file: 'uicore-detection-results-{theme}-1440.png', label: '账号检测' },
  { key: 'groups', path: '/groups', file: 'uicore-groups-{theme}-1440.png', label: '分组管理' },
  { key: 'network', path: '/network', file: 'uicore-network-{theme}-1440.png', label: '网络代理' },
  { key: 'bots', path: '/bots', file: 'uiops-bots-{theme}.png', label: 'Bot 管理' },
  { key: 'relay', path: '/relay', file: 'uiops-relay-{theme}.png', label: 'Bot 转发' },
  { key: 'assignments', path: '/assignments', file: 'uiops-assignments-{theme}.png', label: '成员分配' },
  { key: 'audit', path: '/audit', file: 'uiinbox-audit-{theme}.png', label: '操作记录' },
];

async function login() {
  const response = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD }),
  });
  if (!response.ok) {
    throw new Error(`登录失败 ${response.status}：确认控制台账号密码，或用 SCREENSHOT_USER/PASSWORD 覆盖`);
  }
  const data = await response.json();
  return { token: data.access_token, user: data.user ?? null };
}

async function main() {
  mkdirSync(SHOT_DIR, { recursive: true });
  const { token, user } = await login();
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    locale: 'zh-CN',
    colorScheme: THEME === 'light' ? 'light' : 'dark',
  });
  // 注入登录态与主题：key 与前端一致（tgcc_token / tgcc_theme / tgcc_user）
  await context.addInitScript(
    ([tokenValue, userValue, themeValue]) => {
      window.localStorage.setItem('tgcc_token', tokenValue);
      if (userValue) window.localStorage.setItem('tgcc_user', userValue);
      window.localStorage.setItem('tgcc_theme', themeValue);
      // 侧栏默认展开，避免截图里全是折叠菜单
      window.localStorage.setItem('tgcc_nav_state', JSON.stringify({}));
    },
    [token, user ? JSON.stringify(user) : '', THEME],
  );

  const page = await context.newPage();
  const written = [];
  for (const item of PAGES) {
    if (ONLY.length && !ONLY.includes(item.key)) continue;
    const url = `${BASE}${item.path}`;
    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
      await page.waitForTimeout(1200);
      const file = item.file.replace('{theme}', THEME);
      const target = join(SHOT_DIR, file);
      await page.screenshot({ path: target, fullPage: false });
      written.push({ file, label: item.label });
      console.log(`  ✓ ${item.label.padEnd(14)} ${file}`);
    } catch (error) {
      console.error(`  ! ${item.label} 截图失败：${error.message}`);
    }
  }

  // 登录页单独处理：先清掉登录态，否则会被重定向到工作台
  if (!ONLY.length || ONLY.includes('login')) {
    const anon = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 2,
      locale: 'zh-CN',
      colorScheme: THEME === 'light' ? 'light' : 'dark',
    });
    const anonPage = await anon.newPage();
    await anonPage.goto(`${BASE}/login`, { waitUntil: 'networkidle', timeout: 45000 });
    await anonPage.waitForTimeout(900);
    const file = `uiops-login-${THEME}.png`;
    await anonPage.screenshot({ path: join(SHOT_DIR, file) });
    written.push({ file, label: '登录页' });
    console.log(`  ✓ ${'登录页'.padEnd(12)} ${file}`);
    await anon.close();
  }

  await browser.close();

  // 记录本次截图清单，便于 README 与变更记录引用
  const manifest = join(SHOT_DIR, `manifest-${THEME}.json`);
  writeFileSync(
    manifest,
    JSON.stringify({ generated_at: new Date().toISOString(), theme: THEME, base: BASE, shots: written }, null, 2),
    'utf8',
  );
  console.log(`\n共 ${written.length} 张，输出目录 ${SHOT_DIR}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
