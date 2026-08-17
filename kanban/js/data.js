/* ============================================================
 * data.js
 * Part of offline_board.html
 * REST API client + LocalStorage offline fallback layer
 * Load order: util.js -> data.js -> listbox.js -> board.js -> app.js
 * ============================================================ */

// 默认兜底种子数据
const defaultCardsData = [
    {
        id: "T0000",
        seq: 1,
        name: "架构分析与系统设计",
        status: "进行中",
        assignee: "钱架构",
        handler: "钱架构",
        stage: "S1 需求分析与系统架构设计",
        wp: "工作包1: 架构解耦与设计",
        wbs: "1.1",
        start_date: "2026-08-14 09:00:00",
        end_date: "2026-08-15 18:00:00",
        est_hours: 8,
        act_hours: 2,
        remarks: "执行系统解耦分析与 ADR 架构决策制定",
        process: "[2026-08-14 09:00:00] [系统初始化] 任务 [T0000] 已推入看板，当前状态【待开始】，负责人: 钱架构\n[2026-08-14 09:30:00] [钱架构] 领取任务并开始执行，状态由【待开始】更新至【进行中】"
    }
];

let rawCardsData = [];
let kanbanMetaConfig = null;
let kanbanPreferences = {
    title: "多专家Agent协作任务看板",
    theme: "light",
    row_height: 55,
    card_visible_fields: ["id", "name", "assignee", "est_hours", "status"],
    column_widths: {}
};

// -------------------------------------------------------------
// 1. 初始化元数据与数据加载
// -------------------------------------------------------------
async function fetchKanbanMetaConfig() {
    try {
        const res = await fetch('./json/kanban_meta.json?t=' + Date.now());
        if (res.ok) {
            kanbanMetaConfig = await res.json();
        }
    } catch (err) {}
}

async function loadStorageData() {
    await fetchKanbanMetaConfig();
    await loadBoardPreferences();
    applyServerBoardTitle();
    await fetchBackgroundData();
}

async function loadBoardPreferences() {
    try {
        const res = await fetch('/api/board/meta?t=' + Date.now());
        if (res.ok) {
            const resp = await res.json();
            if (resp && resp.data && typeof resp.data === 'object') {
                kanbanPreferences = Object.assign(kanbanPreferences, resp.data);
                return;
            }
        }
    } catch (e) {}

    // 本地存储兜底
    try {
        const localPref = localStorage.getItem('offline_board_preferences_v1');
        if (localPref) {
            kanbanPreferences = Object.assign(kanbanPreferences, JSON.parse(localPref));
        }
    } catch (e) {}
}

// 服务端标题应用：用户未在本地编辑过标题时，采用服务端偏好（含项目名动态默认）。
// 本地编辑过（localStorage 有 offline_board_title_v1）则尊重本地定制，服务端不覆盖。
function applyServerBoardTitle() {
    try {
        if (localStorage.getItem('offline_board_title_v1')) return; // 用户定制优先
    } catch (e) {}
    const t = (kanbanPreferences.title || '').trim();
    if (t && typeof applyBoardTitle === 'function') {
        applyBoardTitle(t);
    }
}

async function fetchBackgroundData() {
    // 1. 优先通过 REST API /api/tasks 获取
    try {
        const res = await fetch('/api/tasks?t=' + Date.now());
        if (res.ok) {
            const resp = await res.json();
            if (resp && resp.data && Array.isArray(resp.data.items) && resp.data.items.length > 0) {
                rawCardsData = resp.data.items;
                localStorage.setItem('offline_board_cards_v3', JSON.stringify(rawCardsData));
                if (typeof initRender === 'function') initRender();
                applyFilters();
                return;
            }
        }
    } catch (err) {}

    // 2. 向后兼容 /board.json 读取
    try {
        const res = await fetch('./board.json?t=' + Date.now());
        if (res.ok) {
            const fileData = await res.json();
            if (Array.isArray(fileData) && fileData.length > 0) {
                rawCardsData = fileData;
                localStorage.setItem('offline_board_cards_v3', JSON.stringify(rawCardsData));
                if (typeof initRender === 'function') initRender();
                applyFilters();
                return;
            }
        }
    } catch (err) {}

    // 3. 本地 LocalStorage 降级
    const stored = localStorage.getItem('offline_board_cards_v3');
    if (stored) {
        try {
            const parsed = JSON.parse(stored);
            if (Array.isArray(parsed) && parsed.length > 0) {
                rawCardsData = parsed;
                if (typeof initRender === 'function') initRender();
                applyFilters();
                return;
            }
        } catch (e) {}
    }

    // 4. 默认种子数据兜底
    if (!Array.isArray(rawCardsData) || rawCardsData.length === 0) {
        rawCardsData = JSON.parse(JSON.stringify(defaultCardsData));
    }
    if (typeof initRender === 'function') initRender();
    applyFilters();
}

// -------------------------------------------------------------
// 2. 看板 REST API 接口封装 (带优雅降级)
// -------------------------------------------------------------

/**
 * 接口 1: 创建新任务 (POST /api/tasks)
 */
async function apiCreateTask(cardData) {
    try {
        const res = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(cardData)
        });
        const resp = await res.json();
        if (res.ok && resp && resp.data) {
            return resp.data;
        } else {
            throw new Error(resp.message || `服务端返回状态码: ${res.status}`);
        }
    } catch (e) {
        if (e.message && (e.message.includes('已存在') || e.message.includes('不能为空') || e.message.includes('服务端返回'))) {
            throw e;
        }
        console.warn('[API] /api/tasks offline fallback', e);
    }

    // 离线环境本地自增与保存兜底
    if (!cardData.id) {
        let maxId = 0;
        rawCardsData.forEach(c => {
            const m = String(c.id || '').match(/^T(\d+)$/);
            if (m) maxId = Math.max(maxId, parseInt(m[1], 10));
        });
        cardData.id = `T${String(maxId + 1).padStart(4, '0')}`;
    }
    cardData.seq = rawCardsData.length + 1;
    return cardData;
}

/**
 * 接口 2: 更新任务详情 (PUT /api/tasks/{id})
 */
async function apiUpdateTask(taskId, patchData) {
    try {
        const res = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(patchData)
        });
        if (res.ok) {
            return await res.json();
        }
    } catch (e) {
        console.warn(`[API] PUT /api/tasks/${taskId} offline`, e);
    }
    return { code: 200, message: "本地更新完成" };
}

/**
 * 接口 3: 删除任务 (DELETE /api/tasks/{id})
 */
async function apiDeleteTask(taskId) {
    try {
        const res = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            return await res.json();
        }
    } catch (e) {
        console.warn(`[API] DELETE /api/tasks/${taskId} offline`, e);
    }
    return { code: 200, message: "本地删除完成" };
}

/**
 * 接口 4: 批量删除任务 (POST /api/tasks/batch-delete)
 */
async function apiBatchDeleteTasks(taskIds) {
    try {
        const res = await fetch('/api/tasks/batch-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_ids: taskIds })
        });
        if (res.ok) {
            return await res.json();
        }
    } catch (e) {
        console.warn('[API] POST /api/tasks/batch-delete offline', e);
    }
    return { code: 200, message: "本地批量删除完成" };
}

/**
 * 接口 5: 状态流转与审计落盘 (POST /api/tasks/{id}/transition)
 */
async function apiTransitionTask(taskId, transitionData) {
    try {
        const res = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/transition`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(transitionData)
        });
        if (res.ok) {
            return await res.json();
        }
    } catch (e) {
        console.warn(`[API] POST /api/tasks/${taskId}/transition offline`, e);
    }
    return { code: 200, message: "本地流转完成" };
}

/**
 * 接口 6: 拖拽重排序 (PUT /api/tasks/reorder)
 */
async function apiReorderTasks(orderedTaskIds) {
    try {
        const res = await fetch('/api/tasks/reorder', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ordered_task_ids: orderedTaskIds })
        });
        if (res.ok) {
            return await res.json();
        }
    } catch (e) {}
    return { code: 200, message: "本地重排完成" };
}

/**
 * 接口 7: 保存看板主标题与布局偏好 (PUT /api/board/meta)
 */
async function apiSaveBoardMeta(prefData) {
    kanbanPreferences = Object.assign(kanbanPreferences, prefData);
    try {
        localStorage.setItem('offline_board_preferences_v1', JSON.stringify(kanbanPreferences));
    } catch (e) {}

    try {
        await fetch('/api/board/meta', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(kanbanPreferences)
        });
    } catch (e) {}
}

// -------------------------------------------------------------
// 3. 通用全量数据持久化 (保底兼容层)
// -------------------------------------------------------------
let isSyncingToServer = false;
let pendingSyncData = null;

function saveStorageData() {
    try {
        localStorage.setItem('offline_board_cards_v3', JSON.stringify(rawCardsData));
    } catch (e) {}
    syncBoardDataToServer();
}

async function syncBoardDataToServer() {
    if (isSyncingToServer) {
        pendingSyncData = JSON.parse(JSON.stringify(rawCardsData));
        return;
    }

    isSyncingToServer = true;
    try {
        await fetch('./board.json', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(rawCardsData)
        });
    } catch (e) {
    } finally {
        isSyncingToServer = false;
        if (pendingSyncData) {
            const nextData = pendingSyncData;
            pendingSyncData = null;
            rawCardsData = nextData;
            syncBoardDataToServer();
        }
    }
}

/**
 * 纯静态客户端导出: 唤起导出确认与说明模态弹窗
 */
function exportBoardJSON() {
    openExportModal();
}

function openExportModal() {
    const countEl = document.getElementById('export-task-count');
    if (countEl) {
        countEl.innerText = rawCardsData.length;
    }
    const modal = document.getElementById('export-modal');
    if (modal) {
        modal.classList.add('show');
    }
}

function closeExportModal() {
    const modal = document.getElementById('export-modal');
    if (modal) {
        modal.classList.remove('show');
    }
}

/**
 * 用户在弹窗确认后执行真正的文件下载
 */
function confirmAndExecuteExport() {
    try {
        const dataStr = JSON.stringify(rawCardsData, null, 2);
        const blob = new Blob([dataStr], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'board.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        closeExportModal();
        showToast(`已成功导出 ${rawCardsData.length} 项任务至 board.json 文件！`);
    } catch (err) {
        alert('导出 JSON 失败: ' + err.message);
    }
}

/**
 * 纯静态客户端导入: 选择本地 board.json 文件并解析载入
 */
function triggerImportJSON() {
    const input = document.getElementById('import-json-file-input');
    if (input) {
        input.value = '';
        input.click();
    }
}

function handleImportJSON(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            const content = e.target.result;
            const parsed = JSON.parse(content);
            if (!Array.isArray(parsed)) {
                throw new Error('JSON 根结构必须为任务数组 (Array)');
            }
            rawCardsData = parsed;
            saveStorageData();
            applyFilters();
            showToast(`成功导入 ${parsed.length} 条任务数据！`);
        } catch (err) {
            alert('解析并导入 JSON 失败: ' + err.message);
        }
    };
    reader.readAsText(file, 'utf-8');
}