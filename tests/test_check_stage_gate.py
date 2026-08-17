#!/usr/bin/env python3
"""
Unit tests for check_stage_gate.py (YY-Flow Stage Gate Checker)
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
SCRIPTS_PATH = os.path.join(PROJECT_ROOT, "scripts")
if SCRIPTS_PATH not in sys.path:
    sys.path.insert(0, SCRIPTS_PATH)

from check_stage_gate import (
    run_stage_gate_check,
    StageContext,
    check_board_tasks_status,
    check_wbs_reconciliation,
    check_arch_summary,
    check_pm_summary,
    format_terminal_report,
)


@pytest.fixture
def mock_stage_env(tmp_path):
    """构建一个完整的测试用隔离项目环境"""
    proj_dir = tmp_path / "test_project"
    proj_dir.mkdir()
    user_data = proj_dir / "user_data"
    user_data.mkdir()
    docs = proj_dir / "docs"
    docs.mkdir()

    # 1. 创建基础 board.json
    board_cards = [
        {
            "id": "T0001",
            "seq": 1,
            "wbs": "1.1.1",
            "stage": "S1 需求分析与系统架构设计",
            "name": "核心 Schema 与架构定义",
            "status": "已验收",
            "assignee": "钱架构",
            "handler": "严经理",
            "end_date": "2026-08-16 18:00",
        },
        {
            "id": "T0002",
            "seq": 2,
            "wbs": "1.1.2",
            "stage": "S1 需求分析与系统架构设计",
            "name": "任务状态机核心开发",
            "status": "已验收",
            "assignee": "李开发",
            "handler": "严经理",
            "end_date": "2026-08-16 19:30",
        },
        {
            "id": "T0003",
            "seq": 3,
            "wbs": "1.2.1",
            "stage": "S1 需求分析与系统架构设计",
            "name": "S1 阶段管理总结与复盘",
            "status": "已验收",
            "type": "F",
            "assignee": "严经理",
            "handler": "严经理",
            "end_date": "2026-08-16 20:00",
        },
    ]
    with open(user_data / "board.json", "w", encoding="utf-8") as f:
        json.dump(board_cards, f, ensure_ascii=False)

    # 2. 创建 WBS 文档
    task_dir = docs / "D04-研发过程" / "D01-任务"
    task_dir.mkdir(parents=True)
    wbs_content = """---
wbs_id: "WBS-S1.1"
stage: "S1 需求分析与系统架构设计"
---
# S1 WBS 任务清单
| 任务编号 | WBS 编号 | 任务名称 | 负责角色 |
|---------|---------|---------|---------|
| T0001   | 1.1.1   | 架构定义 | 钱架构   |
| T0002   | 1.1.2   | 核心开发 | 李开发   |
| T0003   | 1.2.1   | 阶段复盘 | 严经理   |
"""
    with open(task_dir / "WBS-S1.1.md", "w", encoding="utf-8") as f:
        f.write(wbs_content)

    # 3. 创建架构技术总结文档
    summary_dir = docs / "D04-研发过程" / "D02-报告" / "summary"
    summary_dir.mkdir(parents=True)
    arch_summary_content = """---
title: S1 架构技术总结
stage: S1 需求分析与系统架构设计
type: architecture
author: 钱架构
---
# S1 阶段技术总结与架构决策
"""
    with open(summary_dir / "S1-架构技术总结.md", "w", encoding="utf-8") as f:
        f.write(arch_summary_content)

    # 4. 创建 PM 管理总结文档
    status_dir = docs / "D01-项目管理" / "D02-状态报告"
    status_dir.mkdir(parents=True)
    pm_summary_content = """---
title: S1 阶段管理总结与复盘
stage: S1 需求分析与系统架构设计
type: summary
author: 严经理
---
# S1 阶段管理总结报告
"""
    with open(status_dir / "01-S1阶段总结报告.md", "w", encoding="utf-8") as f:
        f.write(pm_summary_content)

    return str(proj_dir)


def test_stage_gate_all_passed(mock_stage_env):
    """测试场景 1：所有卡片已验收、WBS 对账通过、总结报告齐全 -> 门禁 100% 通过"""
    report = run_stage_gate_check(stage_name="S1", project_root_dir=mock_stage_env)
    assert report.passed is True
    assert report.failed_checks == 0
    assert report.passed_checks == 4
    formatted = format_terminal_report(report)
    assert "✅ 阶段门禁 100% 审查通过" in formatted


def test_stage_gate_unaccepted_tasks_blocked(mock_stage_env):
    """测试场景 2：存在未验收任务（进行中或测试中）-> 阻断结项"""
    board_file = os.path.join(mock_stage_env, "user_data", "board.json")
    with open(board_file, "r", encoding="utf-8") as f:
        cards = json.load(f)
    # 修改第二张卡片为 进行中
    cards[1]["status"] = "进行中"
    with open(board_file, "w", encoding="utf-8") as f:
        json.dump(cards, f)

    report = run_stage_gate_check(stage_name="S1", project_root_dir=mock_stage_env)
    assert report.passed is False
    assert report.failed_checks >= 1
    unaccepted_check = next(r for r in report.results if r.code == "BOARD_TASKS_UNACCEPTED")
    assert unaccepted_check.passed is False
    assert "T0002" in unaccepted_check.detail


def test_stage_gate_missing_end_date_blocked(mock_stage_env):
    """测试场景 3：已验收任务遗漏结束时间 (end_date) -> 阻断结项"""
    board_file = os.path.join(mock_stage_env, "user_data", "board.json")
    with open(board_file, "r", encoding="utf-8") as f:
        cards = json.load(f)
    cards[0]["end_date"] = ""
    with open(board_file, "w", encoding="utf-8") as f:
        json.dump(cards, f)

    report = run_stage_gate_check(stage_name="S1", project_root_dir=mock_stage_env)
    assert report.passed is False
    end_time_check = next(r for r in report.results if r.code == "BOARD_TASKS_MISSING_END_TIME")
    assert end_time_check.passed is False
    assert "T0001" in end_time_check.detail


def test_stage_gate_wbs_missing_field_blocked(mock_stage_env):
    """测试场景 4：看板卡片未填写 WBS 编号 -> 阻断结项"""
    board_file = os.path.join(mock_stage_env, "user_data", "board.json")
    with open(board_file, "r", encoding="utf-8") as f:
        cards = json.load(f)
    cards[0]["wbs"] = ""
    with open(board_file, "w", encoding="utf-8") as f:
        json.dump(cards, f)

    report = run_stage_gate_check(stage_name="S1", project_root_dir=mock_stage_env)
    assert report.passed is False
    wbs_check = next(r for r in report.results if r.code == "WBS_FIELD_MISSING")
    assert wbs_check.passed is False


def test_stage_gate_wbs_doc_mismatch_blocked(mock_stage_env):
    """测试场景 5：WBS 文档中声明的任务在看板中缺失 -> 阻断结项"""
    wbs_file = os.path.join(mock_stage_env, "docs", "D04-研发过程", "D01-任务", "WBS-S1.1.md")
    with open(wbs_file, "a", encoding="utf-8") as f:
        f.write("| T0099 | 1.3.1 | 未建卡幽灵任务 | 李开发 |\n")

    report = run_stage_gate_check(stage_name="S1", project_root_dir=mock_stage_env)
    assert report.passed is False
    wbs_check = next(r for r in report.results if r.code == "WBS_DOC_MISMATCH")
    assert wbs_check.passed is False
    assert "T0099" in wbs_check.detail


def test_stage_gate_missing_arch_summary_blocked(mock_stage_env):
    """测试场景 6：缺少阶段架构技术总结 -> 阻断结项"""
    arch_file = os.path.join(mock_stage_env, "docs", "D04-研发过程", "D02-报告", "summary", "S1-架构技术总结.md")
    if os.path.exists(arch_file):
        os.remove(arch_file)

    report = run_stage_gate_check(stage_name="S1", project_root_dir=mock_stage_env)
    assert report.passed is False
    arch_check = next(r for r in report.results if r.code == "ARCH_SUMMARY_MISSING")
    assert arch_check.passed is False


def test_stage_gate_missing_pm_summary_blocked(mock_stage_env):
    """测试场景 7：缺少 PM 阶段管理总结报告 -> 阻断结项"""
    pm_file = os.path.join(mock_stage_env, "docs", "D01-项目管理", "D02-状态报告", "01-S1阶段总结报告.md")
    if os.path.exists(pm_file):
        os.remove(pm_file)

    report = run_stage_gate_check(stage_name="S1", project_root_dir=mock_stage_env)
    assert report.passed is False
    pm_check = next(r for r in report.results if r.code == "PM_SUMMARY_DOC_MISSING")
    assert pm_check.passed is False


def test_stage_gate_fuzzy_stage_name_matching(mock_stage_env):
    """测试场景 8：模糊阶段名 's1'、'S1' 自动对齐完整名称"""
    report1 = run_stage_gate_check(stage_name="s1", project_root_dir=mock_stage_env)
    assert report1.stage_name == "S1 需求分析与系统架构设计"
    assert report1.passed is True

    report2 = run_stage_gate_check(stage_name="需求分析", project_root_dir=mock_stage_env)
    assert report2.stage_name == "S1 需求分析与系统架构设计"
    assert report2.passed is True


def test_stage_gate_path_adaptation(tmp_path):
    """测试场景 9：路径自适应（平铺 docs/ 目录也能正常识别总结文档）"""
    proj_dir = tmp_path / "flat_project"
    proj_dir.mkdir()
    user_data = proj_dir / "user_data"
    user_data.mkdir()
    docs = proj_dir / "docs"
    docs.mkdir()

    board_cards = [
        {
            "id": "T0001",
            "seq": 1,
            "wbs": "1.1",
            "stage": "S1",
            "name": "任务一",
            "status": "已验收",
            "assignee": "李开发",
            "handler": "严经理",
            "end_date": "2026-08-16 18:00",
        }
    ]
    with open(user_data / "board.json", "w", encoding="utf-8") as f:
        json.dump(board_cards, f)

    # 平铺放置在 docs/summary/ 下
    summary_dir = docs / "summary"
    summary_dir.mkdir()
    with open(summary_dir / "S1-架构总结.md", "w", encoding="utf-8") as f:
        f.write("# S1 架构总结")
    with open(summary_dir / "S1-阶段管理复盘.md", "w", encoding="utf-8") as f:
        f.write("# S1 阶段管理复盘")

    report = run_stage_gate_check(stage_name="S1", project_root_dir=str(proj_dir))
    assert report.passed is True
    assert report.failed_checks == 0


def test_stage_gate_cli_json_output(mock_stage_env, capsys):
    """测试场景 10：CLI --json 输出格式契约"""
    from check_stage_gate import main
    with patch("sys.argv", ["check_stage_gate.py", "--stage", "S1", "--project-root", mock_stage_env, "--json"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["passed"] is True
    assert data["total_checks"] == 4
    assert len(data["results"]) == 4

