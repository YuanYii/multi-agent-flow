/* ============================================================
 * util.js
 * Part of offline_board.html (split for maintainability)
 * Shared pure helpers (no module deps)
 * Load order: util.js -> data.js -> listbox.js -> board.js -> app.js
 * ============================================================ */
        function showToast(msg) {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = 'toast';
            toast.innerText = msg;
            container.appendChild(toast);
            setTimeout(() => {
                toast.remove();
            }, 2500);
        }

        // HTML escape helper (prevent broken rendering / injection from data fields)
        function esc(value) {
            return String(value == null ? '' : value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }
        const escapeHtml = esc;
        window.escapeHtml = esc;

        /* ============================================================
           Custom Color-Coded Dropdown Engine
           Replaces native <select> for status / assignee so the
           open panel can be styled and each option color-coded.
           ============================================================ */
        const STATUS_OPTIONS = ['待开始','进行中','审查中','测试中','已完成','已验收','已退回','已阻塞','已取消'];
        const PERSON_OPTIONS = ['严经理','钱架构','李开发','曹艾','周审查','章测试','李文通','吕改特'];

        // bg = light tint, text = saturated hue (mirrors table .tag aesthetic)
        const STATUS_COLORS = {
            '待开始': { bg:'#f2f3f5', text:'#4e5969' },
            '进行中': { bg:'#e8f0fe', text:'#3370ff' },
            '审查中': { bg:'#e8eaff', text:'#3a5bdb' },
            '测试中': { bg:'#e6fffb', text:'#08979c' },
            '已完成': { bg:'#e8ffea', text:'#00a854' },
            '已验收': { bg:'#e6fae8', text:'#2f9e44' },
            '已退回': { bg:'#fff7e6', text:'#d97706' },
            '已阻塞': { bg:'#fff1f0', text:'#f53f3f' },
            '已取消': { bg:'#f5f5f5', text:'#8c8c8c' }
        };
        const PERSON_COLORS = {
            '严经理': { bg:'#e6f6eb', text:'#248a3d' },
            '钱架构': { bg:'#e1eaff', text:'#3a5bdb' },
            '李开发': { bg:'#fff0e0', text:'#d97706' },
            '曹艾':   { bg:'#f3e8ff', text:'#7c3aed' },
            '周审查': { bg:'#e0f2fe', text:'#0284c7' },
            '章测试': { bg:'#fce8f8', text:'#c21897' },
            '李文通': { bg:'#fff7e6', text:'#b45309' },
            '吕改特': { bg:'#f0f0f0', text:'#595959' }
        };

        function getBadgeStyle(type, value) {
            const map = type === 'status' ? STATUS_COLORS : PERSON_COLORS;
            return map[value] || { bg:'#f2f3f5', text:'#4e5969' };
        }

        function badgeInner(type, value) {
            const st = getBadgeStyle(type, value);
            const caret = `<svg class="ts-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="${st.text}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>`;
            return `<span class="ts-dot" style="background:${st.text}"></span><span class="ts-label">${esc(value)}</span>${caret}`;
        }

        // For trigger rendered inside JS template literals (table rows)
        function tagSelectTriggerHTML(type, value, attrs) {
            const st = getBadgeStyle(type, value);
            return `<div class="tag-select" data-type="${type}" ${attrs || ''} data-value="${esc(value)}" style="background:${st.bg};color:${st.text};border-color:rgba(0,0,0,0.06)">${badgeInner(type, value)}</div>`;
        }

        /* ============================================================
           Sunrise/Sunset Auto Theme
           NOAA 标准天文学算法本地计算日出日落 + 浅/深色主题切换
           ============================================================ */
        const DEFAULT_LAT = 39.9042;   // 默认纬度：北京（北纬为正），按需修改
        const DEFAULT_LNG = 116.4074;  // 默认经度：北京（东经为正），按需修改
        const THEME_KEY = 'board_theme'; // 'light' | 'dark'；无值 = 按日落自动

        /**
         * 纯本地计算日出日落时间（NOAA 标准天文学算法）
         * @param {Date} date - 系统当前时间对象
         * @param {number} lat - 纬度 (北纬为正，南纬为负)
         * @param {number} lng - 经度 (东经为正，西经为负)
         */
        function getSunTimesLocally(date, lat, lng) {
            const D2R = Math.PI / 180;
            const R2D = 180 / Math.PI;

            // 1. 获取当年的第几天 (Day of year)
            const startOfYear = new Date(date.getFullYear(), 0, 0);
            const dayOfYear = Math.floor((date - startOfYear) / 86400000);

            // 2. 太阳天顶角标准修正值（日出日落折射角 90.833 度）
            const zenith = 90.833;

            function calculate(isSunrise) {
                const lngHour = lng / 15;
                const t = dayOfYear + ((isSunrise ? 6 : 18) - lngHour) / 24;

                // 太阳平黄经 M 与真黄经 L
                const M = 0.9856 * t - 3.289;
                let L = M + 1.916 * Math.sin(M * D2R) + 0.02 * Math.sin(2 * M * D2R) + 282.634;
                L = (L + 360) % 360;

                // 太阳赤纬 Dec
                const sinDec = 0.39782 * Math.sin(L * D2R);
                const cosDec = Math.cos(Math.asin(sinDec));

                // 太阳赤经 RA
                let RA = R2D * Math.atan(0.91764 * Math.tan(L * D2R));
                RA = (RA + 360) % 360;
                RA = (RA + (Math.floor(L / 90) * 90 - Math.floor(RA / 90) * 90)) / 15;

                // 当地太阳时角 H
                const cosH = (Math.cos(zenith * D2R) - sinDec * Math.sin(lat * D2R)) / (cosDec * Math.cos(lat * D2R));

                if (cosH > 1) return "极夜 (无日出/日落)";
                if (cosH < -1) return "极昼 (无日出/日落)";

                const H = isSunrise ? 360 - R2D * Math.acos(cosH) : R2D * Math.acos(cosH);
                const H_hours = H / 15;

                // 平均太阳时与世界协调时 (UTC)
                const T = H_hours + RA - 0.06571 * t - 6.622;
                let UT = T - lngHour;
                UT = (UT + 24) % 24;

                // 转为本地系统时间
                const resultDate = new Date(date);
                resultDate.setUTCHours(Math.floor(UT), Math.floor((UT % 1) * 60), Math.round((((UT % 1) * 60) % 1) * 60));
                return resultDate;
            }

            return {
                sunrise: calculate(true),
                sunset: calculate(false)
            };
        }

        // 昼夜判断：日出~日落之间为浅色（白昼），其余时段（含凌晨日出前）为深色
        function isNightBySun(date) {
            const t = getSunTimesLocally(date, DEFAULT_LAT, DEFAULT_LNG);
            if (typeof t.sunrise === 'string') return false; // 极昼 → 浅色
            if (typeof t.sunset === 'string') return true;   // 极夜 → 深色
            const now = date.getTime();
            return now < t.sunrise.getTime() || now >= t.sunset.getTime();
        }

        function applyTheme(theme) {
            document.documentElement.dataset.theme = theme;
            const btn = document.getElementById('theme-toggle-btn');
            const label = document.getElementById('theme-toggle-label');
            if (btn) btn.setAttribute('aria-label', theme === 'dark' ? '切换到浅色主题' : '切换到深色主题');
            if (label) label.textContent = theme === 'dark' ? '浅色' : '深色';
        }

        function initTheme() {
            // 彻底清除历史残留深色缓存干涉，绝对强制默认以纯正浅色 (Light Mode) 初始化
            try { localStorage.removeItem(THEME_KEY); } catch (e) {}
            applyTheme('light');
        }

        function toggleTheme() {
            const cur = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
            applyTheme(cur);
            try { localStorage.setItem(THEME_KEY, cur); } catch (e) {}
            showToast(cur === 'dark' ? '已切换为深色主题' : '已切换为浅色主题');
        }
