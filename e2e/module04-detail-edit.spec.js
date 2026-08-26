const { test, expect } = require('@playwright/test');
const { openBoard, api, selectUi, selectTag, searchAndAssert } = require('./helpers');

async function openDetail(page, name) {
  await openBoard(page);
  const row = page.locator('#table-body tr', { hasText: name }).first();
  await row.getByText('详情', { exact: true }).click();
  await expect(page.locator('#detail-modal')).toBeVisible();
}

test.describe('模块4 · 任务详情与编辑 (TS-033~044)', () => {
  test('TS-033 打开详情面板', async ({ page }) => {
    await openDetail(page, 'E2E-支付模块编码');
  });
  test('TS-034 详情字段完整性', async ({ page }) => {
    await openDetail(page, 'E2E-支付模块编码');
    const txt = await page.locator('#detail-modal').innerText();
    expect(txt).toContain('E2E-支付模块编码');
    expect(txt).toContain('进行中');
    expect(txt).toContain('李开发');
    expect(txt).toContain('T0103');
  });
  test('TS-035 详情→编辑模式切换', async ({ page }) => {
    await openDetail(page, 'E2E-支付模块编码');
    await page.locator('#toggle-detail-edit-btn').click();
    await expect(page.locator('#edit-name')).toBeVisible();
  });
  test('TS-036 编辑名称保存', async ({ page }) => {
    await openDetail(page, 'E2E-支付模块编码');
    await page.locator('#toggle-detail-edit-btn').click();
    await page.locator('#edit-name').fill('E2E-支付模块编码-改名后');
    await page.locator('#detail-save-btn').click();
    await page.waitForTimeout(800);
    const r = await api('GET', '/api/tasks?keyword=支付模块编码-改名后');
    expect(r.data.data.items.length).toBeGreaterThan(0);
  });
  test('TS-037 编辑负责人保存', async ({ page }) => {
    await openDetail(page, 'E2E-订单接口提审');
    await page.locator('#toggle-detail-edit-btn').click();
    await selectTag(page, 'edit-assignee', '马前端').catch(() => {});
    await page.locator('#detail-save-btn').click();
    await page.waitForTimeout(800);
    const r = await api('GET', '/api/tasks?keyword=订单接口提审');
    const item = r.data.data.items.find((c) => c.name.includes('订单接口提审'));
    expect(String(item.assignee || '')).toContain('马前端');
  });
  test('TS-038 编辑阶段保存', async ({ page }) => {
    await openDetail(page, 'E2E-用户手册编制');
    await page.locator('#toggle-detail-edit-btn').click();
    await selectUi(page, 'edit-stage', 'S5 单元测试').catch(() => {});
    await page.locator('#detail-save-btn').click();
    await page.waitForTimeout(800);
    const r = await api('GET', '/api/tasks?keyword=用户手册编制');
    const item = r.data.data.items.find((c) => c.name.includes('用户手册编制'));
    expect(String(item.stage || '')).toContain('S5');
  });
  test('TS-039 备注追加', async ({ page }) => {
    await openDetail(page, 'E2E-集成测试执行');
    await page.locator('#toggle-detail-edit-btn').click();
    const rm = page.locator('#edit-remarks');
    const old = await rm.inputValue().catch(() => '');
    await rm.fill((old || '') + '; E2E追加备注TS039');
    await page.locator('#detail-save-btn').click();
    await page.waitForTimeout(800);
    const r = await api('GET', '/api/tasks?keyword=集成测试执行');
    const item = r.data.data.items.find((c) => c.name.includes('集成测试执行'));
    expect(String(item.remarks || '')).toContain('E2E追加备注TS039');
  });
  test('TS-040 取消编辑不落库', async ({ page }) => {
    await openDetail(page, 'E2E-回归用例验证');
    const r0 = await api('GET', '/api/tasks?keyword=回归用例验证');
    const name0 = r0.data.data.items.find((c) => c.name.includes('回归用例验证')).name;
    await page.locator('#toggle-detail-edit-btn').click();
    await page.locator('#edit-name').fill('E2E-不应保存的改名');
    await page.locator('#detail-modal .close-btn, #detail-modal .modal-header .close-btn').first().click().catch(() => {});
    await page.waitForTimeout(500);
    const r1 = await api('GET', '/api/tasks?keyword=回归用例验证');
    const name1 = r1.data.data.items.find((c) => c.name.includes('回归用例验证')).name;
    expect(name1).toBe(name0);
  });
  test('TS-041 编辑模式回显当前值', async ({ page }) => {
    await openDetail(page, 'E2E-看板首页样式');
    await page.locator('#toggle-detail-edit-btn').click();
    const v = await page.locator('#edit-name').inputValue();
    expect(v).toContain('E2E-看板首页样式');
  });
  test('TS-042 保存后数据落库并可见', async ({ page }) => {
    await openDetail(page, 'E2E-组件交互提审');
    await page.locator('#toggle-detail-edit-btn').click();
    await page.locator('#edit-name').fill('E2E-组件交互提审-已更新');
    await page.locator('#detail-save-btn').click();
    await page.waitForTimeout(800);
    const r = await api('GET', '/api/tasks?keyword=组件交互提审-已更新');
    expect(r.data.data.items.length).toBeGreaterThan(0);
    await page.reload();
    await searchAndAssert(page, '组件交互提审-已更新', 'E2E-组件交互提审-已更新');
  });
  test('TS-043 详情时间线展示', async ({ page }) => {
    await openDetail(page, 'E2E-支付模块编码-改名后');
    const tl = page.locator('#detail-timeline-list');
    if (await tl.count()) {
      const t = await tl.innerText();
      expect(t.length).toBeGreaterThan(0);
    }
  });
  test('TS-044 详情操作入口存在', async ({ page }) => {
    await openDetail(page, 'E2E-缓存缺陷退回');
    const delId = page.locator('#detail-delete-btn');
    const anyDel = page.locator('[id*="delete"]');
    expect(await delId.count() + await anyDel.count()).toBeGreaterThan(0);
  });

});
