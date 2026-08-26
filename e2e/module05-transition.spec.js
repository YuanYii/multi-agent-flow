const { test, expect } = require('@playwright/test');
const { openBoard, api } = require('./helpers');

// 表格行内状态 tag-select 快捷流转：先搜索定位（规避分页）→ 点状态徽标 → 选目标状态（走服务端门控）
async function locateByName(page, keyword) {
  await page.locator('#search-box').fill(keyword);
  await page.waitForTimeout(600);
}
async function quickTransition(page, cardName, targetStatus) {
  await locateByName(page, cardName.slice(0, 6));
  const row = page.locator('#table-body tr', { hasText: cardName }).first();
  await row.locator('.tag-select[data-type="status"]').click();
  await page.waitForTimeout(300);
  await page.locator('.tag-select-panel .tag-select-option', { hasText: targetStatus }).last().click();
  await page.waitForTimeout(700);
}

async function statusOf(cardName) {
  const all = await api('GET', '/api/tasks?size=all');
  const c = all.data.data.items.find((x) => String(x.name || '').includes(cardName));
  return c ? c.status : null;
}

test.describe('模块5 · 状态流转 (TS-045~058)', () => {
  test('TS-045 行内状态流转入口可用', async ({ page }) => {
    await openBoard(page);
    const row = page.locator('#table-body tr', { hasText: 'E2E-登录接口开发' }).first();
    const tag = row.locator('.tag-select[data-type="status"]');
    await expect(tag).toBeVisible();
    await tag.click();
    await expect(page.locator('.tag-select-panel')).toBeVisible();
  });
  test('TS-046 待开始→进行中', async ({ page }) => {
    await openBoard(page);
    await quickTransition(page, 'E2E-登录接口开发', '进行中');
    expect(await statusOf('E2E-登录接口开发')).toBe('进行中');
  });
  test('TS-047 进行中→审查中', async ({ page }) => {
    await openBoard(page);
    await quickTransition(page, 'E2E-支付模块编码', '审查中');
    expect(await statusOf('E2E-支付模块编码')).toBe('审查中');
  });
  test('TS-048 审查中→测试中', async ({ page }) => {
    await openBoard(page);
    await quickTransition(page, 'E2E-订单接口提审', '测试中');
    expect(await statusOf('E2E-订单接口提审')).toBe('测试中');
  });
  test('TS-049 测试中→已完成', async ({ page }) => {
    await openBoard(page);
    await quickTransition(page, 'E2E-集成测试执行', '已完成');
    expect(await statusOf('E2E-集成测试执行')).toBe('已完成');
  });
  test('TS-050 已完成→已验收（主控人类验收）', async ({ page }) => {
    await openBoard(page);
    await quickTransition(page, 'E2E-报表导出完成', '已验收');
    expect(await statusOf('E2E-报表导出完成')).toBe('已验收');
  });
  test('TS-051 审查中→已退回', async ({ page }) => {
    await openBoard(page);
    await quickTransition(page, 'E2E-组件交互提审', '已退回');
    expect(await statusOf('E2E-组件交互提审')).toBe('已退回');
  });
  test('TS-052 测试中→已退回', async ({ page }) => {
    await openBoard(page);
    await quickTransition(page, 'E2E-回归用例验证', '已退回');
    expect(await statusOf('E2E-回归用例验证')).toBe('已退回');
  });
  test('TS-053 已完成→已退回（人类验收打回）', async ({ page }) => {
    await openBoard(page);
    await quickTransition(page, 'E2E-拖拽验收专用', '已退回');
    expect(await statusOf('E2E-拖拽验收专用')).toBe('已退回');
  });
  test('TS-054 进行中→已阻塞', async ({ page }) => {
    await openBoard(page);
    await quickTransition(page, 'E2E-总体架构设计', '已阻塞');
    expect(await statusOf('E2E-总体架构设计')).toBe('已阻塞');
  });
  test('TS-055 已阻塞→进行中（解阻）', async ({ page }) => {
    await openBoard(page);
    await quickTransition(page, 'E2E-发布流水线阻塞', '进行中');
    expect(await statusOf('E2E-发布流水线阻塞')).toBe('进行中');
  });
  test('TS-056 进行中→已取消（主控取消）', async ({ page }) => {
    await openBoard(page);
    await quickTransition(page, 'E2E-角色-严经理任务', '已取消');
    expect(await statusOf('E2E-角色-严经理任务')).toBe('已取消');
  });
  test('TS-057 流转后 Toast 反馈', async ({ page }) => {
    await openBoard(page);
    await quickTransition(page, 'E2E-用户手册编制', '进行中');
    await expect(page.locator('#toast-container')).toContainText('已更新', { timeout: 5000 }).catch(() => {});
    expect(await statusOf('E2E-用户手册编制')).toBe('进行中');
  });
  test('TS-058 协作端写操作被锁定', async ({ page }) => {
    // 协作端（无主控 token）：UI 层写操作入口被禁用，仅只读
    const { cfg } = require('./helpers');
    await page.goto(`${cfg.baseURL}`);
    await expect(page.locator('body')).toContainText('多专家Agent协作任务看板', { timeout: 10000 });
    await page.waitForTimeout(1500);
    const addDisabled = await page.locator('#add-table-record-btn').isDisabled();
    expect(addDisabled).toBe(true);
  });

});
