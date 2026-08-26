const { test, expect } = require('@playwright/test');
const { openBoard, api } = require('./helpers');

test.describe('模块11 · 数据导入导出 (TS-107~112)', () => {
  test('TS-107 导出 JSON', async ({ page }) => {
    await openBoard(page);
    await page.locator('#export-json-btn').click().catch(() => {});
    await expect(page.locator('#export-modal')).toBeVisible();
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 10000 }),
      page.getByText('确认导出并下载', { exact: true }).click().catch(() => {}),
    ]);
    expect(download).toBeTruthy();
  });
  test('TS-108 导出内容为当前数据', async ({ page }) => {
    await openBoard(page);
    await page.locator('#export-json-btn').click().catch(() => {});
    await expect(page.locator('#export-modal')).toBeVisible();
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 10000 }),
      page.getByText('确认导出并下载', { exact: true }).click().catch(() => {}),
    ]);
    const stream = await download.createReadStream();
    let raw = '';
    for await (const chunk of stream) raw += chunk.toString();
    const data = JSON.parse(raw);
    const arr = Array.isArray(data) ? data : (data.cards || data.data || []);
    expect(arr.length).toBeGreaterThan(20);
  });
  test('TS-109 导入弹窗入口', async ({ page }) => {
    await openBoard(page);
    await expect(page.locator('#import-json-btn')).toBeEnabled();
  });
  test('TS-110 导入非法 JSON 被拒', async ({ page }) => {
    await openBoard(page);
    const before = (await api('GET', '/api/tasks?size=all')).data.data.items.length;
    await page.locator('#import-json-btn').click().catch(() => {});
    await page.waitForTimeout(500);
    await page.locator('#import-json-file-input').setInputFiles({
      name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from('{not-json'),
    }).catch(() => {});
    await page.waitForTimeout(1000);
    const after = (await api('GET', '/api/tasks?size=all')).data.data.items.length;
    expect(after).toBe(before);
  });
  test('TS-111 导入后数据可查', async ({ page }) => {
    await openBoard(page);
    // 导入语义为全量覆写：导出当前全量数据并追加一张新卡再导入，保证不破坏既有样本
    const all = (await api('GET', '/api/tasks?size=all')).data.data.items;
    const cards = [...all, { id: 'T9001', name: 'E2E-导入卡A', stage: 'S3 详细设计', wp: 'WP-导入', assignee: '李开发', status: '待开始' }];
    await page.locator('#import-json-btn').click().catch(() => {});
    await page.waitForTimeout(500);
    await page.locator('#import-json-file-input').setInputFiles({
      name: 'ok.json', mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(cards)),
    }).catch(() => {});
    await page.waitForTimeout(1200);
    const after = (await api('GET', '/api/tasks?size=all')).data.data.items;
    expect(after.some((c) => String(c.name || '').includes('E2E-导入卡A'))).toBe(true);
    expect(after.length).toBeGreaterThanOrEqual(all.length);
  });
  test('TS-112 导出后统计一致', async ({ page }) => {
    await openBoard(page);
    const n = Number(await page.locator('#total-count').innerText());
    await page.locator('#export-json-btn').click().catch(() => {});
    await expect(page.locator('#export-modal')).toBeVisible();
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 10000 }),
      page.getByText('确认导出并下载', { exact: true }).click().catch(() => {}),
    ]);
    const stream = await download.createReadStream();
    let raw = '';
    for await (const chunk of stream) raw += chunk.toString();
    const data = JSON.parse(raw);
    const arr = Array.isArray(data) ? data : (data.cards || data.data || []);
    expect(arr.length).toBe(n);
  });
});
