#!/usr/bin/env python3
"""
审计日志轮转回归测试 (Audit Log Rotation Regression Tests)
覆盖:
  1. 同日日志写入后调用 rotate_if_needed 幂等返回 no_rotation_needed，不重复清空/归档
  2. 历史跨日日志成功归档为 audit_trail-YYYYMMDD.log.gz 并清空当前日志
  3. 单文件超容 (>= max_size_mb) 时触发 size_limit 归档并附加时间戳
  4. file_lock 并发锁保护与 context manager 验证
"""
import os
import sys
import json
import gzip
import pytest
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from _lib.audit import audit_logger
from _lib.core import file_lock


@pytest.fixture
def mock_audit_env(tmp_path, monkeypatch):
    """隔离 AUDIT_LOG_DIR 到临时目录"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AUDIT_LOG_DIR", str(log_dir))
    return log_dir


def test_lock_handle_context_manager(tmp_path):
    """验证 LockHandle 上下文管理器语法支持"""
    lock_file = tmp_path / "test.lock"
    with file_lock.acquire_lock(str(lock_file), blocking=True) as handle:
        assert handle is not None
        assert os.path.exists(lock_file)
    # 退出 with 块后底层文件对象已关闭
    assert handle.file is None


def test_same_day_no_rotation(mock_audit_env):
    """同日日志写入后不应触发 daily rotation"""
    today_iso = datetime.now().isoformat()
    log_file = os.path.join(str(mock_audit_env), "audit_trail.log")
    
    event = {
        "timestamp": today_iso,
        "task_id": "T0001",
        "role": "DEV",
        "from_status": "待开始",
        "to_status": "进行中",
        "assignee": "李开发",
        "success": True,
    }
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    res = audit_logger.rotate_if_needed(max_size_mb=50)
    assert res["rotated"] is False
    assert res["reason"] == "no_rotation_needed"
    assert os.path.exists(log_file)
    # 确认文件内容未被删除
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1


def test_cross_day_rotation(mock_audit_env):
    """历史跨日日志应归档为 audit_trail-YYYYMMDD.log.gz"""
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_iso = yesterday.isoformat()
    yesterday_date = yesterday.strftime("%Y%m%d")
    log_file = os.path.join(str(mock_audit_env), "audit_trail.log")
    
    event = {
        "timestamp": yesterday_iso,
        "task_id": "T0001",
        "role": "DEV",
        "from_status": "待开始",
        "to_status": "进行中",
        "assignee": "李开发",
        "success": True,
    }
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    res = audit_logger.rotate_if_needed(max_size_mb=50)
    assert res["rotated"] is True
    assert res["reason"] == "daily_rotation"
    expected_archive = os.path.join(str(mock_audit_env), "archive", f"audit_trail-{yesterday_date}.log.gz")
    assert res["archived_to"] == expected_archive
    assert os.path.exists(expected_archive)
    assert not os.path.exists(log_file)

    # 验证 gzip 归档内数据完整
    with gzip.open(expected_archive, "rt", encoding="utf-8") as gz:
        content = gz.read()
        assert "T0001" in content


def test_size_limit_rotation(mock_audit_env):
    """超容文件应触发 size_limit 归档"""
    today_iso = datetime.now().isoformat()
    log_file = os.path.join(str(mock_audit_env), "audit_trail.log")
    
    with open(log_file, "w", encoding="utf-8") as f:
        event = {"timestamp": today_iso, "task_id": "T0002", "payload": "x" * 1024}
        for _ in range(100):
            f.write(json.dumps(event) + "\n")

    res = audit_logger.rotate_if_needed(max_size_mb=0)
    assert res["rotated"] is True
    assert "size_limit" in res["reason"]
    assert os.path.exists(res["archived_to"])
