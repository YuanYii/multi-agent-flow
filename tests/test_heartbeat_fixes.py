#!/usr/bin/env python3
"""
心跳巡检与并发归一化回归测试 (Heartbeat Fixes Regression Tests)
覆盖:
  1. heartbeat.py import 零异常
  2. 滞留时间基于 process 节点真实入态时间计算（而非 start_date）
  3. 并发统计统一通过 normalize_role 将别名（flow-dev, dev, 李开发）归一化并正确报警
  4. 终态与处理人一致性校验
"""
import os
import sys
import json
import pytest
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import heartbeat
from _lib.boards.offline_board_adapter import OfflineBoardAdapter


def test_heartbeat_import_safe():
    """验证 heartbeat 模块 import 安全，无未定义函数引用"""
    assert hasattr(heartbeat, "run_heartbeat")
    assert hasattr(heartbeat, "_get_status_entry_time")


def test_stale_dwell_time_from_process_nodes(tmp_path):
    """验证滞留时间从 process 节点获取，避免误报"""
    now = datetime(2026, 8, 17, 18, 0, 0)
    
    # 任务在 100 小时前开始，但在 1 小时前才刚转入【审查中】
    started_long_ago = (now - timedelta(hours=100)).strftime("%Y-%m-%d %H:%M:%S")
    recent_entry = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    
    process_text = (
        f"[T0001-N01] [{started_long_ago}] 状态由【待开始】更新至【进行中】，操作人: 李开发\n"
        f"[T0001-N02] [{recent_entry}] 状态由【进行中】更新至【审查中】，操作人: 周审查"
    )
    
    board_file = tmp_path / "board.json"
    cards = [{
        "id": "T0001",
        "name": "核心功能开发",
        "status": "审查中",
        "assignee": "周审查",
        "start_date": started_long_ago,
        "process": process_text,
    }]
    board_file.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    
    adapter = OfflineBoardAdapter(str(board_file))
    # 审查滞留阈值设为 12 小时；因最近进入仅 1 小时，不应触发 STALE_REVIEW_OR_TEST 告警
    result = heartbeat.run_heartbeat(adapter, thresholds={"stale_review_or_test_hours": 12}, now=now)
    alert_codes = [a["code"] for a in result["alerts"]]
    assert "STALE_REVIEW_OR_TEST" not in alert_codes


def test_concurrency_aggregation_with_role_normalization(tmp_path):
    """验证并发统计将 flow-dev / dev / 李开发 统一归一化为 李开发 并正确检测超额"""
    now = datetime.now()
    board_file = tmp_path / "board.json"
    
    # 4 张进行中任务，分别使用不同别名派发给同一个开发
    cards = [
        {"id": "T0001", "name": "任务1", "status": "进行中", "assignee": "flow-dev", "start_date": now.isoformat()},
        {"id": "T0002", "name": "任务2", "status": "进行中", "assignee": "dev", "start_date": now.isoformat()},
        {"id": "T0003", "name": "任务3", "status": "进行中", "assignee": "李开发", "start_date": now.isoformat()},
        {"id": "T0004", "name": "任务4", "status": "进行中", "assignee": "dev_user_1", "start_date": now.isoformat()},
    ]
    board_file.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    
    adapter = OfflineBoardAdapter(str(board_file))
    # 开发并发上限设为 3；4 个别名聚合后总计 4，应触发 DEV_CONCURRENCY_EXCEEDED
    result = heartbeat.run_heartbeat(adapter, thresholds={"dev_max_parallel": 3}, now=now)
    alert_codes = [a["code"] for a in result["alerts"]]
    assert "DEV_CONCURRENCY_EXCEEDED" in alert_codes
    concurrency_alert = next(a for a in result["alerts"] if a["code"] == "DEV_CONCURRENCY_EXCEEDED")
    assert "李开发 进行中任务数 4" in concurrency_alert["message"]


def test_time_skew_instant_transition_alert(tmp_path):
    """验证多节点瞬时流转（<=5秒完成多步）触发 TIME_SKEW_INSTANT 告警并正确计算有效交付周期"""
    board_file = tmp_path / "board.json"
    same_time = "2026-08-23 10:00:00"
    process_text = (
        f"[T0001-N01] [{same_time}] 状态由【待开始】更新至【进行中】，操作人: 李开发\n"
        f"[T0001-N02] [{same_time}] 状态由【进行中】更新至【审查中】，操作人: 李开发\n"
        f"[T0001-N03] [{same_time}] 状态由【审查中】更新至【测试中】，操作人: 周审查\n"
        f"[T0001-N04] [{same_time}] 状态由【测试中】更新至【已完成】，操作人: 章测试\n"
        f"[T0001-N05] [{same_time}] 状态由【已完成】更新至【已验收】，操作人: 严经理"
    )
    cards = [
        {
            "id": "T0001",
            "name": "秒级冲卡任务",
            "status": "已验收",
            "assignee": "严经理",
            "start_date": same_time,
            "end_date": same_time,
            "process": process_text,
        },
        {
            "id": "T0002",
            "name": "真实研发任务",
            "status": "已验收",
            "assignee": "严经理",
            "start_date": "2026-08-23 08:00:00",
            "end_date": "2026-08-23 10:00:00",
            "process": "[T0002-N01] [2026-08-23 08:00:00] 状态由【待开始】更新至【进行中】\n[T0002-N02] [2026-08-23 10:00:00] 状态由【进行中】更新至【已完成】",
        }
    ]
    board_file.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")

    adapter = OfflineBoardAdapter(str(board_file))
    result = heartbeat.run_heartbeat(adapter, thresholds={}, now=datetime(2026, 8, 23, 10, 0, 0))
    alert_codes = [a["code"] for a in result["alerts"]]
    assert "TIME_SKEW_INSTANT" in alert_codes

    m = result.get("metrics", {})
    assert m.get("instant_tasks_count") == 1
    # T0001 耗时 0h，T0002 耗时 2h；全量平均 1.0h，有效平均（排除<=1min）应为 2.0h
    assert m.get("avg_lead_time_hours") == 1.0
    assert m.get("effective_avg_lead_time_hours") == 2.0
