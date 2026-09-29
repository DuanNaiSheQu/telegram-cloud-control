/**
 * 验证「首次进入自动弹声明」与「用户菜单里的关于入口」。
 * 单独成文件，避免 bash heredoc 吃掉模板字符串。
 */
import { chromium } from 'playwright';

const b = await chromium.launch({ channel: 'chrome' });
try {
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1.4 });
  await p.goto('http://127.0.0.1:5173/login', { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(2000);

  // 清掉"已读"标记，模拟首次进入
  await p.evaluate(() => localStorage.removeItem('tgcc_about_seen')).catch(() => {});

  await p.locator('input').first().fill('admin').catch(() => {});
  await p.locator('input[type="password"]').first().fill('admin12345').catch(() => {});
  await p.keyboard.press('Enter');
  await p.waitForTimeout(4000);

  // ① 首次应自动弹窗
  const modal = await p.evaluate(() => {
    const m = document.querySelector('.ant-modal-content');
    const title = m?.querySelector('.ant-modal-title')?.textContent?.trim() ?? '';
    const text = m?.textContent ?? '';
    return {
      visible: !!m,
      title,
      hasSource: text.includes('telegram-cloud-control'),
      hasUsdt: text.includes('TYozr2b8tV4fikCuQYYvaHRCW555555555'),
      hasRisk: text.includes('风险') || text.includes('自行承担'),
      sponsorImgs: m ? m.querySelectorAll('img').length : 0,
    };
  });
  console.log('首次弹窗:', JSON.stringify(modal));
  await p.screenshot({ path: '/tmp/about_modal.png' });

  // ② 关闭后，菜单里应有入口
  if (modal.visible) {
    await p.locator('button:has-text("我已了解")').first().click().catch(() => {});
    await p.waitForTimeout(800);
  }
  await p.locator('.app-user-trigger').first().click().catch(() => {});
  await p.waitForTimeout(1200);
  await p.waitForTimeout(900);
  const menu = await p.evaluate(() => {
    const items = Array.from(document.querySelectorAll('.ant-dropdown-menu li, .ant-dropdown-menu-item')).map((i) =>
      (i.textContent || '').trim(),
    );
    return { items };
  });
  console.log('用户菜单:', JSON.stringify(menu));

  // ③ 再刷新一次，不应再自动弹
  await p.reload({ waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(3500);
  const second = await p.evaluate(() => !!document.querySelector('.ant-modal-content'));
  console.log('二次进入是否再弹:', second);
} catch (e) {
  console.log('ERR:', String(e).split('\n')[0]);
} finally {
  await b.close();
}
