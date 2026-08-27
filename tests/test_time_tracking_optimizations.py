import os
import json
import pytest
from datetime import datetime, timedelta
from _lib.boards.offline_board_adapter import OfflineBoardAdapter
from transition_task import transition_task_pipeline


@pytest.fixture
def temp_board_json(tmp_path):
    board_file = tmp_path / "board.json"
    board_file.write_text("[]", encoding="utf-8")
    return str(board_file)


def test_offline_board_adapter_explicit_start_and_end_time(temp_board_json):
    adapter = OfflineBoardAdapter(board_file=temp_board_json)
    task_id = adapter.create_record({
        "name": "工时测试任务1",
        "start_date": "2026-08-27 10:00:00",
        "end_date": "2026-08-27 11:30:00",
        "est_hours": 2.0,
    })
    assert task_id is not None
    rec = adapter.get_record(task_id)
    assert rec["fields"]["start_date"] == "2026-08-27 10:00:00"
    assert rec["fields"]["end_date"] == "2026-08-27 11:30:00"
    assert rec["fields"]["act_hours"] == 1.5


def test_offline_board_adapter_smart_backfill_when_same_second(temp_board_json):
    adapter = OfflineBoardAdapter(board_file=temp_board_json)
    # When start_date == end_date (e.g. from auto_task loop in same second), but est_hours = 1.5
    now_str = "2026-08-27 14:00:00"
    task_id = adapter.create_record({
        "name": "自动建单工时回溯任务",
        "start_date": now_str,
        "end_date": now_str,
        "est_hours": 1.5,
    })
    assert task_id is not None
    rec = adapter.get_record(task_id)
    # Expected: start_date backfilled to 1.5 hours earlier (12:30:00), act_hours = 1.5
    assert rec["fields"]["start_date"] == "2026-08-27 12:30:00"
    assert rec["fields"]["end_date"] == now_str
    assert rec["fields"]["act_hours"] == 1.5


def test_offline_board_adapter_update_record_smart_backfill(temp_board_json):
    adapter = OfflineBoardAdapter(board_file=temp_board_json)
    task_id = adapter.create_record({
        "name": "更新回溯测试任务",
        "est_hours": 2.0,
        "status": "待开始",
    })
    now_str = "2026-08-27 16:00:00"
    # Update with same start and end date
    ok = adapter.update_record(task_id, {
        "status": "已完成",
        "start_date": now_str,
        "end_date": now_str,
    })
    assert ok is True
    rec = adapter.get_record(task_id)
    assert rec["fields"]["start_date"] == "2026-08-27 14:00:00"
    assert rec["fields"]["end_date"] == now_str
    assert rec["fields"]["act_hours"] == 2.0
