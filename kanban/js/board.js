/* ============================================================
 * board.js
 * Part of offline_board.html (split for maintainability)
 * Core UI: title, fields, kanban/table, filter/sort, drag, modal, row height, resizable
 * Load order: util.js -> data.js -> listbox.js -> board.js -> app.js
 * ============================================================ */

        // Person Multi-Select State & Logic
        let selectedPersons = new Set();
        const allPersons = ['严经理', '钱架构', '李开发', '曹艾', '周审查', '章测试', '李文通', '吕改特'];

        function renderPersonCheckboxList() {
            const container = document.getElementById('person-checkbox-list');
            if (!container) return;
            container.innerHTML = '';
            allPersons.forEach(p => {
                const isChecked = selectedPersons.has(p);
                const label = document.createElement('label');
                label.className = 'checkbox-label';
                label.style.fontSize = '12px';
                label.style.cursor = 'pointer';
                label.innerHTML = `<input type="checkbox" value="${p}" ${isChecked ? 'checked' : ''} onchange="togglePersonSelect('${p}', this.checked)"> ${p}`;
                container.appendChild(label);
            });

            const labelSpan = document.getElementById('person-select-label');
            if (labelSpan) {
                if (!isPersonFocusActive()) {
                    labelSpan.innerText = '全部人员';
                } else if (selectedPersons.size === 1) {
                    labelSpan.innerText = Array.from(selectedPersons)[0];
                } else {
                    labelSpan.innerText = `已选 (${selectedPersons.size}人)`;
                }
            }
        }

        function togglePersonSelect(person, checked) {
            if (checked) {
                selectedPersons.add(person);
            } else {
                selectedPersons.delete(person);
            }
            renderPersonCheckboxList();
            applyFilters();
        }

        function selectAllPersons(selectAll) {
            selectedPersons.clear();
            if (selectAll) {
                allPersons.forEach(p => selectedPersons.add(p));
            }
            renderPersonCheckboxList();
            applyFilters();
        }

        let currentCardsData = [];
        let selectedTaskIds = new Set();
        const rowHeights = {};

        /* 2. Field Registry — SINGLE SOURCE OF TRUTH
           Each entry maps 1:1 to a data column of the table (in the same order).
           `th` must equal the table header text so drift is detectable at runtime. */
        const BOARD_FIELDS = [
            { key: 'seq',        th: '序号',          label: '序号 (Seq)' },
            { key: 'id',         th: '任务编号',      label: '任务编号 (ID)' },
            { key: 'wbs',        th: 'WBS编号',       label: 'WBS 编号 (WBS)' },
            { key: 'pretask',    th: '前置任务',      label: '前置任务 (Pretask)' },
            { key: 'stage',      th: '阶段 / 工作包', label: '阶段 / 工作包 (Stage / WP)' },
            { key: 'name',       th: '任务名称',      label: '任务名称 (Task Name)' },
            { key: 'status',     th: '状态',          label: '状态 (Status)' },
            { key: 'assignee',   th: '负责人',        label: '负责人 (Assignee)' },
            { key: 'handler',    th: '处理人',        label: '处理人 (Handler)' },
            { key: 'est_hours',  th: '预估(h)',       label: '预估工时 (Est Hours)' },
            { key: 'act_hours',  th: '实际(h)',       label: '实际工时 (Act Hours)' },
            { key: 'start_date', th: '开始时间',      label: '开始时间 (Start Date)' },
            { key: 'end_date',   th: '结束时间',      label: '结束时间 (End Date)' },
            { key: 'remarks',    th: '备注',          label: '备注 (Remarks)' },
            { key: 'process',    th: '过程描述',      label: '过程描述 (Process)' }
        ];

        // Card display config: one flag per BOARD_FIELDS entry + a label-prefix toggle
        let cardFieldConfig = BOARD_FIELDS.reduce((acc, f) => { acc[f.key] = true; return acc; }, { showLabels: true });

        // Build the field-config popover from the registry so it can never drift from the table
        function renderFieldConfigPopover() {
            const container = document.getElementById('field-checkbox-list');
            if (!container) return;
            container.innerHTML = BOARD_FIELDS.map(f =>
                `<label class="checkbox-label"><input type="checkbox" ${cardFieldConfig[f.key] ? 'checked' : ''} data-field="${f.key}" onchange="updateFieldConfig()"> ${esc(f.label)}</label>`
            ).join('');
            const countEl = document.getElementById('field-count-hint');
            if (countEl) countEl.innerText = `共 ${BOARD_FIELDS.length} 个字段，与表格 ${BOARD_FIELDS.length} 列一一对应`;
        }

        // Runtime guard: warn if the table headers and the field registry ever diverge
        function verifyFieldTableParity() {
            const ths = Array.from(document.querySelectorAll('#main-data-table thead th'));
            // skip the leading checkbox column and the trailing 操作 column
            const dataThs = ths.slice(1, -1).map(th => {
                const clone = th.cloneNode(true);
                clone.querySelectorAll('.resizer, .row-resizer').forEach(el => el.remove());
                return (clone.textContent || '').trim();
            });
            const expected = BOARD_FIELDS.map(f => f.th);
            const ok = dataThs.length === expected.length && dataThs.every((t, i) => t === expected[i]);
            if (!ok) {
                console.warn('[board] 字段配置与表格列不一致\n  表格列:', dataThs, '\n  字段表:', expected);
            }
            return { ok, tableColumns: dataThs, fields: expected };
        }

        // Column Configurations
        const assigneeColsConfig = [
            { name: "严经理", theme: "pm" },
            { name: "钱架构", theme: "arch" },
            { name: "李开发", theme: "dev" },
            { name: "曹艾", theme: "purple" },
            { name: "周审查", theme: "rev" },
            { name: "章测试", theme: "qa" },
            { name: "李文通", theme: "doc" },
            { name: "吕改特", theme: "ops" }
        ];

        const statusColsConfig = [
            { name: "待开始", theme: "gray" },
            { name: "进行中", theme: "blue" },
            { name: "审查中", theme: "orange" },
            { name: "测试中", theme: "pink" },
            { name: "已完成", theme: "pm" },
            { name: "已验收", theme: "pm" },
            { name: "已退回", theme: "orange" },
            { name: "已阻塞", theme: "gray" },
            { name: "已取消", theme: "gray" }
        ];

        /* ==========================================================
           Editable Board Title (persisted to localStorage)
           ========================================================== */
        const DEFAULT_BOARD_TITLE = '多专家Agent协作任务看板';
        const BOARD_TITLE_KEY = 'offline_board_title_v1';
        const BOARD_TITLE_MAX = 60;
        let boardTitleSnapshot = DEFAULT_BOARD_TITLE;

        function getBoardTitle() {
            try {
                const saved = localStorage.getItem(BOARD_TITLE_KEY);
                const trimmed = (saved || '').trim();
                return trimmed || DEFAULT_BOARD_TITLE;
            } catch (e) {
                return DEFAULT_BOARD_TITLE;
            }
        }

        function applyBoardTitle(title) {
            const el = document.getElementById('board-title');
            if (el) el.textContent = title;
            document.title = title;
            boardTitleSnapshot = title;
        }

        function commitBoardTitle() {
            const el = document.getElementById('board-title');
            if (!el) return;
            // Strip any pasted markup / newlines, clamp length
            let next = (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, BOARD_TITLE_MAX);
            const restored = !next;
            if (restored) next = DEFAULT_BOARD_TITLE;

            const changed = next !== boardTitleSnapshot;
            applyBoardTitle(next);

            try {
                if (next === DEFAULT_BOARD_TITLE) localStorage.removeItem(BOARD_TITLE_KEY);
                else localStorage.setItem(BOARD_TITLE_KEY, next);
            } catch (e) { /* storage full / disabled — title still applies in-session */ }

            if (changed) {
                showToast(restored ? '标题已恢复默认：' + DEFAULT_BOARD_TITLE : '标题已更新：' + next);
            }
        }

        function initBoardTitle() {
            const el = document.getElementById('board-title');
            if (!el) return;
            applyBoardTitle(getBoardTitle());

            el.addEventListener('focus', () => { boardTitleSnapshot = (el.textContent || '').trim(); });

            el.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    el.blur();
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    e.stopPropagation(); // don't let the global Esc handler close modals/popovers
                    el.textContent = boardTitleSnapshot;
                    el.blur();
                }
            });

            // Paste as plain text only (no markup, no line breaks)
            el.addEventListener('paste', (e) => {
                e.preventDefault();
                const raw = ((e.clipboardData || window.clipboardData).getData('text/plain') || '')
                    .replace(/\s+/g, ' ');
                let inserted = false;
                try { inserted = document.execCommand('insertText', false, raw); } catch (err) { inserted = false; }
                if (!inserted) {
                    const sel = window.getSelection();
                    if (sel && sel.rangeCount) {
                        const range = sel.getRangeAt(0);
                        range.deleteContents();
                        const node = document.createTextNode(raw);
                        range.insertNode(node);
                        range.setStartAfter(node);
                        range.collapse(true);
                        sel.removeAllRanges();
                        sel.addRange(range);
                    } else {
                        el.textContent = (el.textContent || '') + raw;
                    }
                }
            });

            // Keep the element truly empty (so the CSS placeholder shows) and drop stray markup
            el.addEventListener('input', () => {
                if (!(el.textContent || '').trim() && el.innerHTML !== '') el.innerHTML = '';
            });

            el.addEventListener('blur', commitBoardTitle);
        }

        // Toast Notification Helper

        let activeTagPanel = null;
        let activeTagTrigger = null;

        function closeTagPanel() {
            if (activeTagPanel) { activeTagPanel.remove(); activeTagPanel = null; }
            if (activeTagTrigger) { activeTagTrigger.classList.remove('open'); activeTagTrigger = null; }
        }

        function setActiveOption(opts, idx) {
            opts.forEach(o => o.classList.remove('active'));
            if (idx >= 0 && opts[idx]) {
                opts[idx].classList.add('active');
                opts[idx].scrollIntoView({ block:'nearest' });
            }
        }

        function openTagPanel(trigger) {
            closeTagPanel();
            const type = trigger.dataset.type;
            const options = type === 'status' ? STATUS_OPTIONS : PERSON_OPTIONS;
            const current = trigger.dataset.value;

            const panel = document.createElement('div');
            panel.className = 'tag-select-panel';
            panel.setAttribute('role', 'listbox');
            panel.tabIndex = -1;

            options.forEach(opt => {
                const st = getBadgeStyle(type, opt);
                const o = document.createElement('div');
                o.className = 'tag-select-option' + (opt === current ? ' selected' : '');
                o.setAttribute('role', 'option');
                o.dataset.value = opt;
                o.style.background = st.bg;
                o.style.color = st.text;
                const check = opt === current
                    ? `<svg class="ts-check" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
                    : '';
                o.innerHTML = `<span class="ts-dot" style="background:${st.text}"></span><span>${esc(opt)}</span>${check}`;
                o.addEventListener('click', (e) => {
                    e.stopPropagation();
                    selectTagOption(trigger, opt);
                });
                panel.appendChild(o);
            });

            document.body.appendChild(panel);

            // Position near trigger (viewport-aware)
            const r = trigger.getBoundingClientRect();
            const pw = panel.offsetWidth;
            const ph = panel.offsetHeight;
            let top = r.bottom + 4;
            let left = r.left;
            if (left + pw > window.innerWidth - 8) left = Math.max(8, window.innerWidth - pw - 8);
            if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - 4);
            panel.style.top = top + 'px';
            panel.style.left = left + 'px';

            trigger.classList.add('open');
            activeTagPanel = panel;
            activeTagTrigger = trigger;

            // Keyboard navigation inside panel
            const opts = Array.from(panel.querySelectorAll('.tag-select-option'));
            const curIdx = opts.findIndex(o => o.dataset.value === current);
            setActiveOption(opts, curIdx);
            panel.addEventListener('keydown', (e) => {
                e.stopPropagation();
                let idx = opts.findIndex(o => o.classList.contains('active'));
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    idx = idx < 0 ? 0 : (idx + 1) % opts.length;
                    setActiveOption(opts, idx);
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    idx = idx < 0 ? 0 : (idx - 1 + opts.length) % opts.length;
                    setActiveOption(opts, idx);
                } else if (e.key === 'Enter') {
                    e.preventDefault();
                    const a = opts.find(o => o.classList.contains('active')) || opts.find(o => o.dataset.value === current);
                    if (a) selectTagOption(trigger, a.dataset.value);
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    closeTagPanel();
                }
            });
            panel.focus();
        }

        function selectTagOption(trigger, value) {
            const type = trigger.dataset.type;
            const st = getBadgeStyle(type, value);
            trigger.dataset.value = value;
            trigger.style.background = st.bg;
            trigger.style.color = st.text;
            trigger.innerHTML = badgeInner(type, value);

            // Sync linked hidden input (modal fields)
            const target = trigger.dataset.target;
            if (target) {
                const hi = document.getElementById(target);
                if (hi) hi.value = value;
            }

            // Table inline -> write back to data + re-render
            const cardId = trigger.dataset.cardId;
            if (cardId) {
                if (type === 'status') quickUpdateStatus(cardId, value);
                else quickUpdateAssignee(cardId, value);
            }
            closeTagPanel();
        }

        // Sync modal trigger displays from their hidden inputs
        function refreshModalTagSelectors() {
            document.querySelectorAll('.tag-select[data-target]').forEach(t => {
                const hi = document.getElementById(t.dataset.target);
                if (!hi) return;
                const val = hi.value || (t.dataset.type === 'status' ? '待开始' : '李开发');
                t.dataset.value = val;
                const st = getBadgeStyle(t.dataset.type, val);
                t.style.background = st.bg;
                t.style.color = st.text;
                t.style.borderColor = 'rgba(0,0,0,0.06)';
                t.innerHTML = badgeInner(t.dataset.type, val);
            });
        }

        // Global click delegation: open / toggle / outside-close
        document.addEventListener('click', (e) => {
            const trigger = e.target.closest('.tag-select');
            if (trigger) {
                if (trigger === activeTagTrigger) closeTagPanel();
                else openTagPanel(trigger);
                return;
            }
            if (activeTagPanel && !e.target.closest('.tag-select-panel')) {
                closeTagPanel();
            }
        });

        // Close the floating panel on scroll / resize so it never detaches from its trigger
        window.addEventListener('scroll', () => { if (activeTagPanel) closeTagPanel(); }, true);
        window.addEventListener('resize', () => { if (activeTagPanel) closeTagPanel(); });

        // Card HTML Generator with all fields & label toggle support
        function createCardHTML(card) {
            const lbl = cardFieldConfig.showLabels;

            // --- Header line: 任务编号 + 序号 (independently toggleable) ---
            const idPart = cardFieldConfig.id ? `<span>${lbl ? '编号: ' : ''}${esc(card.id)}</span>` : '';
            const seqPart = cardFieldConfig.seq ? `<small style="font-weight:normal; color:#8f959e;">${lbl ? '序号: ' : '#'}${esc(card.seq)}</small>` : '';
            let idHtml = (idPart || seqPart) ? `<div class="card-id">${idPart}${seqPart}</div>` : '';

            // --- WBS 编号 ---
            let wbsHtml = (cardFieldConfig.wbs && card.wbs) ? `<div class="card-sub">${lbl ? 'WBS: ' : ''}${esc(card.wbs)}</div>` : '';
            let nameHtml = cardFieldConfig.name ? `<div class="card-title">${esc(card.name)}</div>` : '';

            // --- Tag row ---
            let tagsList = [];
            if (cardFieldConfig.status && card.status) tagsList.push(`<span class="tag tag-status">${lbl ? '状态: ' : ''}${esc(card.status)}</span>`);
            if (cardFieldConfig.assignee && card.assignee) tagsList.push(`<span class="tag tag-person">${lbl ? '负责人: ' : ''}${esc(card.assignee)}</span>`);
            // 阶段 / 工作包 — mirrors the single "阶段 / 工作包" table column
            if (cardFieldConfig.stage && (card.stage || card.wp)) {
                const stageText = [card.stage, card.wp].filter(Boolean).join(' · ');
                tagsList.push(`<span class="tag tag-stage">${lbl ? '阶段: ' : ''}${esc(stageText)}</span>`);
            }
            if (cardFieldConfig.handler && card.handler) tagsList.push(`<span class="tag tag-stage">${lbl ? '处理人: ' : ''}${esc(card.handler)}</span>`);
            if (cardFieldConfig.pretask && card.pretask) tagsList.push(`<span class="tag tag-stage">${lbl ? '前置: ' : ''}${esc(card.pretask)}</span>`);

            let tagsHtml = tagsList.length > 0 ? `<div class="card-tags">${tagsList.join('')}</div>` : '';

            // --- 开始时间 / 结束时间 (independently toggleable) ---
            const showStart = cardFieldConfig.start_date && card.start_date;
            const showEnd = cardFieldConfig.end_date && card.end_date;
            let datesHtml = '';
            if (showStart || showEnd) {
                const startTxt = showStart ? esc(card.start_date) : '-';
                const endTxt = showEnd ? esc(card.end_date) : '-';
                datesHtml = `<div style="font-size:11px; color:#8f959e; margin-bottom:4px;">${lbl ? '周期: ' : ''}${startTxt} ~ ${endTxt}</div>`;
            }

            let remarksHtml = (cardFieldConfig.remarks && card.remarks) ? `<div style="margin-top:4px; font-size:12px; color:#4e5969; line-height:1.4;">${lbl ? '备注: ' : ''}${esc(card.remarks.length > 60 ? card.remarks.substring(0, 60) + '...' : card.remarks)}</div>` : '';
            let processHtml = (cardFieldConfig.process && card.process) ? `<div style="margin-top:4px; font-size:12px; color:#4e5969; line-height:1.4;">${lbl ? '过程: ' : ''}${esc(card.process.length > 60 ? card.process.substring(0, 60) + '...' : card.process)}</div>` : '';

            // --- 预估工时 / 实际工时 (independently toggleable) ---
            let hoursHtml = '';
            if (cardFieldConfig.est_hours || cardFieldConfig.act_hours) {
                const parts = [];
                if (cardFieldConfig.est_hours) parts.push(`${esc(card.est_hours || '0')}h (预)`);
                if (cardFieldConfig.act_hours) parts.push(`${esc(card.act_hours || '0')}h (实)`);
                hoursHtml = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> ${lbl ? '工时: ' : ''}${parts.join(' / ')}`;
            }

            let metaHtml = (hoursHtml || datesHtml || remarksHtml || processHtml) ? `
                <div class="card-meta">
                    ${hoursHtml}
                    ${datesHtml}
                    ${remarksHtml}
                    ${processHtml}
                </div>` : '';

            return `
                <div class="card" draggable="true" ondragstart="drag(event)" ondragend="dragEnd(event)" id="card-${esc(card.id)}" data-id="${esc(card.id)}" onclick="openTaskDetail('${esc(card.id)}')">
                    ${idHtml}
                    ${wbsHtml}
                    ${nameHtml}
                    ${tagsHtml}
                    ${metaHtml}
                </div>
            `;
        }

        // Render Kanban View
        function renderKanban(containerId, columnsConfig, groupByField) {
            const container = document.getElementById(containerId);
            if (!container) return;
            container.innerHTML = "";

            const existingColNames = new Set(columnsConfig.map(c => c.name));
            const extraNames = new Set();
            currentCardsData.forEach(c => {
                const val = c[groupByField] || '未分类';
                if (!existingColNames.has(val)) {
                    extraNames.add(val);
                }
            });

            const fullConfig = [...columnsConfig];
            extraNames.forEach(name => {
                fullConfig.push({ name: name, theme: "gray" });
            });

            fullConfig.forEach(col => {
                const colCards = currentCardsData.filter(c => (c[groupByField] || '未分类') === col.name);
                
                const colHTML = `
                    <div class="column" data-col="${col.name}" data-groupfield="${groupByField}">
                        <div class="col-header theme-${col.theme}">
                            <div class="col-title">${col.name} <span class="col-count">${colCards.length}</span></div>
                        </div>
                        <div class="card-list" ondrop="drop(event)" ondragover="allowDrop(event)" ondragenter="dragEnter(event)" ondragleave="dragLeave(event)">
                            ${colCards.map(c => createCardHTML(c)).join('')}
                        </div>
                    </div>
                `;
                container.insertAdjacentHTML('beforeend', colHTML);
            });
        }

        // Kanban Drag & Drop
        function drag(event) {
            const card = event.currentTarget;
            const id = card.getAttribute('data-id');
            event.dataTransfer.setData('text/plain', id);
            event.dataTransfer.effectAllowed = 'move';
            card.classList.add('dragging');
        }

        function dragEnd(event) {
            const card = event.currentTarget;
            card.classList.remove('dragging');
            document.querySelectorAll('.card-list.drag-over').forEach(l => l.classList.remove('drag-over'));
        }

        function allowDrop(event) {
            event.preventDefault();
            event.dataTransfer.dropEffect = 'move';
        }

        function dragEnter(event) {
            event.currentTarget.classList.add('drag-over');
        }

        function dragLeave(event) {
            const list = event.currentTarget;
            if (!list.contains(event.relatedTarget)) {
                list.classList.remove('drag-over');
            }
        }

        function appendProcessLog(card, logActionText) {
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            const hours = String(now.getHours()).padStart(2, '0');
            const mins = String(now.getMinutes()).padStart(2, '0');
            const secs = String(now.getSeconds()).padStart(2, '0');
            const nowStr = `${year}-${month}-${day} ${hours}:${mins}:${secs}`;
            const logLine = `[${nowStr}] ${logActionText}`;

            if (card.process) {
                card.process = card.process.trim() + '\n' + logLine;
            } else {
                card.process = logLine;
            }
        }

        let pendingTransition = null;

        function drop(event) {
            event.preventDefault();
            const list = event.currentTarget;
            list.classList.remove('drag-over');
            const cardId = event.dataTransfer.getData('text/plain');
            if (!cardId) return;
            const column = list.closest('.column');
            if (!column) return;
            const groupField = column.getAttribute('data-groupfield');
            const colValue = column.getAttribute('data-col');
            const card = rawCardsData.find(c => c.id === cardId);
            if (!card || !groupField || colValue === '未分类') return;

            if (card[groupField] === colValue) return;

            let newHandler = card.handler;
            if (groupField === 'assignee') {
                newHandler = colValue;
            } else if (groupField === 'status') {
                const statusRoleMap = {
                    '审查中': '周审查',
                    '测试中': '章测试',
                    '进行中': '李开发',
                    '处理中': '李开发',
                    '已完成': '严经理'
                };
                if (statusRoleMap[colValue]) {
                    newHandler = statusRoleMap[colValue];
                }
            }

            pendingTransition = {
                cardId,
                groupField,
                oldVal: card[groupField],
                newVal: colValue,
                newHandler
            };

            const banner = document.getElementById('transition-change-banner');
            if (banner) {
                const fieldName = groupField === 'status' ? '状态' : (groupField === 'assignee' ? '负责人' : '阶段');
                banner.innerHTML = `
                    <div style="font-weight:600; font-size:14px; margin-bottom:4px; color:var(--text-main);">
                        [${esc(card.id)}] ${esc(card.name)}
                    </div>
                    <div>
                        ${fieldName}: <span style="text-decoration:line-through; color:var(--text-muted);">${esc(card[groupField] || '未设定')}</span>
                        &nbsp;&rarr;&nbsp;
                        <strong style="color:var(--primary); font-size:14px;">${esc(colValue)}</strong>
                        ${newHandler ? `<span class="tag tag-stage" style="margin-left:8px;">处理人移交至: ${esc(newHandler)}</span>` : ''}
                    </div>
                `;
            }

            const commentInput = document.getElementById('transition-comment-input');
            if (commentInput) commentInput.value = '';

            document.getElementById('transition-modal').classList.add('show');
            setTimeout(() => { if (commentInput) commentInput.focus(); }, 100);
        }

        function cancelTransition() {
            pendingTransition = null;
            document.getElementById('transition-modal').classList.remove('show');
        }

        function confirmTransition() {
            if (!pendingTransition) {
                cancelTransition();
                return;
            }

            const { cardId, groupField, oldVal, newVal, newHandler } = pendingTransition;
            const card = rawCardsData.find(c => c.id === cardId);
            if (!card) {
                cancelTransition();
                return;
            }

            card[groupField] = newVal;
            if (newHandler) {
                card.handler = newHandler;
            }

            const userComment = (document.getElementById('transition-comment-input').value || '').trim();
            const fieldName = groupField === 'status' ? '状态' : (groupField === 'assignee' ? '负责人' : '阶段');
            const defaultAction = `[看板拖拽联动] 将${fieldName}由【${oldVal || '未设定'}】更新至【${newVal}】${newHandler ? `(处理人: ${newHandler})` : ''}`;
            const logMsg = userComment ? `${defaultAction} — 说明: ${userComment}` : defaultAction;

            appendProcessLog(card, logMsg);
            saveStorageData();
            applyFilters();

            cancelTransition();
            showToast(`已成功流转 ${cardId} → ${newVal}`);
        }

        function onTableRowClick(event, cardId) {
            // 若点击的是复选框或下拉选择面板触发器，不拦截其原生行为
            if (event.target.closest('input[type="checkbox"]') || event.target.closest('.tag-select') || event.target.closest('.ui-select-trigger') || event.target.closest('.row-resizer')) {
                return;
            }
            openTaskDetail(cardId);
        }

        function renderTable() {
            renderTableBody(currentCardsData);
        }

        function renderTableBody(currentCardsData) {
            const tbody = document.getElementById('table-body');
            tbody.innerHTML = '';

            currentCardsData.forEach((card, idx) => {
                const isSelected = selectedTaskIds.has(card.id);
                const savedH = rowHeights[card.id];
                const trStyle = savedH ? rowHeightVars(savedH) : '';

                const tr = `
                    <tr data-id="${esc(card.id)}" style="${trStyle}; cursor:pointer;" class="clickable-row" onclick="onTableRowClick(event, '${esc(card.id)}')">
                        <td style="text-align:center;"><input type="checkbox" class="row-cb" value="${esc(card.id)}" ${isSelected ? 'checked' : ''} onchange="toggleSelectRow('${esc(card.id)}', this.checked)"></td>
                        <td style="font-weight:600; color:var(--text-muted); position:relative;">${idx + 1}<div class="row-resizer" title="拖拽调节行高"></div></td>
                        <td><strong style="color:var(--primary);">${esc(card.id)}</strong></td>
                        <td>${esc(card.wbs) || '-'}</td>
                        <td><small style="color:var(--text-muted);">${esc(card.pretask) || '-'}</small></td>
                        <td><div class="cell-content">${esc(card.stage)}<br><small style="color:var(--text-muted)">${esc(card.wp)}</small></div></td>
                        <td><div class="cell-content" style="font-weight:600;">${esc(card.name)}</div></td>
                        <td>
                            ${tagSelectTriggerHTML('status', card.status || '待开始', `data-card-id="${esc(card.id)}"`)}
                        </td>
                        <td>
                            ${tagSelectTriggerHTML('person', card.assignee || '李开发', `data-card-id="${esc(card.id)}"`)}
                        </td>
                        <td>${esc(card.handler) || '-'}</td>
                        <td>${esc(card.est_hours)}</td>
                        <td>${esc(card.act_hours)}</td>
                        <td><small style="color:#4e5969;">${esc(card.start_date) || '-'}</small></td>
                        <td><small style="color:#4e5969;">${esc(card.end_date) || '-'}</small></td>
                        <td><div class="cell-content" style="font-size:12px; color:#4e5969;">${esc(card.remarks) || '-'}</div></td>
                        <td><div class="cell-content" style="font-size:12px; color:#4e5969;">${esc(card.process) || '-'}</div></td>
                        <td><button class="btn sm" onclick="openTaskDetail('${esc(card.id)}')">详情</button></td>
                    </tr>
                `;
                tbody.insertAdjacentHTML('beforeend', tr);
            });

            updateBatchDeleteBtn();
            makeRowsResizable();
        }

        function updateCounter() {
            document.getElementById('total-count').innerText = currentCardsData.length;
            document.getElementById('raw-count').innerText = rawCardsData.length;
        }

        function initRender() {
            // 1. Kanban Assignee
            renderKanban("board-assignee", assigneeColsConfig, "assignee");

            // 2. Kanban Stage
            const stageNames = Array.from(new Set(rawCardsData.map(c => c.stage || 'S6 工作流集成测试')));
            const stageColsConfig = stageNames.map(s => ({ name: s, theme: "blue" }));
            renderKanban("board-stage", stageColsConfig, "stage");

            // 3. Kanban Status
            renderKanban("board-status", statusColsConfig, "status");

            // 4. Data Table
            renderTable();
            renderPersonCheckboxList();
            updateCounter();
            refreshModalTagSelectors();
        }

        // Search, Filter, Sort Handlers
        function onSearch() {
            applyFilters();
        }

        function applyFilters() {
            const query = document.getElementById('search-box').value.trim().toLowerCase();
            const statusFilter = document.getElementById('filter-status').value;
            const assigneeFilter = document.getElementById('filter-assignee').value;
            const personFocusActive = isPersonFocusActive();

            currentCardsData = rawCardsData.filter(c => {
                const matchQuery = !query || (
                    (c.id && c.id.toLowerCase().includes(query)) ||
                    (c.name && c.name.toLowerCase().includes(query)) ||
                    (c.assignee && c.assignee.toLowerCase().includes(query)) ||
                    (c.status && c.status.toLowerCase().includes(query)) ||
                    (c.stage && c.stage.toLowerCase().includes(query)) ||
                    (c.wbs && c.wbs.toLowerCase().includes(query)) ||
                    (c.remarks && c.remarks.toLowerCase().includes(query)) ||
                    (c.process && c.process.toLowerCase().includes(query))
                );
                const matchStatus = !statusFilter || c.status === statusFilter;
                // Each assignee filter is a no-op when unset; when both are set they intersect (AND).
                const matchDropdownAssignee = !assigneeFilter || c.assignee === assigneeFilter;
                const matchMultiPerson = !personFocusActive || selectedPersons.has(c.assignee);

                return matchQuery && matchStatus && matchDropdownAssignee && matchMultiPerson;
            });

            updateActiveFilterHint(query, statusFilter, assigneeFilter);
            applySort();
        }

        // Is the "聚焦人员" multi-select actually narrowing anything?
        // (empty = untouched, all-selected = equivalent to 全部人员) → both are no-ops
        function isPersonFocusActive() {
            return selectedPersons.size > 0 && selectedPersons.size < allPersons.length;
        }

        // Surface which filters are currently narrowing the result set, so an empty
        // result never looks like "the data vanished".
        function updateActiveFilterHint(query, statusFilter, assigneeFilter) {
            const el = document.getElementById('active-filter-hint');
            if (!el) return;

            const parts = [];
            if (query) parts.push(`搜索"${query}"`);
            if (statusFilter) parts.push(`状态=${statusFilter}`);
            if (assigneeFilter) parts.push(`负责人=${assigneeFilter}`);
            if (isPersonFocusActive()) parts.push(`聚焦人员=${Array.from(selectedPersons).join('/')}`);

            if (parts.length === 0) {
                el.style.display = 'none';
                el.innerText = '';
                el.removeAttribute('data-conflict');
                return;
            }

            el.style.display = 'inline-flex';
            const conflict = assigneeFilter && isPersonFocusActive() && !selectedPersons.has(assigneeFilter);
            if (conflict) {
                el.setAttribute('data-conflict', 'true');
                el.innerText = `筛选冲突：${parts.join(' 且 ')} — 两个负责人条件互斥，结果必然为空`;
            } else {
                el.removeAttribute('data-conflict');
                el.innerText = `筛选中：${parts.join(' 且 ')}（${currentCardsData.length} 条）`;
            }
        }

        function resetFilters() {
            document.getElementById('search-box').value = '';
            document.getElementById('filter-status').value = '';
            document.getElementById('filter-assignee').value = '';
            selectedPersons.clear();
            renderPersonCheckboxList();
            refreshUiSelects();
            applyFilters();
            closeAllCustomPopovers();
        }

        async function resetAllFiltersAndData() {
            document.getElementById('search-box').value = '';
            document.getElementById('filter-status').value = '';
            document.getElementById('filter-assignee').value = '';
            document.getElementById('sort-field').value = 'seq';
            document.getElementById('sort-order').value = 'asc';
            selectedPersons.clear();
            renderPersonCheckboxList();
            refreshUiSelects();
            closeAllCustomPopovers();

            // 安全拉取与防消失保护：重置所有筛选视角
            const snapshot = Array.isArray(rawCardsData) && rawCardsData.length > 0 ? [...rawCardsData] : null;
            await fetchBackgroundData();
            if ((!rawCardsData || rawCardsData.length === 0) && snapshot) {
                rawCardsData = snapshot;
                saveStorageData();
            }
            applyFilters();
            showToast('已重置所有筛选条件与视图！');
        }

        function applySort() {
            const field = document.getElementById('sort-field').value;
            const order = document.getElementById('sort-order').value;

            if (field !== 'seq') {
                currentCardsData.sort((a, b) => {
                    let valA = a[field] || '';
                    let valB = b[field] || '';

                    if (field === 'est_hours' || field === 'act_hours') {
                        valA = parseFloat(valA) || 0;
                        valB = parseFloat(valB) || 0;
                    }

                    if (valA < valB) return order === 'asc' ? -1 : 1;
                    if (valA > valB) return order === 'asc' ? 1 : -1;
                    return 0;
                });
            } else {
                currentCardsData.sort((a, b) => order === 'asc' ? a.seq - b.seq : b.seq - a.seq);
            }

            initRender();
        }

        // Quick Inline Updates from Data Table
        function quickUpdateStatus(cardId, newStatus) {
            const card = rawCardsData.find(c => c.id === cardId);
            if (card && card.status !== newStatus) {
                const oldStatus = card.status;
                card.status = newStatus;
                appendProcessLog(card, `[快捷状态变更] 状态由【${oldStatus || '未设定'}】调整为【${newStatus}】`);
                saveStorageData();
                applyFilters();
                showToast(`已更新 ${card.id} 状态为: ${newStatus}`);
            }
        }

        function quickUpdateAssignee(cardId, newAssignee) {
            const card = rawCardsData.find(c => c.id === cardId);
            if (card && card.assignee !== newAssignee) {
                const oldAssignee = card.assignee;
                card.assignee = newAssignee;
                appendProcessLog(card, `[快捷负责人变更] 负责人由【${oldAssignee || '未设定'}】变更为【${newAssignee}】`);
                saveStorageData();
                applyFilters();
                showToast(`已更新 ${card.id} 负责人为: ${newAssignee}`);
            }
        }

        // Selection Checkboxes Handlers
        function toggleSelectAll(checked) {
            selectedTaskIds.clear();
            if (checked) {
                currentCardsData.forEach(c => selectedTaskIds.add(c.id));
            }
            renderTable();
        }

        function toggleSelectRow(cardId, checked) {
            if (checked) {
                selectedTaskIds.add(cardId);
            } else {
                selectedTaskIds.delete(cardId);
            }
            updateBatchDeleteBtn();
            makeRowsResizable();
        }

        function updateBatchDeleteBtn() {
            const count = selectedTaskIds.size;
            document.getElementById('selected-count').innerText = count;
            document.getElementById('batch-delete-btn').style.display = count > 0 ? 'inline-flex' : 'none';
        }

        function batchDeleteRecords() {
            if (!confirm(`确定要批量删除选中的 ${selectedTaskIds.size} 条任务记录吗？`)) return;
            rawCardsData = rawCardsData.filter(c => !selectedTaskIds.has(c.id));
            selectedTaskIds.clear();
            saveStorageData();
            applyFilters();
            showToast('已完成批量删除操作！');
        }

        // Field Config Listener
        function updateFieldConfig() {
            document.querySelectorAll('#field-popover input[type="checkbox"]').forEach(cb => {
                const field = cb.getAttribute('data-field');
                if (field) cardFieldConfig[field] = cb.checked;
            });
            initRender();
        }

        function setAllCardFields(checked) {
            BOARD_FIELDS.forEach(f => { cardFieldConfig[f.key] = checked; });
            renderFieldConfigPopover();
            initRender();
        }

        /* ------------------------------------------------------------------
         * Custom Select (listbox)
         *
         * A native <select> renders its option list through the OS, which
         * ignores page CSS — on a dark system theme it pops up as a dark menu
         * against this light UI. Each select is therefore wrapped in a
         * .ui-select: a styled trigger plus a DOM listbox. The native element
         * is kept as the single source of truth for the value and still fires
         * `change`, so existing inline handlers (applyFilters / applySort /
         * changeRowHeight) work untouched.
         * ------------------------------------------------------------------ */


        /* ------------------------------------------------------------------
         * Row Height System
         *
         * Previously changeRowHeight() only set --row-max-height, but
         * .cell-content also carried a hard-coded `-webkit-line-clamp: 2`.
         * Two lines ≈ 39px, which is below every preset (40/55/85/150), so the
         * max-height never bound and the selector appeared dead. The height is
         * now derived as a set: row height, vertical padding, line clamp and
         * content max-height, all as custom properties.
         * ------------------------------------------------------------------ */
        const ROW_LINE_HEIGHT = 19.5;           // 13px font x 1.5 line-height
        const ROW_HEIGHT_KEY = 'offline_board_row_height_v1';
        const ROW_HEIGHT_DEFAULT = 55;

        /* The rendered row height is driven by the tallest .cell-content, i.e.
         * by the line clamp — not by td{height}, which only acts as a minimum.
         * So each preset pins an explicit clamp; a derived value would round
         * 40px up to 2 lines and make 紧凑 indistinguishable from 标准. */
        const ROW_HEIGHT_PRESETS = {
            40:  { padY: 4,  clamp: 1 },   // 紧凑
            55:  { padY: 8,  clamp: 2 },   // 标准
            85:  { padY: 10, clamp: 3 },   // 宽松
            150: { padY: 12, clamp: 6 }    // 展开
        };

        function rowHeightMetrics(heightPx) {
            const h = Math.max(32, parseInt(heightPx, 10) || ROW_HEIGHT_DEFAULT);
            const preset = ROW_HEIGHT_PRESETS[h];
            const padY = preset ? preset.padY : (h <= 40 ? 4 : (h <= 55 ? 8 : (h <= 85 ? 10 : 12)));
            // Arbitrary heights (manual drag) floor to whole lines so the last
            // line is never sliced in half.
            const clamp = preset ? preset.clamp : Math.max(1, Math.floor((h - padY * 2) / ROW_LINE_HEIGHT));
            return { h, padY, clamp, maxH: Math.round(clamp * ROW_LINE_HEIGHT) };
        }

        // Inline style string for a <tr> (used when replaying a manual drag).
        function rowHeightVars(heightPx) {
            const m = rowHeightMetrics(heightPx);
            // A dragged row shows everything it can fit, hence the loose clamp.
            return `--row-height:${m.h}px; --row-pad-y:${m.padY}px; --row-line-clamp:99; --row-max-height:${m.h - m.padY * 2}px;`;
        }

        function applyRowHeightVars(tr, heightPx) {
            const m = rowHeightMetrics(heightPx);
            tr.style.setProperty('--row-height', m.h + 'px');
            tr.style.setProperty('--row-pad-y', m.padY + 'px');
            tr.style.setProperty('--row-line-clamp', '99');
            tr.style.setProperty('--row-max-height', (m.h - m.padY * 2) + 'px');
        }

        function changeRowHeight(heightPx) {
            const m = rowHeightMetrics(heightPx);
            const root = document.documentElement;
            root.style.setProperty('--row-height', m.h + 'px');
            root.style.setProperty('--row-pad-y', m.padY + 'px');
            root.style.setProperty('--row-line-clamp', String(m.clamp));
            root.style.setProperty('--row-max-height', m.maxH + 'px');

            // Choosing a preset is a global intent, so per-row manual drags are
            // discarded — otherwise those rows would silently ignore the change.
            Object.keys(rowHeights).forEach(k => { delete rowHeights[k]; });
            const tbody = document.getElementById('table-body');
            if (tbody) {
                tbody.querySelectorAll('tr').forEach(tr => {
                    ['--row-height', '--row-pad-y', '--row-line-clamp', '--row-max-height']
                        .forEach(p => tr.style.removeProperty(p));
                    tr.style.removeProperty('height');
                    tr.querySelectorAll('.cell-content').forEach(cell => {
                        cell.style.removeProperty('max-height');
                        cell.style.removeProperty('-webkit-line-clamp');
                    });
                });
            }

            try { localStorage.setItem(ROW_HEIGHT_KEY, String(m.h)); } catch (e) { /* storage blocked */ }
            return m;
        }

        function initRowHeight() {
            let saved = null;
            try { saved = localStorage.getItem(ROW_HEIGHT_KEY); } catch (e) { /* storage blocked */ }
            const allowed = Object.keys(ROW_HEIGHT_PRESETS);
            const value = (saved && allowed.indexOf(saved) !== -1)
                ? saved
                : String(ROW_HEIGHT_DEFAULT);
            changeRowHeight(value);
            updateRowHeightBtn(value);
        }

        const ROW_HEIGHT_LABELS = { 40: '紧凑', 55: '标准', 85: '宽松', 150: '展开' };

        // Sync the toolbar button label + highlight the active option
        function updateRowHeightBtn(h) {
            const label = document.getElementById('row-height-label');
            if (label) label.textContent = ROW_HEIGHT_LABELS[h] || ROW_HEIGHT_LABELS[ROW_HEIGHT_DEFAULT];
            document.querySelectorAll('#row-height-popover .rh-option').forEach(o => {
                o.classList.toggle('active', o.dataset.h === String(h));
            });
        }

        function pickRowHeight(h) {
            changeRowHeight(h);
            updateRowHeightBtn(h);
            closeAllCustomPopovers();
            const btn = document.getElementById('row-height-btn');
            if (btn) btn.setAttribute('aria-expanded', 'false');
        }

        // Tab Switching Logic
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                const targetTab = e.target.closest('.tab');
                targetTab.classList.add('active');

                document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
                
                const targetId = targetTab.getAttribute('data-target');
                document.getElementById(targetId).classList.add('active');

                const filterTag = document.getElementById('filter-label');

                if (targetId === 'view-table') {
                    filterTag.innerText = "分组依据: 明细表格";
                } else if (targetId === 'view-kanban-status') {
                    filterTag.innerText = "分组依据: 状态";
                } else if (targetId === 'view-kanban-assignee') {
                    filterTag.innerText = "分组依据: 负责人";
                } else if (targetId === 'view-kanban-stage') {
                    filterTag.innerText = "分组依据: 阶段工作包";
                }
            });
        });

        // Popover Controls with dynamic positioning relative to trigger button
        function toggleCustomPopover(event, id) {
            if (event) event.stopPropagation();
            const btn = event ? (event.currentTarget || (event.target ? event.target.closest('.btn') : null)) : null;
            const popover = document.getElementById(id);
            if (!popover) return;
            const isOpen = popover.classList.contains('show');
            if (btn) btn.setAttribute('aria-expanded', (!isOpen).toString());

            closeAllCustomPopovers();

            if (!isOpen) {
                popover.classList.add('show');
                if (btn) {
                    const toolbar = document.querySelector('.toolbar');
                    const toolbarRect = toolbar.getBoundingClientRect();
                    const btnRect = btn.getBoundingClientRect();
                    
                    let offsetLeft = btnRect.left - toolbarRect.left;
                    const popWidth = popover.offsetWidth || 220;
                    if (offsetLeft + popWidth > toolbarRect.width - 15) {
                        offsetLeft = Math.max(10, toolbarRect.width - popWidth - 15);
                    }
                    
                    popover.style.left = Math.max(10, offsetLeft) + 'px';
                    popover.style.top = (btnRect.bottom - toolbarRect.top + 4) + 'px';
                }
            }
        }

        function closeAllCustomPopovers() {
            closeUiSelect();
            document.querySelectorAll('.popover').forEach(p => p.classList.remove('show'));
        }

        document.addEventListener('click', (e) => {
            if (!e.target.closest('.popover') && !e.target.closest('.btn')) {
                closeAllCustomPopovers();
            }
        });
        
        document.querySelectorAll('.popover').forEach(p => {
            p.addEventListener('click', (e) => e.stopPropagation());
        });

        // Add Record Modal Controls
        function openAddModal() {
            refreshModalTagSelectors();
            document.getElementById('add-modal').classList.add('show');
            setTimeout(() => { const el = document.getElementById('new-id'); if (el) el.focus(); }, 50);
        }
        function closeAddModal() {
            document.getElementById('add-modal').classList.remove('show');
        }
        function submitNewRecord() {
            const id = document.getElementById('new-id').value.trim();
            const name = document.getElementById('new-name').value.trim();
            if (!id || !name) {
                alert('请填写任务编号和任务名称！');
                return;
            }
            const newCard = {
                seq: rawCardsData.length + 1,
                id: id,
                name: name,
                stage: 'S6 工作流集成测试',
                wp: document.getElementById('new-wp').value.trim() || 'WP-自定义',
                wbs: document.getElementById('new-wbs').value.trim() || '',
                assignee: document.getElementById('new-assignee').value,
                status: document.getElementById('new-status').value,
                handler: '严经理',
                est_hours: document.getElementById('new-est').value || '2',
                act_hours: document.getElementById('new-act').value || '0',
                remarks: document.getElementById('new-desc').value,
                process: '手动新增任务'
            };
            rawCardsData.push(newCard);
            saveStorageData();
            applyFilters();
            closeAddModal();
            showToast(`成功创建任务 ${id}！`);
        }

        let isTaskEditMode = false;

        function toggleTaskEditMode(forceEdit) {
            if (typeof forceEdit === 'boolean') {
                isTaskEditMode = forceEdit;
            } else {
                isTaskEditMode = !isTaskEditMode;
            }

            const readBox = document.getElementById('detail-read-container');
            const editBox = document.getElementById('detail-edit-container');
            const toggleBtn = document.getElementById('toggle-detail-edit-btn');
            const saveBtn = document.getElementById('detail-save-btn');
            const deleteBtn = document.getElementById('detail-delete-btn');

            if (isTaskEditMode) {
                if (readBox) readBox.style.display = 'none';
                if (editBox) editBox.style.display = 'flex';
                if (toggleBtn) toggleBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px; vertical-align:-1px;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>切换为查看详情';
                if (saveBtn) saveBtn.style.display = 'inline-flex';
                if (deleteBtn) deleteBtn.style.display = 'inline-flex';
            } else {
                if (readBox) readBox.style.display = 'flex';
                if (editBox) editBox.style.display = 'none';
                if (toggleBtn) toggleBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px; vertical-align:-1px;"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>切换为编辑模式';
                if (saveBtn) saveBtn.style.display = 'none';
                if (deleteBtn) deleteBtn.style.display = 'none';
            }
        }

        // Task Detail & Audit Logs Traceability Modal Controls
        function openTaskDetail(cardId) {
            const card = rawCardsData.find(c => c.id === cardId);
            if (!card) return;

            // 1. Populate Edit Mode Inputs
            const editId = document.getElementById('edit-id');
            const editSeq = document.getElementById('edit-seq');
            const editName = document.getElementById('edit-name');
            const editWp = document.getElementById('edit-wp');
            const editWbs = document.getElementById('edit-wbs');
            const editEst = document.getElementById('edit-est');
            const editAct = document.getElementById('edit-act');
            const editProcess = document.getElementById('edit-process');
            const editOriginalId = document.getElementById('edit-original-id');

            if (editId) editId.value = card.id;
            if (editSeq) editSeq.value = card.seq;
            if (editName) editName.value = card.name;
            if (editWp) editWp.value = card.wp || card.stage || '';
            if (editWbs) editWbs.value = card.wbs || '';
            if (editEst) editEst.value = card.est_hours || 0;
            if (editAct) editAct.value = card.act_hours || 0;
            if (editProcess) editProcess.value = card.process || card.remarks || '';
            if (editOriginalId) editOriginalId.value = card.id;

            const editAssigneeInput = document.getElementById('edit-assignee');
            if (editAssigneeInput) editAssigneeInput.value = card.assignee || '李开发';

            const editStatusInput = document.getElementById('edit-status');
            if (editStatusInput) editStatusInput.value = card.status || '待开始';

            refreshModalTagSelectors();

            // 2. Populate Read Mode View (Header Card & Attributes Grid)
            const headCard = document.getElementById('detail-header-card');
            if (headCard) {
                headCard.innerHTML = `
                    <div class="detail-header-title">
                        <span style="color:var(--primary); font-family:monospace;">[${esc(card.id)}]</span>
                        <span>${esc(card.name || '未命名任务')}</span>
                    </div>
                    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                        <span class="tag tag-status">${esc(card.status || '待开始')}</span>
                        <span class="tag tag-person">负责人: ${esc(card.assignee || '未分配')}</span>
                        ${card.handler ? `<span class="tag tag-stage">当前处理人: ${esc(card.handler)}</span>` : ''}
                        ${card.wbs ? `<span class="tag" style="background:#e8f0fe; color:#2b5cd9;">WBS: ${esc(card.wbs)}</span>` : ''}
                    </div>
                `;
            }

            const attrGrid = document.getElementById('detail-attr-grid');
            if (attrGrid) {
                attrGrid.innerHTML = `
                    <div class="detail-item">
                        <span class="detail-label">阶段 / 工作包</span>
                        <span class="detail-value">${esc(card.wp || card.stage || '-')}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">前置任务依赖</span>
                        <span class="detail-value">${esc(card.pre_tasks || card.prerequisite || '无前置')}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">工时消耗 (预估/实际)</span>
                        <span class="detail-value">${card.est_hours || 0}h / ${card.act_hours || 0}h</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">时间周期</span>
                        <span class="detail-value">${esc(card.start_time || '-')} ~ ${esc(card.end_time || '-')}</span>
                    </div>
                    <div class="detail-item" style="grid-column: 1 / -1;">
                        <span class="detail-label">核心备注</span>
                        <span class="detail-value" style="font-weight:400;">${esc(card.remarks || '暂无备注')}</span>
                    </div>
                `;
            }

            // 3. Populate Timeline Audit Logs & Defect Trace (Multi-field Aggregator)
            const timelineList = document.getElementById('detail-timeline-list');
            if (timelineList) {
                timelineList.innerHTML = '';
                
                let rawLogs = [];
                if (card.process) rawLogs.push(card.process);
                if (card.history && card.history !== card.process) rawLogs.push(card.history);
                if (card.remarks && !card.process) rawLogs.push(`[备注记录] ${card.remarks}`);

                let lines = rawLogs.join('\n').split('\n').map(l => l.trim()).filter(Boolean);
                
                // 智能保底推演：若没有任何显式日志行，自动基于元数据推导首条初始化流转记录
                if (lines.length === 0) {
                    lines = [
                        `[系统初始化] 任务 [${card.id}] 已推入看板，当前状态【${card.status || '待开始'}】，负责人: ${card.assignee || '未分配'}`
                    ];
                    if (card.remarks) lines.push(`[说明/备注] ${card.remarks}`);
                }

                lines.forEach(line => {
                    const item = document.createElement('div');
                    const isDefect = line.includes('DEF-') || line.includes('DEFECT') || line.includes('退回') || line.includes('阻塞');
                    item.className = `timeline-item ${isDefect ? 'defect' : ''}`;
                    
                    let timeStr = '';
                    let contentStr = line;
                    const timeMatch = line.match(/^\[(\d{4}-\d{2}-\d{2}[^\]]*)\]\s*(.*)$/);
                    if (timeMatch) {
                        timeStr = timeMatch[1];
                        contentStr = timeMatch[2];
                    }

                    item.innerHTML = `
                        ${timeStr ? `<div class="timeline-time"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:3px;"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>${esc(timeStr)}</div>` : ''}
                        <div class="timeline-content">${esc(contentStr)}</div>
                    `;
                    timelineList.appendChild(item);
                });
            }

            // Default to Read Mode
            toggleTaskEditMode(false);
            document.getElementById('detail-modal').classList.add('show');

            // 自动将 Timeline 流转记录滑至最底部，保证优先展示最新的流转与移交数据
            setTimeout(() => {
                const timelineList = document.getElementById('detail-timeline-list');
                if (timelineList) {
                    timelineList.scrollTop = timelineList.scrollHeight;
                }
            }, 60);
        }

        function closeDetailModal() {
            document.getElementById('detail-modal').classList.remove('show');
        }

        function saveTaskDetails() {
            const cardId = document.getElementById('edit-original-id').value;
            const card = rawCardsData.find(c => c.id === cardId);
            if (!card) return;

            card.name = document.getElementById('edit-name').value.trim();
            card.wp = document.getElementById('edit-wp').value.trim();
            card.wbs = document.getElementById('edit-wbs').value.trim();
            card.assignee = document.getElementById('edit-assignee').value;
            card.status = document.getElementById('edit-status').value;
            card.est_hours = document.getElementById('edit-est').value;
            card.act_hours = document.getElementById('edit-act').value;
            card.process = document.getElementById('edit-process').value;

            saveStorageData();
            applyFilters();
            closeDetailModal();
            showToast(`任务 ${cardId} 保存成功！`);
        }

        function deleteCurrentTask() {
            const cardId = document.getElementById('edit-original-id').value;
            if (confirm(`确认删除任务 ${cardId} 吗？删除后不可恢复。`)) {
                rawCardsData = rawCardsData.filter(c => c.id !== cardId);
                saveStorageData();
                applyFilters();
                closeDetailModal();
                showToast(`已删除任务 ${cardId}`);
            }
        }

                // Column & Row Resizable Drag Event Handlers
        function makeColumnsResizable() {
            const table = document.getElementById('main-data-table');
            if (!table) return;
            
            const ths = table.querySelectorAll('th');
            ths.forEach(th => {
                th.setAttribute('scope', 'col');
                const resizer = th.querySelector('.resizer');
                if (!resizer) return;

                resizer.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    e.stopPropagation();

                    const startX = e.pageX;
                    const startWidth = th.offsetWidth;
                    resizer.classList.add('resizing');

                    function onMouseMove(e) {
                        const newWidth = Math.max(45, startWidth + (e.pageX - startX));
                        th.style.width = newWidth + 'px';
                        
                        // Recalculate total table width
                        let totalW = 0;
                        table.querySelectorAll('th').forEach(t => {
                            totalW += t.offsetWidth;
                        });
                        table.style.width = totalW + 'px';
                    }

                    function onMouseUp() {
                        resizer.classList.remove('resizing');
                        document.removeEventListener('mousemove', onMouseMove);
                        document.removeEventListener('mouseup', onMouseUp);
                    }

                    document.addEventListener('mousemove', onMouseMove);
                    document.addEventListener('mouseup', onMouseUp);
                });
            });
        }

        function makeRowsResizable() {
            const tbody = document.getElementById('table-body');
            if (!tbody) return;

            tbody.querySelectorAll('.row-resizer').forEach(resizer => {
                resizer.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    e.stopPropagation();

                    const tr = resizer.closest('tr');
                    if (!tr) return;

                    const startY = e.pageY;
                    const startHeight = tr.offsetHeight;
                    resizer.classList.add('resizing');

                    function onMouseMove(e) {
                        const newHeight = Math.max(32, startHeight + (e.pageY - startY));
                        const rowId = tr.getAttribute('data-id');
                        if (rowId) rowHeights[rowId] = newHeight;
                        // Row-scoped custom properties cascade to td and
                        // .cell-content, keeping drag and preset on one model.
                        applyRowHeightVars(tr, newHeight);
                    }

                    function onMouseUp() {
                        resizer.classList.remove('resizing');
                        document.removeEventListener('mousemove', onMouseMove);
                        document.removeEventListener('mouseup', onMouseUp);
                    }

                    document.addEventListener('mousemove', onMouseMove);
                    document.addEventListener('mouseup', onMouseUp);
                });
            });
        }
