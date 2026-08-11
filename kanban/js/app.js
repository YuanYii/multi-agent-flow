/* ============================================================
 * app.js
 * Part of offline_board.html (split for maintainability)
 * Global keydown handling + init sequence (load last)
 * Load order: util.js -> data.js -> listbox.js -> board.js -> app.js
 * ============================================================ */
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                // A listbox sits above the popover, so it consumes Escape first.
                if (activeUiSelect) {
                    const t = activeUiSelect.trigger;
                    closeUiSelect();
                    if (t) t.focus();
                    return;
                }
                closeAllCustomPopovers();
                closeAddModal();
                closeDetailModal();
            }
        });

        initTheme();
        initBoardTitle();
        initRowHeight();
        // After initRowHeight so the trigger picks up the restored value.
        enhanceAllSelects();
        renderFieldConfigPopover();
        verifyFieldTableParity();
        loadStorageData();
        makeColumnsResizable();