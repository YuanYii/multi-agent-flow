const { test, expect } = require('@playwright/test');
const { openBoard } = require('./helpers');

test.describe('模块1 · 页面加载与基础布局 (TS-001~008)', () => {
  test('TS-001 首页加载', async ({ page }) => {
    await openBoard(page);
    await expect(page.locator('#board-title')).toContainText('多专家Agent协作任务看板');
  });
  test('TS-002 看板数据加载', async ({ page }) => {
    await openBoard(page);
    const total = await page.locator('#total-count').innerText();
    expect(Number(total)).toBeGreaterThanOrEqual(25);
  });
  test('TS-003 默认视图为数据表格', async ({ page }) => {
    await openBoard(page);
    await expect(page.locator('#view-table')).toHaveClass(/active/);
  });
  test('TS-004 看板标题展示', async ({ page }) => {
    await openBoard(page);
    const title = (await page.locator('#board-title').innerText()).trim();
    expect(title.length).toBeGreaterThan(0);
  });
  test('TS-005 操作人回显', async ({ page }) => {
    await openBoard(page);
    const op = await page.locator('#header-user-name-input').inputValue();
    expect(op.trim().length).toBeGreaterThan(0);
  });
  test('TS-006 深色模式切换', async ({ page }) => {
    await openBoard(page);
    const label0 = await page.locator('#theme-toggle-label').innerText();
    await page.locator('#theme-toggle-btn').click();
    await expect(page.locator('#theme-toggle-label')).not.toHaveText(label0, { timeout: 3000 });
  });
  test('TS-007 刷新后保持加载', async ({ page }) => {
    await openBoard(page);
    await page.reload();
    await expect(page.locator('#board-title')).toContainText('多专家Agent协作任务看板', { timeout: 10000 });
  });
  test('TS-008 四视图切换控制台纯净', async ({ page }) => {
    const errs = [];
    page.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
    await openBoard(page);
    for (const v of ['view-kanban-status', 'view-kanban-assignee', 'view-kanban-stage', 'view-table']) {
      await page.evaluate((id) => { const el = document.getElementById(id); if (el) el.click(); }, v);
      await page.waitForTimeout(500);
    }
    expect(errs).toEqual([]);
  });
});
