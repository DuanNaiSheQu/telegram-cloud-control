/** 看 Playwright 给 Chrome 加了哪些参数 + 试启用 WebGPU。 */
import { chromium } from 'patchright';
const mode = process.argv[2] || 'inspect';

if (mode === 'inspect') {
  const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--window-size=900,700'] });
  const page = await (await browser.newContext()).newPage();
  await page.goto('chrome://version', { waitUntil: 'domcontentloaded' }).catch(() => {});
  await page.waitForTimeout(1500);
  const txt = await page.innerText('body').catch(() => '');
  const line = txt.split('\n').find((l) => l.includes('--')) || txt.slice(0, 900);
  console.log('=== Chrome 实际参数 ===');
  console.log(line.slice(0, 1400));
  await browser.close();
} else {
  const args = mode.split('|');
  console.log('测试 args:', JSON.stringify(args));
  const browser = await chromium.launch({ channel: 'chrome', headless: false, args });
  const ctx = await browser.newContext({ locale: 'zh-TW' });
  const page = await ctx.newPage();
  await page.goto('about:blank');
  const r = await page.evaluate(async () => {
    const out = { hasGpu: typeof navigator.gpu !== 'undefined' };
    if (navigator.gpu) {
      try { const a = await navigator.gpu.requestAdapter(); out.adapter = a ? 'OK' : 'null'; } catch (e) { out.err = String(e).slice(0, 80); }
    }
    return out;
  });
  console.log('结果:', JSON.stringify(r));
  await browser.close();
}
