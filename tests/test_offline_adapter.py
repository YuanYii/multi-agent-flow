"""
离线看板 Adapter 单元测试：接口正确性 + 多专家并发新建任务编号唯一性。
"""
import os
import sys
import json
import threading

SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPT_DIR)

from offline_board_adapter import OfflineBoardAdapter, init_board_file

FIELD_MAP = {
    "task_id": "task_id",
    "task_name": "task_name",
    "status": "status",
    "assignee": "assignee",
    "owner": "owner",
    "end_time": "end_time",
    "remarks": "remarks",
    "stage": "stage",
    "workpackage": "workpackage",
    "wbs_id": "wbs_id",
    "process_desc": "process_desc",
}


def _make_adapter(tmpdir, seed=None):
    board_file = os.path.join(tmpdir, "board.json")
    if seed:
        with open(board_file, "w", encoding="utf-8") as f:
            json.dump(seed, f, ensure_ascii=False, indent=2)
    return OfflineBoardAdapter(board_file=board_file, field_map=FIELD_MAP), board_file


def test_create_record_auto_increments_id(tmpdir):
    """未指定编号时自动分配 max(T\\d+)+1"""
    adapter, _ = _make_adapter(tmpdir, seed=[
        {"id": "T0100", "name": "a", "status": "已验收"},
        {"id": "T0123", "name": "b", "status": "已验收"},
    ])
    tid = adapter.create_record({"task_name": "新任务", "assignee": "李开发", "owner": "严经理"})
    assert tid == "T0124"
    rec = adapter.get_record("T0124")
    assert rec["fields"]["name"] == "新任务"
    assert rec["fields"]["status"] == "进行中"
    assert rec["fields"]["handler"] == "严经理"  # owner → handler 翻译


def test_create_record_empty_board_starts_t0001(tmpdir):
    """空看板从 T0001 开始"""
    adapter, _ = _make_adapter(tmpdir)
    tid = adapter.create_record({"task_name": "首个任务"})
    assert tid == "T0001"


def test_create_record_explicit_duplicate_rejected(tmpdir):
    """显式编号重复时 Fail-Closed 拒绝"""
    adapter, _ = _make_adapter(tmpdir, seed=[{"id": "T0005", "name": "x"}])
    assert adapter.create_record({"task_id": "T0005", "task_name": "重复"}) is None
    assert adapter.create_record({"task_id": "T0006", "task_name": "ok"}) == "T0006"


def test_update_and_append_remarks(tmpdir):
    """update_record 翻译字段；append_remarks 原子追加"""
    adapter, _ = _make_adapter(tmpdir, seed=[{"id": "T0001", "name": "x", "remarks": ""}])
    assert adapter.update_record("T0001", {"status": "进行中", "assignee": "Dev_User_1"}) is True
    rec = adapter.get_record("T0001")
    assert rec["fields"]["status"] == "进行中"
    assert rec["fields"]["assignee"] == "Dev_User_1"

    assert adapter.append_remarks("T0001", "remarks", "缺陷编号：DEF-T0001-1") is True
    assert adapter.append_remarks("T0001", "remarks", "根因：xxx") is True
    remarks = adapter.get_record("T0001")["fields"]["remarks"]
    assert "DEF-T0001-1" in remarks and "根因：xxx" in remarks


def test_update_missing_record_fails(tmpdir):
    adapter, _ = _make_adapter(tmpdir)
    assert adapter.update_record("T9999", {"status": "进行中"}) is False
    assert adapter.get_record("T9999") is None


def test_list_records_filter(tmpdir):
    adapter, _ = _make_adapter(tmpdir, seed=[
        {"id": "T0001", "status": "进行中", "assignee": "李开发"},
        {"id": "T0002", "status": "已验收", "assignee": "章测试"},
    ])
    items = adapter.list_records({"conjunction": "and", "conditions": [
        {"field_name": "status", "operator": "is", "value": ["进行中"]}
    ]})
    assert len(items) == 1 and items[0]["fields"]["id"] == "T0001"
    assert len(adapter.list_records()) == 2


def test_concurrent_create_records_unique_ids(tmpdir):
    """
    多专家并发新建任务（不指定编号）：编号必须全部唯一且连续。
    每个线程独立 adapter 实例 → 独立 fd 的 flock 排他互斥 → 读改写原子。
    """
    adapter, board_file = _make_adapter(tmpdir, seed=[{"id": "T0050", "name": "seed"}])
    n_threads = 10
    results = []
    lock = threading.Lock()

    def worker(i):
        a = OfflineBoardAdapter(board_file=board_file, field_map=FIELD_MAP)
        tid = a.create_record({"task_name": f"并发任务-{i}", "assignee": f"专家{i}"})
        with lock:
            results.append(tid)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert None not in results, f"存在创建失败: {results}"
    assert len(set(results)) == n_threads, f"编号重复! {sorted(results)}"
    nums = sorted(int(tid[1:]) for tid in results)
    assert nums == list(range(51, 51 + n_threads)), f"编号应连续递增: {nums}"


def test_init_board_file_no_overwrite(tmpdir):
    board_file = os.path.join(tmpdir, "board.json")
    init_board_file(board_file)
    init_board_file(board_file)
    with open(board_file, encoding="utf-8") as f:
        assert json.load(f) == []
