/* ============================================================
 * data.js
 * Part of offline_board.html
 * REST API client + LocalStorage offline fallback layer
 * Load order: util.js -> data.js -> listbox.js -> board.js -> app.js
 * ============================================================ */

// 默认兜底种子数据（初始化为空看板）
const defaultCardsData = [];

let rawCardsData = [];
let currentBoardVersion = "";
let isWriteInFlight = false;
let versionPollingTimer = null;
let activePollIntervalMs = 15000;  // 活跃状态 15 秒探测一次
let idlePollIntervalMs = 30000;    // 闲置状态 30 秒探测一次
let longIdlePollIntervalMs = 60000;// 深度闲置 60 秒探测一次
let lastUserActivity = Date.now();

let kanbanPreferences = {
    title: "多专家Agent协作任务看板",
    theme: "light",
    row_height: 55,
    card_visible_fields: ["id", "name", "assignee", "act_hours", "status"],
    card_field_config: null,
    column_widths: {},
    filters: null,
    sort: null
};

// -------------------------------------------------------------
// 1. 初始化偏好与数据加载
// -------------------------------------------------------------
async function loadStorageData() {
    await loadBoardPreferences();
    if (typeof restoreCardFieldConfig === 'function') {
        restoreCardFieldConfig();
    }
    if (typeof renderFieldConfigPopover === 'function') {
        renderFieldConfigPopover();
    }
    applyServerBoardTitle();
    await fetchKanbanTasksFromServer();
    if (typeof initRender === 'function') {
        initRender();
    }
    startVersionPolling();
}

async function loadBoardPreferences() {
    // 1. 本地存储快速恢复 (0ms 兜底)
    try {
        const localPref = localStorage.getItem('offline_board_preferences_v1');
        if (localPref) {
            const parsed = JSON.parse(localPref);
            if (parsed && typeof parsed === 'object') {
                kanbanPreferences = Object.assign({}, kanbanPreferences, parsed);
            }
        }
    } catch (e) {}

    // 2. 服务端拉取并深度合并最新偏好
    try {
        const res = await fetch('/api/board/meta?t=' + Date.now());
        if (res.ok) {
            const resp = await res.json();
            if (resp && resp.data && typeof resp.data === 'object') {
                const serverPref = resp.data;
                if (serverPref.filters) {
                    kanbanPreferences.filters = Object.assign({}, kanbanPreferences.filters || {}, serverPref.filters);
                }
                if (serverPref.sort) {
                    kanbanPreferences.sort = Object.assign({}, kanbanPreferences.sort || {}, serverPref.sort);
                }
                kanbanPreferences = Object.assign({}, kanbanPreferences, serverPref);
            }
        }
    } catch (e) {}
}

// 服务端标题应用：统一由服务端偏好/项目动态标题驱动
function applyServerBoardTitle() {
    const t = (kanbanPreferences.title || '').trim();
    if (t && typeof applyBoardTitle === 'function') {
        applyBoardTitle(t);
    }
}

let tableServerData = {
    items: [],
    total: 0,
    v: ""
};

async function fetchBackgroundData(isInitial = false) {
    // 默认通过服务端分页拉取表格首页数据（20条），不全量传输
    if (typeof loadTablePage === 'function') {
        await loadTablePage(1);
    }
}

/**
 * 真·服务端分页查询：向后端发起带有 page/size/sort/filter/keyword 的 HTTP GET 请求
 */
async function fetchTableTasksFromServer(params = {}) {
    const queryParts = [];
    
    const page = params.page || 1;
    const size = params.size || 20;
    queryParts.push(`page=${encodeURIComponent(page)}`);
    queryParts.push(`size=${encodeURIComponent(size)}`);

    if (params.status) queryParts.push(`status=${encodeURIComponent(params.status)}`);
    if (params.assignee) queryParts.push(`assignee=${encodeURIComponent(params.assignee)}`);
    if (params.stage) queryParts.push(`stage=${encodeURIComponent(params.stage)}`);
    if (params.wp) queryParts.push(`wp=${encodeURIComponent(params.wp)}`);
    if (params.handler) queryParts.push(`handler=${encodeURIComponent(params.handler)}`);
    if (params.creator) queryParts.push(`creator=${encodeURIComponent(params.creator)}`);
    if (params.start_from) queryParts.push(`start_from=${encodeURIComponent(params.start_from)}`);
    if (params.start_to) queryParts.push(`start_to=${encodeURIComponent(params.start_to)}`);
    if (params.end_from) queryParts.push(`end_from=${encodeURIComponent(params.end_from)}`);
    if (params.end_to) queryParts.push(`end_to=${encodeURIComponent(params.end_to)}`);
    if (params.keyword) queryParts.push(`keyword=${encodeURIComponent(params.keyword)}`);
    if (params.sort) queryParts.push(`sort=${encodeURIComponent(params.sort)}`);
    if (params.order) queryParts.push(`order=${encodeURIComponent(params.order)}`);
    queryParts.push(`t=${Date.now()}`);

    const qs = queryParts.join('&');
    const url = `/api/tasks?${qs}`;

    try {
        const res = await fetch(url);
        if (res.ok) {
            const resp = await res.json();
            if (resp && resp.data && Array.isArray(resp.data.items)) {
                tableServerData = {
                    items: resp.data.items,
                    total: resp.data.total !== undefined ? resp.data.total : resp.data.items.length,
                    v: resp.data.v || ""
                };
                if (resp.data.v) {
                    currentBoardVersion = resp.data.v;
                }
                return tableServerData;
            }
        }
    } catch (e) {
        console.warn('[API] /api/tasks table query offline fallback', e);
    }

    // 离线环境本地降级
    const stored = localStorage.getItem('offline_board_cards_v3');
    let localCards = [];
    if (stored) {
        try { localCards = JSON.parse(stored) || []; } catch (err) {}
    }
    tableServerData = {
        items: localCards.slice((page - 1) * (parseInt(size, 10) || 20), page * (parseInt(size, 10) || 20)),
        total: localCards.length,
        v: currentBoardVersion
    };
    return tableServerData;
}

/**
 * 看板视图按需拉取全量集（仅在切换到看板视图时触发）
 */
async function fetchKanbanTasksFromServer() {
    try {
        const res = await fetch('/api/tasks?size=all&t=' + Date.now());
        if (res.ok) {
            const resp = await res.json();
            if (resp && resp.data && Array.isArray(resp.data.items)) {
                rawCardsData = resp.data.items;
                if (resp.data.v) {
                    currentBoardVersion = resp.data.v;
                }
                try { localStorage.setItem('offline_board_cards_v3', JSON.stringify(rawCardsData)); } catch (e) {}
                return rawCardsData;
            }
        }
    } catch (err) {
        console.warn('[API] fetchKanbanTasksFromServer offline fallback', err);
    }

    const stored = localStorage.getItem('offline_board_cards_v3');
    if (stored) {
        try { rawCardsData = JSON.parse(stored) || []; } catch (e) {}
    }
    return rawCardsData;
}

// -------------------------------------------------------------
// 2. 自适应版本轮询 (GET /api/version)
// -------------------------------------------------------------
function startVersionPolling() {
    stopVersionPolling();
    scheduleNextVersionPoll();
}

function stopVersionPolling() {
    if (versionPollingTimer) {
        clearTimeout(versionPollingTimer);
        versionPollingTimer = null;
    }
}

function isUserActiveEditing() {
    // 检查是否有打开的任务详情/编辑弹窗，避免编辑中途中断
    const openModal = document.querySelector('.modal.show, #task-modal.show, #detail-modal.show, #export-modal.show');
    return Boolean(openModal);
}

function scheduleNextVersionPoll() {
    if (document.visibilityState === 'hidden') return;

    const now = Date.now();
    const idleDuration = now - lastUserActivity;
    let nextDelay = activePollIntervalMs;
    if (idleDuration > 120000) {
        nextDelay = longIdlePollIntervalMs;
    } else if (idleDuration > 30000) {
        nextDelay = idlePollIntervalMs;
    }

    versionPollingTimer = setTimeout(async () => {
        if (!isWriteInFlight && document.visibilityState === 'visible' && !isUserActiveEditing()) {
            await checkServerVersion();
        }
        scheduleNextVersionPoll();
    }, nextDelay);
}

async function checkServerVersion() {
    try {
        const res = await fetch('/api/version?t=' + Date.now());
        if (res.ok) {
            const resp = await res.json();
            if (resp && resp.data && resp.data.v) {
                const serverV = resp.data.v;
                if (currentBoardVersion && serverV !== currentBoardVersion) {
                    currentBoardVersion = serverV;
                    // 后台静默拉取并更新数据（用户处于非编辑状态时）
                    if (!isUserActiveEditing()) {
                        await fetchBackgroundData(false);
                    }
                } else {
                    currentBoardVersion = serverV;
                }
            }
        }
    } catch (e) {
        // 离线/服务暂未启动
    }
}

// 监听用户活跃动作（节流 5 秒更新一次时间戳）
if (typeof window !== 'undefined') {
    let lastActivityLog = 0;
    ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'].forEach(evt => {
        window.addEventListener(evt, () => {
            const now = Date.now();
            if (now - lastActivityLog > 5000) {
                lastUserActivity = now;
                lastActivityLog = now;
            }
        }, { passive: true });
    });

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            lastUserActivity = Date.now();
            checkServerVersion();
            startVersionPolling();
        } else {
            stopVersionPolling();
        }
    });
}

function handle409Conflict(conflictData) {
    if (conflictData && conflictData.v) {
        currentBoardVersion = conflictData.v;
    }
    if (typeof showToast === 'function') {
        showToast('检测到数据已被外部修改发生版本冲突，已自动为您重载最新看板！', 'warning');
    }
    fetchBackgroundData(false);
}

// -------------------------------------------------------------
// 3. 看板 REST API 接口封装 (带双层并发锁与 409 处理)
// -------------------------------------------------------------

/**
 * 接口 1: 创建新任务 (POST /api/tasks)
 */
async function apiCreateTask(cardData) {
    isWriteInFlight = true;
    try {
        const payload = Object.assign({}, cardData);
        if (currentBoardVersion) payload._v = currentBoardVersion;

        const headers = { 'Content-Type': 'application/json' };
        if (currentBoardVersion) headers['If-Match'] = currentBoardVersion;

        const res = await fetch('/api/tasks', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload)
        });
        const resp = await res.json();
        if (res.status === 409) {
            handle409Conflict(resp.data);
            throw new Error(resp.message || '版本冲突 (409)');
        }
        if (res.ok && resp && resp.data) {
            if (resp.data.v) currentBoardVersion = resp.data.v;
            return resp.data;
        } else {
            throw new Error(resp.message || `服务端返回状态码: ${res.status}`);
        }
    } catch (e) {
        if (e.message && (e.message.includes('已存在') || e.message.includes('不能为空') || e.message.includes('服务端返回') || e.message.includes('409'))) {
            throw e;
        }
        console.warn('[API] /api/tasks offline fallback', e);
    } finally {
        isWriteInFlight = false;
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
    isWriteInFlight = true;
    try {
        const payload = Object.assign({}, patchData);
        if (currentBoardVersion) payload._v = currentBoardVersion;

        const headers = { 'Content-Type': 'application/json' };
        if (currentBoardVersion) headers['If-Match'] = currentBoardVersion;

        const res = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
            method: 'PUT',
            headers: headers,
            body: JSON.stringify(payload)
        });
        const resp = await res.json();
        if (res.status === 409) {
            handle409Conflict(resp.data);
            return { ok: false, code: 409, message: resp.message, error: resp.message };
        }
        if (res.ok && resp) {
            if (resp.data && resp.data.v) currentBoardVersion = resp.data.v;
            return { ok: true, code: 200, message: resp.message, data: resp.data };
        }
        return { ok: false, code: res.status, message: resp.message, error: resp.message || `HTTP ${res.status}` };
    } catch (e) {
        console.warn(`[API] PUT /api/tasks/${taskId} offline`, e);
        return { ok: false, error: e.message || '网络连接异常' };
    } finally {
        isWriteInFlight = false;
    }
}

/**
 * 接口 3: 删除任务 (DELETE /api/tasks/{id})
 */
async function apiDeleteTask(taskId) {
    isWriteInFlight = true;
    try {
        const headers = {};
        if (currentBoardVersion) headers['If-Match'] = currentBoardVersion;

        const res = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
            method: 'DELETE',
            headers: headers
        });
        const resp = await res.json();
        if (res.status === 409) {
            handle409Conflict(resp.data);
            return { ok: false, code: 409, message: resp.message, error: resp.message };
        }
        if (res.ok && resp) {
            if (resp.data && resp.data.v) currentBoardVersion = resp.data.v;
            return { ok: true, code: 200, message: resp.message, data: resp.data };
        }
        return { ok: false, code: res.status, message: resp.message, error: resp.message || `HTTP ${res.status}` };
    } catch (e) {
        console.warn(`[API] DELETE /api/tasks/${taskId} offline`, e);
        return { ok: false, error: e.message || '网络连接异常' };
    } finally {
        isWriteInFlight = false;
    }
}

/**
 * 接口 4: 批量删除任务 (POST /api/tasks/batch-delete)
 */
async function apiBatchDeleteTasks(taskIds) {
    isWriteInFlight = true;
    try {
        const payload = { task_ids: taskIds };
        if (currentBoardVersion) payload._v = currentBoardVersion;

        const headers = { 'Content-Type': 'application/json' };
        if (currentBoardVersion) headers['If-Match'] = currentBoardVersion;

        const res = await fetch('/api/tasks/batch-delete', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload)
        });
        const resp = await res.json();
        if (res.status === 409) {
            handle409Conflict(resp.data);
            return { ok: false, code: 409, message: resp.message, error: resp.message };
        }
        if (res.ok && resp) {
            if (resp.data && resp.data.v) currentBoardVersion = resp.data.v;
            return { ok: true, code: 200, message: resp.message, data: resp.data };
        }
        return { ok: false, code: res.status, message: resp.message, error: resp.message || `HTTP ${res.status}` };
    } catch (e) {
        console.warn('[API] POST /api/tasks/batch-delete offline', e);
        return { ok: false, error: e.message || '网络连接异常' };
    } finally {
        isWriteInFlight = false;
    }
}

/**
 * 接口 5: 状态流转与审计落盘 (POST /api/tasks/{id}/transition)
 */
async function apiTransitionTask(taskId, transitionData, operator, note) {
    isWriteInFlight = true;
    try {
        let payload = {};
        if (typeof transitionData === 'string') {
            payload = {
                target_status: transitionData,
                operator_name: operator || 'Corey',
                comment: note || '快捷状态流转'
            };
        } else if (transitionData && typeof transitionData === 'object') {
            payload = Object.assign({}, transitionData);
        }
        if (currentBoardVersion) payload._v = currentBoardVersion;

        const headers = { 'Content-Type': 'application/json' };
        if (currentBoardVersion) headers['If-Match'] = currentBoardVersion;

        const res = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/transition`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload)
        });
        const resp = await res.json();
        if (res.status === 409) {
            handle409Conflict(resp.data);
            return { ok: false, code: 409, message: resp.message, error: resp.message };
        }
        if (res.ok && resp) {
            if (resp.data && resp.data.v) currentBoardVersion = resp.data.v;
            return { ok: true, code: 200, message: resp.message, data: resp.data };
        }
        return { ok: false, code: res.status, message: resp.message, error: resp.message || `HTTP ${res.status}` };
    } catch (e) {
        console.warn(`[API] POST /api/tasks/${taskId}/transition offline`, e);
        return { ok: false, error: e.message || '网络连接异常' };
    } finally {
        isWriteInFlight = false;
    }
}

/**
 * 接口 6: 拖拽重排序 (PUT /api/tasks/reorder)
 */
async function apiReorderTasks(orderedTaskIds) {
    isWriteInFlight = true;
    try {
        const payload = { ordered_task_ids: orderedTaskIds };
        if (currentBoardVersion) payload._v = currentBoardVersion;

        const headers = { 'Content-Type': 'application/json' };
        if (currentBoardVersion) headers['If-Match'] = currentBoardVersion;

        const res = await fetch('/api/tasks/reorder', {
            method: 'PUT',
            headers: headers,
            body: JSON.stringify(payload)
        });
        const resp = await res.json();
        if (res.status === 409) {
            handle409Conflict(resp.data);
            return resp;
        }
        if (res.ok && resp) {
            if (resp.data && resp.data.v) currentBoardVersion = resp.data.v;
            return resp;
        }
    } catch (e) {} finally {
        isWriteInFlight = false;
    }
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
// 4. 通用全量数据持久化 (保底兼容层)
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
    isWriteInFlight = true;
    try {
        const headers = { 'Content-Type': 'application/json' };
        if (currentBoardVersion) headers['If-Match'] = currentBoardVersion;

        const res = await fetch('./board.json', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(rawCardsData)
        });
        if (res.status === 409) {
            const resp = await res.json();
            handle409Conflict(resp.data);
        } else if (res.ok) {
            const resp = await res.json();
            if (resp && resp.data && resp.data.v) {
                currentBoardVersion = resp.data.v;
            }
        }
    } catch (e) {
    } finally {
        isSyncingToServer = false;
        isWriteInFlight = false;
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