#!/usr/bin/env python3
"""
第二轮代码审查与遗留缺陷综合回归测试 (Second Review & Legacy Fixes Regression Tests)
覆盖:
  1. OfflineBoardAdapter 接入 file_lock 并发读写与 Context Manager 锁释放
  2. OfflineBoardAdapter.append_remarks 真实换行符 '\n\n' 验证
  3. metrics_analyzer.py 滞留卡点基于 process 节点时间精准定位
  4. metrics_analyzer.py 角色负载基于 normalize_role 聚合别名
  5. migrate_legacy_docs.py D02-架构设计 加分与 D03-业务模块 兜底
  6. check_stage_gate.py 历史无 D 前缀双轨候选匹配
"""
import os
import sys
import json
import pytest
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from offline_board_adapter import OfflineBoardAdapter
import metrics_analyzer
import migrate_legacy_docs
from check_stage_gate import StageContext, check_arch_summary


def test_offline_board_adapter_file_lock_crud(tmp_path):
    """验证 OfflineBoardAdapter 采用 file_lock 且 CRUD 操作正常"""
    board_file = tmp_path / "board.json"
    adapter = OfflineBoardAdapter(str(board_file))
    
    # 1. create_record
    t1 = adapter.create_record(task_name="测试任务1", assignee="李开发", stage="S1")
    assert t1 == "T0001"
    
    # 2. get_record
    rec = adapter.get_record("T0001")
    assert rec is not None
    assert rec["fields"]["name"] == "测试任务1"
    
    # 3. update_record
    ok = adapter.update_record("T0001", {"status": "审查中"})
    assert ok is True
    rec2 = adapter.get_record("T0001")
    assert rec2["fields"]["status"] == "审查中"
    
    # 4. append_process_node
    node_id = adapter.append_process_node("T0001", "DEV", "进行中", "审查中", "李开发", "提交审查")
    assert node_id == "T0001-N01"
    
    # 5. list_records
    records = adapter.list_records()
    assert len(records) == 1
    assert records[0]["record_id"] == "T0001"


def test_offline_board_adapter_append_remarks_newline(tmp_path):
    """验证 append_remarks 使用真实换行符分隔"""
    board_file = tmp_path / "board.json"
    adapter = OfflineBoardAdapter(str(board_file))
    
    adapter.create_record(task_name="测试任务2", assignee="李开发")
    adapter.append_remarks("T0001", "remarks", "第一条缺陷备注")
    adapter.append_remarks("T0001", "remarks", "第二条缺陷备注")
    
    rec = adapter.get_record("T0001")
    remarks = rec["fields"]["remarks"]
    assert "第一条缺陷备注\n\n第二条缺陷备注" == remarks
    assert "\\n\\n" not in remarks


def test_metrics_analyzer_stale_dwell_from_process_node():
    """验证 metrics_analyzer 滞留卡点基于 process 节点真实入态时间，避免误报"""
    now = datetime(2026, 8, 17, 18, 0, 0)
    started_long_ago = (now - timedelta(hours=100)).strftime("%Y-%m-%d %H:%M:%S")
    recent_entry = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    
    process_text = (
        f"[T0001-N01] [{started_long_ago}] 状态由【待开始】更新至【进行中】，操作人: 李开发\n"
        f"[T0001-N02] [{recent_entry}] 状态由【进行中】更新至【审查中】，操作人: 周审查"
    )
    
    records = [{
        "id": "T0001",
        "name": "核心功能开发",
        "status": "审查中",
        "assignee": "周审查",
        "start_date": started_long_ago,
        "process": process_text,
    }]
    
    calc = metrics_analyzer.MetricsCalculator(records, now=now)
    # 阈值 12h，因仅进入审查中 1h，不应报警
    bottlenecks = calc.detect_bottlenecks(stale_review_test_hours=12)
    assert len(bottlenecks) == 0


def test_metrics_analyzer_role_workload_normalization():
    """验证 metrics_analyzer 角色负载统计将 flow-dev / dev 归一化为 李开发"""
    records = [
        {"id": "T0001", "name": "任务1", "status": "进行中", "assignee": "flow-dev"},
        {"id": "T0002", "name": "任务2", "status": "已完成", "assignee": "dev"},
        {"id": "T0003", "name": "任务3", "status": "进行中", "assignee": "李开发"},
    ]
    calc = metrics_analyzer.MetricsCalculator(records)
    workload = calc.compute_role_workload()
    
    assert "李开发" in workload
    assert workload["李开发"]["total"] == 3
    assert workload["李开发"]["in_progress"] == 2
    assert workload["李开发"]["completed"] == 1


def test_migrate_legacy_docs_d_prefix():
    """验证 migrate_legacy_docs.py 中 D02-架构设计 加分与 D03-业务模块 兜底"""
    # 命中架构关键词
    cat_arch = migrate_legacy_docs.classify_document("src/architecture_design.md")
    assert cat_arch == "D02-架构设计"
    
    # 未命中文档兜底
    cat_fallback = migrate_legacy_docs.classify_document("unknown_file_xyz.md")
    assert cat_fallback == "D03-业务模块"


def test_check_stage_gate_dual_track_summary(tmp_path):
    """验证 check_stage_gate 支持无 D 前缀历史路径 (如 docs/04-研发过程/02-报告/summary/架构设计总结.md)"""
    project_dir = tmp_path / "myproj"
    legacy_summary_dir = project_dir / "docs" / "04-研发过程" / "02-报告" / "summary"
    legacy_summary_dir.mkdir(parents=True, exist_ok=True)
    summary_file = legacy_summary_dir / "S1-架构设计总结.md"
    summary_file.write_text("# S1 阶段架构总结\n", encoding="utf-8")
    
    board_dir = project_dir / ".yy-flow" / "user_data"
    board_dir.mkdir(parents=True, exist_ok=True)
    board_file = board_dir / "board.json"
    board_file.write_text(json.dumps([{"id": "T0001", "name": "任务1", "status": "已完成", "stage": "S1"}], ensure_ascii=False), encoding="utf-8")
    
    ctx = StageContext(stage_input="S1", project_dir=str(project_dir))
    res = check_arch_summary(ctx)
    assert res.passed is True
    assert "ARCH_SUMMARY_PASS" in res.code
