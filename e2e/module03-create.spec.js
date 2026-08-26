const { test, expect } = require('@playwright/test');
const { openBoard, api, selectUi, selectTag, createTask, searchAndAssert } = require('./helpers');

test.describe('模块3 · 任务创建 (TS-021~032)', () => {
  test('TS-021 打开添加弹窗', async ({ page }) => {
    await openBoard(page);
    await page.locator('#add-table-record-btn').click();
    await expect(page.locator('#add-modal')).toBeVisible();
  });
  test('TS-022 必填校验（空表单不创建）', async ({ page }) => {
    await openBoard(page);
    const before = Number(await page.locator('#total-count').innerText());
    await page.locator('#add-table-record-btn').click();
    await page.getByText('提交保存', { exact: true }).click();
    await page.waitForTimeout(500);
    const after = Number(await page.locator('#total-count').innerText());
    expect(after).toBe(before);
  });
  test('TS-023 正常创建', async ({ page }) => {
    await openBoard(page);
    await createTask(page, { name: 'E2E-新建任务TS023', stage: 'S3 详细设计', assignee: '李开发' });
    await searchAndAssert(page, 'TS023', 'E2E-新建任务TS023');
  });
  test('TS-024 WBS 自动生成', async ({ page }) => {
    await openBoard(page);
    await page.locator('#add-table-record-btn').click();
    await page.locator('#new-name').fill('E2E-新建任务TS024');
    await selectUi(page, 'new-stage', 'S2 架构设计');
    await page.getByText('提交保存', { exact: true }).click();
    await page.waitForTimeout(800);
    const r = await api('GET', '/api/tasks?keyword=TS024');
    const item = r.data.data.items.find((c) => c.name.includes('TS024'));
    expect(item && String(item.wbs || '').length).toBeGreaterThan(0);
  });
  test('TS-025 工作包自动生成', async ({ page }) => {
    await openBoard(page);
    await page.locator('#add-table-record-btn').click();
    await page.locator('#new-name').fill('E2E-新建任务TS025');
    await selectUi(page, 'new-stage', 'S7 文档与发布');
    await page.getByText('提交保存', { exact: true }).click();
    await page.waitForTimeout(800);
    const r = await api('GET', '/api/tasks?keyword=TS025');
    const item = r.data.data.items.find((c) => c.name.includes('TS025'));
    expect(String(item.wp || '').length).toBeGreaterThan(0);
  });
  test('TS-026 重复名称创建行为', async ({ page }) => {
    await openBoard(page);
    // UI 创建层允许同名卡（去重为 CLI 层约束），验证可创建且编号递增
    const before = Number(await page.locator('#total-count').innerText());
    await createTask(page, { name: 'E2E-登录接口开发' });
    expect(Number(await page.locator('#total-count').innerText())).toBe(before + 1);
  });
  test('TS-027 取消创建不产生卡', async ({ page }) => {
    await openBoard(page);
    const before = Number(await page.locator('#total-count').innerText());
    await page.locator('#add-table-record-btn').click();
    await page.locator('#new-name').fill('E2E-取消任务TS027');
    await page.locator('#add-modal .close-btn, #add-modal .modal-header .close-btn').first().click().catch(() => {});
    await page.waitForTimeout(400);
    const after = Number(await page.locator('#total-count').innerText());
    expect(after).toBe(before);
  });
  test('TS-028 创建指定状态', async ({ page }) => {
    await openBoard(page);
    await page.locator('#add-table-record-btn').click();
    await page.locator('#new-name').fill('E2E-指定状态TS028');
    if (await page.locator('#new-status').count()) {
      await selectTag(page, 'new-status', '进行中');
    }
    await page.getByText('提交保存', { exact: true }).click();
    await page.waitForTimeout(800);
    const r = await api('GET', '/api/tasks?keyword=TS028');
    const item = r.data.data.items.find((c) => c.name.includes('TS028'));
    expect(item.status).toBe('进行中');
  });
  test('TS-029 特殊字符名称', async ({ page }) => {
    await openBoard(page);
    await createTask(page, { name: '<script>alert(9)</script> UI测试' });
    await searchAndAssert(page, 'alert(9)', '<script>alert(9)</script> UI测试');
  });
  test('TS-030 超长名称不破版', async ({ page }) => {
    const errs = [];
    page.on('pageerror', (e) => errs.push(String(e).slice(0, 200)));
    await openBoard(page);
    const longName = 'E2E-超长名称测试'.padEnd(40, '名');
    const r = await api('POST', '/api/tasks', { name: longName, stage: 'S3 详细设计', wp: 'WP-后端', assignee: '李开发', status: '待开始' });
    expect(r.status).toBe(200);
    const all = await api('GET', '/api/tasks?size=all');
    const found = all.data.data.items.find((c) => String(c.name || '').includes('超长名称测试'));
    expect(found).toBeTruthy();
    await page.reload();
    await page.waitForFunction(() => document.querySelectorAll('#table-body tr').length > 0, { timeout: 10000 });
    expect(await page.locator('#table-body tr').count()).toBeGreaterThan(0);
    expect(errs).toEqual([]);
  });
  test('TS-031 创建后统计即时更新', async ({ page }) => {
    await openBoard(page);
    const before = Number(await page.locator('#total-count').innerText());
    await page.locator('#add-table-record-btn').click();
    await page.locator('#new-name').fill('E2E-统计更新TS031');
    await page.getByText('提交保存', { exact: true }).click();
    await expect(page.locator('#total-count')).not.toHaveText(String(before), { timeout: 5000 });
  });
  test('TS-032 创建按钮存在可用', async ({ page }) => {
    await openBoard(page);
    await expect(page.locator('#add-table-record-btn')).toBeEnabled();
  });
});
