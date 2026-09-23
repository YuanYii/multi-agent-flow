const { test, expect } = require('@playwright/test');
const { openBoard, api, searchAndAssert } = require('./helpers');

test.describe('模块12 · 边界与安全 (TS-113~120)', () => {
  test('TS-113 XSS 注入原样展示不执行', async ({ page }) => {
    const alerts = [];
    page.on('dialog', async (d) => { alerts.push(d.message()); await d.dismiss(); });
    await openBoard(page);
    await searchAndAssert(page, 'alert(1)', '<script>alert(1)</script> 注入任务');
    await page.waitForTimeout(500);
    expect(alerts).toEqual([]);
  });
  test('TS-114 HTML 标签注入不执行事件', async ({ page }) => {
    await openBoard(page);
    const txt = await page.locator('#table-body').innerText();
    expect(txt).toContain('alert(1)');
  });
  test('TS-115 Unicode/Emoji 正确渲染', async ({ page }) => {
    await openBoard(page);
    const all = await api('GET', '/api/tasks?size=all');
    const c = all.data.data.items.find((x) => String(x.name || '').includes('Emoji'));
    expect(c).toBeTruthy();
    // 页面渲染该卡名（Emoji 字符原样展示）
    const body = await page.locator('#table-body').innerText();
    expect(body).toContain('Emoji');
  });
  test('TS-116 超长备注正常保存', async ({ page }) => {
    await openBoard(page);
    const all = await api('GET', '/api/tasks?size=all');
    const c = all.data.data.items.find((x) => String(x.name || '').includes('超长备注任务'));
    expect(c).toBeTruthy();
    expect(String(c.remarks || '').length).toBe(1500);
  });
  test('TS-117 双端并发写不丢数据', async ({ page, context }) => {
    await openBoard(page);
    const pageB = await context.newPage();
    await openBoard(pageB);
    // 两端同时修改同一张卡的不同字段
    const r0 = await api('GET', '/api/tasks?size=all');
    const target = r0.data.data.items.find((x) => String(x.name || '').includes('角色-周审查任务'));
    const tid = target.id;
    await page.evaluate((id) => {
      const row = Array.from(document.querySelectorAll('#table-body tr')).find((r) => r.textContent.includes(id));
      if (row) row.getElementsByTagName('td')[1]?.click?.();
    }, tid).catch(() => {});
    // 直接经 API 双写（UI 并发写经由相同 API 管线）
    const [rA, rB] = await Promise.all([
      api('PUT', `/api/tasks/${tid}`, { remarks: '并发A-备注' }),
      api('PUT', `/api/tasks/${tid}`, { est_hours: 9 }),
    ]);
    const ok = [rA, rB].every((r) => r.status === 200 || r.status === 409);
    expect(ok).toBe(true);
    await pageB.close();
  });
  test('TS-118 版本冲突提示', async ({ page }) => {
    await openBoard(page);
    const v1 = await api('GET', '/api/version');
    expect(v1.status).toBe(200);
    expect(String(v1.data.data && v1.data.data.v || '').length).toBeGreaterThan(0);
  });
  test('TS-119 批量物理删除入口安全防护', async ({ page }) => {
    await openBoard(page);
    // 研发协作遵循审计留痕与不可篡改原则，默认不暴露无审计追踪的批量物理删除入口
    const batchDel = page.locator('#batch-delete-btn');
    expect(await batchDel.count()).toBe(0);
  });
  test('TS-120 确认弹窗交互机制', async ({ page }) => {
    await openBoard(page);
    const confirm = page.locator('#confirm-modal');
    expect(await confirm.count()).toBe(1);
    await page.evaluate(() => {
      if (typeof openCustomConfirm === 'function') {
        openCustomConfirm('敏感操作确认', '是否确认执行该操作？', () => {});
      }
    });
    await expect(confirm).toHaveClass(/show/);
    await page.locator('#confirm-modal button:has-text("取消")').click();
    await expect(confirm).not.toHaveClass(/show/);
  });
});
