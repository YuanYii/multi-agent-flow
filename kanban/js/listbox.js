/* ============================================================
 * listbox.js
 * Part of offline_board.html (split for maintainability)
 * Custom DOM listbox replacing native <select>
 * Load order: util.js -> data.js -> listbox.js -> board.js -> app.js
 * ============================================================ */
        let activeUiSelect = null;   // { wrap, trigger, panel, select }

        function closeUiSelect() {
            if (!activeUiSelect) return;
            const { trigger, panel } = activeUiSelect;
            panel.remove();
            trigger.setAttribute('aria-expanded', 'false');
            activeUiSelect = null;
        }

        function syncUiSelectLabel(wrap) {
            const select = wrap.querySelector('select');
            const value = wrap.querySelector('.ui-select-value');
            if (!select || !value) return;
            const opt = select.options[select.selectedIndex];
            value.textContent = opt ? opt.textContent : '';
        }

        function commitUiSelect(wrap, optionValue) {
            const select = wrap.querySelector('select');
            if (select.value !== optionValue) {
                select.value = optionValue;
                // Inline on* attributes are real handlers, so a dispatched
                // event drives the existing wiring without any refactor.
                select.dispatchEvent(new Event('change', { bubbles: true }));
            }
            syncUiSelectLabel(wrap);
            closeUiSelect();
            wrap.querySelector('.ui-select-trigger').focus();
        }

        function openUiSelect(wrap) {
            const alreadyOpen = activeUiSelect && activeUiSelect.wrap === wrap;
            closeUiSelect();
            if (alreadyOpen) return;

            const select = wrap.querySelector('select');
            const trigger = wrap.querySelector('.ui-select-trigger');
            const panel = document.createElement('div');
            panel.className = 'ui-select-panel';
            panel.setAttribute('role', 'listbox');
            panel.id = trigger.getAttribute('aria-controls');
            panel.tabIndex = -1;
            // The panel lives on <body>, outside the .popover it belongs to,
            // so its clicks must not reach the "click outside" closer.
            panel.addEventListener('click', (e) => e.stopPropagation());

            const current = select.value;
            Array.from(select.options).forEach(opt => {
                const row = document.createElement('div');
                row.className = 'ui-select-option' + (opt.value === current ? ' selected' : '');
                row.setAttribute('role', 'option');
                row.setAttribute('aria-selected', opt.value === current ? 'true' : 'false');
                row.dataset.value = opt.value;
                row.innerHTML = `<span>${esc(opt.textContent)}</span>` +
                    `<svg class="uis-check" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
                row.addEventListener('click', (e) => {
                    e.stopPropagation();
                    commitUiSelect(wrap, opt.value);
                });
                panel.appendChild(row);
            });

            document.body.appendChild(panel);

            // Match the trigger width, then keep the panel inside the viewport.
            const r = trigger.getBoundingClientRect();
            panel.style.minWidth = Math.max(r.width, 120) + 'px';
            const pw = panel.offsetWidth;
            const ph = panel.offsetHeight;
            let top = r.bottom + 4;
            let left = r.left;
            if (left + pw > window.innerWidth - 8) left = Math.max(8, window.innerWidth - pw - 8);
            if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - 4);
            panel.style.top = top + 'px';
            panel.style.left = left + 'px';

            trigger.setAttribute('aria-expanded', 'true');
            activeUiSelect = { wrap, trigger, panel, select };

            const opts = Array.from(panel.querySelectorAll('.ui-select-option'));
            const curIdx = opts.findIndex(o => o.dataset.value === current);
            setActiveOption(opts, curIdx < 0 ? 0 : curIdx);

            panel.addEventListener('keydown', (e) => {
                e.stopPropagation();
                let idx = opts.findIndex(o => o.classList.contains('active'));
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    setActiveOption(opts, idx < 0 ? 0 : (idx + 1) % opts.length);
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    setActiveOption(opts, idx < 0 ? 0 : (idx - 1 + opts.length) % opts.length);
                } else if (e.key === 'Home') {
                    e.preventDefault();
                    setActiveOption(opts, 0);
                } else if (e.key === 'End') {
                    e.preventDefault();
                    setActiveOption(opts, opts.length - 1);
                } else if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    const a = opts[idx];
                    if (a) commitUiSelect(wrap, a.dataset.value);
                } else if (e.key === 'Escape' || e.key === 'Tab') {
                    e.preventDefault();
                    closeUiSelect();
                    trigger.focus();
                }
            });
            panel.focus();
        }

        let uiSelectSeq = 0;

        function enhanceSelect(select) {
            if (!select || select.dataset.uiEnhanced === 'true') return;

            const wrap = document.createElement('div');
            wrap.className = 'ui-select';
            select.parentNode.insertBefore(wrap, select);
            wrap.appendChild(select);

            const panelId = 'ui-select-panel-' + (++uiSelectSeq);
            const trigger = document.createElement('button');
            trigger.type = 'button';
            trigger.className = 'ui-select-trigger';
            trigger.setAttribute('aria-haspopup', 'listbox');
            trigger.setAttribute('aria-expanded', 'false');
            trigger.setAttribute('aria-controls', panelId);

            // Move the accessible name off the now-hidden native control.
            const label = select.id ? document.querySelector('label[for="' + select.id + '"]') : null;
            if (label) {
                if (!label.id) label.id = select.id + '-label';
                trigger.setAttribute('aria-labelledby', label.id);
                label.removeAttribute('for');
            } else if (select.getAttribute('aria-label')) {
                trigger.setAttribute('aria-label', select.getAttribute('aria-label'));
            }

            const value = document.createElement('span');
            value.className = 'ui-select-value';
            trigger.appendChild(value);
            wrap.insertBefore(trigger, select);

            select.classList.add('ui-select-native');
            select.setAttribute('aria-hidden', 'true');
            select.tabIndex = -1;
            select.dataset.uiEnhanced = 'true';

            trigger.addEventListener('click', (e) => {
                e.stopPropagation();
                openUiSelect(wrap);
            });
            trigger.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    openUiSelect(wrap);
                }
            });
            // Programmatic value changes (e.g. resetFilters) must refresh the label.
            select.addEventListener('change', () => syncUiSelectLabel(wrap));

            syncUiSelectLabel(wrap);
        }

        function enhanceAllSelects() {
            document.querySelectorAll('select:not([data-ui-enhanced])').forEach(enhanceSelect);
        }

        // Keep every trigger label in sync after code paths that set .value directly.
        function refreshUiSelects() {
            document.querySelectorAll('.ui-select').forEach(syncUiSelectLabel);
        }

        document.addEventListener('click', (e) => {
            if (activeUiSelect && !e.target.closest('.ui-select-panel') && !e.target.closest('.ui-select')) {
                closeUiSelect();
            }
        });
        window.addEventListener('resize', closeUiSelect);
        window.addEventListener('scroll', closeUiSelect, true);