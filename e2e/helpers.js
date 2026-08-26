const { expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const cfg = JSON.parse(fs.readFileSync(path.resolve(__dirname, '.runtime/config.json'), 'utf-8'));

async function api(method, urlPath, body, token = cfg.masterToken) {
  const res = await fetch(`${cfg.baseURL}${urlPath}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Master-Token': token,
      'X-Device-Name': 'E2E-Client',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  return { status: res.status, data };
}

async function openBoard(page, { master = true } = {}) {
  const url = master ? `${cfg.baseURL}/?token=${cfg.masterToken}` : cfg.baseURL;
  await page.goto(url);
  await expect(page.locator('body')).toContainText('多专家Agent协作任务看板', { timeout: 10000 });
  // 等待表格数据与行渲染就绪（避免读初始空值）
  await page.waitForFunction(() => {
    const el = document.getElementById('total-count');
    return el && Number(el.innerText) > 0 && document.querySelectorAll('#table-body tr').length > 0;
  }, { timeout: 15000 });
  return page;
}

// 自定义 listbox 增强下拉：点开 trigger → 点选项文本（原生 select 为 aria-hidden 不可直接 selectOption）
async function selectUi(page, nativeId, label) {
  const wrap = page.locator(`#${nativeId}`).locator('..');
  // 尝试最多 2 次点击打开面板并选择；失败则回退到原生 select change 事件
  for (let i = 0; i < 2; i++) {
    await wrap.locator('.ui-select-trigger').click().catch(() => {});
    await page.waitForTimeout(350);
    const opt = page.locator('[role="option"]', { hasText: label }).last();
    if (await opt.count()) {
      try { await opt.click(); await page.waitForTimeout(250); return; } catch (e) { /* fallthrough */ }
    }
    await page.keyboard.press('Escape').catch(() => {});
  }
  await page.locator(`#${nativeId}`).evaluate((el, lbl) => {
    const target = Array.from(el.options).find((o) => o.textContent.includes(lbl));
    if (target) { el.value = target.value; el.dispatchEvent(new Event('change', { bubbles: true })); }
  }, label);
  await page.waitForTimeout(250);
}

// HTML5 拖拽：从卡片 #card-<id> 拖到目标列（列内包含指定标题文本）
async function dndCard(page, cardId, columnTitle, containerId = 'board-status') {
  return page.evaluate(({ cardId, columnTitle, containerId }) => {
    const src = document.getElementById(`card-${cardId}`);
    if (!src) throw new Error(`card-${cardId} 不存在`);
    // drop 监听绑定在 .column 内的 .card-list 上（事件不向上冒泡，须直接作用目标层）
    const dst = document.querySelector(`#${containerId} .column[data-col="${columnTitle}"] .card-list`);
    if (!dst) throw new Error(`目标列 ${columnTitle} 的 card-list 不存在`);
    const dt = new DataTransfer();
    src.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
    dst.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true }));
    dst.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true }));
    dst.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true }));
    src.dispatchEvent(new DragEvent('dragend', { dataTransfer: dt, bubbles: true }));
    return true;
  }, { cardId, columnTitle, containerId });
}

async function submitTransition(page, comment) {
  await expect(page.locator('#transition-modal')).toBeVisible();
  if (comment) await page.locator('#transition-comment-input').fill(comment);
  await page.getByText('确认流转并记录', { exact: true }).click();
  await expect(page.locator('#transition-modal')).toBeHidden();
}

// tag-select 组件（hidden input + 标签选择器，用于人员/状态等）
async function selectTag(page, targetId, label) {
  await page.locator(`.tag-select[data-target="${targetId}"]`).click();
  await page.waitForTimeout(300);
  await page.locator('.tag-select-panel .tag-select-option', { hasText: label }).last().click();
  await page.waitForTimeout(250);
}

// 创建任务：打开弹窗 → 填名 → 选阶段(select)/人员·状态(tag) → 提交 → 等待总数+1
async function createTask(page, { name, stage = 'S3 详细设计', assignee = '李开发', status = null }) {
  const before = Number(await page.locator('#total-count').innerText());
  await page.locator('#add-table-record-btn').click();
  await expect(page.locator('#add-modal')).toBeVisible();
  await page.locator('#new-name').fill(name);
  if (stage) await selectUi(page, 'new-stage', stage);
  if (assignee) await selectTag(page, 'new-assignee', assignee);
  if (status) await selectTag(page, 'new-status', status);
  await page.getByText('提交保存', { exact: true }).click();
  await expect(page.locator('#total-count')).toHaveText(String(before + 1), { timeout: 10000 });
  return before + 1;
}

// 搜索框过滤后断言表格包含目标文本（规避分页导致新卡不在首屏）
async function searchAndAssert(page, keyword, text) {
  await page.locator('#search-box').fill(keyword);
  await page.waitForTimeout(600);
  await expect(page.locator('#table-body')).toContainText(text, { timeout: 5000 });
}

// 视图切换：点击 header 的 tab 按钮（data-target 指向视图容器）
async function switchView(page, viewId) {
  await page.locator(`.tab[data-target="${viewId}"]`).click();
  await page.waitForTimeout(800);
}

module.exports = { cfg, api, openBoard, dndCard, submitTransition, selectUi, selectTag, createTask, searchAndAssert, switchView };
