/* ============================================================
 * util.js
 * Part of offline_board.html
 * Shared pure helpers & color systems (load first)
 * Load order: util.js -> data.js -> listbox.js -> board.js -> app.js
 * ============================================================ */

function showToast(msg) {
    const container = document.getElementById('toast-container');
    if (!container) return;
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
   Custom Color-Coded Dropdown Engine & Role Mapping
   ============================================================ */
const ROLE_MAP = {
    'flow-pm': '严经理', 'pm': '严经理', 'PM': '严经理', 'pm_user': '严经理',
    'flow-architect': '钱架构', 'architect': '钱架构', 'ARCHITECT': '钱架构', 'architect_user': '钱架构',
    'flow-dev': '李开发', 'dev': '李开发', 'DEV': '李开发', 'dev_user': '李开发', 'dev_user_1': '李开发', 'dev_user_2': '李开发',
    'flow-frontend': '马前端', 'frontend': '马前端', 'FRONTEND': '马前端', '前端开发': '马前端', 'frontend_user': '马前端',
    'flow-reviewer': '周审查', 'reviewer': '周审查', 'REVIEWER': '周审查', 'reviewer_user': '周审查', 'reviewer_user_1': '周审查',
    'flow-qa': '章测试', 'qa': '章测试', 'QA': '章测试', 'qa_user': '章测试',
    'flow-docs': '李文通', 'docs': '李文通', 'DOCS': '李文通', 'docs_user': '李文通',
    'flow-devops': '吕改特', 'devops': '吕改特', 'DEVOPS': '吕改特', 'devops_user': '吕改特'
};

function normalizeRoleName(val) {
    if (!val) return '未分配';
    const trimmed = String(val).trim();
    return ROLE_MAP[trimmed] || ROLE_MAP[trimmed.toLowerCase()] || ROLE_MAP[trimmed.toUpperCase()] || trimmed;
}

const STATUS_OPTIONS = ['待开始','进行中','审查中','测试中','已完成','已验收','已退回','已阻塞','已取消'];
const PERSON_OPTIONS = ['严经理','钱架构','李开发','马前端','周审查','章测试','李文通','吕改特'];

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
    '马前端': { bg:'#e0e7ff', text:'#4338ca' },
    '前端开发': { bg:'#e0e7ff', text:'#4338ca' },
    '周审查': { bg:'#e0f2fe', text:'#0284c7' },
    '章测试': { bg:'#fce8f8', text:'#c21897' },
    '李文通': { bg:'#fff7e6', text:'#b45309' },
    '吕改特': { bg:'#f0f0f0', text:'#595959' },
    '未分配': { bg:'#f2f3f5', text:'#8c8c8c' }
};

const STAGE_OPTIONS = ['Phase-1', 'Phase-2', 'Phase-3', 'WP1-需求', 'WP2-后端', 'WP2-前端', 'WP3-测试', 'WP4-运维', '-'];
const STAGE_COLORS = {
    'Phase-1': { bg:'#e6f4ff', text:'#0958d9' },
    'Phase-2': { bg:'#f6ffed', text:'#389e0d' },
    'Phase-3': { bg:'#fff7e6', text:'#d46b08' },
    'WP1-需求': { bg:'#f9f0ff', text:'#722ed1' },
    'WP2-后端': { bg:'#fff0f6', text:'#c41d7f' },
    'WP2-前端': { bg:'#e6fffb', text:'#08979c' },
    'WP3-测试': { bg:'#feffe6', text:'#7cb305' },
    'WP4-运维': { bg:'#e6f7ff', text:'#1890ff' },
    '-':        { bg:'#f2f3f5', text:'#8c8c8c' }
};

function getBadgeStyle(type, value) {
    if (type === 'person') {
        const norm = normalizeRoleName(value);
        return PERSON_COLORS[norm] || PERSON_COLORS[value] || { bg:'#e8f0fe', text:'#3370ff' };
    }
    const map = type === 'status' ? STATUS_COLORS : (type === 'stage' ? STAGE_COLORS : PERSON_COLORS);
    return map[value] || { bg:'#e8f0fe', text:'#3370ff' };
}

function badgeInner(type, value) {
    const displayVal = type === 'person' ? normalizeRoleName(value) : value;
    const st = getBadgeStyle(type, value);
    const caret = `<svg class="ts-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="${st.text}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>`;
    return `<span class="ts-dot" style="background:${st.text}"></span><span class="ts-label">${esc(displayVal)}</span>${caret}`;
}

// For trigger rendered inside JS template literals (table rows)
function tagSelectTriggerHTML(type, value, attrs) {
    const displayVal = type === 'person' ? normalizeRoleName(value) : value;
    const st = getBadgeStyle(type, value);
    return `<div class="tag-select" data-type="${type}" ${attrs || ''} data-value="${esc(displayVal)}" style="background:${st.bg};color:${st.text};border-color:rgba(0,0,0,0.06)">${badgeInner(type, value)}</div>`;
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
 */
function getSunTimesLocally(date, lat, lng) {
    const D2R = Math.PI / 180;
    const R2D = 180 / Math.PI;

    const startOfYear = new Date(date.getFullYear(), 0, 0);
    const dayOfYear = Math.floor((date - startOfYear) / 86400000);
    const zenith = 90.833;

    function calculate(isSunrise) {
        const lngHour = lng / 15;
        const t = dayOfYear + ((isSunrise ? 6 : 18) - lngHour) / 24;

        const M = 0.9856 * t - 3.289;
        let L = M + 1.916 * Math.sin(M * D2R) + 0.02 * Math.sin(2 * M * D2R) + 282.634;
        L = (L + 360) % 360;

        let RA = R2D * Math.atan(0.91764 * Math.tan(L * D2R));
        RA = (RA + 360) % 360;

        const Lquadrant = Math.floor(L / 90) * 90;
        const RAquadrant = Math.floor(RA / 90) * 90;
        RA = (RA + (Lquadrant - RAquadrant)) / 15;

        const sinDec = 0.39782 * Math.sin(L * D2R);
        const cosDec = Math.cos(Math.asin(sinDec));

        const cosH = (Math.cos(zenith * D2R) - (sinDec * Math.sin(lat * D2R))) / (cosDec * Math.cos(lat * D2R));
        if (cosH > 1 || cosH < -1) return null;

        let H = isSunrise ? (360 - R2D * Math.acos(cosH)) : (R2D * Math.acos(cosH));
        H = H / 15;

        const T = H + RA - (0.06571 * t) - 6.622;
        let UT = (T - lngHour + 24) % 24;

        const localT = UT + (-date.getTimezoneOffset() / 60);
        const hours = Math.floor((localT + 24) % 24);
        const minutes = Math.floor(((localT + 24) % 1) * 60);

        const result = new Date(date);
        result.setHours(hours, minutes, 0, 0);
        return result;
    }

    return {
        sunrise: calculate(true),
        sunset: calculate(false)
    };
}

function computeAutoTheme() {
    const now = new Date();
    const sunTimes = getSunTimesLocally(now, DEFAULT_LAT, DEFAULT_LNG);
    if (!sunTimes.sunrise || !sunTimes.sunset) return 'light';
    const isNight = now < sunTimes.sunrise || now >= sunTimes.sunset;
    return isNight ? 'dark' : 'light';
}

function getActiveTheme() {
    return localStorage.getItem(THEME_KEY) || computeAutoTheme();
}

function applyTheme(theme) {
    if (theme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.body.classList.add('dark-theme');
    } else {
        document.documentElement.removeAttribute('data-theme');
        document.body.classList.remove('dark-theme');
    }
    const label = document.getElementById('theme-toggle-label');
    if (label) {
        label.textContent = theme === 'dark' ? '浅色' : '深色';
    }
}

function toggleTheme() {
    const current = getActiveTheme();
    const next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
    showToast(`已切换至${next === 'dark' ? '深色' : '浅色'}主题`);
}

function initTheme() {
    applyTheme(getActiveTheme());
}
