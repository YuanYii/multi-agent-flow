const { test, expect } = require('@playwright/test');
const { cfg, openBoard } = require('./helpers');

test.describe('模块10 · 协作权限与只读 (TS-099~106)', () => {
  test('TS-099 主控模式可读写', async ({ page }) => {
    await openBoard(page);
    await expect(page.locator('#add-table-record-btn')).toBeEnabled();
  });
  test('TS-100 协作端只读浏览', async ({ page }) => {
    await page.goto(`${cfg.baseURL}`);
    await expect(page.locator('body')).toContainText('多专家Agent协作任务看板', { timeout: 10000 });
    await page.waitForTimeout(1500);
    expect(await page.locator('#table-body tr').count()).toBeGreaterThan(0);
  });
  test('TS-101 协作端添加被锁定', async ({ page }) => {
    await page.goto(`${cfg.baseURL}`);
    await page.waitForTimeout(1500);
    const disabled = await page.locator('#add-table-record-btn').isDisabled();
    expect(disabled).toBe(true);
  });
  test('TS-102 协作端标题只读', async ({ page }) => {
    await page.goto(`${cfg.baseURL}`);
    await page.waitForTimeout(1500);
    const editable = await page.locator('#board-title').getAttribute('contenteditable');
    expect(editable).toBe('false');
  });
  test('TS-103 协作端编辑受限', async ({ page }) => {
    await page.goto(`${cfg.baseURL}`);
    await page.waitForTimeout(1500);
    const row = page.locator('#table-body tr').first();
    await row.getByText('详情', { exact: true }).click().catch(() => {});
    await page.waitForTimeout(600);
    // 协作端：编辑入口不可用（按钮禁用或不存在）或编辑框只读
    const editBtn = page.locator('#toggle-detail-edit-btn');
    const editName = page.locator('#edit-name');
    const btnCount = await editBtn.count();
    if (btnCount > 0) {
      const disabled = await editBtn.isDisabled().catch(() => true);
      if (!disabled) {
        // 编辑按钮可用时点击进入编辑视图，锁定体现在编辑框只读
        await editBtn.click().catch(() => {});
        await page.waitForTimeout(500);
        const ro = await page.locator('#edit-name').getAttribute('readonly');
        expect(ro !== null).toBe(true);
      } else {
        expect(true).toBe(true);
      }
    } else if (await editName.count()) {
      const ro = await editName.getAttribute('readonly');
      expect(ro !== null).toBe(true);
    } else {
      // 详情只读视图存在
      await expect(page.locator('#detail-read-container')).toBeVisible();
    }
  });
  test('TS-104 协作端搜索可读', async ({ page }) => {
    await page.goto(`${cfg.baseURL}`);
    await page.waitForTimeout(1500);
    await page.locator('#search-box').fill('登录接口');
    await page.waitForTimeout(700);
    expect(await page.locator('#table-body').innerText()).toContain('登录接口');
  });
  test('TS-105 操作人切换', async ({ page }) => {
    await openBoard(page);
    const input = page.locator('#header-user-name-input');
    await input.fill('E2E操作人');
    await page.waitForTimeout(400);
    const v = await input.inputValue();
    expect(v).toContain('E2E操作人');
  });
  test('TS-106 主控恢复写权限', async ({ page }) => {
    await openBoard(page);
    await expect(page.locator('#add-table-record-btn')).toBeEnabled();
  });
});
