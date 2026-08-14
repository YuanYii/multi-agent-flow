"""
修复 ③ 回归测试:HEARTBEAT 巡检脚本 + 审计日志查询 / 轮转。

覆盖:
- heartbeat.run_heartbeat() 4 项门控:
  1. 滞留任务 (in_progress / review / test)
  2. 并发上限 (DEV/FRONTEND)
  3. 状态-处理人一致性 (审查中→REVIEWER, 测试中→QA, 终态→PM)
  4. 终态 end_time 必填
- 阈值可配置
- audit_logger.query_events() 按 task_id / role / success / time 过滤
- audit_logger.rotate_if_needed() 日切分 + 大小切分 + gzip 归档
"""
import os
import json
import gzip
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

sys.path.insert(0, SCRIPTS_DIR)
from heartbeat import run_heartbeat  # noqa: E402
from offline_board_adapter import OfflineBoardAdapter  # noqa: E402


# ---------- heartbeat 4 项门控 ----------

class _FakeAdapter:
    """最小化可注入 records 的伪适配器,供 heartbeat.run_heartbeat 测试用"""

    def __init__(self, records):
        self._records = records

    def list_records(self, limit=100, offset=0, filter_json=None):
        return [{"record_id": r.get("id"), "fields": r} for r in self._records[offset:offset + limit]]


def _now():
    return datetime(2026, 8, 14, 12, 0, 0)


def test_heartbeat_clean_state_no_alerts():
    """全部合规的看板: 0 告警"""
    records = [
        {"id": "T0001", "status": "进行中", "assignee": "李开发",
         "start_date": "2026-08-14 08:00:00"},  # 4h,未超 24h
    ]
    result = run_heartbeat(_FakeAdapter(records), now=_now())
    assert result["summary"]["critical"] == 0
    assert result["summary"]["warning"] == 0
    assert result["alerts"] == []


def test_heartbeat_stale_in_progress_warning():
    """巡检 1a: 进行中超过阈值 → warning"""
    stale_start = (_now() - timedelta(hours=30)).strftime("%Y-%m-%d %H:%M:%S")
    records = [
        {"id": "T0001", "status": "进行中", "assignee": "李开发",
         "start_date": stale_start},
    ]
    result = run_heartbeat(_FakeAdapter(records), now=_now())
    codes = [a["code"] for a in result["alerts"]]
    assert "STALE_IN_PROGRESS" in codes


def test_heartbeat_stale_review_test_warning():
    """巡检 1b: 审查中/测试中超阈值 → warning"""
    stale_start = (_now() - timedelta(hours=15)).strftime("%Y-%m-%d %H:%M:%S")
    records = [
        {"id": "T0001", "status": "审查中", "assignee": "周审查",
         "start_date": stale_start},
        {"id": "T0002", "status": "测试中", "assignee": "章测试",
         "start_date": stale_start},
    ]
    result = run_heartbeat(_FakeAdapter(records), now=_now())
    codes = [a["code"] for a in result["alerts"]]
    assert "STALE_REVIEW_OR_TEST" in codes
    assert codes.count("STALE_REVIEW_OR_TEST") == 2


def test_heartbeat_dev_concurrency_exceeded():
    """巡检 2: DEV 并发超 3 → critical"""
    records = [
        {"id": f"T000{i}", "status": "进行中", "assignee": "李开发",
         "start_date": "2026-08-14 08:00:00"} for i in range(4)
    ]
    result = run_heartbeat(_FakeAdapter(records), now=_now())
    codes = [a["code"] for a in result["alerts"]]
    assert "DEV_CONCURRENCY_EXCEEDED" in codes


def test_heartbeat_frontend_concurrency_exceeded():
    """巡检 2: FRONTEND 并发超 3 → critical"""
    records = [
        {"id": f"T000{i}", "status": "进行中", "assignee": "前端开发-小红",
         "start_date": "2026-08-14 08:00:00"} for i in range(4)
    ]
    result = run_heartbeat(_FakeAdapter(records), now=_now())
    codes = [a["code"] for a in result["alerts"]]
    assert "FRONTEND_CONCURRENCY_EXCEEDED" in codes


def test_heartbeat_assignee_mismatch_review_critical():
    """巡检 3: 审查中处理人非 REVIEWER → critical"""
    records = [
        {"id": "T0001", "status": "审查中", "assignee": "李开发",
         "start_date": "2026-08-14 08:00:00"},
    ]
    result = run_heartbeat(_FakeAdapter(records), now=_now())
    codes = [a["code"] for a in result["alerts"]]
    assert "ASSIGNEE_MISMATCH_REVIEW" in codes


def test_heartbeat_assignee_mismatch_test_critical():
    """巡检 3: 测试中处理人非 QA → critical"""
    records = [
        {"id": "T0001", "status": "测试中", "assignee": "李开发",
         "start_date": "2026-08-14 08:00:00"},
    ]
    result = run_heartbeat(_FakeAdapter(records), now=_now())
    codes = [a["code"] for a in result["alerts"]]
    assert "ASSIGNEE_MISMATCH_TEST" in codes


def test_heartbeat_terminal_missing_end_time_critical():
    """巡检 4: 终态(已完成/已验收)缺 end_date → critical"""
    records = [
        {"id": "T0001", "status": "已完成", "assignee": "严经理",
         "start_date": "2026-08-13 08:00:00"},  # 无 end_date
        {"id": "T0002", "status": "已验收", "assignee": "严经理",
         "start_date": "2026-08-13 08:00:00"},  # 无 end_date
    ]
    result = run_heartbeat(_FakeAdapter(records), now=_now())
    codes = [a["code"] for a in result["alerts"]]
    assert codes.count("MISSING_END_TIME") == 2


def test_heartbeat_thresholds_override():
    """阈值可覆盖:把进行中阈值改为 1h,触发滞留告警"""
    stale_start = (_now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    records = [
        {"id": "T0001", "status": "进行中", "assignee": "李开发",
         "start_date": stale_start},
    ]
    # 默认 24h 阈值不告警
    r1 = run_heartbeat(_FakeAdapter(records), now=_now())
    assert "STALE_IN_PROGRESS" not in [a["code"] for a in r1["alerts"]]
    # 覆盖为 1h,告警
    r2 = run_heartbeat(_FakeAdapter(records), now=_now(),
                       thresholds={"stale_in_progress_hours": 1, "stale_review_or_test_hours": 12,
                                   "dev_max_parallel": 3, "frontend_max_parallel": 3})
    assert "STALE_IN_PROGRESS" in [a["code"] for a in r2["alerts"]]


def test_heartbeat_real_local_board_no_crash():
    """对真实本地 board.json 跑巡检,不崩溃即可(数据可能 0~N 条)"""
    board_file = os.path.join(PROJECT_ROOT, "user_data", "board.json")
    if not os.path.exists(board_file):
        board_file = os.path.join(PROJECT_ROOT, "kanban", "board.json")
    if not os.path.exists(board_file):
        pytest.skip("本地 board.json 不存在")
    adapter = OfflineBoardAdapter(board_file=board_file)
    result = run_heartbeat(adapter, now=_now())
    assert "summary" in result
    assert "alerts" in result
    assert result["total_tasks"] >= 0


# ---------- audit_logger.query_events ----------

def test_query_events_by_task_id():
    """按 task_id 精确过滤"""
    from audit_logger import record_audit_event, query_events, AUDIT_LOG_FILE, ARCHIVE_DIR
    # 准备临时目录,避免污染真实 log
    tmp = tempfile.mkdtemp(prefix="maf_audit_test_")
    try:
        # monkey-patch 路径
        import audit_logger
        orig_log = audit_logger.AUDIT_LOG_FILE
        orig_arch = audit_logger.ARCHIVE_DIR
        audit_logger.AUDIT_LOG_FILE = os.path.join(tmp, "audit_trail.log")
        audit_logger.ARCHIVE_DIR = os.path.join(tmp, "archive")
        try:
            record_audit_event("T9001", "DEV", "待开始", "进行中", "李开发", True, "test1")
            record_audit_event("T9002", "QA", "测试中", "已完成", "章测试", True, "test2")
            record_audit_event("T9001", "PM", "已完成", "已验收", "严经理", True, "test3")
            evs = audit_logger.query_events(task_id="T9001")
            assert len(evs) == 2
            assert all(e["task_id"] == "T9001" for e in evs)
        finally:
            audit_logger.AUDIT_LOG_FILE = orig_log
            audit_logger.ARCHIVE_DIR = orig_arch
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_query_events_by_role_and_success():
    """按 role + success 联合过滤"""
    from audit_logger import record_audit_event
    import audit_logger

    tmp = tempfile.mkdtemp(prefix="maf_audit_test_")
    try:
        orig_log = audit_logger.AUDIT_LOG_FILE
        orig_arch = audit_logger.ARCHIVE_DIR
        audit_logger.AUDIT_LOG_FILE = os.path.join(tmp, "audit_trail.log")
        audit_logger.ARCHIVE_DIR = os.path.join(tmp, "archive")
        try:
            record_audit_event("T8001", "DEV", "待开始", "进行中", "李开发", True, "ok")
            record_audit_event("T8001", "DEV", "进行中", "审查中", "李开发", False, "fail")
            record_audit_event("T8002", "QA", "测试中", "已完成", "章测试", True, "ok")
            ok_evs = audit_logger.query_events(role="DEV", success=True)
            assert len(ok_evs) == 1
            assert ok_evs[0]["success"] is True
            fail_evs = audit_logger.query_events(role="DEV", success=False)
            assert len(fail_evs) == 1
            assert fail_evs[0]["success"] is False
        finally:
            audit_logger.AUDIT_LOG_FILE = orig_log
            audit_logger.ARCHIVE_DIR = orig_arch
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------- audit_logger.rotate_if_needed ----------

def test_rotate_archives_log_to_gz():
    """rotate_if_needed 把当前 log gzip 归档到 ARCHIVE_DIR"""
    import audit_logger

    tmp = tempfile.mkdtemp(prefix="maf_rotate_test_")
    try:
        log_file = os.path.join(tmp, "audit_trail.log")
        with open(log_file, "w") as f:
            f.write('{"timestamp":"2026-01-01","task_id":"T0","role":"X","from_status":"a","to_status":"b","assignee":"y","success":true}\n')

        orig_log = audit_logger.AUDIT_LOG_FILE
        orig_arch = audit_logger.ARCHIVE_DIR
        audit_logger.AUDIT_LOG_FILE = log_file
        audit_logger.ARCHIVE_DIR = os.path.join(tmp, "archive")
        try:
            result = audit_logger.rotate_if_needed()
            assert result["rotated"] is True
            assert result["reason"] == "daily_rotation"
            assert result["archived_to"].endswith(".log.gz")
            assert not os.path.exists(log_file), "原 log 文件应已被归档移除"
            # 归档目录应有 1 个 .gz
            gzs = [f for f in os.listdir(audit_logger.ARCHIVE_DIR) if f.endswith(".log.gz")]
            assert len(gzs) == 1
        finally:
            audit_logger.AUDIT_LOG_FILE = orig_log
            audit_logger.ARCHIVE_DIR = orig_arch
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rotate_no_op_for_small_log_with_date_suffix():
    """带日期后缀且未超 50MB 的 log 不轮转"""
    import audit_logger

    tmp = tempfile.mkdtemp(prefix="maf_rotate_test_")
    try:
        today = datetime.now().strftime("%Y%m%d")
        log_file = os.path.join(tmp, f"audit_trail-{today}.log")
        with open(log_file, "w") as f:
            f.write("x" * 1024)  # 1KB,远小于 50MB

        orig_log = audit_logger.AUDIT_LOG_FILE
        orig_arch = audit_logger.ARCHIVE_DIR
        audit_logger.AUDIT_LOG_FILE = log_file
        audit_logger.ARCHIVE_DIR = os.path.join(tmp, "archive")
        try:
            result = audit_logger.rotate_if_needed()
            assert result["rotated"] is False
            assert os.path.exists(log_file), "log 不应被切"
        finally:
            audit_logger.AUDIT_LOG_FILE = orig_log
            audit_logger.ARCHIVE_DIR = orig_arch
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
