/**
 * 佩奇验证的浏览器阶段：屏幕外 Chrome（不弹窗、看不见）打开签名 URL，
 * 让页面里的 cap-widget 自动解完工作量证明，然后自动提交。
 *
 * 为什么用「窗口挪到屏幕外」而不是 headless：
 * Cap 的 instrumentation 协议会采集浏览器环境特征，无头模式的指纹缺项容易被判机器；
 * 窗口真实存在（只是坐标在屏幕外）时指纹完整，同时你又看不到它。
 *
 * 用法：
 *   node scripts/peiqi_web_solve.mjs /tmp/peiqi_auto_url.txt [--visible]
 */
import { chromium } from 'playwright';
import fs from 'node:fs';

const [, , urlFile, ...flags] = process.argv;
const visible = flags.includes('--visible');
if (!urlFile || !fs.existsSync(urlFile)) {
  console.error('缺少 URL 文件:', urlFile);
  process.exit(2);
}
const url = fs.readFileSync(urlFile, 'utf8').trim();

// 无头模式：完全不出现任何窗口。用系统真 Chrome + 新无头内核，
// 指纹比打包的 Chromium 干净，Cap 的 instrumentation 才有机会通过。
// 无头模式实测会被 Cap 的 instrumentation 拦掉（captcha 根本不跑），
// 所以必须跑「真实窗口」：
//   - 有桌面（macOS/Windows）：窗口挪走 + CDP 最小化，你看不到它；
//   - 无桌面服务器（Linux）：由上层脚本起 Xvfb 造虚拟显示，Chrome 照样有屏幕。
// 浏览器优先级：系统真 Chrome（指纹最好）→ Playwright 自带 Chromium（兜底）。
let browser = null;
let browserLabel = '';
const launchArgs = [
  // 不用屏幕外坐标：那会让 Chrome 挂起渲染进程（页面会被关掉）。
  // 藏窗口统一交给下面的 CDP 最小化。
  '--window-size=1000,760',
  '--disable-blink-features=AutomationControlled',
  '--no-first-run',
  '--no-default-browser-check',
  ...(visible ? ['--window-position=0,0'] : []),
];
for (const channel of ['chrome', null]) {
  try {
    browser = await chromium.launch({
      ...(channel ? { channel } : {}),
      headless: false,
      args: launchArgs,
    });
    browserLabel = channel ? '系统 Chrome' : 'Playwright Chromium（兜底）';
    break;
  } catch (error) {
    // 装不上系统 Chrome 就退到自带内核，不在这里失败
  }
}
if (!browser) {
  console.error('没有可用的浏览器内核，请先跑 bash scripts/install_browser.sh');
  process.exit(2);
}
console.log('[浏览器]', browserLabel);

const ctx = await browser.newContext({
  locale: 'zh-CN',
  viewport: { width: 1000, height: 740 },
  timezoneId: 'Asia/Shanghai',
});
await ctx.addInitScript(() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
});
const page = await ctx.newPage();

// 把窗口最小化：CDP 直接控制浏览器窗口状态，不依赖窗口坐标（macOS 会纠正负坐标）
if (!visible) {
  try {
    const cdp = await ctx.newCDPSession(page);
    const { windowId } = await cdp.send('Browser.getWindowForTarget');
    await cdp.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'minimized' } });
    console.log('[窗口] 已最小化（不占用屏幕）');
  } catch (error) {
    console.log('[窗口] 最小化失败:', String(error.message).slice(0, 100));
  }
}

let verifyBody = '';
let lastRedeemToken = '';
page.on('response', async (response) => {
  const target = response.url();
  if (/captcha\/verify/.test(target)) {
    try { verifyBody = await response.text(); } catch {}
    console.log(`[验证响应] ${response.status()} ${verifyBody.slice(0, 200)}`);
  } else if (/\/redeem|\/challenge/.test(target)) {
    let body = '';
    try { body = await response.text(); } catch {}
    if (target.endsWith('/redeem') && body.includes('"success":true')) {
      const m = body.match(/"token"\s*:\s*"([^"]+)"/);
      if (m) lastRedeemToken = m[1];
    }
    console.log(`[${target.split('/').pop()}] ${response.status()} ${body.slice(0, 120)}`);
  }
});

try {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
} catch (error) {
  console.log('打开失败:', String(error.message).slice(0, 120));
}

// 等页面把 URL fragment 解析成 initData，并等 cap-widget 解出 captcha_token
let initData = '';
let captchaToken = '';
for (let i = 0; i < 100; i += 1) {
  await page.waitForTimeout(400);
  if (!initData) {
    initData = await page.evaluate(() => window.Telegram?.WebApp?.initData || '').catch(() => '');
  }
  if (!captchaToken) captchaToken = lastRedeemToken || '';
  if (initData && captchaToken) break;
}
console.log('initData 长度:', initData.length, '| captcha_token:', captchaToken.slice(0, 40));

// 绕开页面 UI 事件，自己提交（三段数据都拿到了，直接打接口最可靠）
const peiqiToken = new URL(url).searchParams.get('token') || '';
if (initData && captchaToken && peiqiToken) {
  const resp = await page.evaluate(
    async ({ token, init, captcha }) => {
      const r = await fetch('/gk/captcha/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, init_data: init, captcha_token: captcha, provider: 'cap' }),
      });
      return { status: r.status, body: await r.text() };
    },
    { token: peiqiToken, init: initData, captcha: captchaToken },
  );
  console.log(`[主动提交] ${resp.status} ${resp.body.slice(0, 200)}`);
  verifyBody = resp.body;
} else {
  console.log('缺少提交要素:', { initData: initData.length, captchaToken: captchaToken.length, peiqiToken: peiqiToken.length });
}

const statusText = await page.innerText('#status').catch(() => '取不到');
console.log('页面状态:', statusText);
const passed = /"ok"\s*:\s*true/.test(verifyBody) || /通过/.test(statusText);
console.log(passed ? 'PASSED' : 'FAILED');
await browser.close();
process.exit(passed ? 0 : 1);
