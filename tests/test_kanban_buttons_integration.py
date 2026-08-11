#!/usr/bin/env python3
"""
Multi-Agent Flow · 看板 UI 每一个可点击按钮的静态与 DOM 响应集成测试
测试范围：21 组前端交互按钮、函数名匹配、DOM 元素绑定及 JavaScript 语法健全性断言
"""

import os
import re
import pytest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
KANBAN_HTML = os.path.join(PROJECT_ROOT, "kanban", "offline_board.html")
KANBAN_JS_BOARD = os.path.join(PROJECT_ROOT, "kanban", "js", "board.js")
KANBAN_JS_UTIL = os.path.join(PROJECT_ROOT, "kanban", "js", "util.js")
KANBAN_JS_DATA = os.path.join(PROJECT_ROOT, "kanban", "js", "data.js")
KANBAN_JS_LISTBOX = os.path.join(PROJECT_ROOT, "kanban", "js", "listbox.js")


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_kanban_html_exists():
    assert os.path.exists(KANBAN_HTML)
    assert os.path.exists(KANBAN_JS_BOARD)
    assert os.path.exists(KANBAN_JS_UTIL)


def test_all_button_onclick_handlers_exist_in_js():
    """解析 offline_board.html 中所有 button 和 a 标签的 onclick，断言其调用的 JS 函数必须在 JS 代码中定义"""
    html_content = read_file(KANBAN_HTML)
    all_js_code = read_file(KANBAN_JS_BOARD) + read_file(KANBAN_JS_UTIL) + read_file(KANBAN_JS_DATA) + read_file(KANBAN_JS_LISTBOX)

    # 正则提取 onclick="xxx(...)"
    onclick_matches = re.findall(r'onclick="([^"]+)"', html_content)
    assert len(onclick_matches) > 0, "HTML 中未找到任何 onclick 事件"

    tested_functions = set()
    for handler in onclick_matches:
        # 提取函数名
        fn_match = re.match(r'([a-zA-Z0-9_$]+)\s*\(', handler.strip())
        if fn_match:
            fn_name = fn_match.group(1)
            tested_functions.add(fn_name)
            # 断言 JS 中存在 function fn_name 或 fn_name = 
            pattern = r'function\s+' + fn_name + r'\b|' + fn_name + r'\s*=\s*'
            assert re.search(pattern, all_js_code) is not None, f"❌ HTML 绑定的 onclick 函数 '{fn_name}' 未在 JS 文件中定义！"

    print(f"✅ HTML 中定义的 {len(tested_functions)} 个全局按钮点击函数全部存在: {sorted(tested_functions)}")


def test_all_popover_and_modal_elements_exist():
    """断言 onclick 中 toggleCustomPopover 和 openModal 操作的目标 ID 必须在 HTML 中真实存在"""
    html_content = read_file(KANBAN_HTML)

    popover_targets = re.findall(r"toggleCustomPopover\(event,\s*'([^']+)'\)", html_content)
    for target_id in popover_targets:
        assert f'id="{target_id}"' in html_content, f"❌ 按钮调用的 Popover 容器 ID '{target_id}' 在 HTML 中不存在！"

    modal_targets = re.findall(r"openModal\('([^']+)'\)", html_content)
    for modal_id in modal_targets:
        assert f'id="{modal_id}"' in html_content, f"❌ 按钮调用的 Modal 容器 ID '{modal_id}' 在 HTML 中不存在！"


def test_all_filter_and_sort_inputs_bound_correctly():
    """断言筛选、排序、搜索框引用的输入框 ID 全部正确且在 JS 代码全集中被调用"""
    html_content = read_file(KANBAN_HTML)
    all_js_code = read_file(KANBAN_JS_BOARD) + read_file(KANBAN_JS_UTIL) + read_file(KANBAN_JS_DATA) + read_file(KANBAN_JS_LISTBOX)

    required_ids = [
        "search-box",
        "filter-status",
        "filter-assignee",
        "sort-field",
        "sort-order",
        "batch-delete-btn"
    ]
    for element_id in required_ids:
        assert f'id="{element_id}"' in html_content, f"❌ 关键按钮/控件元素 ID '{element_id}' 在 HTML 中不存在！"
        assert element_id in all_js_code, f"❌ ID '{element_id}' 未在 JS 代码全集中被绑定"


def test_js_syntax_integrity():
    """检查 JS 文件基本语法是否合法"""
    for js_path in [KANBAN_JS_BOARD, KANBAN_JS_UTIL, KANBAN_JS_DATA, KANBAN_JS_LISTBOX]:
        content = read_file(js_path)
        # 简单语法断言：括号匹配
        assert content.count("{") == content.count("}"), f"❌ {os.path.basename(js_path)} 花括号数量不匹配"
        assert content.count("(") == content.count(")"), f"❌ {os.path.basename(js_path)} 圆括号数量不匹配"


def test_no_undefined_global_function_calls():
    """扫描所有 JS 文件，断言常调用的全局 helper 函数必须都在 JS 代码全集中定义"""
    all_js_code = read_file(KANBAN_JS_BOARD) + read_file(KANBAN_JS_UTIL) + read_file(KANBAN_JS_DATA) + read_file(KANBAN_JS_LISTBOX)
    
    helpers = ["esc", "badgeInner", "getBadgeStyle", "showToast", "applyFilters", "renderTable", "openTaskDetail", "closeDetailModal", "toggleTaskEditMode", "saveTaskDetails", "refreshUiSelects", "appendProcessLog", "confirmTransition", "cancelTransition", "openCustomConfirm", "closeConfirmModal"]
    for fn_name in helpers:
        pattern = r'function\s+' + fn_name + r'\b|const\s+' + fn_name + r'\b|let\s+' + fn_name + r'\b|var\s+' + fn_name + r'\b'
        assert re.search(pattern, all_js_code) is not None, f"❌ JS 核心辅助函数 '{fn_name}' 未在 JS 代码全集中定义！"
