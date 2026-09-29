/**
 * 通过网页版 Telegram 过佩奇验证。
 *
 * 思路（关键）：`init_data` 只有 Telegram 客户端能签发——而 web.telegram.org
 * 本身就是官方客户端（Web A），它在打开 WebApp 时会注入合法的 `initData`。
 * 所以只要在网页版里点那个「点此完成网页人机验证」按钮，
 * mini app 拿到的就是真数据，佩奇后端会认。
 *
 * 阶段：
 *   1. 打开 web.telegram.org/a/ —— 人工登录一次（扫码或验证码）；
 *   2. 登录态存到 run/telegram_web_state.json，之后免登录复用；
 *   3. 导航到与佩奇的私聊 —— 这一步交给脚本点击验证按钮，打开 WebApp；
 *   4. WebApp 内部（iframe）Cap 会自动解，提交时带上真 init_data。
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = '/Users/duannai/telegram云控';
const STATE = path.join(ROOT, 'run/telegram_web_state.json');
const MODE = process.argv[2] || 'login';

const browser = await chromium.launch({
  channel: 'chrome',
  headless: false,                                    // 要人看着操作
  args: ['--disable-blink-features=AutomationControlled'],
});
const ctx = await browser.newContext({
  locale: 'zh-CN',
  viewport: { width: 1360, height: 900 },
  storageState: fs.existsSync(STATE) ? STATE : undefined,
});
await ctx.addInitScript(() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
});
const page = await ctx.newPage();

page.on('console', (m) => {
  const t = m.text();
  if (/initData|web_app|WebView/i.test(t)) console.log('[页面]', t.slice(0, 200));
});

if (MODE === 'login') {
  console.log('打开 web.telegram.org … 请在窗口里登录（扫码最快）');
  await page.goto('https://web.telegram.org/a/', { waitUntil: 'domcontentloaded', timeout: 90000 });

  // 登录成功的判定：URL 里出现会话，或页面出现聊天列表容器
  await page.waitForFunction(
    () => {
      const hash = location.hash || '';
      if (/[?&#].*(chat|@)/.test(hash)) return true;
      return Boolean(document.querySelector('.ChatList, .chat-list, .LeftMainHeader'));
    },
    { timeout: 600_000, polling: 2000 },
  );
  await ctx.storageState({ path: STATE });
  console.log('✅ 登录态已保存:', STATE);
  console.log('当前 URL:', page.url());
  fs.writeFileSync('/tmp/tgweb_login_ok.txt', 'ok', 'utf8');
} else {
  console.log('复用登录态，导航到佩奇私聊…');
  await page.goto('https://web.telegram.org/a/#@PeiQiBot', { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.waitForTimeout(6000);
  await page.screenshot({ path: '/tmp/tgweb_peiqi.png' });
  console.log('已截图 /tmp/tgweb_peiqi.png，URL:', page.url());
}

// 不自动关闭：留给人操作 / 后续步骤复用同一窗口
console.log('（窗口保持打开，用完手动关）');
await new Promise(() => {});
