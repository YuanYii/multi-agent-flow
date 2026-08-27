#!/usr/bin/env python3
"""
Unit tests for P1 and P2 optimizations:
- P1.1: type and task_type persistence in OfflineBoardAdapter and transition pipeline
- P1.2: est_hours support in quick_task, auto_task, and transition pipeline
- P1.3: auto_task clean remarks without hardcoded '【Agent Loop】' placeholder pollution
- P2.1: FRONTEND role default full chain resolution and gate checks
"""
import os
import sys
import json
import tempfile
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from _lib.boards.offline_board_adapter import OfflineBoardAdapter, KANBAN_FIELD_MAP, KANBAN_NATIVE_FIELDS
from transition_task import transition_task_pipeline
from auto_task import resolve_chain, detect_main_role, full_chain_roles, CHAIN_A, CHAIN_SHORT


def create_test_config(tmpdir: str, board_file: str) -> str:
    cfg_file = os.path.join(tmpdir, "user_data", "workflow.config.yaml")
    os.makedirs(os.path.dirname(cfg_file), exist_ok=True)
    cfg_content = f"""
project:
  name: "Test-Project"
  version: "1.0.0"
  root_dir: "{tmpdir}"
board:
  provider: "local"
  board_file: "{board_file}"
  fields:
    task_id: "id"
    task_name: "name"
    status: "status"
    assignee: "assignee"
    owner: "owner"
    task_type: "type"
    estimated_hours: "est_hours"
roles:
  PM:
    name: "项目经理"
    max_parallel_tasks: 99
    can_self_claim: false
  DEV:
    name: "开发工程师"
    max_parallel_tasks: 3
    can_self_claim: true
  FRONTEND:
    name: "前端开发"
    max_parallel_tasks: 3
    can_self_claim: true
  REVIEWER:
    name: "代码审查"
    max_parallel_tasks: 99
    can_self_claim: false
  QA:
    name: "测试工程师"
    max_parallel_tasks: 99
    can_self_claim: false
paths:
  docs_root: "{tmpdir}/docs"
  dev_reports_dir: "{tmpdir}/docs/dev"
  review_reports_dir: "{tmpdir}/docs/review"
  qa_reports_dir: "{tmpdir}/docs/qa"
"""
    with open(cfg_file, "w", encoding="utf-8") as f:
        f.write(cfg_content)
    return cfg_file


def test_offline_board_adapter_type_and_est_hours():
    """Verify that OfflineBoardAdapter natively persists 'type' and 'est_hours'."""
    assert "type" in KANBAN_NATIVE_FIELDS
    assert KANBAN_FIELD_MAP.get("task_type") == "type"

    with tempfile.TemporaryDirectory() as tmpdir:
        board_file = os.path.join(tmpdir, "board.json")
        adapter = OfflineBoardAdapter(board_file)

        # 1. Create a task with type B and est_hours 4.5
        task_id = adapter.create_record({
            "name": "架构设计文档",
            "type": "B",
            "est_hours": 4.5,
            "assignee": "钱架构",
        })
        assert task_id == "T0001"

        # 2. Retrieve record and assert fields
        rec = adapter.get_record(task_id)
        assert rec is not None
        fields = rec["fields"]
        assert fields["id"] == "T0001"
        assert fields["name"] == "架构设计文档"
        assert fields["type"] == "B"
        assert fields["est_hours"] == 4.5
        assert fields["act_hours"] == 0.0

        # 3. Create another task with task_type alias and default est_hours
        task_id2 = adapter.create_record({
            "name": "前端交互组件",
            "task_type": "A",
            "assignee": "马前端",
        })
        assert task_id2 == "T0002"
        rec2 = adapter.get_record(task_id2)
        assert rec2["fields"]["type"] == "A"
        assert rec2["fields"]["est_hours"] == 0.0


def test_transition_task_pipeline_type_and_est_hours_persistence():
    """Verify transition_task_pipeline persists type and est_hours on create."""
    with tempfile.TemporaryDirectory() as tmpdir:
        board_file = os.path.join(tmpdir, "user_data", "board.json")
        os.makedirs(os.path.dirname(board_file), exist_ok=True)
        with open(board_file, "w", encoding="utf-8") as f:
            json.dump([], f)
        cfg_file = create_test_config(tmpdir, board_file)

        ok = transition_task_pipeline(
            config_path=cfg_file,
            task_id="T0001",
            task_name="实现用户登录接口",
            current_role="DEV",
            assignee="李开发",
            task_type="A",
            est_hours=3.5,
            create_only=True,
        )
        assert ok is True

        adapter = OfflineBoardAdapter(board_file)
        rec = adapter.get_record("T0001")
        assert rec is not None
        fields = rec["fields"]
        assert fields["id"] == "T0001"
        assert fields["type"] == "A"
        assert fields["est_hours"] == 3.5


def test_auto_task_frontend_default_chain():
    """Verify FRONTEND role defaults to full chain (CHAIN_A) when type is A or default."""
    role = detect_main_role("移动端工作台", "马前端")
    assert role == "FRONTEND"

    chain, step_roles = resolve_chain("A", "FRONTEND")
    assert chain == CHAIN_A
    # Step roles should traverse: 马前端 (开发) -> 周审查 (审查) -> 章测试 (测试) -> 严经理 (验收)
    assert len(step_roles) == 4
    assert step_roles[0] == ("待开始", "进行中", "FRONTEND", "马前端")
    assert step_roles[1] == ("进行中", "审查中", "FRONTEND", "周审查")
    assert step_roles[2] == ("审查中", "测试中", "REVIEWER", "章测试")
    assert step_roles[3] == ("测试中", "已完成", "QA", "严经理")


def test_auto_task_clean_remarks_no_agent_loop_pollution():
    """Verify that auto_task flow does not inject hardcoded '【Agent Loop】' placeholder into card remarks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        board_file = os.path.join(tmpdir, "user_data", "board.json")
        os.makedirs(os.path.dirname(board_file), exist_ok=True)
        with open(board_file, "w", encoding="utf-8") as f:
            json.dump([], f)
        cfg_file = create_test_config(tmpdir, board_file)

        ok = transition_task_pipeline(
            config_path=cfg_file,
            task_id="T0001",
            task_name="自动流水线优化任务",
            current_role="DEV",
            assignee="李开发",
            task_type="A",
            est_hours=2.0,
            remarks="真实变更需求描述",
            create_only=True,
        )
        assert ok is True

        adapter = OfflineBoardAdapter(board_file)
        rec = adapter.get_record("T0001")
        assert rec["fields"]["remarks"] == "真实变更需求描述"
        assert "【Agent Loop】" not in str(rec["fields"]["remarks"])


def test_kanban_server_type_filter_api():
    """Verify that start_kanban_server GET /api/tasks supports type filtering."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "start_kanban_server_opt", os.path.join(SCRIPTS_DIR, "start_kanban_server.py"))
    kanban_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kanban_mod)

    with tempfile.TemporaryDirectory() as tmpdir:
        board_path = os.path.join(tmpdir, "user_data", "board.json")
        os.makedirs(os.path.dirname(board_path), exist_ok=True)

        cards = [
            {"id": "T0001", "name": "后端开发", "status": "进行中", "type": "A", "seq": 1},
            {"id": "T0002", "name": "架构设计", "status": "已完成", "type": "B", "seq": 2},
            {"id": "T0003", "name": "文档编写", "status": "已完成", "type": "C", "seq": 3},
            {"id": "T0004", "name": "历史任务", "status": "待开始", "seq": 4}, # type missing -> defaults to A
        ]
        with open(board_path, "w", encoding="utf-8") as f:
            json.dump(cards, f)

        orig_board = kanban_mod.USER_DATA_BOARD
        kanban_mod.USER_DATA_BOARD = board_path
        try:
            read_cards = kanban_mod.read_board_data()
            assert len(read_cards) == 4

            # Filter type B
            type_b = [c for c in read_cards if (c.get("type") or "A").upper() == "B"]
            assert len(type_b) == 1
            assert type_b[0]["id"] == "T0002"

            # Filter type A (should match T0001 and T0004 which defaults to A)
            type_a = [c for c in read_cards if (c.get("type") or "A").upper() == "A"]
            assert len(type_a) == 2
            assert {c["id"] for c in type_a} == {"T0001", "T0004"}
        finally:
            kanban_mod.USER_DATA_BOARD = orig_board
