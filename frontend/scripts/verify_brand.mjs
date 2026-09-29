/**
 * 验证登录页赞助区与侧栏开源入口是否渲染正常（截图存档）。
 * 单独成文件避免 bash heredoc 展开 ${} 造成语法错误。
 */
import { chromium } from 'playwright';

const b = await chromium.launch({ channel: 'chrome' });
try {
  const p = await b.newPage({ viewport: { width: 1680, height: 1000 }, deviceScaleFactor: 1.5 });
  await p.goto('http://127.0.0.1:5173/login', { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(2500);

  const login = await p.evaluate(() => {
    const sp = document.querySelector('.login-brand-sponsors');
    const links = Array.from(document.querySelectorAll('.login-brand-links a')).map(
      (a) => (a.textContent || '').trim(),
    );
    const imgs = Array.from(document.querySelectorAll('.login-brand-sponsor-logo')).map((i) => ({
      loaded: i.complete && i.naturalWidth > 0,
      w: i.naturalWidth,
      h: i.naturalHeight,
    }));
    return {
      sponsorBox: !!sp,
      boxWidth: sp ? Math.round(sp.getBoundingClientRect().width) : 0,
      boxHeight: sp ? Math.round(sp.getBoundingClientRect().height) : 0,
      links,
      imgs,
    };
  });
  console.log('登录页赞助区:', JSON.stringify(login));
  await p.screenshot({ path: '/tmp/login_sponsor.png' });

  // 登录后检查侧栏
  await p.locator('input').first().fill('admin').catch(() => {});
  await p.locator('input[type="password"]').first().fill('admin12345').catch(() => {});
  await p.keyboard.press('Enter');
  await p.waitForTimeout(3500);
  const sider = await p.evaluate(() => {
    const box = document.querySelector('.app-sider-links');
    return {
      exists: !!box,
      linkCount: box ? box.querySelectorAll('a').length : 0,
      text: box ? (box.textContent || '').trim() : '',
    };
  });
  console.log('侧栏入口:', JSON.stringify(sider));
  await p.screenshot({ path: '/tmp/sider_links.png' });
} catch (e) {
  console.log('ERR:', String(e).split('\n')[0]);
} finally {
  await b.close();
}
