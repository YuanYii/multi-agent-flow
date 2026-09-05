#!/usr/bin/env python3
"""
单元测试：固定 50 任务分卷看板适配器 ChunkedBoardAdapter (CCP V2.0 工业级基石)
覆盖并发发号、O(1) 算术物理分卷、50 容量边界跨卷顺延、契约持久化、原位就地更新、僵尸锁破锁自愈等关键场景。
"""
import os
import sys
import tempfile
import shutil
import threading
import time
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_SCRIPTS_DIR = os.path.join(_PROJ_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _lib.boards.chunked_board_adapter import ChunkedBoardAdapter


@pytest.fixture
def temp_chunked_env():
    td = tempfile.mkdtemp(prefix="test_chunked_board_")
    tasks_dir = os.path.join(td, "docs", "D04-研发过程", "D01-任务")
    os.makedirs(tasks_dir, exist_ok=True)
    locks_dir = os.path.join(td, "user_data", "locks")
    os.makedirs(locks_dir, exist_ok=True)

    adapter = ChunkedBoardAdapter(
        tasks_dir=tasks_dir,
        locks_dir=locks_dir,
        chunk_size=50
    )
    yield adapter, td
    shutil.rmtree(td, ignore_errors=True)


def test_arithmetic_o1_chunk_addressing(temp_chunked_env):
    """场景1：O(1) 算术物理寻址验证"""
    adapter, _ = temp_chunked_env

    # 1~50 归属 tasks_0001_0050.yaml
    assert adapter.get_chunk_range(1) == (1, 50)
    assert adapter.get_chunk_filename(1) == "tasks_0001_0050.yaml"
    assert adapter.get_chunk_range(50) == (1, 50)
    assert adapter.get_chunk_filename(50) == "tasks_0001_0050.yaml"

    # 51~100 归属 tasks_0051_0100.yaml
    assert adapter.get_chunk_range(51) == (51, 100)
    assert adapter.get_chunk_filename(51) == "tasks_0051_0100.yaml"
    assert adapter.get_chunk_range(100) == (51, 100)
    assert adapter.get_chunk_filename(100) == "tasks_0051_0100.yaml"

    # 101 归属 tasks_0101_0150.yaml
    assert adapter.get_chunk_range(101) == (101, 150)
    assert adapter.get_chunk_filename(101) == "tasks_0101_0150.yaml"


def test_concurrent_id_allocation(temp_chunked_env):
    """场景2：多线程并发建卡，发号锁保障 ID 严格递增且零重复"""
    adapter, _ = temp_chunked_env
    allocated_ids = []
    list_lock = threading.Lock()

    def _worker():
        tid = adapter._next_task_id()
        # 实际创建卡片以推进 max_num
        created = adapter.create_record({
            "id": tid,
            "name": f"并发任务 {tid}",
            "assignee": "李开发",
            "status": "待开始"
        })
        with list_lock:
            allocated_ids.append(created)

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(allocated_ids) == 8
    assert len(set(allocated_ids)) == 8
    assert sorted(allocated_ids) == [f"T{i:04d}" for i in range(1, 9)]


def test_contract_and_return_contract_persistence(temp_chunked_env):
    """场景3：CCP 防御性契约与结案回执四件套在 YAML 中结构化持久化"""
    adapter, _ = temp_chunked_env

    contract_payload = {
        "preconditions": ["users 表已存在 is_active 字段"],
        "interface_contract": {"path": "/api/v1/user/delete", "method": "POST"},
        "scope": {"in_scope": ["app/api/user.py"], "out_of_scope": ["app/core/auth.py"]},
        "semantic_boundaries": ["diff 最小化"],
        "new_files_policy": ["允许新建 test_user_delete.py"],
        "ambiguity_policy": ["发生二义性立即上报"]
    }
    return_contract_payload = {
        "required_items": ["变更清单", "单测凭据", "偏离说明", "遗留问题"],
        "report_path": "docs/D04-研发过程/D02-报告/dev/DEV_T0001_Report.md"
    }

    tid = adapter.create_record({
        "name": "用户软注销接口开发",
        "target": "实现注销软删除与会话清理",
        "acceptance_criteria": ["1. 软删除成功", "2. Redis 会话清理"],
        "tier": "Tier-1",
        "assignee": "李开发",
        "contract": contract_payload,
        "return_contract": return_contract_payload,
    })

    assert tid == "T0001"
    rec = adapter.get_record("T0001")
    assert rec is not None
    fields = rec["fields"]
    assert fields["tier"] == "Tier-1"
    assert fields["target"] == "实现注销软删除与会话清理"
    assert len(fields["acceptance_criteria"]) == 2
    assert fields["contract"]["interface_contract"]["method"] == "POST"
    assert fields["return_contract"]["report_path"] == "docs/D04-研发过程/D02-报告/dev/DEV_T0001_Report.md"
    assert fields["_source_file"].endswith("tasks_0001_0050.yaml")


def test_chunk_capacity_rollover(temp_chunked_env):
    """场景4：容量边界顺延（50 任务顺延至下一个分卷）"""
    adapter, _ = temp_chunked_env

    # 创建 T0050
    tid_50 = adapter.create_record({
        "id": "T0050",
        "name": "第50项任务卡",
        "assignee": "李开发"
    })
    assert tid_50 == "T0050"
    rec_50 = adapter.get_record("T0050")
    assert rec_50["fields"]["_source_file"].endswith("tasks_0001_0050.yaml")

    # 创建 T0051（自动归入新分卷 tasks_0051_0100.yaml）
    tid_51 = adapter.create_record({
        "id": "T0051",
        "name": "第51项任务卡",
        "assignee": "李开发"
    })
    assert tid_51 == "T0051"
    rec_51 = adapter.get_record("T0051")
    assert rec_51["fields"]["_source_file"].endswith("tasks_0051_0100.yaml")


def test_in_place_update_and_terminal_protection(temp_chunked_env):
    """场景5：原位就地更新与终态防篡改校验"""
    adapter, _ = temp_chunked_env

    tid = adapter.create_record({
        "id": "T0010",
        "name": "核心功能验证",
        "assignee": "李开发",
        "status": "进行中"
    })
    assert tid == "T0010"

    # 原位更新状态
    ok = adapter.update_record("T0010", {"status": "已完成"})
    assert ok is True
    rec = adapter.get_record("T0010")
    assert rec["fields"]["status"] == "已完成"
    assert rec["fields"]["_source_file"].endswith("tasks_0001_0050.yaml")

    # 推进至终态
    ok_accepted = adapter.update_record("T0010", {"status": "已验收"})
    assert ok_accepted is True

    # 试图非法修改已验收卡片 -> 拒绝
    tamper_ok = adapter.update_record("T0010", {"status": "进行中"})
    assert tamper_ok is False

    # 显式 force_reopen 允许纠偏
    reopen_ok = adapter.update_record("T0010", {"status": "进行中"}, force_reopen=True)
    assert reopen_ok is True
    rec_after = adapter.get_record("T0010")
    assert rec_after["fields"]["status"] == "进行中"


def test_list_records_and_filters(temp_chunked_env):
    """场景6：跨分卷列表联合查询与多条件过滤"""
    adapter, _ = temp_chunked_env

    adapter.create_record({"id": "T0001", "name": "任务一", "status": "待开始", "assignee": "李开发"})
    adapter.create_record({"id": "T0052", "name": "任务五十二", "status": "进行中", "assignee": "马前端"})

    all_recs = adapter.list_records(limit=100)
    assert len(all_recs) == 2

    # 过滤 status = 进行中
    filter_query = {
        "conditions": [
            {"field_name": "status", "operator": "is", "value": ["进行中"]}
        ]
    }
    filtered = adapter.list_records(filter_json=filter_query)
    assert len(filtered) == 1
    assert filtered[0]["fields"]["id"] == "T0052"


def test_zombie_lock_auto_recovery(temp_chunked_env):
    """场景7：僵尸锁破锁自愈"""
    adapter, td = temp_chunked_env

    # 写入假死 PID 的僵尸锁文件
    with open(adapter.seq_lock_file, "w", encoding="utf-8") as f:
        f.write("pid=9999999 timestamp=1000000\n")

    # 修改 mtime 制造超时
    old_time = time.time() - 100
    os.utime(adapter.seq_lock_file, (old_time, old_time))

    # 执行发号，触发自愈破锁
    next_id = adapter._next_task_id()
    assert next_id == "T0001"
