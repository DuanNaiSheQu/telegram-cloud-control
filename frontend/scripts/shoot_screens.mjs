/**
 * 截取最新界面截图，供发行仓库 README 的「界面预览」使用。
 *
 * 为什么要重新截：文档里的截图一旦落后于界面，看的人会以为功能长那样，
 * 而我们刚做完触达中心全站排版优化 —— 旧图已经不能代表现状。
 *
 * 用法：node scripts/shoot_screens.mjs <输出目录>
 */
import { chromium } from 'playwright';
import * as pathlib from 'node:path';
import fs from 'node:fs';

const OUT = process.argv[2] || '/tmp/shots';
const BASE = 'http://127.0.0.1:5173';

// 每张图的用途写在注释里，出图后一眼能对上是给 README 哪一段用的
const PAGES = [
  { file: 'dashboard.png', url: '/dashboard', note: '工作台：在线概览、Worker 心跳、最近失败' },
  { file: 'accounts.png', url: '/accounts', note: '账号管理：状态、健康分、设备身份、批量操作' },
  { file: 'campaigns.png', url: '/campaigns/broadcast', note: '触达中心：批量群发（本轮刚优化过排版）' },
  { file: 'tasks.png', url: '/tasks', note: '任务中心：批次、实时执行日志' },
  { file: 'bulk-pm.png', url: '/campaigns/bulk-pm', note: '批量私信' },
];

fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome' });
const page = await browser.newPage({
  viewport: { width: 1680, height: 1050 },
  deviceScaleFactor: 2, // 2 倍图，README 里缩放显示更锐利
});

const done = [];
try {
  // 登录
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  await page.locator('input').first().fill('admin').catch(() => {});
  await page.locator('input[type="password"]').first().fill('admin12345').catch(() => {});
  await page.keyboard.press('Enter');
  await page.waitForTimeout(3500);

  // 登录页单独截（先截，避免登录后回不去）
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2200);
  await page.screenshot({ path: pathlib.join(OUT, 'login.png') });
  done.push('login.png');

  for (const p of PAGES) {
    await page.goto(`${BASE}${p.url}`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2600);
    await page.screenshot({ path: pathlib.join(OUT, p.file) });
    done.push(p.file);
    console.log(`  ✓ ${p.file.padEnd(18)} ${p.note}`);
  }
} catch (err) {
  console.log('ERR:', String(err).split('\n')[0]);
} finally {
  await browser.close();
}

console.log(`\n共 ${done.length} 张 → ${OUT}`);
