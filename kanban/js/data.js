/* ============================================================
 * data.js
 * Part of offline_board.html (split for maintainability)
 * Seed dataset + storage/person-state loaders
 * Load order: util.js -> data.js -> listbox.js -> board.js -> app.js
 * ============================================================ */
        // 1. Raw Initial Dataset & Standalone JSON Loader (Default Seed Task T9999)
        const defaultCardsData = [
            {
                id: "T9999",
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
                process: "[2026-08-14 09:00:00] [系统初始化] 任务 [T9999] 已推入看板，当前状态【待开始】，负责人: 钱架构\n[2026-08-14 09:30:00] [钱架构] 领取任务并开始执行，状态由【待开始】更新至【进行中】"
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
            } catch (err) {}

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
            if (!Array.isArray(rawCardsData) || rawCardsData.length === 0) {
                rawCardsData = JSON.parse(JSON.stringify(defaultCardsData));
            }
            applyFilters();
        }

        function saveStorageData() {
            localStorage.setItem('offline_board_cards_v3', JSON.stringify(rawCardsData));
        }