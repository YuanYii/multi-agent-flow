/* ============================================================
 * board.js
 * Part of offline_board.html (split for maintainability)
 * Core UI: title, fields, kanban/table, filter/sort, drag, modal, row height, resizable
 * Load order: util.js -> data.js -> listbox.js -> board.js -> app.js
 * ============================================================ */

        // Person Multi-Select State & Logic
        let selectedPersons = new Set();
        const allPersons = ['严经理', '钱架构', '李开发', '马前端', '周审查', '章测试', '李文通', '吕改特'];

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
            { key: 'creator',    th: '创建人',        label: '创建人 (Creator)' },
            { key: 'act_hours',  th: '任务耗时(m)',   label: '任务耗时 (Duration)' },
            { key: 'start_date', th: '开始时间',      label: '开始时间 (Start Date)' },
            { key: 'end_date',   th: '结束时间',      label: '结束时间 (End Date)' },
            { key: 'remarks',    th: '备注',          label: '备注 (Remarks)' },
            { key: 'process',    th: '过程描述',      label: '过程描述 (Process)' }
        ];

        /**
         * 精确计算任务耗时（分钟）
         * 口径：从首次进入【进行中】到进入【已完成】的时间跨度，严格不含【已验收】
         */
        function computeCardDuration(card) {
            if (!card) return;
            // 仅对【已完成】或【已验收】的任务计算闭环耗时；在途任务不提前结算，返回 null (显示 '-')
            if (card.status !== '已完成' && card.status !== '已验收') {
                card._duration_mins = null;
                return;
            }

            // 1. 优先从 process 审计日志中提取 开工时刻 与 完工时刻（严格排除【已验收】）
            if (card.process) {
                const lines = String(card.process).split(/\n|\\n/);
                let inProgressTs = null;
                let completedTs = null;
                const timeRegex = /\[(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:?\d{2}|Z)?)\]/i;

                for (const line of lines) {
                    const tm = line.match(timeRegex);
                    if (!tm) continue;
                    const tsStr = tm[1].replace('T', ' ');
                    const dt = new Date(tsStr.replace(/-/g, '/')).getTime();
                    if (isNaN(dt)) continue;

                    if (line.includes('更新至【进行中】') || line.includes('初始状态【进行中】')) {
                        if (inProgressTs === null || dt < inProgressTs) inProgressTs = dt;
                    }
                    if (line.includes('更新至【已完成】') || line.includes('初始状态【已完成】')) {
                        if (completedTs === null || dt > completedTs) completedTs = dt;
                    }
                }

                if (inProgressTs !== null && completedTs !== null && completedTs >= inProgressTs) {
                    card._duration_mins = Math.max(1, Math.round((completedTs - inProgressTs) / (1000 * 60)));
                    return;
                }
            }

            // 2. 兜底：若 process 无精确记录，读取 start_date 与 end_date
            const st = card.start_date || card.start_time;
            const et = card.end_date || card.end_time;
            if (st && et) {
                const sTime = new Date(String(st).replace('T', ' ').replace(/-/g, '/')).getTime();
                const eTime = new Date(String(et).replace('T', ' ').replace(/-/g, '/')).getTime();
                if (!isNaN(sTime) && !isNaN(eTime) && eTime >= sTime) {
                    card._duration_mins = Math.max(1, Math.round((eTime - sTime) / (1000 * 60)));
                    return;
                }
            }

            // 3. 兜底：读取历史已有 act_hours
            if (card.act_hours !== undefined && card.act_hours !== null && card.act_hours !== '' && card.act_hours !== '-') {
                const s = String(card.act_hours).trim();
                const m = s.match(/^(\d+(?:\.\d+)?)/);
                if (m) {
                    let val = parseFloat(m[1]);
                    if (s.includes('h') && !s.includes('min') && !s.includes('m')) val = Math.round(val * 60);
                    card._duration_mins = Math.round(val);
                    return;
                }
            }

            card._duration_mins = null;
        }

        function formatTaskDuration(card) {
            if (!card) return '-';
            if (card._duration_mins === undefined) {
                computeCardDuration(card);
            }
            return (card._duration_mins !== null && card._duration_mins !== undefined) ? `${card._duration_mins}m` : '-';
        }

        function computeAllCardsDuration(cards) {
            if (!Array.isArray(cards)) return;
            cards.forEach(c => computeCardDuration(c));
        }

        // Card display config: one flag per BOARD_FIELDS entry + a label-prefix toggle
        let cardFieldConfig = BOARD_FIELDS.reduce((acc, f) => { acc[f.key] = true; return acc; }, { showLabels: true });

        function restoreCardFieldConfig() {
            if (typeof kanbanPreferences !== 'undefined' && kanbanPreferences && kanbanPreferences.card_field_config && typeof kanbanPreferences.card_field_config === 'object') {
                cardFieldConfig = Object.assign(cardFieldConfig, kanbanPreferences.card_field_config);
            }
        }

        // Build the field-config popover from the registry so it can never drift from the table
        function renderFieldConfigPopover() {
            restoreCardFieldConfig();
            const showLabelsCb = document.querySelector('#field-popover input[data-field="showLabels"]');
            if (showLabelsCb) {
                showLabelsCb.checked = cardFieldConfig.showLabels !== false;
            }
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

        // Column Configurations (Color-coded dynamically via getBadgeStyle)
        const assigneeColsConfig = [
            { name: "严经理" },
            { name: "钱架构" },
            { name: "李开发" },
            { name: "马前端" },
            { name: "周审查" },
            { name: "章测试" },
            { name: "李文通" },
            { name: "吕改特" }
        ];

        const statusColsConfig = [
            { name: "待开始" },
            { name: "进行中" },
            { name: "审查中" },
            { name: "测试中" },
            { name: "已完成" },
            { name: "已验收" },
            { name: "已退回" },
            { name: "已阻塞" },
            { name: "已取消" }
        ];

        /* ==========================================================
           Board Title Management (统一由 preferences.json 数据源驱动)
           ========================================================== */
        const DEFAULT_BOARD_TITLE = '多专家Agent协作任务看板';
        const BOARD_TITLE_MAX = 60;
        let boardTitleSnapshot = DEFAULT_BOARD_TITLE;

        function getBoardTitle() {
            if (typeof kanbanPreferences === 'object' && kanbanPreferences && kanbanPreferences.title) {
                const t = (kanbanPreferences.title || '').trim();
                if (t) return t;
            }
            return DEFAULT_BOARD_TITLE;
        }

        function applyBoardTitle(title) {
            const el = document.getElementById('board-title');
            if (el) el.textContent = title;
            document.title = title;
            boardTitleSnapshot = title;
            if (typeof kanbanPreferences === 'object' && kanbanPreferences) {
                kanbanPreferences.title = title;
            }
        }

        function commitBoardTitle() {
            const el = document.getElementById('board-title');
            if (!el) return;
            // 去除多余空格并限制长度
            let next = (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, BOARD_TITLE_MAX);
            const restored = !next;
            if (restored) next = DEFAULT_BOARD_TITLE;

            const changed = next !== boardTitleSnapshot;
            if (!changed) return; // 未修改失焦直接忽略，不触发多余落盘

            applyBoardTitle(next);

            // 统一调用 REST API 异步持久化至服务端的 preferences.json
            if (typeof apiSaveBoardMeta === 'function') {
                apiSaveBoardMeta({ title: restored ? '' : next });
            }

            showToast(restored ? '标题已恢复默认：' + DEFAULT_BOARD_TITLE : '标题已更新：' + next);
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
            const field = trigger.dataset.field;
            if (cardId) {
                if (type === 'status') quickUpdateStatus(cardId, value);
                else if (field === 'handler') quickUpdateHandler(cardId, value);
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
            if (cardFieldConfig.status && card.status) {
                const st = getBadgeStyle('status', card.status);
                tagsList.push(`<span class="tag tag-status" style="background:${st.bg}; color:${st.text}; border:1px solid rgba(0,0,0,0.06);">${lbl ? '状态: ' : ''}${esc(card.status)}</span>`);
            }
            if (cardFieldConfig.assignee && card.assignee) {
                const normRole = normalizeRoleName(card.assignee);
                const st = getBadgeStyle('person', normRole);
                tagsList.push(`<span class="tag tag-person" style="background:${st.bg}; color:${st.text}; border:1px solid rgba(0,0,0,0.06);">${lbl ? '负责人: ' : ''}${esc(normRole)}</span>`);
            }
            // 阶段 / 工作包 — mirrors the single "阶段 / 工作包" table column
            if (cardFieldConfig.stage && (card.stage || card.wp)) {
                const stageText = [card.stage, card.wp].filter(Boolean).join(' · ');
                const st = getBadgeStyle('stage', card.stage || card.wp);
                tagsList.push(`<span class="tag tag-stage" style="background:${st.bg}; color:${st.text}; border:1px solid rgba(0,0,0,0.06);">${lbl ? '阶段: ' : ''}${esc(stageText)}</span>`);
            }
            if (cardFieldConfig.handler && card.handler) {
                const normHandler = normalizeRoleName(card.handler);
                const st = getBadgeStyle('person', normHandler);
                tagsList.push(`<span class="tag tag-stage" style="background:${st.bg}; color:${st.text}; border:1px solid rgba(0,0,0,0.06);">${lbl ? '处理人: ' : ''}${esc(normHandler)}</span>`);
            }
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

            // --- 任务耗时 (m) ---
            let hoursHtml = '';
            if (cardFieldConfig.act_hours) {
                const durText = formatTaskDuration(card);
                if (durText !== '-') {
                    hoursHtml = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> ${lbl ? '耗时: ' : ''}${durText}`;
                }
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

        // Render Kanban View (Unified with table dropdown colors)
        function renderKanban(containerId, columnsConfig, groupByField) {
            const container = document.getElementById(containerId);
            if (!container) return;
            container.innerHTML = "";

            const existingColNames = new Set(columnsConfig.map(c => c.name));
            const extraNames = new Set();
            currentCardsData.forEach(c => {
                const rawVal = c[groupByField];
                const val = groupByField === 'assignee' ? normalizeRoleName(rawVal) : (rawVal || '未分类');
                if (!existingColNames.has(val)) {
                    extraNames.add(val);
                }
            });

            const fullConfig = [...columnsConfig];
            extraNames.forEach(name => {
                fullConfig.push({ name: name });
            });

            fullConfig.forEach(col => {
                const colCards = currentCardsData.filter(c => {
                    const rawVal = c[groupByField];
                    const val = groupByField === 'assignee' ? normalizeRoleName(rawVal) : (rawVal || '未分类');
                    return val === col.name;
                });
                
                const typeMap = groupByField === 'assignee' ? 'person' : (groupByField === 'status' ? 'status' : 'stage');
                const st = getBadgeStyle(typeMap, col.name);

                const colHTML = `
                    <div class="column" data-col="${esc(col.name)}" data-groupfield="${groupByField}" style="border-top: 3px solid ${st.text};">
                        <div class="col-header" style="background:${st.bg}; color:${st.text};">
                            <div class="col-title" style="color:${st.text}; font-weight:600;">
                                <span class="ts-dot" style="background:${st.text}; width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:6px; flex-shrink:0;"></span>
                                ${esc(col.name)}
                                <span class="col-count" style="background:rgba(0,0,0,0.06); color:${st.text}; font-weight:700; border-radius:10px; padding:2px 8px; font-size:12px; margin-left:6px;">${colCards.length}</span>
                            </div>
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

        // -------------------------------------------------------------
        // 表格分页状态与渲染
        // -------------------------------------------------------------
        let tablePaginationState = {
            page: 1,
            size: 20 // 10, 20, 50, 100, 或 'all'
        };

        function renderTable() {
            const totalFiltered = currentCardsData.length;
            const sizeParam = tablePaginationState.size;

            let pageCards = currentCardsData;
            let totalPages = 1;
            let startIndex = 0;

            if (sizeParam !== 'all') {
                const sz = parseInt(sizeParam, 10) || 20;
                totalPages = Math.max(1, Math.ceil(totalFiltered / sz));
                if (tablePaginationState.page > totalPages) {
                    tablePaginationState.page = totalPages;
                }
                if (tablePaginationState.page < 1) {
                    tablePaginationState.page = 1;
                }
                startIndex = (tablePaginationState.page - 1) * sz;
                pageCards = currentCardsData.slice(startIndex, startIndex + sz);
            } else {
                tablePaginationState.page = 1;
            }

            renderTableBody(pageCards, startIndex);
            renderPaginationBar(totalFiltered, tablePaginationState.page, sizeParam, totalPages, pageCards.length, startIndex);
        }

        function renderTableBody(pageCards, startIndex = 0) {
            const tbody = document.getElementById('table-body');
            tbody.innerHTML = '';

            pageCards.forEach((card, idx) => {
                const isSelected = selectedTaskIds.has(card.id);
                const savedH = rowHeights[card.id];
                const trStyle = savedH ? rowHeightVars(savedH) : '';
                const displaySeq = startIndex + idx + 1;

                const tr = `
                    <tr data-id="${esc(card.id)}" style="${trStyle}; cursor:pointer;" class="clickable-row" onclick="onTableRowClick(event, '${esc(card.id)}')">
                        <td style="text-align:center;"><input type="checkbox" class="row-cb" value="${esc(card.id)}" ${isSelected ? 'checked' : ''} onchange="toggleSelectRow('${esc(card.id)}', this.checked)"></td>
                        <td style="font-weight:600; color:var(--text-muted); position:relative;">${displaySeq}<div class="row-resizer" title="拖拽调节行高"></div></td>
                        <td><strong style="color:var(--primary);">${esc(card.id)}</strong></td>
                        <td>${esc(card.wbs) || '-'}</td>
                        <td><small style="color:var(--text-muted);">${esc(card.pretask) || '-'}</small></td>
                        <td><div class="cell-content">${esc(card.stage)}<br><small style="color:var(--text-muted)">${esc(card.wp)}</small></div></td>
                        <td><div class="cell-content" style="font-weight:600;">${esc(card.name)}</div></td>
                        <td>
                            ${tagSelectTriggerHTML('status', card.status || '待开始', `data-card-id="${esc(card.id)}"`)}
                        </td>
                        <td>
                            ${tagSelectTriggerHTML('person', card.assignee || '未分配', `data-card-id="${esc(card.id)}" data-field="assignee"`)}
                        </td>
                        <td>
                            ${tagSelectTriggerHTML('person', card.handler || card.assignee || '未分配', `data-card-id="${esc(card.id)}" data-field="handler"`)}
                        </td>
                        <td><small style="color:var(--text-muted); font-family:inherit;">${esc(card.creator || '-')}</small></td>
                        <td>${formatTaskDuration(card)}</td>
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

        function renderPaginationBar(total, page, size, totalPages, currentPageCount, startIndex) {
            const barEl = document.getElementById('table-pagination-bar');
            if (!barEl) return;

            const endIdx = startIndex + currentPageCount;
            const infoRange = total > 0 ? `（第 ${startIndex + 1} - ${endIdx} 条）` : '';

            barEl.innerHTML = `
                <div class="pagination-container">
                    <div class="pagination-info">
                        共 <strong id="pg-total-count">${total}</strong> 条任务 ${infoRange}
                    </div>
                    <div class="pagination-controls">
                        <div class="pagination-size-selector">
                            <span>每页展示：</span>
                            <select id="pagination-size-select" onchange="onTablePageSizeChange(this.value)" class="form-control sm" style="width:auto; padding:2px 8px; height:28px;">
                                <option value="10" ${String(size) === '10' ? 'selected' : ''}>10 条/页</option>
                                <option value="20" ${String(size) === '20' ? 'selected' : ''}>20 条/页</option>
                                <option value="50" ${String(size) === '50' ? 'selected' : ''}>50 条/页</option>
                                <option value="100" ${String(size) === '100' ? 'selected' : ''}>100 条/页</option>
                                <option value="all" ${String(size) === 'all' ? 'selected' : ''}>全部展示</option>
                            </select>
                        </div>
                        ${size !== 'all' && totalPages > 1 ? `
                        <div class="pagination-pager">
                            <button class="btn sm" id="btn-prev-page" onclick="changeTablePage(-1)" ${page <= 1 ? 'disabled' : ''} style="padding:2px 10px; height:28px;">上一页</button>
                            <span class="page-current-indicator">第 <strong>${page}</strong> / <strong>${totalPages}</strong> 页</span>
                            <button class="btn sm" id="btn-next-page" onclick="changeTablePage(1)" ${page >= totalPages ? 'disabled' : ''} style="padding:2px 10px; height:28px;">下一页</button>
                        </div>
                        <div class="pagination-jump">
                            <span>跳至</span>
                            <input type="number" min="1" max="${totalPages}" value="${page}" class="form-control sm" style="width: 50px; text-align: center; height:28px; padding:2px;" onkeydown="if(event.key==='Enter') goToTablePage(this.value)">
                            <span>页</span>
                        </div>
                        ` : (size !== 'all' ? `
                        <div class="pagination-pager">
                            <span class="page-current-indicator">第 <strong>1</strong> / <strong>1</strong> 页</span>
                        </div>
                        ` : '')}
                    </div>
                </div>
            `;
        }

        function onTablePageSizeChange(newSize) {
            tablePaginationState.size = newSize === 'all' ? 'all' : (parseInt(newSize, 10) || 20);
            tablePaginationState.page = 1;
            renderTable();
        }

        function changeTablePage(delta) {
            tablePaginationState.page += delta;
            renderTable();
        }

        function goToTablePage(targetPage) {
            const p = parseInt(targetPage, 10);
            if (!isNaN(p) && p >= 1) {
                tablePaginationState.page = p;
                renderTable();
            }
        }

        function updateCounter() {
            document.getElementById('total-count').innerText = currentCardsData.length;
            document.getElementById('raw-count').innerText = rawCardsData.length;
        }

        function renderStageFilterOptions() {
            const selectEl = document.getElementById('filter-stage');
            if (!selectEl) return;

            const currentVal = selectEl.value;
            const stageSet = new Set();
            rawCardsData.forEach(c => {
                const stg = (c.stage || '').trim();
                if (stg && stg !== '-') stageSet.add(stg);
            });
            const sorted = Array.from(stageSet).sort();
            let html = '<option value="">全部阶段</option>';
            sorted.forEach(name => {
                html += `<option value="${esc(name)}">${esc(name)}</option>`;
            });
            selectEl.innerHTML = html;
            if (sorted.includes(currentVal)) {
                selectEl.value = currentVal;
            }
            if (typeof refreshUiSelects === 'function') {
                refreshUiSelects();
            }
        }

        function renderCreatorFilterOptions() {
            const selectEl = document.getElementById('filter-creator');
            if (!selectEl) return;

            const currentVal = selectEl.value;
            const creatorSet = new Set();
            rawCardsData.forEach(c => {
                const cr = (c.creator || '').trim();
                if (cr && cr !== '-') creatorSet.add(cr);
            });
            const sorted = Array.from(creatorSet).sort();
            let html = '<option value="">全部创建人</option>';
            sorted.forEach(name => {
                html += `<option value="${esc(name)}">${esc(name)}</option>`;
            });
            selectEl.innerHTML = html;
            if (sorted.includes(currentVal)) {
                selectEl.value = currentVal;
            }
            if (typeof refreshUiSelects === 'function') {
                refreshUiSelects();
            }
        }

        const DEFAULT_SAVED_FILTERS = {
            query: '', status: '', stage: '', handler: '', creator: '',
            selected_persons: [], start_from: '', start_to: '', end_from: '', end_to: ''
        };
        const DEFAULT_SAVED_SORT = { field: 'seq', order: 'asc' };

        let filterPersistTimer = null;
        function debouncedPersistFilterAndSort() {
            if (filterPersistTimer) clearTimeout(filterPersistTimer);
            filterPersistTimer = setTimeout(() => {
                persistCurrentFilterAndSortState();
            }, 350);
        }

        function persistCurrentFilterAndSortState() {
            if (typeof apiSaveBoardMeta !== 'function') return;
            const filters = {
                query: (document.getElementById('search-box')?.value || '').trim(),
                status: document.getElementById('filter-status')?.value || '',
                stage: document.getElementById('filter-stage')?.value || '',
                handler: document.getElementById('filter-handler')?.value || '',
                creator: document.getElementById('filter-creator')?.value || '',
                selected_persons: Array.from(selectedPersons),
                start_from: document.getElementById('filter-start-from')?.value || '',
                start_to: document.getElementById('filter-start-to')?.value || '',
                end_from: document.getElementById('filter-end-from')?.value || '',
                end_to: document.getElementById('filter-end-to')?.value || ''
            };
            const sort = {
                field: document.getElementById('sort-field')?.value || 'seq',
                order: document.getElementById('sort-order')?.value || 'asc'
            };
            apiSaveBoardMeta({ filters, sort });
        }

        let hasRestoredInitialFilters = false;
        let isRestoringFilterState = false;
        function restoreFilterAndSortState(force = false) {
            if (hasRestoredInitialFilters && !force) return;
            hasRestoredInitialFilters = true;

            const f = (typeof kanbanPreferences !== 'undefined' && kanbanPreferences && kanbanPreferences.filters && typeof kanbanPreferences.filters === 'object') ? kanbanPreferences.filters : DEFAULT_SAVED_FILTERS;
            const s = (typeof kanbanPreferences !== 'undefined' && kanbanPreferences && kanbanPreferences.sort && typeof kanbanPreferences.sort === 'object') ? kanbanPreferences.sort : DEFAULT_SAVED_SORT;

            isRestoringFilterState = true;
            try {
                if (document.getElementById('search-box')) document.getElementById('search-box').value = f.query || '';
                if (document.getElementById('filter-status')) document.getElementById('filter-status').value = f.status || '';
                if (document.getElementById('filter-stage') && f.stage) document.getElementById('filter-stage').value = f.stage;
                if (document.getElementById('filter-handler')) document.getElementById('filter-handler').value = f.handler || '';
                if (document.getElementById('filter-creator') && f.creator) document.getElementById('filter-creator').value = f.creator;
                if (document.getElementById('filter-start-from')) document.getElementById('filter-start-from').value = f.start_from || '';
                if (document.getElementById('filter-start-to')) document.getElementById('filter-start-to').value = f.start_to || '';
                if (document.getElementById('filter-end-from')) document.getElementById('filter-end-from').value = f.end_from || '';
                if (document.getElementById('filter-end-to')) document.getElementById('filter-end-to').value = f.end_to || '';

                if (Array.isArray(f.selected_persons) && f.selected_persons.length > 0) {
                    selectedPersons = new Set(f.selected_persons);
                } else {
                    selectedPersons.clear();
                }
                renderPersonCheckboxList();

                if (document.getElementById('sort-field')) document.getElementById('sort-field').value = s.field || 'seq';
                if (document.getElementById('sort-order')) document.getElementById('sort-order').value = s.order || 'asc';

                if (typeof refreshUiSelects === 'function') refreshUiSelects();
            } finally {
                isRestoringFilterState = false;
            }
        }

        function initRender() {
            // 0. Pre-calculate duration for all cards for O(1) renders and sorts
            computeAllCardsDuration(rawCardsData);

            // 1. Kanban Assignee
            renderKanban("board-assignee", assigneeColsConfig, "assignee");

            // 2. Kanban Stage
            const stageNames = Array.from(new Set(rawCardsData.map(c => c.stage || 'S6 工作流集成测试')));
            const stageColsConfig = stageNames.map(s => ({ name: s, theme: "blue" }));
            renderKanban("board-stage", stageColsConfig, "stage");

            // 3. Kanban Status
            renderKanban("board-status", statusColsConfig, "status");

            // 4. Data Table & Filters
            renderTable();
            renderPersonCheckboxList();
            renderStageFilterOptions();
            renderCreatorFilterOptions();
            restoreFilterAndSortState();
            updateCounter();
            refreshModalTagSelectors();
        }

        // Search, Filter, Sort Handlers
        function onSearch() {
            applyFilters();
        }

        function applyFilters() {
            const query = document.getElementById('search-box').value.trim().toLowerCase();
            const statusFilter = document.getElementById('filter-status') ? document.getElementById('filter-status').value : '';
            const stageFilter = document.getElementById('filter-stage') ? document.getElementById('filter-stage').value : '';
            const handlerFilter = document.getElementById('filter-handler') ? document.getElementById('filter-handler').value : '';
            const creatorFilter = document.getElementById('filter-creator') ? document.getElementById('filter-creator').value : '';
            const startFrom = document.getElementById('filter-start-from') ? document.getElementById('filter-start-from').value : '';
            const startTo = document.getElementById('filter-start-to') ? document.getElementById('filter-start-to').value : '';
            const endFrom = document.getElementById('filter-end-from') ? document.getElementById('filter-end-from').value : '';
            const endTo = document.getElementById('filter-end-to') ? document.getElementById('filter-end-to').value : '';
            const personFocusActive = isPersonFocusActive();

            currentCardsData = rawCardsData.filter(c => {
                const matchQuery = !query || (
                    (c.id && c.id.toLowerCase().includes(query)) ||
                    (c.name && c.name.toLowerCase().includes(query)) ||
                    (c.assignee && c.assignee.toLowerCase().includes(query)) ||
                    (c.handler && c.handler.toLowerCase().includes(query)) ||
                    (c.creator && c.creator.toLowerCase().includes(query)) ||
                    (c.status && c.status.toLowerCase().includes(query)) ||
                    (c.stage && c.stage.toLowerCase().includes(query)) ||
                    (c.wbs && c.wbs.toLowerCase().includes(query)) ||
                    (c.remarks && c.remarks.toLowerCase().includes(query)) ||
                    (c.process && c.process.toLowerCase().includes(query))
                );
                const matchStatus = !statusFilter || c.status === statusFilter;
                const matchStage = !stageFilter || (c.stage && c.stage === stageFilter);

                // Handler matching:
                let matchHandler = true;
                if (handlerFilter) {
                    if (handlerFilter === '未分配') {
                        matchHandler = !c.handler || c.handler === '未分配' || (!c.handler && !c.assignee);
                    } else {
                        const eff = normalizeRoleName(c.handler || c.assignee);
                        matchHandler = eff === normalizeRoleName(handlerFilter);
                    }
                }

                // Creator matching:
                const matchCreator = !creatorFilter || (c.creator && c.creator === creatorFilter);

                // Person focus matching (Assignee multi-select from toolbar):
                const matchMultiPerson = !personFocusActive || selectedPersons.has(c.assignee) || selectedPersons.has(normalizeRoleName(c.assignee));

                // Date range comparisons (pure ISO string prefix comparison)
                const cStartDate = (c.start_date || c.start_time || '').slice(0, 10);
                const matchStartFrom = !startFrom || (cStartDate && cStartDate >= startFrom);
                const matchStartTo = !startTo || (cStartDate && cStartDate <= startTo);

                const cEndDate = (c.end_date || c.end_time || '').slice(0, 10);
                const matchEndFrom = !endFrom || (cEndDate && cEndDate >= endFrom);
                const matchEndTo = !endTo || (cEndDate && cEndDate <= endTo);

                return matchQuery && matchStatus && matchStage && matchHandler && matchCreator &&
                       matchMultiPerson && matchStartFrom && matchStartTo && matchEndFrom && matchEndTo;
            });

            updateActiveFilterHint(query, statusFilter, stageFilter, handlerFilter, creatorFilter, startFrom, startTo, endFrom, endTo);
            if (!isRestoringFilterState) {
                debouncedPersistFilterAndSort();
            }
            if (typeof tablePaginationState !== 'undefined') {
                tablePaginationState.page = 1;
            }
            applySort();
        }

        // Is the "聚焦人员" multi-select actually narrowing anything?
        // (empty = untouched, all-selected = equivalent to 全部人员) → both are no-ops
        function isPersonFocusActive() {
            return selectedPersons.size > 0 && selectedPersons.size < allPersons.length;
        }

        // Surface which filters are currently narrowing the result set, so an empty
        // result never looks like "the data vanished".
        function updateActiveFilterHint(query, statusFilter, stageFilter, handlerFilter, creatorFilter, startFrom, startTo, endFrom, endTo) {
            const el = document.getElementById('active-filter-hint');
            if (!el) return;

            const parts = [];
            if (query) parts.push(`搜索"${query}"`);
            if (statusFilter) parts.push(`状态=${statusFilter}`);
            if (stageFilter) parts.push(`阶段=${stageFilter}`);
            if (handlerFilter) parts.push(`处理人=${handlerFilter}`);
            if (creatorFilter) parts.push(`创建人=${creatorFilter}`);
            if (isPersonFocusActive()) parts.push(`聚焦人员=${Array.from(selectedPersons).join('/')}`);
            if (startFrom || startTo) parts.push(`开始时间=${startFrom || '...'}~${startTo || '...'}`);
            if (endFrom || endTo) parts.push(`结束时间=${endFrom || '...'}~${endTo || '...'}`);

            if (parts.length === 0) {
                el.style.display = 'none';
                el.innerText = '';
                el.removeAttribute('data-conflict');
                return;
            }

            el.style.display = 'inline-flex';
            el.removeAttribute('data-conflict');
            el.innerText = `筛选中：${parts.join(' 且 ')}（${currentCardsData.length} 条）`;
        }

        function resetFilters() {
            document.getElementById('search-box').value = '';
            const st = document.getElementById('filter-status'); if (st) st.value = '';
            const stg = document.getElementById('filter-stage'); if (stg) stg.value = '';
            const hd = document.getElementById('filter-handler'); if (hd) hd.value = '';
            const cr = document.getElementById('filter-creator'); if (cr) cr.value = '';
            const sf = document.getElementById('filter-start-from'); if (sf) sf.value = '';
            const st_to = document.getElementById('filter-start-to'); if (st_to) st_to.value = '';
            const ef = document.getElementById('filter-end-from'); if (ef) ef.value = '';
            const et = document.getElementById('filter-end-to'); if (et) et.value = '';
            document.getElementById('sort-field').value = 'seq';
            document.getElementById('sort-order').value = 'asc';
            selectedPersons.clear();
            renderPersonCheckboxList();
            renderStageFilterOptions();
            renderCreatorFilterOptions();
            refreshUiSelects();
            if (typeof tablePaginationState !== 'undefined') {
                tablePaginationState.page = 1;
            }
            if (typeof apiSaveBoardMeta === 'function') {
                apiSaveBoardMeta({ filters: DEFAULT_SAVED_FILTERS, sort: DEFAULT_SAVED_SORT });
            }
            applyFilters();
            closeAllCustomPopovers();
            showToast('已重置所有筛选条件！');
        }

        function applySort() {
            const field = document.getElementById('sort-field').value;
            const order = document.getElementById('sort-order').value;

            if (field !== 'seq') {
                currentCardsData.sort((a, b) => {
                    let valA = a[field] || '';
                    let valB = b[field] || '';
                    if (field === 'act_hours') {
                        valA = (a._duration_mins !== undefined && a._duration_mins !== null) ? a._duration_mins : -1;
                        valB = (b._duration_mins !== undefined && b._duration_mins !== null) ? b._duration_mins : -1;
                    }

                    if (valA < valB) return order === 'asc' ? -1 : 1;
                    if (valA > valB) return order === 'asc' ? 1 : -1;
                    return 0;
                });
            } else {
                currentCardsData.sort((a, b) => order === 'asc' ? a.seq - b.seq : b.seq - a.seq);
            }

            if (!isRestoringFilterState) {
                debouncedPersistFilterAndSort();
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

        function quickUpdateHandler(cardId, newHandler) {
            const card = rawCardsData.find(c => c.id === cardId);
            if (card && card.handler !== newHandler) {
                const oldHandler = card.handler;
                card.handler = newHandler;
                appendProcessLog(card, `[快捷处理人变更] 处理人由【${oldHandler || '未设定'}】变更为【${newHandler}】`);
                saveStorageData();
                applyFilters();
                showToast(`已更新 ${card.id} 处理人为: ${newHandler}`);
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

        let pendingConfirmAction = null;

        function openCustomConfirm(title, message, onConfirm) {
            const titleEl = document.getElementById('confirm-modal-title');
            const msgEl = document.getElementById('confirm-modal-msg');
            const okBtn = document.getElementById('confirm-modal-ok-btn');

            if (titleEl) {
                titleEl.innerHTML = `
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    ${esc(title || '操作确认')}
                `;
            }
            if (msgEl) msgEl.innerHTML = esc(message);

            pendingConfirmAction = onConfirm;
            if (okBtn) {
                okBtn.onclick = () => {
                    if (pendingConfirmAction) pendingConfirmAction();
                    closeConfirmModal();
                };
            }

            document.getElementById('confirm-modal').classList.add('show');
        }

        function closeConfirmModal() {
            pendingConfirmAction = null;
            document.getElementById('confirm-modal').classList.remove('show');
        }

        function batchDeleteRecords() {
            if (selectedTaskIds.size === 0) return;
            openCustomConfirm('批量删除确认', `确定要批量删除选中的 ${selectedTaskIds.size} 条任务记录吗？删除后无法恢复。`, () => {
                rawCardsData = rawCardsData.filter(c => !selectedTaskIds.has(c.id));
                selectedTaskIds.clear();
                saveStorageData();
                applyFilters();
                showToast('已完成批量删除操作！');
            });
        }

        // Field Config Listener
        function updateFieldConfig() {
            document.querySelectorAll('#field-popover input[type="checkbox"]').forEach(cb => {
                const field = cb.getAttribute('data-field');
                if (field) cardFieldConfig[field] = cb.checked;
            });
            if (typeof apiSaveBoardMeta === 'function') {
                apiSaveBoardMeta({ card_field_config: cardFieldConfig });
            }
            initRender();
        }

        function setAllCardFields(checked) {
            BOARD_FIELDS.forEach(f => { cardFieldConfig[f.key] = checked; });
            if (typeof apiSaveBoardMeta === 'function') {
                apiSaveBoardMeta({ card_field_config: cardFieldConfig });
            }
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

        function syncToolbarForActiveView(targetId) {
            const isTable = targetId === 'view-table';
            const fieldConfigBtn = document.getElementById('field-config-btn');
            if (fieldConfigBtn) fieldConfigBtn.style.display = isTable ? 'none' : 'inline-flex';

            const rowHeightBtn = document.getElementById('row-height-btn');
            if (rowHeightBtn) rowHeightBtn.style.display = isTable ? 'inline-flex' : 'none';

            const rowHeightDivider = document.getElementById('row-height-divider');
            if (rowHeightDivider) rowHeightDivider.style.display = isTable ? 'inline-block' : 'none';

            const importBtn = document.getElementById('import-json-btn');
            if (importBtn) importBtn.style.display = isTable ? 'inline-flex' : 'none';

            const exportBtn = document.getElementById('export-json-btn');
            if (exportBtn) exportBtn.style.display = isTable ? 'inline-flex' : 'none';

            const ioDivider = document.getElementById('import-export-divider');
            if (ioDivider) ioDivider.style.display = isTable ? 'inline-block' : 'none';
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

                syncToolbarForActiveView(targetId);
            });
        });

        // Initialize toolbar visibility according to active view
        syncToolbarForActiveView('view-table');

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
                showToast('[WARN]  请填写任务编号和任务名称！');
                return;
            }
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            const hours = String(now.getHours()).padStart(2, '0');
            const mins = String(now.getMinutes()).padStart(2, '0');
            const secs = String(now.getSeconds()).padStart(2, '0');
            const nowStr = `${year}-${month}-${day} ${hours}:${mins}:${secs}`;
            const initStatus = document.getElementById('new-status').value || '待开始';
            const initAssignee = document.getElementById('new-assignee').value || '严经理';

            const newCard = {
                seq: rawCardsData.length + 1,
                id: id,
                name: name,
                stage: 'S6 工作流集成测试',
                wp: document.getElementById('new-wp').value.trim() || 'WP-自定义',
                wbs: document.getElementById('new-wbs').value.trim() || '',
                assignee: initAssignee,
                status: initStatus,
                handler: '严经理',
                act_hours: document.getElementById('new-act').value || '0',
                remarks: document.getElementById('new-desc').value,
                process: `[${nowStr}] [${initStatus}] 手动创建任务 [${id}]，初始状态【${initStatus}】，负责人: ${initAssignee}`
            };
            computeCardDuration(newCard);
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
            const editAct = document.getElementById('edit-act');
            const editProcess = document.getElementById('edit-process');
            const editOriginalId = document.getElementById('edit-original-id');

            if (editId) editId.value = card.id;
            if (editSeq) editSeq.value = card.seq;
            if (editName) editName.value = card.name;
            if (editWp) editWp.value = card.wp || card.stage || '';
            if (editWbs) editWbs.value = card.wbs || '';
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
                        <span class="tag" style="background:${getBadgeStyle('status', card.status).bg}; color:${getBadgeStyle('status', card.status).text}; border:1px solid rgba(0,0,0,0.06);">${esc(card.status || '待开始')}</span>
                        <span class="tag" style="background:${getBadgeStyle('person', card.assignee).bg}; color:${getBadgeStyle('person', card.assignee).text}; border:1px solid rgba(0,0,0,0.06);">负责人: ${esc(card.assignee || '未分配')}</span>
                        ${card.handler ? `<span class="tag" style="background:${getBadgeStyle('person', card.handler).bg}; color:${getBadgeStyle('person', card.handler).text}; border:1px solid rgba(0,0,0,0.06);">处理人: ${esc(card.handler)}</span>` : ''}
                        ${card.wbs ? `<span class="tag" style="background:#e8f0fe; color:#2b5cd9;">WBS: ${esc(card.wbs)}</span>` : ''}
                    </div>
                `;
            }

            const attrGrid = document.getElementById('detail-attr-grid');
            if (attrGrid) {
                let cleanRemarks = (card.remarks || '暂无备注').replace(/\\n/g, '\n');
                let remarkLines = cleanRemarks.split('\n').map(l => l.trim()).filter(Boolean);
                let uniqueRemarks = Array.from(new Set(remarkLines)).join('\n');

                attrGrid.innerHTML = `
                    <div class="detail-item">
                        <span class="detail-label">阶段 / 工作包</span>
                        <span class="detail-value">${esc(card.wp || card.stage || '-')}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">创建人 (Creator)</span>
                        <span class="detail-value" style="color:var(--primary); font-weight:600;">${esc(card.creator || '-')}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">前置任务依赖</span>
                        <span class="detail-value">${esc(card.pre_tasks || card.prerequisite || '无前置')}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">任务耗时 (Duration)</span>
                        <span class="detail-value" style="font-weight:600; color:var(--primary);">${formatTaskDuration(card)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">时间周期</span>
                        <span class="detail-value">${esc(card.start_date || card.start_time || '-')} ~ ${esc(card.end_date || card.end_time || '-')}</span>
                    </div>
                    <div class="detail-item" style="grid-column: 1 / -1;">
                        <span class="detail-label">核心备注</span>
                        <span class="detail-value" style="font-weight:400; white-space: pre-wrap; word-break: break-word;">${esc(uniqueRemarks)}</span>
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

                let rawStr = rawLogs.join('\n').replace(/\\n/g, '\n');
                let lines = rawStr.split('\n').map(l => l.trim()).filter(Boolean);

                // 多行节点合并：'操作说明:' 起始的行是上一节点的说明段，合并进上一行
                // （数据两行、渲染一节点；旧格式单行节点不受影响）
                let merged = [];
                for (const l of lines) {
                    if (/^操作说明[:：]/.test(l) && merged.length) {
                        merged[merged.length - 1] += '\n' + l;
                    } else {
                        merged.push(l);
                    }
                }
                lines = merged;
                
                // 智能保底推演：若没有任何显式日志行，自动基于元数据推导首条初始化流转记录
                if (lines.length === 0) {
                    lines = [
                        `[${card.start_date || '系统初始化'}] [待开始] 任务 [${card.id}] 已推入看板，当前状态【${card.status || '待开始'}】，负责人: ${card.assignee || '未分配'}`
                    ];
                    if (card.status === '进行中' || card.status === '审查中' || card.status === '测试中' || card.status === '已完成' || card.status === '已验收') {
                        lines.push(`[${card.start_date || '执行阶段'}] [进行中] 开始排查与执行任务`);
                    }
                    if (card.status === '已完成' || card.status === '已验收') {
                        lines.push(`[${card.end_date || '完成阶段'}] [${card.status}] ${card.remarks || '完成任务规范排查与归档'}`);
                    }
                }

                let uniqueLines = Array.from(new Set(lines));

                // 节点序号排序：含 [{任务ID}-N{序号}] 双标识的行按序号升序；
                // 无节点标识的旧格式行保持原相对顺序排最前（历史数据兼容）
                const nodeSeqOf = (l) => {
                    const m = l.match(/\[(T\d+)-N(\d+)\]/);
                    return m ? parseInt(m[2], 10) : -1;
                };
                uniqueLines.sort((a, b) => {
                    const na = nodeSeqOf(a), nb = nodeSeqOf(b);
                    if (na !== nb) return na - nb;
                    return 0; // 同号或同为旧行：稳定排序保持原序
                });

                uniqueLines.forEach(line => {
                    const row = document.createElement('div');
                    row.className = 'timeline-row';

                    const isDefect = line.includes('DEF-') || line.includes('DEFECT') || line.includes('退回') || line.includes('阻塞');
                    
                    let timeStr = '';
                    let contentStr = line;
                    let statusTag = '';

                    // 1. 时间提取（旧格式: 行首 [时间]；新格式: [节点ID]  [时间]  描述）
                    const timeMatch = line.match(/^\[(\d{4}-\d{2}-\d{2}[^\]]*)\]\s*(.*)$/);
                    if (timeMatch) {
                        timeStr = timeMatch[1];
                        contentStr = timeMatch[2];
                    } else {
                        const nodeTimeMatch = line.match(/^\[T\d+-N\d+\]\s+\[(\d{4}-\d{2}-\d{2}[^\]]*)\]\s*([\s\S]*)$/);
                        if (nodeTimeMatch) {
                            timeStr = nodeTimeMatch[1];
                            contentStr = nodeTimeMatch[2];
                        }
                    }

                    // 2. 多维智能标签提取 (状态 / 负责人移交 / 阶段工作包 / 记录保底)
                    const validStatuses = ['待开始', '进行中', '审查中', '测试中', '已完成', '已验收', '已退回', '已阻塞', '已取消'];
                    const validPersons = ['严经理', '钱架构', '李开发', '马前端', '前端开发', '周审查', '章测试', '李文通', '吕改特'];
                    const validStages = ['Phase-1', 'Phase-2', 'Phase-3', 'WP1-需求', 'WP2-后端', 'WP2-前端', 'WP3-测试', 'WP4-运维'];

                    let tagType = '';
                    let tagLabel = '';

                    // 优先模式 A: 匹配明确的流转目标动词 (更新至、更新为、流转至、移交至、变更为、调整为、置为、退回到、回到、-> 等)
                    const transitionVerbRegex = /(?:更新至|更新为|流转至|流转到|变更为|调整为|推至|置为|移交至|退回到|退回至|重置为|切换至|回到|->|=>|to)\s*[【\\[]?([^】\\]\s]+)[】\\]?/i;
                    const verbMatch = contentStr.match(transitionVerbRegex);
                    if (verbMatch) {
                        const rawTarget = verbMatch[1].trim();
                        if (validStatuses.includes(rawTarget)) {
                            tagType = 'status';
                            tagLabel = rawTarget;
                        } else {
                            const normP = normalizeRoleName(rawTarget);
                            if (validPersons.includes(normP) || validPersons.includes(rawTarget)) {
                                tagType = 'person';
                                tagLabel = normP;
                            } else if (validStages.some(stg => rawTarget.includes(stg) || stg.includes(rawTarget))) {
                                tagType = 'stage';
                                tagLabel = rawTarget;
                            }
                        }
                    }

                    // 优先模式 B: 从右向左扫描所有括号提取终态实体
                    if (!tagLabel) {
                        const allBrackets = Array.from(contentStr.matchAll(/[\\[【]([^\\]】]+)[\\]】]/g)).map(m => m[1].trim());
                        for (let i = allBrackets.length - 1; i >= 0; i--) {
                            const item = allBrackets[i];
                            if (validStatuses.includes(item)) {
                                tagType = 'status';
                                tagLabel = item;
                                break;
                            }
                            const normP = normalizeRoleName(item);
                            if (validPersons.includes(normP) || validPersons.includes(item)) {
                                tagType = 'person';
                                tagLabel = normP;
                                break;
                            }
                            if (validStages.some(stg => item.includes(stg))) {
                                tagType = 'stage';
                                tagLabel = item;
                                break;
                            }
                            if (item === '系统初始化' || item === '待开始' || item === '初始化') {
                                tagType = 'status';
                                tagLabel = '待开始';
                                break;
                            }
                            if (item === '备注记录' || item === '备注') {
                                tagType = 'generic';
                                tagLabel = '备注';
                                break;
                            }
                        }
                    }

                    // 优先模式 C: 全文关键词倒序扫描
                    if (!tagLabel) {
                        let lastIdx = -1;
                        let foundSt = '';
                        validStatuses.forEach(st => {
                            const idx = contentStr.lastIndexOf(st);
                            if (idx > lastIdx) {
                                lastIdx = idx;
                                foundSt = st;
                            }
                        });
                        if (foundSt) {
                            tagType = 'status';
                            tagLabel = foundSt;
                        }
                    }
                    if (!tagLabel) {
                        let lastIdx = -1;
                        let foundP = '';
                        validPersons.forEach(p => {
                            const idx = contentStr.lastIndexOf(p);
                            if (idx > lastIdx) {
                                lastIdx = idx;
                                foundP = p;
                            }
                        });
                        if (foundP) {
                            tagType = 'person';
                            tagLabel = normalizeRoleName(foundP);
                        }
                    }

                    // 兜底模式 D: 语义分类兜底
                    if (!tagLabel) {
                        if (isDefect) {
                            tagType = 'status';
                            tagLabel = '已退回';
                        } else if (contentStr.includes('手动新增') || contentStr.includes('新增任务') || contentStr.includes('创建任务') || contentStr.includes('初始化') || contentStr.includes('建单')) {
                            tagType = 'status';
                            tagLabel = '待开始';
                        } else if (contentStr.includes('负责人') || contentStr.includes('处理人') || contentStr.includes('移交')) {
                            tagType = 'generic';
                            tagLabel = '移交';
                        } else {
                            tagType = 'generic';
                            tagLabel = '记录';
                        }
                    }

                    // 渲染对应色彩徽标
                    let st;
                    if (tagType === 'status') {
                        st = getBadgeStyle('status', tagLabel);
                    } else if (tagType === 'person') {
                        st = getBadgeStyle('person', tagLabel);
                    } else if (tagType === 'stage') {
                        st = getBadgeStyle('stage', tagLabel);
                    } else {
                        st = { bg: '#f1f5f9', text: '#475569' };
                    }

                    const statusBadgeHTML = `<span class="timeline-status-tag" style="background:${st.bg};color:${st.text};border:1px solid rgba(0,0,0,0.06);"><span class="ts-dot" style="background:${st.text}"></span><span class="ts-label">${esc(tagLabel)}</span></span>`;

                    row.innerHTML = `
                        <div class="timeline-node">
                            ${statusBadgeHTML}
                        </div>
                        <div class="timeline-item ${isDefect ? 'defect' : ''}">
                            ${timeStr ? `<div class="timeline-time"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:3px;"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>${esc(timeStr)}</div>` : ''}
                            <div class="timeline-content" style="word-break:break-word; line-height:1.4; color:var(--text-color);">${esc(contentStr)}</div>
                        </div>
                    `;
                    timelineList.appendChild(row);
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
            card.act_hours = document.getElementById('edit-act').value;
            card.process = document.getElementById('edit-process').value;
            computeCardDuration(card);

            saveStorageData();
            applyFilters();
            closeDetailModal();
            showToast(`任务 ${cardId} 保存成功！`);
        }

        function deleteCurrentTask() {
            const cardId = document.getElementById('edit-original-id').value;
            closeDetailModal();
            openCustomConfirm('删除任务确认', `确认要永久删除任务 [${cardId}] 吗？删除后无法恢复。`, () => {
                rawCardsData = rawCardsData.filter(c => c.id !== cardId);
                saveStorageData();
                applyFilters();
                showToast(`已删除任务 ${cardId}`);
            });
        }

        // Column & Row Resizable Drag Event Handlers
        const DEFAULT_COL_WIDTHS = [40, 55, 90, 90, 110, 170, 320, 110, 110, 110, 90, 95, 105, 105, 260, 320, 70];

        function applyColumnWidths(table, widths) {
            if (!table) return;
            const ths = table.querySelectorAll('thead th');
            let totalW = 0;
            ths.forEach((th, idx) => {
                const w = widths[idx] || DEFAULT_COL_WIDTHS[idx] || 90;
                th.style.width = w + 'px';
                totalW += w;
            });
            table.style.width = totalW + 'px';
            table.style.minWidth = totalW + 'px';
        }

        function makeColumnsResizable() {
            const table = document.getElementById('main-data-table');
            if (!table) return;
            
            // Load saved widths or apply standard defaults
            let savedWidths = null;
            try {
                const raw = localStorage.getItem('kanban_col_widths');
                if (raw) savedWidths = JSON.parse(raw);
            } catch (e) {}

            applyColumnWidths(table, Array.isArray(savedWidths) && savedWidths.length === DEFAULT_COL_WIDTHS.length ? savedWidths : DEFAULT_COL_WIDTHS);

            const ths = table.querySelectorAll('thead th');
            ths.forEach((th, idx) => {
                th.setAttribute('scope', 'col');
                const resizer = th.querySelector('.resizer');
                if (!resizer) return;

                // Double-click resizer to restore default standard width
                resizer.addEventListener('dblclick', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const defW = DEFAULT_COL_WIDTHS[idx] || 90;
                    th.style.width = defW + 'px';
                    let currentWidths = [];
                    let totalW = 0;
                    table.querySelectorAll('thead th').forEach(t => {
                        const w = t.offsetWidth;
                        currentWidths.push(w);
                        totalW += w;
                    });
                    table.style.width = totalW + 'px';
                    table.style.minWidth = totalW + 'px';
                    try { localStorage.setItem('kanban_col_widths', JSON.stringify(currentWidths)); } catch (err) {}
                    showToast(`已重置 [${th.textContent.replace('▼','').replace('▲','').trim()}] 为标准默认宽度 (${defW}px)`);
                });

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
                        table.querySelectorAll('thead th').forEach(t => {
                            totalW += t.offsetWidth;
                        });
                        table.style.width = totalW + 'px';
                        table.style.minWidth = totalW + 'px';
                    }

                    function onMouseUp() {
                        resizer.classList.remove('resizing');
                        document.removeEventListener('mousemove', onMouseMove);
                        document.removeEventListener('mouseup', onMouseUp);

                        // Persist customized widths
                        let currentWidths = [];
                        table.querySelectorAll('thead th').forEach(t => {
                            currentWidths.push(t.offsetWidth);
                        });
                        try { localStorage.setItem('kanban_col_widths', JSON.stringify(currentWidths)); } catch (err) {}
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
