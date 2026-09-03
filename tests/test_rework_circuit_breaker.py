import os
import sys
import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(SCRIPT_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from _lib.boards.weekly_board_adapter import WeeklyBoardAdapter
from transition_task import transition_task_pipeline


def test_rework_circuit_breaker_escalates_on_third_rejection(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "user_data" / "tasks"
    tasks_dir.mkdir(parents=True)
    adapter = WeeklyBoardAdapter(tasks_dir=str(tasks_dir))

    # 预设一条已被打回 2 次的任务卡 T8801
    adapter.create_record({
        "id": "T8801",
        "name": "顽疾缺陷修复",
        "status": "审查中",
        "assignee": "周审查",
        "owner": "李开发",
        "type": "A",
        "est_hours": 2.0,
        "process": [
            "[T8801-N01] 待开始 -> 进行中",
            "[T8801-N02] 进行中 -> 审查中",
            "[T8801-N03] 审查中 -> 已退回 (第 1 次打回)",
            "[T8801-N04] 已退回 -> 进行中",
            "[T8801-N05] 进行中 -> 审查中",
            "[T8801-N06] 审查中 -> 已退回 (第 2 次打回)",
            "[T8801-N07] 已退回 -> 进行中",
            "[T8801-N08] 进行中 -> 审查中",
        ],
        "week": "2026-W36"
    })

    # mock get_board_adapter 返回当前 adapter
    import transition_task
    monkeypatch.setattr(transition_task, "get_board_adapter", lambda cfg=None: adapter)

    # 周审查触发第 3 次打回 (to_status="已退回")
    ok = transition_task_pipeline(
        config_path=None,
        task_id="T8801",
        current_role="REVIEWER",
        from_status="审查中",
        to_status="已退回",
        assignee="李开发",
        remarks="第3次审查仍有致命并发死锁",
        force=False
    )
    assert ok is True

    # 验证任务卡状态已被熔断升级为【已阻塞】，处理人移交钱架构
    raw_rec = adapter.get_record("T8801")
    task = raw_rec.get("fields", raw_rec)
    assert task["status"] == "已阻塞"
    assert "钱架构" in task.get("handler", "") or "钱架构" in task.get("assignee", "")
    assert "打回熔断仲裁" in task.get("remarks", "")


def test_rework_circuit_breaker_allows_force_override(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "user_data" / "tasks"
    tasks_dir.mkdir(parents=True)
    adapter = WeeklyBoardAdapter(tasks_dir=str(tasks_dir))

    # 预设已被打回 2 次的任务卡 T8802
    adapter.create_record({
        "id": "T8802",
        "name": "强制退回任务",
        "status": "审查中",
        "assignee": "周审查",
        "owner": "李开发",
        "type": "A",
        "est_hours": 2.0,
        "process": [
            "[T8802-N01] 待开始 -> 进行中",
            "[T8802-N02] 审查中 -> 已退回 (第 1 次)",
            "[T8802-N03] 审查中 -> 已退回 (第 2 次)",
        ],
        "week": "2026-W36"
    })

    import transition_task
    monkeypatch.setattr(transition_task, "get_board_adapter", lambda cfg=None: adapter)

    # 携带 force=True 触发第 3 次打回
    ok = transition_task_pipeline(
        config_path=None,
        task_id="T8802",
        current_role="REVIEWER",
        from_status="审查中",
        to_status="已退回",
        assignee="李开发",
        remarks="强制打回重构",
        force=True
    )
    assert ok is True

    raw_rec = adapter.get_record("T8802")
    task = raw_rec.get("fields", raw_rec)
    # 强制模式下允许继续退回
    assert task["status"] == "已退回"
    assert "李开发" in task.get("handler", "")
