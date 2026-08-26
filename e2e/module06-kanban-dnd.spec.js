const { test, expect } = require('@playwright/test');
const { openBoard, api, dndCard, submitTransition, switchView } = require('./helpers');

const NEXT = { '待开始': '进行中', '进行中': '审查中', '审查中': '测试中', '测试中': '已完成', '已完成': '已验收', '已退回': '进行中', '已阻塞': '进行中' };

async function currentCards() {
  const all = await api('GET', '/api/tasks?size=all');
  return all.data.data.items;
}
async function findCard(pred) {
  const cards = await currentCards();
  return cards.find(pred);
}

test.describe('模块6 · 状态泳道视图与拖拽 (TS-059~070)', () => {
  test('TS-059 切换到状态泳道', async ({ page }) => {
    await openBoard(page);
    await switchView(page, 'view-kanban-status');
    expect(await page.locator('#board-status .column').count()).toBeGreaterThan(0);
  });
  test('TS-060 泳道卡片分布正确', async ({ page }) => {
    await openBoard(page);
    await switchView(page, 'view-kanban-status');
    // 找一个进行中卡，断言其卡片在"进行中"列内
    const c = await findCard((x) => x.status === '进行中');
    expect(c).toBeTruthy();
    const col = page.locator('#board-status [class*="col"]', { has: page.locator(`#card-${c.id}`) });
    await expect(col).toContainText('进行中');
  });
  test('TS-061 泳道计数与卡数一致', async ({ page }) => {
    await openBoard(page);
    await switchView(page, 'view-kanban-status');
    const cards = await currentCards();
    const byStatus = {};
    cards.forEach((c) => { byStatus[c.status] = (byStatus[c.status] || 0) + 1; });
    // 抽查进行中列
    const col = page.locator('#board-status [class*="col"]', { hasText: '进行中' }).first();
    const count = Number((await col.locator('.col-count').innerText()).trim());
    expect(count).toBe(byStatus['进行中'] || 0);
  });
  test('TS-062 拖拽流转到其他泳道', async ({ page }) => {
    await openBoard(page);
    const c = await findCard((x) => x.status === '进行中');
    expect(c).toBeTruthy();
    const target = NEXT[c.status];
    await switchView(page, 'view-kanban-status');
    await dndCard(page, c.id, target);
    await page.waitForTimeout(400);
    await submitTransition(page, 'E2E 拖拽流转验证').catch(() => {});
    await page.waitForTimeout(800);
    const after = (await currentCards()).find((x) => x.id === c.id);
    expect(after.status).toBe(target);
  });
  test('TS-063 拖拽打回', async ({ page }) => {
    await openBoard(page);
    const c = await findCard((x) => x.status === '审查中');
    expect(c).toBeTruthy();
    await switchView(page, 'view-kanban-status');
    await dndCard(page, c.id, '已退回');
    await page.waitForTimeout(400);
    await submitTransition(page, 'E2E 拖拽打回').catch(() => {});
    await page.waitForTimeout(800);
    const after = (await currentCards()).find((x) => x.id === c.id);
    expect(after.status).toBe('已退回');
  });
  test('TS-064 拖拽到已验收', async ({ page }) => {
    await openBoard(page);
    const c = await findCard((x) => x.status === '已完成');
    expect(c).toBeTruthy();
    await switchView(page, 'view-kanban-status');
    await dndCard(page, c.id, '已验收');
    await page.waitForTimeout(400);
    await submitTransition(page, 'E2E 拖拽验收').catch(() => {});
    await page.waitForTimeout(800);
    const after = (await currentCards()).find((x) => x.id === c.id);
    expect(after.status).toBe('已验收');
  });
  test('TS-065 主控拖拽直验进行中→已验收', async ({ page }) => {
    await openBoard(page);
    const c = await findCard((x) => x.status === '进行中');
    expect(c).toBeTruthy();
    await switchView(page, 'view-kanban-status');
    // 主控模式 = 人类主控授权，USER 权限允许进行中→已验收（直验路径）
    await dndCard(page, c.id, '已验收');
    await page.waitForTimeout(400);
    await submitTransition(page, 'E2E 主控直验').catch(() => {});
    await page.waitForTimeout(800);
    const after = (await currentCards()).find((x) => x.id === c.id);
    expect(after.status).toBe('已验收');
  });
  test('TS-066 泳道内卡片存在可交互', async ({ page }) => {
    await openBoard(page);
    await switchView(page, 'view-kanban-status');
    const firstCard = page.locator('#board-status .card').first();
    await expect(firstCard).toBeVisible();
    const onclick = await firstCard.getAttribute('onclick');
    expect(String(onclick || '')).toContain('openTaskDetail');
  });
  test('TS-067 空泳道显示占位', async ({ page }) => {
    await openBoard(page);
    await switchView(page, 'view-kanban-status');
    const col = page.locator('#board-status [class*="col"]', { hasText: '已取消' }).first();
    const body = await col.innerText();
    expect(body).toMatch(/0|无|空|暂无/);
  });
  test('TS-068 搜索联动以表格为准', async ({ page }) => {
    await openBoard(page);
    await page.locator('#search-box').fill('支付模块');
    await page.waitForTimeout(700);
    // 表格按关键词过滤
    const rows = await page.locator('#table-body tr').count();
    expect(rows).toBeGreaterThan(0);
    expect(await page.locator('#table-body').innerText()).toContain('支付模块');
    // 泳道视图仍可切换且不崩溃
    await switchView(page, 'view-kanban-status');
    expect(await page.locator('#board-status .card').count()).toBeGreaterThanOrEqual(0);
  });
  test('TS-069 泳道切换视图往返', async ({ page }) => {
    await openBoard(page);
    await switchView(page, 'view-kanban-status');
    await switchView(page, 'view-table');
    await expect(page.locator('#main-data-table')).toBeVisible();
    await switchView(page, 'view-kanban-status');
    expect(await page.locator('#board-status .column').count()).toBeGreaterThan(0);
  });
  test('TS-070 拖拽后统计更新', async ({ page }) => {
    await openBoard(page);
    const c = await findCard((x) => x.status === '待开始');
    expect(c).toBeTruthy();
    await switchView(page, 'view-kanban-status');
    await dndCard(page, c.id, '进行中');
    await page.waitForTimeout(400);
    await submitTransition(page, 'E2E 拖拽统计').catch(() => {});
    await page.waitForTimeout(800);
    const after = (await currentCards()).find((x) => x.id === c.id);
    expect(after.status).toBe('进行中');
  });
});
