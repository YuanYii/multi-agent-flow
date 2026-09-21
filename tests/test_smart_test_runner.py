"""
Unit tests for Smart Incremental Test Runner (tests/test_smart_test_runner.py)
"""
import os
import sys
import pytest

from run_tests import (
    is_doc_or_ignorable,
    resolve_target_tests,
    PROJECT_ROOT
)


def test_doc_and_asset_skipping():
    """验证纯文档与静态资产是否被正确识别与过滤。"""
    assert is_doc_or_ignorable("README.md") is True
    assert is_doc_or_ignorable("docs/0-系统架构/guide.html") is True
    assert is_doc_or_ignorable("kanban/css/board.css") is True
    assert is_doc_or_ignorable(".yy-flow/user_data/board.json") is True
    assert is_doc_or_ignorable("scripts/transition_task.py") is False
    assert is_doc_or_ignorable("tests/test_workflow_v2.py") is False


def test_pure_docs_skips_testing():
    """验证仅有文档变更时，返回空用例列表并给出分级豁免理由。"""
    docs_changed = ["README.md", "docs/analysis.md", "kanban/screenshots/demo.png"]
    target_tests, reason = resolve_target_tests(docs_changed, PROJECT_ROOT)
    assert target_tests == []
    assert "跳过代码测试" in reason


def test_transition_task_mapping():
    """验证任务流转脚本变更精确映射到工作流与节点测试。"""
    changed = ["scripts/transition_task.py"]
    target_tests, reason = resolve_target_tests(changed, PROJECT_ROOT)
    assert "tests/test_workflow_v2.py" in target_tests
    assert "tests/test_process_node.py" in target_tests
    assert len(target_tests) >= 2


def test_kanban_mapping():
    """验证看板前端脚本变更精确映射到看板接口与服务测试。"""
    changed = ["kanban/js/board.js"]
    target_tests, reason = resolve_target_tests(changed, PROJECT_ROOT)
    assert "tests/test_kanban_api_v2.py" in target_tests
    assert "tests/test_kanban_server.py" in target_tests


def test_test_file_reflexive_matching():
    """验证修改测试文件自身时，直接执行该测试文件。"""
    changed = ["tests/test_task_linter.py"]
    target_tests, reason = resolve_target_tests(changed, PROJECT_ROOT)
    assert target_tests == ["tests/test_task_linter.py"]


def test_core_infrastructure_triggers_full():
    """验证核心基础设施变更时触发全量测试兜底。"""
    changed = ["tests/conftest.py"]
    target_tests, reason = resolve_target_tests(changed, PROJECT_ROOT)
    assert target_tests == ["tests/"]
    assert "全量回归测试" in reason


def test_cli_integration():
    """验证 cli.py 的 HANDLERS 字典中已正确注册 test 子命令。"""
    from cli import HANDLERS
    assert "test" in HANDLERS
    assert callable(HANDLERS["test"])
