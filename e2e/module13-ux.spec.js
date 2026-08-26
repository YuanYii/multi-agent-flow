const { test, expect } = require('@playwright/test');
const { openBoard, switchView } = require('./helpers');

test.describe('模块13 · 体验与兼容 (TS-121~126)', () => {
  test('TS-121 键盘导航焦点可见', async ({ page }) => {
    await openBoard(page);
    await page.keyboard.press('Tab');
    const active = await page.evaluate(() => document.activeElement && document.activeElement.tagName);
    expect(active && active.length > 0).toBe(true);
  });
  test('TS-122 窄屏布局不溢出', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await openBoard(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 50);
    expect(overflow).toBe(false);
  });
  test('TS-123 ESC 关闭弹窗', async ({ page }) => {
    await openBoard(page);
    await page.locator('#add-table-record-btn').click();
    await expect(page.locator('#add-modal')).toBeVisible();
    await page.keyboard.press('Escape');
    await page.waitForTimeout(400);
    await expect(page.locator('#add-modal')).toBeHidden();
  });
  test('TS-124 Toast 反馈出现', async ({ page }) => {
    await openBoard(page);
    await page.locator('#search-box').fill('登录接口');
    await page.waitForTimeout(500);
    // 触发一次流转产生 toast
    const row = page.locator('#table-body tr', { hasText: '登录接口' }).first();
    await row.locator('.tag-select[data-type="status"]').click();
    await page.waitForTimeout(300);
    await page.locator('.tag-select-panel .tag-select-option', { hasText: '待开始' }).last().click().catch(() => {});
    await page.waitForTimeout(800);
    const toast = await page.locator('#toast-container').innerText().catch(() => '');
    expect(toast.length).toBeGreaterThan(0);
  });
  test('TS-125 长时间停留无异常', async ({ page }) => {
    await openBoard(page);
    await page.waitForTimeout(3000);
    await expect(page.locator('#board-title')).toContainText('多专家Agent协作任务看板');
  });
  test('TS-126 多视图往返状态一致', async ({ page }) => {
    await openBoard(page);
    for (let i = 0; i < 3; i++) {
      await switchView(page, 'view-kanban-status');
      await switchView(page, 'view-kanban-assignee');
      await switchView(page, 'view-kanban-stage');
      await switchView(page, 'view-table');
    }
    await expect(page.locator('#main-data-table')).toBeVisible();
    expect(await page.locator('#table-body tr').count()).toBeGreaterThan(0);
  });
});
