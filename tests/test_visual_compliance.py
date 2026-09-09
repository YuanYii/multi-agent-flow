"""
test_visual_compliance.py · 界面与控制台扁平化视觉规范单元测试套件
验证 kanban/js/board.js、CLI 生产脚本以及核心规范文件中不存在 3D 拟真 Emoji，
确保严格遵循现代极简扁平化设计 (Strict Flat Vector Design)。
"""

import os
import pytest


def _contains_emoji(text: str) -> list:
    hits = []
    for idx, line in enumerate(text.splitlines(), start=1):
        for char in line:
            cp = ord(char)
            # 常见 Emoji 编码区间: Dingbats (2600-27BF), Pictographs/Emoticons (1F300-1FAFF)
            if (0x2600 <= cp <= 0x27BF) or (0x1F300 <= cp <= 0x1FAFF):
                hits.append((idx, char, line.strip()))
                break
    return hits


def test_kanban_board_js_no_emojis():
    """断言 Web 看板核心脚本 board.js 不包含任何 Emoji 拟真图标"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    board_js_path = os.path.join(base_dir, "kanban", "js", "board.js")
    assert os.path.exists(board_js_path), f"未找到文件: {board_js_path}"

    with open(board_js_path, "r", encoding="utf-8") as f:
        content = f.read()

    violations = _contains_emoji(content)
    assert not violations, f"board.js 中检测到违规 Emoji: {violations}"


def test_core_cli_scripts_no_emojis():
    """断言核心生产 CLI 脚本的终端输出中不包含 Emoji"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scripts_dir = os.path.join(base_dir, "scripts")

    target_scripts = [
        "quick_task.py",
        "dispatch_task.py",
        "transition_task.py",
        "show_help.py",
        "sync_pr_status.py",
        "start_kanban_server.py",
        "auto_task.py",
    ]

    all_violations = {}
    for s_name in target_scripts:
        s_path = os.path.join(scripts_dir, s_name)
        if not os.path.exists(s_path):
            continue
        with open(s_path, "r", encoding="utf-8") as f:
            content = f.read()
        violations = _contains_emoji(content)
        if violations:
            all_violations[s_name] = violations

    assert not all_violations, f"CLI 脚本中检测到违规 Emoji: {all_violations}"


def test_rules_and_readme_no_emojis():
    """断言规则契约与说明文档中不包含 Emoji 表情"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_docs = [
        os.path.join(base_dir, "rules", "AGENTS.md"),
        os.path.join(base_dir, "README.md"),
        os.path.join(base_dir, "SKILL.md"),
    ]

    for doc_path in target_docs:
        if os.path.exists(doc_path):
            with open(doc_path, "r", encoding="utf-8") as f:
                content = f.read()
            violations = _contains_emoji(content)
            assert not violations, f"{doc_path} 中检测到违规 Emoji: {violations}"
