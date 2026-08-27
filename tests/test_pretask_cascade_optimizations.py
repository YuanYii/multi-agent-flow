#!/usr/bin/env python3
"""
Unit tests for pretask cascading & dependency gate optimizations:
- Pretask persistence in OfflineBoardAdapter & normalization
- Self-dependency prevention
- Pretask gate enforcement on transition (待开始 -> 进行中)
- Pretask bypass via ignore_pretask / force
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
from _lib.core.validate_transition import validate
from transition_task import transition_task_pipeline


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
    pretask: "pretask"
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


def test_offline_board_adapter_pretask_persistence():
    """Verify pretask normalization, alias support, and self-dependency rejection."""
    assert "pretask" in KANBAN_NATIVE_FIELDS
    assert KANBAN_FIELD_MAP.get("depends_on") == "pretask"

    with tempfile.TemporaryDirectory() as tmpdir:
        board_file = os.path.join(tmpdir, "board.json")
        adapter = OfflineBoardAdapter(board_file)

        # 1. Create task T0001
        t1 = adapter.create_record({"name": "基础库开发", "assignee": "李开发"})
        assert t1 == "T0001"

        # 2. Create task T0002 with depends_on alias
        t2 = adapter.create_record({
            "name": "业务模块接入",
            "assignee": "马前端",
            "depends_on": "T0001",
        })
        assert t2 == "T0002"
        rec2 = adapter.get_record(t2)
        assert rec2["fields"]["pretask"] == "T0001"

        # 3. Create task T0003 with multiple pretask IDs
        t3 = adapter.create_record({
            "name": "集成调试",
            "assignee": "章测试",
            "pretask": "T0001, T0002",
        })
        assert t3 == "T0003"
        rec3 = adapter.get_record(t3)
        assert rec3["fields"]["pretask"] == "T0001,T0002"

        # 4. Self-dependency rejection on create
        t_self = adapter.create_record({
            "id": "T0099",
            "name": "自依赖非法任务",
            "pretask": "T0099",
        })
        assert t_self is None


def test_pretask_gate_blocking_in_progress():
    """Verify validate() blocks 待开始 -> 进行中 when pretask is not 已完成/已验收."""
    with tempfile.TemporaryDirectory() as tmpdir:
        board_file = os.path.join(tmpdir, "board.json")
        adapter = OfflineBoardAdapter(board_file)

        # T0001 is in 待开始
        adapter.create_record({"name": "前置模块", "assignee": "李开发", "status": "待开始"})
        # T0002 depends on T0001
        adapter.create_record({"name": "后置模块", "assignee": "马前端", "pretask": "T0001", "status": "待开始"})

        # Attempt to start T0002 -> Should be REJECTED because T0001 is 待开始
        ok_blocked = validate(
            role="FRONTEND",
            from_status="待开始",
            to_status="进行中",
            assignee="马前端",
            end_time="",
            active_dev_count=0,
            task_type="A",
            pretask="T0001",
            adapter=adapter,
        )
        assert ok_blocked is False

        # Move T0001 to 进行中
        adapter.update_record("T0001", {"status": "进行中"})
        # Attempt to start T0002 -> Should still be REJECTED because T0001 is 进行中
        ok_blocked2 = validate(
            role="FRONTEND",
            from_status="待开始",
            to_status="进行中",
            assignee="马前端",
            end_time="",
            active_dev_count=0,
            task_type="A",
            pretask="T0001",
            adapter=adapter,
        )
        assert ok_blocked2 is False

        # Move T0001 to 已完成
        adapter.update_record("T0001", {"status": "已完成", "end_date": "2026-08-27 12:00:00"})
        # Attempt to start T0002 -> Should PASS because T0001 is 已完成!
        ok_passed = validate(
            role="FRONTEND",
            from_status="待开始",
            to_status="进行中",
            assignee="马前端",
            end_time="",
            active_dev_count=0,
            task_type="A",
            pretask="T0001",
            adapter=adapter,
        )
        assert ok_passed is True


def test_pretask_gate_ignore_pretask_bypass():
    """Verify ignore_pretask=True bypasses the pretask gate check."""
    with tempfile.TemporaryDirectory() as tmpdir:
        board_file = os.path.join(tmpdir, "board.json")
        adapter = OfflineBoardAdapter(board_file)

        # T0001 is in 待开始
        adapter.create_record({"name": "前置模块", "assignee": "李开发", "status": "待开始"})

        # Bypass pretask check with ignore_pretask=True
        ok_bypassed = validate(
            role="FRONTEND",
            from_status="待开始",
            to_status="进行中",
            assignee="马前端",
            end_time="",
            active_dev_count=0,
            task_type="A",
            pretask="T0001",
            adapter=adapter,
            ignore_pretask=True,
        )
        assert ok_bypassed is True


def test_transition_pipeline_pretask_end_to_end():
    """Verify transition_task_pipeline persists pretask and enforces gate in pipeline."""
    with tempfile.TemporaryDirectory() as tmpdir:
        board_file = os.path.join(tmpdir, "user_data", "board.json")
        os.makedirs(os.path.dirname(board_file), exist_ok=True)
        with open(board_file, "w", encoding="utf-8") as f:
            json.dump([], f)
        cfg_file = create_test_config(tmpdir, board_file)

        # 1. Create T0001
        ok1 = transition_task_pipeline(
            config_path=cfg_file,
            task_id="T0001",
            task_name="后端服务接口",
            current_role="DEV",
            assignee="李开发",
            create_only=True,
        )
        assert ok1 is True

        # 2. Create T0002 with pretask=T0001
        ok2 = transition_task_pipeline(
            config_path=cfg_file,
            task_id="T0002",
            task_name="前端界面对接",
            current_role="FRONTEND",
            assignee="马前端",
            pretask="T0001",
            create_only=True,
        )
        assert ok2 is True

        adapter = OfflineBoardAdapter(board_file)
        rec2 = adapter.get_record("T0002")
        assert rec2["fields"]["pretask"] == "T0001"

        # 3. Attempt to transition T0002 from 待开始 -> 进行中 -> Blocked!
        ok_trans_blocked = transition_task_pipeline(
            config_path=cfg_file,
            task_id="T0002",
            current_role="FRONTEND",
            from_status="待开始",
            to_status="进行中",
            assignee="马前端",
        )
        assert ok_trans_blocked is False

        # 4. Advance T0001 to 已完成
        adapter.update_record("T0001", {"status": "已完成", "end_date": "2026-08-27 14:00:00"})

        # 5. Transition T0002 from 待开始 -> 进行中 -> Succeeded!
        ok_trans_passed = transition_task_pipeline(
            config_path=cfg_file,
            task_id="T0002",
            current_role="FRONTEND",
            from_status="待开始",
            to_status="进行中",
            assignee="马前端",
        )
        assert ok_trans_passed is True
