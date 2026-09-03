import os
import sys
import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(SCRIPT_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from _lib.models.task_record import TaskRecord


def test_task_record_from_dict_and_to_dict():
    raw_data = {
        "id": "T0001",
        "name": "编写流式解析引擎",
        "status": "进行中",
        "stage": "阶段三: 编码实现",
        "type": "A",
        "assignee": "李开发",
        "owner": "李开发",
        "est_hours": "3.5",
        "acceptance_criteria": "单测覆盖率 90%",
        "process": ["[T0001-N01] 待开始 -> 进行中"]
    }

    record = TaskRecord.from_dict(raw_data)
    assert record.id == "T0001"
    assert record.name == "编写流式解析引擎"
    assert record.status == "进行中"
    assert record.est_hours == 3.5
    assert record.acceptance_criteria == ["单测覆盖率 90%"]
    assert record.is_active is True
    assert record.is_terminal is False
    assert record.is_blocked is False

    d = record.to_dict()
    assert d["id"] == "T0001"
    assert d["est_hours"] == 3.5
    assert len(d.keys()) == 23


def test_task_record_from_wrapped_fields():
    wrapped = {
        "record_id": "T0002",
        "fields": {
            "id": "T0002",
            "name": "架构仲裁评审",
            "status": "已阻塞",
            "assignee": "钱架构",
            "est_hours": 1.0
        }
    }
    record = TaskRecord.from_dict(wrapped)
    assert record.id == "T0002"
    assert record.status == "已阻塞"
    assert record.is_blocked is True


def test_task_record_validate():
    valid = TaskRecord(id="T0099", name="正常任务", status="进行中", est_hours=2.0)
    assert valid.validate() == []

    invalid = TaskRecord(id="INVALID-123", name="", status="火星状态", est_hours=-5.0)
    errs = invalid.validate()
    assert len(errs) >= 4
    assert any("任务编号" in e for e in errs)
    assert any("任务名称不能为空" in e for e in errs)
    assert any("合法状态枚举" in e for e in errs)
    assert any("预估工时不能为负数" in e for e in errs)
