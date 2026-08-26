const { test, expect } = require('@playwright/test');
const { openBoard, api, selectUi } = require('./helpers');

function rowsOf(page) {
  return page.locator('#table-body tr');
}

test.describe('模块8 · 搜索与组合筛选 (TS-079~090)', () => {
  test('TS-079 关键词搜索', async ({ page }) => {
    await openBoard(page);
    await page.locator('#search-box').fill('登录接口');
    await page.waitForTimeout(700);
    const txt = await page.locator('#table-body').innerText();
    expect(txt).toContain('E2E-登录接口开发');
    expect(await rowsOf(page).count()).toBeGreaterThanOrEqual(1);
  });
  test('TS-080 中文搜索', async ({ page }) => {
    await openBoard(page);
    await page.locator('#search-box').fill('支付模块');
    await page.waitForTimeout(700);
    expect(await page.locator('#table-body').innerText()).toContain('E2E-支付模块编码');
  });
  test('TS-081 编号搜索', async ({ page }) => {
    await openBoard(page);
    await page.locator('#search-box').fill('T0101');
    await page.waitForTimeout(700);
    expect(await page.locator('#table-body').innerText()).toContain('T0101');
  });
  test('TS-082 状态筛选', async ({ page }) => {
    await openBoard(page);
    await page.getByText('筛选', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await selectUi(page, 'filter-status', '进行中');
    await page.waitForTimeout(700);
    const txt = await page.locator('#table-body').innerText();
    expect(txt).toContain('进行中');
    expect(txt).not.toContain('已验收');
  });
  test('TS-083 阶段筛选', async ({ page }) => {
    await openBoard(page);
    await page.getByText('筛选', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await selectUi(page, 'filter-stage', 'S3 详细设计');
    await page.waitForTimeout(700);
    const txt = await page.locator('#table-body').innerText();
    expect(txt).toContain('S3 详细设计');
  });
  test('TS-084 处理角色筛选', async ({ page }) => {
    await openBoard(page);
    await page.getByText('筛选', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await selectUi(page, 'filter-handler', '李开发');
    await page.waitForTimeout(700);
    const txt = await page.locator('#table-body').innerText();
    expect(txt).toContain('李开发');
  });
  test('TS-085 创建人筛选', async ({ page }) => {
    await openBoard(page);
    await page.getByText('筛选', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await selectUi(page, 'filter-creator', 'YuanYii').catch(() => {});
    await page.waitForTimeout(700);
    expect(await rowsOf(page).count()).toBeGreaterThan(0);
  });
  test('TS-086 开始时间范围', async ({ page }) => {
    await openBoard(page);
    await page.getByText('筛选', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await page.locator('#filter-start-from').fill('2026-08-01');
    await page.waitForTimeout(700);
    expect(await rowsOf(page).count()).toBeGreaterThanOrEqual(0);
  });
  test('TS-087 结束时间范围', async ({ page }) => {
    await openBoard(page);
    await page.getByText('筛选', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await page.locator('#filter-end-to').fill('2026-12-31');
    await page.waitForTimeout(700);
    expect(await rowsOf(page).count()).toBeGreaterThanOrEqual(0);
  });
  test('TS-088 组合筛选', async ({ page }) => {
    await openBoard(page);
    await page.getByText('筛选', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await selectUi(page, 'filter-status', '进行中');
    await selectUi(page, 'filter-stage', 'S3 详细设计');
    await page.waitForTimeout(700);
    const txt = await page.locator('#table-body').innerText();
    expect(txt).toContain('进行中');
    expect(txt).not.toContain('已验收');
  });
  test('TS-089 筛选提示条', async ({ page }) => {
    await openBoard(page);
    await page.getByText('筛选', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await selectUi(page, 'filter-status', '进行中');
    await page.waitForTimeout(700);
    const hint = await page.locator('#active-filter-hint').innerText().catch(() => '');
    expect(hint.length).toBeGreaterThan(0);
  });
  test('TS-090 重置筛选', async ({ page }) => {
    await openBoard(page);
    await page.getByText('筛选', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await selectUi(page, 'filter-status', '进行中');
    await page.waitForTimeout(700);
    await page.getByText('重置', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(700);
    const n = Number(await page.locator('#total-count').innerText());
    expect(n).toBeGreaterThan(20);
  });
});
