/* ============================================================
 * data.js
 * Part of offline_board.html (Pure Static MVP Edition)
 * Seed dataset + pure client-side JSON loader & import/export
 * Load order: util.js -> data.js -> listbox.js -> board.js -> app.js
 * ============================================================ */
// 1. Raw Initial Dataset & Standalone JSON Loader (Default Seed Task T0000)
const defaultCardsData = [
    {
        id: "T0000",
        seq: 1,
        name: "架构分析",
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
    await fetchBackgroundData();
}

async function fetchBackgroundData() {
    // 1. 尝试从本地相对路径 board.json 异步拉取 (HTTP 服务环境下)
    try {
        const res = await fetch('./board.json?t=' + Date.now());
        if (res.ok) {
            const fileData = await res.json();
            if (Array.isArray(fileData) && fileData.length > 0) {
                rawCardsData = fileData;
                localStorage.setItem('offline_board_cards_v3', JSON.stringify(rawCardsData));
                applyFilters();
                return;
            }
        }
    } catch (err) {
        // file:// 协议或跨域安全拦截时静默进入本地降级模式
    }

    // 2. 尝试从 localStorage 本地缓存读取
    const stored = localStorage.getItem('offline_board_cards_v3');
    if (stored) {
        try {
            const parsed = JSON.parse(stored);
            if (Array.isArray(parsed) && parsed.length > 0) {
                rawCardsData = parsed;
                applyFilters();
                return;
            }
        } catch (e) {}
    }

    // 3. 兜底使用初始种子数据 (T0000 任务)
    if (!Array.isArray(rawCardsData) || rawCardsData.length === 0) {
        rawCardsData = JSON.parse(JSON.stringify(defaultCardsData));
    }
    applyFilters();
}

function saveStorageData() {
    localStorage.setItem('offline_board_cards_v3', JSON.stringify(rawCardsData));
}

/**
 * 纯静态客户端导出: 将当前看板全量卡片生成 board.json 并触发浏览器文件下载
 */
function exportBoardJSON() {
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
        showToast('已成功导出 board.json 文件！');
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
            let importedCards = [];

            if (Array.isArray(parsed)) {
                importedCards = parsed;
            } else if (parsed && Array.isArray(parsed.cards)) {
                importedCards = parsed.cards;
            } else {
                throw new Error('JSON 数据格式不符合看板规范（必须为任务数组或包含 cards 属性）');
            }

            if (importedCards.length === 0) {
                throw new Error('导入的 JSON 文件中未包含任何任务数据');
            }

            rawCardsData = importedCards;
            saveStorageData();
            applyFilters();
            showToast(`成功导入 ${importedCards.length} 条任务数据！`);
        } catch (err) {
            alert('导入 JSON 失败: ' + err.message);
        }
    };
    reader.readAsText(file, 'utf-8');
}