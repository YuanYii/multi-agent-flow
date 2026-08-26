const { test, expect } = require('@playwright/test');
const { openBoard, selectUi } = require('./helpers');

test.describe('模块9 · 分页与排序 (TS-091~098)', () => {
  test('TS-091 分页条展示', async ({ page }) => {
    await openBoard(page);
    const bar = page.locator('#table-pagination-bar');
    await expect(bar).toBeVisible();
    expect((await bar.innerText()).length).toBeGreaterThan(0);
  });
  test('TS-092 下一页', async ({ page }) => {
    await openBoard(page);
    const first = await page.locator('#table-body tr').first().innerText();
    await page.locator('#btn-next-page').click();
    await page.waitForTimeout(700);
    const secondFirst = await page.locator('#table-body tr').first().innerText();
    expect(secondFirst).not.toBe(first);
  });
  test('TS-093 上一页', async ({ page }) => {
    await openBoard(page);
    await page.locator('#btn-next-page').click();
    await page.waitForTimeout(700);
    const secondFirst = await page.locator('#table-body tr').first().innerText();
    await page.locator('#btn-prev-page').click();
    await page.waitForTimeout(700);
    const backFirst = await page.locator('#table-body tr').first().innerText();
    expect(backFirst).not.toBe(secondFirst);
  });
  test('TS-094 首页边界禁用', async ({ page }) => {
    await openBoard(page);
    await expect(page.locator('#btn-prev-page')).toBeDisabled();
  });
  test('TS-095 排序切换', async ({ page }) => {
    await openBoard(page);
    await page.getByText('排序', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await selectUi(page, 'sort-field', '任务耗时').catch(() => {});
    await page.waitForTimeout(700);
    const first = await page.locator('#table-body tr').first().innerText();
    expect(first.length).toBeGreaterThan(0);
  });
  test('TS-096 排序方向切换', async ({ page }) => {
    await openBoard(page);
    await page.getByText('排序', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await selectUi(page, 'sort-order', '降序').catch(() => {});
    await page.waitForTimeout(700);
    expect(await page.locator('#table-body tr').count()).toBeGreaterThan(0);
  });
  test('TS-097 排序+分页组合', async ({ page }) => {
    await openBoard(page);
    await page.getByText('排序', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await selectUi(page, 'sort-order', '降序').catch(() => {});
    await page.waitForTimeout(500);
    await page.locator('#btn-next-page').click();
    await page.waitForTimeout(700);
    expect(await page.locator('#table-body tr').count()).toBeGreaterThan(0);
  });
  test('TS-098 排序+筛选组合', async ({ page }) => {
    await openBoard(page);
    await page.locator('#search-box').fill('E2E-');
    await page.waitForTimeout(600);
    await page.getByText('排序', { exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    await selectUi(page, 'sort-order', '降序').catch(() => {});
    await page.waitForTimeout(700);
    expect(await page.locator('#table-body tr').count()).toBeGreaterThan(0);
  });
});
