import pytest
import os
import sys
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPT_DIR)

from metrics_analyzer import MetricsCalculator, TerminalRenderer, parse_datetime


def test_parse_datetime():
    dt = parse_datetime("2026-08-14 12:00:00")
    assert dt is not None
    assert dt.year == 2026

    dt_iso = parse_datetime("2026-08-14T12:00:00+08:00")
    assert dt_iso is not None

    assert parse_datetime("") is None
    assert parse_datetime(None) is None


def test_metrics_calculator_empty():
    calc = MetricsCalculator([])
    summary = calc.compute_summary()
    assert summary["total_tasks"] == 0
    assert summary["completion_rate_percent"] == 0.0
    assert summary["avg_lead_time_hours"] == 0.0

    workload = calc.compute_role_workload()
    assert len(workload) == 0

    bottlenecks = calc.detect_bottlenecks()
    assert len(bottlenecks) == 0


def test_metrics_calculator_normal():
    now = datetime(2026, 8, 14, 12, 0, 0)
    records = [
        {
            "fields": {
                "task_id": "T001",
                "task_name": "任务一",
                "status": "已完成",
                "assignee": "李开发",
                "start_date": "2026-08-14 08:00:00",
                "end_date": "2026-08-14 10:00:00",
            }
        },
        {
            "fields": {
                "task_id": "T002",
                "task_name": "任务二",
                "status": "进行中",
                "assignee": "前端开发",
                "start_date": "2026-08-12 08:00:00",  # 48h 前开始，滞留
            }
        },
        {
            "fields": {
                "task_id": "T003",
                "task_name": "任务三",
                "status": "审查中",
                "assignee": "周审查",
                "start_date": "2026-08-13 20:00:00",  # 16h 前开始，滞留
            }
        }
    ]

    calc = MetricsCalculator(records, now=now)
    summary = calc.compute_summary()
    assert summary["total_tasks"] == 3
    assert summary["completed_tasks"] == 1
    assert summary["in_progress_tasks"] == 1
    assert summary["completion_rate_percent"] == 33.3
    assert summary["avg_lead_time_hours"] == 2.0

    workload = calc.compute_role_workload()
    assert "李开发" in workload
    assert workload["李开发"]["completed"] == 1
    assert workload["前端开发"]["in_progress"] == 1

    bottlenecks = calc.detect_bottlenecks(stale_in_progress_hours=24, stale_review_test_hours=12)
    assert len(bottlenecks) == 2
    b_types = [b["type"] for b in bottlenecks]
    assert "STALE_IN_PROGRESS" in b_types
    assert "STALE_REVIEW_TEST" in b_types


def test_terminal_renderer_outputs():
    summary = {
        "total_tasks": 2,
        "completed_tasks": 1,
        "in_progress_tasks": 1,
        "completion_rate_percent": 50.0,
        "avg_lead_time_hours": 3.5,
    }
    workload = {
        "李开发": {"in_progress": 1, "completed": 0, "total": 1},
        "周审查": {"in_progress": 0, "completed": 1, "total": 1}
    }
    bottlenecks = [
        {
            "task_id": "T001",
            "task_name": "卡顿任务",
            "status": "进行中",
            "assignee": "李开发",
            "elapsed_hours": 30.0,
            "threshold_hours": 24,
        }
    ]

    dash = TerminalRenderer.render_terminal_dashboard(summary, workload, bottlenecks)
    assert "看板效能度量与流转诊断仪表盘" in dash
    assert "50.0%" in dash
    assert "李开发" in dash

    md = TerminalRenderer.render_markdown_report(summary, workload, bottlenecks)
    assert "# 📈 看板效能度量与诊断报告" in md
    assert "| 任务总数 | 2 |" in md
    assert "卡顿任务" in md
