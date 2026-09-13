import os
import sys
import pytest

# 确保加载 scripts 目录
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(TESTS_DIR), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from transition_task import validate_subagent_context


def test_subagent_gate_exempts_pytest_env():
    """断言：在 pytest 环境下，自动放行所有流转，确保既有 CI/单测零摩擦"""
    ok, msg = validate_subagent_context(
        task_id="T0001",
        current_role="DEV",
        from_status="进行中",
        to_status="审查中",
        token=None,
        task_type="A",
        existing_card={"fields": {"id": "T0001"}}
    )
    assert ok is True
    assert "测试环境" in msg or "单测" in msg


def test_subagent_gate_blocks_missing_token_outside_test(monkeypatch):
    """断言：在非测试环境下，A 类任务专业角色未携带 token 会被物理阻断"""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("YYFLOW_TEST_ENV", raising=False)
    monkeypatch.delenv("YYFLOW_TEST_MODE", raising=False)
    fake_modules = dict(sys.modules)
    fake_modules.pop("pytest", None)
    monkeypatch.setattr(sys, "modules", fake_modules)

    card = {
        "fields": {
            "id": "T0001",
            "type": "A",
            "handover_context": {"dispatch_token": "valid_token_123"}
        }
    }

    ok, msg = validate_subagent_context(
        task_id="T0001",
        current_role="DEV",
        from_status="进行中",
        to_status="审查中",
        token=None,
        task_type="A",
        existing_card=card
    )
    assert ok is False
    assert "dispatch_token" in msg or "物理隔离" in msg


def test_subagent_gate_blocks_wrong_token_outside_test(monkeypatch):
    """断言：在非测试环境下，携带错误的 token 会被阻断"""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("YYFLOW_TEST_ENV", raising=False)
    monkeypatch.delenv("YYFLOW_TEST_MODE", raising=False)
    fake_modules = dict(sys.modules)
    fake_modules.pop("pytest", None)
    monkeypatch.setattr(sys, "modules", fake_modules)

    card = {
        "fields": {
            "id": "T0001",
            "type": "A",
            "handover_context": {"dispatch_token": "valid_token_123"}
        }
    }

    ok, msg = validate_subagent_context(
        task_id="T0001",
        current_role="DEV",
        from_status="进行中",
        to_status="审查中",
        token="wrong_token_456",
        task_type="A",
        existing_card=card
    )
    assert ok is False
    assert "无效" in msg or "缺失" in msg


def test_subagent_gate_allows_valid_token_outside_test(monkeypatch):
    """断言：在非测试环境下，携带正确的 token 顺利通过门禁"""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("YYFLOW_TEST_ENV", raising=False)
    monkeypatch.delenv("YYFLOW_TEST_MODE", raising=False)
    fake_modules = dict(sys.modules)
    fake_modules.pop("pytest", None)
    monkeypatch.setattr(sys, "modules", fake_modules)

    card = {
        "fields": {
            "id": "T0001",
            "type": "A",
            "handover_context": {"dispatch_token": "valid_token_123"}
        }
    }

    ok, msg = validate_subagent_context(
        task_id="T0001",
        current_role="DEV",
        from_status="进行中",
        to_status="审查中",
        token="valid_token_123",
        task_type="A",
        existing_card=card
    )
    assert ok is True
    assert "核验通过" in msg


def test_subagent_gate_exempts_pm_and_user_outside_test(monkeypatch):
    """断言：PM 角色和用户角色（验收、建单、取消）无需 Subagent token"""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("YYFLOW_TEST_ENV", raising=False)
    monkeypatch.delenv("YYFLOW_TEST_MODE", raising=False)
    fake_modules = dict(sys.modules)
    fake_modules.pop("pytest", None)
    monkeypatch.setattr(sys, "modules", fake_modules)

    card = {"fields": {"id": "T0001", "type": "A"}}

    ok, msg = validate_subagent_context(
        task_id="T0001",
        current_role="PM",
        from_status="待开始",
        to_status="进行中",
        token=None,
        task_type="A",
        existing_card=card
    )
    assert ok is True

    ok2, msg2 = validate_subagent_context(
        task_id="T0001",
        current_role="USER",
        from_status="已完成",
        to_status="已验收",
        token=None,
        task_type="A",
        existing_card=card
    )
    assert ok2 is True


def test_subagent_gate_exempts_l1_tasks_outside_test(monkeypatch):
    """断言：L1 轻量短链任务（B/C/E/F/G 类）免 Subagent token"""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("YYFLOW_TEST_ENV", raising=False)
    monkeypatch.delenv("YYFLOW_TEST_MODE", raising=False)
    fake_modules = dict(sys.modules)
    fake_modules.pop("pytest", None)
    monkeypatch.setattr(sys, "modules", fake_modules)

    for l1_type in ["B", "C", "E", "F", "G"]:
        card = {"fields": {"id": "T0002", "type": l1_type}}
        ok, msg = validate_subagent_context(
            task_id="T0002",
            current_role="DOCS" if l1_type == "C" else "ARCHITECT",
            from_status="进行中",
            to_status="已完成",
            token=None,
            task_type=l1_type,
            existing_card=card
        )
        assert ok is True
        assert "轻量短链" in msg


def test_subagent_gate_emergency_bypass(monkeypatch):
    """断言：开启紧急旁路开关 YYFLOW_DISABLE_SUBAGENT_GATE=1 时放行"""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("YYFLOW_DISABLE_SUBAGENT_GATE", "1")
    fake_modules = dict(sys.modules)
    fake_modules.pop("pytest", None)
    monkeypatch.setattr(sys, "modules", fake_modules)

    card = {"fields": {"id": "T0001", "type": "A"}}
    ok, msg = validate_subagent_context(
        task_id="T0001",
        current_role="DEV",
        from_status="进行中",
        to_status="审查中",
        token=None,
        task_type="A",
        existing_card=card
    )
    assert ok is True
    assert "紧急全局旁路" in msg
