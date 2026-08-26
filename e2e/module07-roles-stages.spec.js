const { test, expect } = require('@playwright/test');
const { openBoard, api, dndCard, switchView, submitTransition } = require('./helpers');

async function currentCards() {
  const all = await api('GET', '/api/tasks?size=all');
  return all.data.data.items;
}

test.describe('模块7 · 负责角色 / 阶段工作包视图 (TS-071~078)', () => {
  test('TS-071 切换到负责角色视图', async ({ page }) => {
    await openBoard(page);
    await switchView(page, 'view-kanban-assignee');
    expect(await page.locator('#board-assignee .column').count()).toBeGreaterThan(0);
  });
  test('TS-072 角色分组正确', async ({ page }) => {
    await openBoard(page);
    const c = (await currentCards()).find((x) => String(x.assignee || '').includes('李开发'));
    expect(c).toBeTruthy();
    await switchView(page, 'view-kanban-assignee');
    const col = page.locator('#board-assignee .column[data-col="李开发"]');
    await expect(col).toContainText(c.name, { timeout: 5000 });
  });
  test('TS-073 角色负载计数', async ({ page }) => {
    await openBoard(page);
    const cards = await currentCards();
    const cnt = cards.filter((x) => String(x.assignee || '').includes('李开发')).length;
    await switchView(page, 'view-kanban-assignee');
    const col = page.locator('#board-assignee .column[data-col="李开发"]').first();
    const n = Number((await col.locator('.col-count').innerText()).trim());
    expect(n).toBe(cnt);
  });
  test('TS-074 角色视图拖拽到其他角色组', async ({ page }) => {
    await openBoard(page);
    const c = (await currentCards()).find((x) => String(x.assignee || '').includes('李开发'));
    expect(c).toBeTruthy();
    await switchView(page, 'view-kanban-assignee');
    await dndCard(page, c.id, '马前端', 'board-assignee');
    await page.waitForTimeout(400);
    await submitTransition(page, 'E2E 拖拽换负责人').catch(() => {});
    await page.waitForTimeout(800);
    const after = (await currentCards()).find((x) => x.id === c.id);
    expect(String(after.assignee || '')).toContain('马前端');
  });
  test('TS-075 切换到阶段工作包视图', async ({ page }) => {
    await openBoard(page);
    await switchView(page, 'view-kanban-stage');
    expect(await page.locator('#board-stage .column').count()).toBeGreaterThan(0);
  });
  test('TS-076 阶段分组正确', async ({ page }) => {
    await openBoard(page);
    const c = (await currentCards()).find((x) => String(x.stage || '').includes('S5 单元测试'));
    expect(c).toBeTruthy();
    await switchView(page, 'view-kanban-stage');
    const col = page.locator('#board-stage .column[data-col="S5 单元测试"]');
    await expect(col).toContainText(c.name, { timeout: 5000 });
  });
  test('TS-077 阶段分组计数', async ({ page }) => {
    await openBoard(page);
    const cards = await currentCards();
    const cnt = cards.filter((x) => String(x.stage || '').includes('S3 详细设计')).length;
    await switchView(page, 'view-kanban-stage');
    const col = page.locator('#board-stage .column[data-col="S3 详细设计"]').first();
    const n = Number((await col.locator('.col-count').innerText()).trim());
    expect(n).toBe(cnt);
  });
  test('TS-078 阶段视图往返不崩溃', async ({ page }) => {
    await openBoard(page);
    await switchView(page, 'view-kanban-stage');
    await switchView(page, 'view-table');
    await expect(page.locator('#main-data-table')).toBeVisible();
    await switchView(page, 'view-kanban-stage');
    expect(await page.locator('#board-stage .column').count()).toBeGreaterThan(0);
  });
});
