/* ============================================================
 * data.js
 * Part of offline_board.html (split for maintainability)
 * Seed dataset + storage/person-state loaders
 * Load order: util.js -> data.js -> listbox.js -> board.js -> app.js
 * ============================================================ */
        // 1. Raw Initial Dataset & Standalone JSON Loader
        const defaultCardsData = [];

        let rawCardsData = [];

        async function loadStorageData() {
            await fetchBackgroundData();
        }

        async function fetchBackgroundData() {
            try {
                const res = await fetch('./board.json?t=' + Date.now());
                if (res.ok) {
                    const fileData = await res.json();
                    if (Array.isArray(fileData)) {
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
                    if (Array.isArray(parsed)) {
                        rawCardsData = parsed;
                        applyFilters();
                        return;
                    }
                } catch (e) {}
            }
            rawCardsData = [];
            applyFilters();
        }

        function saveStorageData() {
            localStorage.setItem('offline_board_cards_v3', JSON.stringify(rawCardsData));
        }