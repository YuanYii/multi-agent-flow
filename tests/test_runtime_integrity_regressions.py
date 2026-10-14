"""状态事实来源、任务类型、只读模拟和验收授权的回归测试。"""
import json
import sys

import pytest

from _lib.boards.chunked_board_adapter import ChunkedBoardAdapter
from _lib.boards.offline_board_adapter import OfflineBoardAdapter
from _lib.boards.weekly_board_adapter import WeeklyBoardAdapter
from _lib.core.validate_transition import validate_delegation_authority
import transition_task


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("board:\n  fields: {}\nroles: {}\n", encoding="utf-8")
    board = tmp_path / "board.json"
    board.write_text(json.dumps([{"id": "T0001", "status": "进行中", "type": "A", "name": "实现状态检查", "assignee": "李开发"}], ensure_ascii=False), encoding="utf-8")
    adapter = OfflineBoardAdapter(str(board))
    monkeypatch.setattr(transition_task, "get_board_adapter", lambda _: adapter)
    monkeypatch.setattr(transition_task, "acquire_concurrency_lock", lambda _: (True, None))
    monkeypatch.setattr(transition_task, "release_concurrency_lock", lambda _: None)
    monkeypatch.setattr(transition_task, "record_audit_event", lambda *a, **k: None)
    return config, adapter


def test_transition_rejects_stale_source_status(pipeline):
    config, adapter = pipeline
    result = transition_task.transition_task_pipeline(str(config), task_id="T0001", current_role="QA", from_status="测试中", to_status="已完成", assignee="严经理", end_time="2026-10-03 12:00:00")
    assert result is False
    assert adapter.get_record("T0001")["fields"]["status"] == "进行中"


def test_transition_uses_stored_task_type(pipeline, monkeypatch):
    config, adapter = pipeline
    received = []
    def subagent_check(**kwargs):
        received.append(kwargs["task_type"])
        return True, ""
    monkeypatch.setattr(transition_task, "validate_subagent_context", subagent_check)
    result = transition_task.transition_task_pipeline(str(config), task_id="T0001", current_role="DEV", from_status="进行中", to_status="已完成", assignee="严经理", task_type="B", end_time="2026-10-03 12:00:00")
    assert received == ["A"]
    assert result is False
    assert adapter.get_record("T0001")["fields"]["status"] == "进行中"


def test_preview_state_is_read_only(pipeline):
    config, adapter = pipeline
    assert transition_task.transition_task_pipeline(str(config), task_id="T0001", current_role="DEV", from_status="进行中", to_status="审查中", assignee="周审查", dry_run=True)
    assert transition_task.transition_task_pipeline(str(config), task_id="T0001", current_role="REVIEWER", from_status="审查中", to_status="测试中", assignee="章测试", dry_run=True, preview_from_status="审查中")
    assert adapter.get_record("T0001")["fields"]["status"] == "进行中"
    assert not transition_task.transition_task_pipeline(str(config), task_id="T0001", current_role="REVIEWER", from_status="审查中", to_status="测试中", assignee="章测试", preview_from_status="审查中")


def test_existing_task_auto_simulation_preserves_storage(pipeline, tmp_path, monkeypatch, capsys):
    import auto_task
    config, adapter = pipeline
    monkeypatch.setenv("YY_FLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(auto_task, "get_board_adapter", lambda _: adapter)
    monkeypatch.setattr(sys, "argv", ["auto_task.py", "--config", str(config), "--task-id", "T0001", "--simulate"])
    before = adapter.get_record("T0001")
    with pytest.raises(SystemExit) as stopped:
        auto_task.main()
    assert stopped.value.code == 0
    assert "[PASS]" in capsys.readouterr().out
    assert adapter.get_record("T0001") == before


def test_reserved_marker_is_not_role_authorization(pipeline):
    config, adapter = pipeline
    assert not validate_delegation_authority("PM", "OPERATOR_VIA_TOKEN")
    adapter.update_record("T0001", {"status": "已完成"})
    result = transition_task.transition_task_pipeline(str(config), task_id="T0001", current_role="PM", from_status="已完成", to_status="已验收", assignee="严经理", delegated_by="OPERATOR_VIA_TOKEN", end_time="2026-10-03 12:00:00")
    assert result is False
    assert adapter.get_record("T0001")["fields"]["status"] == "已完成"


@pytest.mark.parametrize("adapter_type", [ChunkedBoardAdapter, WeeklyBoardAdapter])
@pytest.mark.parametrize("field", ["type", "task_type"])
def test_yaml_storage_preserves_task_type(tmp_path, adapter_type, field):
    kwargs = {"tasks_dir": str(tmp_path / "tasks"), "locks_dir": str(tmp_path / "locks")}
    if adapter_type is WeeklyBoardAdapter:
        kwargs["index_file"] = str(tmp_path / "index.json")
    adapter = adapter_type(**kwargs)
    task_id = adapter.create_record({"name": "短链任务", field: "B"})
    assert adapter.get_record(task_id)["fields"]["type"] == "B"
