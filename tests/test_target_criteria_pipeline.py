#!/usr/bin/env python3
"""
单元测试：验证 target 与 criteria 在 transition_task 与 quick_task 全链路下的正确装配与持久化
"""
import os
import sys
import tempfile
import shutil
import subprocess
import pytest
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_SCRIPTS_DIR = os.path.join(_PROJ_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from transition_task import transition_task_pipeline
from _lib.boards.board_adapter_factory import get_board_adapter


@pytest.fixture
def temp_board_workspace():
    td = tempfile.mkdtemp(prefix="test_pipeline_tc_")
    board_file = os.path.join(td, "user_data", "board.json")
    os.makedirs(os.path.dirname(board_file), exist_ok=True)
    cfg_dir = os.path.join(td, "config")
    os.makedirs(cfg_dir, exist_ok=True)
    cfg_path = os.path.join(cfg_dir, "workflow.config.yaml")
    
    cfg_data = {
        "project": {
            "name": "TestProject",
            "version": "1.0.0",
            "root_dir": td
        },
        "board": {
            "provider": "local",
            "storage_mode": "single",
            "board_file": board_file,
            "fields": {
                "task_id": "task_id",
                "task_name": "task_name",
                "status": "status",
                "assignee": "assignee",
                "owner": "owner",
                "remarks": "remarks",
                "target": "target",
                "acceptance_criteria": "acceptance_criteria"
            }
        },
        "roles": {
            "PM": {"name": "严经理", "max_parallel_tasks": 99, "can_self_claim": False},
            "DEV": {"name": "李开发", "max_parallel_tasks": 3, "can_self_claim": True}
        },
        "paths": {
            "docs_root": "docs",
            "task_breakdown_dir": "docs/D04-研发过程/D01-任务",
            "dev_reports_dir": "docs/D04-研发过程/D02-报告",
            "review_reports_dir": "docs/D04-研发过程/D02-报告",
            "qa_reports_dir": "docs/D04-研发过程/D02-报告",
            "summary_dir": "docs/D04-研发过程/D02-报告"
        }
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg_data, f)

    yield cfg_path, td
    shutil.rmtree(td, ignore_errors=True)


def test_explicit_create_target_criteria(temp_board_workspace):
    """测试场景 1：显式建单模式 (create_only=True) 下 target 与 criteria 正确透传并持久化"""
    cfg_path, _ = temp_board_workspace
    ok = transition_task_pipeline(
        config_path=cfg_path,
        task_name="用户权限重构",
        current_role="PM",
        assignee="李开发",
        task_type="A",
        create_only=True,
        target="支持细粒度 RBAC 权限控制",
        criteria=["1. 支持角色继承", "2. 单测覆盖率达标"],
        remarks="核心设计: 基于现有中间件拦截",
        no_dup_check=True
    )
    assert ok is True
    adapter = get_board_adapter(cfg_path)
    recs = adapter.list_records()
    assert len(recs) >= 1
    created = recs[0]["fields"]
    assert created["name"] == "用户权限重构"
    assert created["target"] == "支持细粒度 RBAC 权限控制"
    assert len(created["acceptance_criteria"]) == 2
    assert "1. 支持角色继承" in created["acceptance_criteria"]
    assert created["remarks"] == "核心设计: 基于现有中间件拦截"


def test_fallback_auto_create_target_criteria(temp_board_workspace):
    """测试场景 2：直接流转触发兜底自动建单时，target 与 criteria 正确装配不丢弃"""
    cfg_path, _ = temp_board_workspace
    ok = transition_task_pipeline(
        config_path=cfg_path,
        task_id="T0099",
        task_name="兜底初始化任务",
        current_role="DEV",
        from_status="待开始",
        to_status="进行中",
        assignee="李开发",
        task_type="B",
        create_only=False,
        target="验证兜底建单字段装配",
        criteria=["1. 兜底写入无报错", "2. target 不为空"],
        remarks="自动补单备注",
        no_dup_check=True
    )
    assert ok is True
    adapter = get_board_adapter(cfg_path)
    rec = adapter.get_record("T0099")
    assert rec is not None
    f = rec["fields"]
    assert f["target"] == "验证兜底建单字段装配"
    assert len(f["acceptance_criteria"]) == 2
    assert "2. target 不为空" in f["acceptance_criteria"]
    assert f["remarks"] == "自动补单备注"


def test_transition_task_cli_target_criteria(temp_board_workspace):
    """测试场景 3：transition_task.py CLI 携带 --target 与 --criteria 能被成功解析执行"""
    cfg_path, _ = temp_board_workspace
    cmd = [
        sys.executable,
        os.path.join(_SCRIPTS_DIR, "transition_task.py"),
        "--config", cfg_path,
        "--create",
        "--name", "CLI创建测试任务",
        "--role", "PM",
        "--assignee", "李开发",
        "--type", "A",
        "--target", "CLI 入口目标验证",
        "--criteria", "1. CLI 参数解析成功",
        "--criteria", "2. 多条 criteria 合并",
        "--no-dup-check"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"

    adapter = get_board_adapter(cfg_path)
    recs = adapter.list_records()
    target_rec = next((r for r in recs if r["fields"]["name"] == "CLI创建测试任务"), None)
    assert target_rec is not None
    f = target_rec["fields"]
    assert f["target"] == "CLI 入口目标验证"
    assert len(f["acceptance_criteria"]) == 2
    assert "1. CLI 参数解析成功" in f["acceptance_criteria"]


def test_quick_task_cli_target_criteria(temp_board_workspace):
    """测试场景 4：quick_task.py create CLI 携带 --target 与 --criteria 能被成功解析执行"""
    cfg_path, _ = temp_board_workspace
    cmd = [
        sys.executable,
        os.path.join(_SCRIPTS_DIR, "quick_task.py"),
        "create",
        "--config", cfg_path,
        "--name", "QuickTask创建测试任务",
        "--role", "PM",
        "--assignee", "李开发",
        "--type", "A",
        "--target", "QuickTask 目标测试",
        "--criteria", "1. 标准一",
        "--criteria", "2. 标准二; 3. 标准三",
        "--remarks", "QuickTask 备注说明",
        "--no-dup-check"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"

    adapter = get_board_adapter(cfg_path)
    recs = adapter.list_records()
    target_rec = next((r for r in recs if r["fields"]["name"] == "QuickTask创建测试任务"), None)
    assert target_rec is not None
    f = target_rec["fields"]
    assert f["target"] == "QuickTask 目标测试"
    assert len(f["acceptance_criteria"]) == 3
    assert "1. 标准一" in f["acceptance_criteria"]
    assert "3. 标准三" in f["acceptance_criteria"]
    assert f["remarks"] == "QuickTask 备注说明"
