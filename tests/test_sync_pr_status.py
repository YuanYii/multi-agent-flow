#!/usr/bin/env python3
"""
Unit tests for sync_pr_status.py (YY-Flow GitHub PR Gate & Auto-Unblock)
"""

import os
import sys
import json
import shutil
import pytest
from unittest.mock import patch, MagicMock

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
SCRIPTS_PATH = os.path.join(PROJECT_ROOT, "scripts")
if SCRIPTS_PATH not in sys.path:
    sys.path.insert(0, SCRIPTS_PATH)

from sync_pr_status import (
    extract_pr_identifiers,
    query_pr_status,
    sync_blocked_prs,
    format_pm_notification_card,
    format_terminal_summary,
)


def test_extract_pr_identifiers():
    """测试不同格式的 PR 引用提取"""
    # 1. 完整 URL 格式
    t1 = "【阻断】PR 已发起: https://github.com/YuanYii/multi-agent-flow/pull/42"
    r1 = extract_pr_identifiers(t1)
    assert len(r1) == 1
    assert r1[0]["number"] == "42"
    assert r1[0]["repo"] == "YuanYii/multi-agent-flow"

    # 2. Markdown 徽标格式
    t2 = "任务挂起 [PR: https://github.com/example/repo/pull/108] 等待 Review"
    r2 = extract_pr_identifiers(t2)
    assert len(r2) == 1
    assert r2[0]["number"] == "108"

    # 3. 简写格式
    t3 = "【阻断】等待 PR #256 合并入库"
    r3 = extract_pr_identifiers(t3)
    assert len(r3) == 1
    assert r3[0]["number"] == "256"

    # 4. 空文本
    assert extract_pr_identifiers("") == []
    assert extract_pr_identifiers(None) == []


def test_query_pr_status_merged_and_closed():
    """测试 query_pr_status 对 MERGED 与 CLOSED 状态的解析"""
    # 模拟 gh pr view 输出 MERGED
    mock_gh_output = json.dumps({
        "number": 42,
        "state": "MERGED",
        "mergedAt": "2026-08-23T10:00:00Z",
        "mergeCommit": {"oid": "6ba5f04123456789"},
        "title": "feat: 新增核心功能",
        "url": "https://github.com/org/repo/pull/42",
        "headRefName": "feature/s1-core",
        "baseRefName": "main"
    })

    with patch("shutil.which", return_value="/usr/local/bin/gh"):
        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0, stdout=mock_gh_output, stderr="")
            res = query_pr_status("42", repo="org/repo")
            assert res is not None
            assert res["is_merged"] is True
            assert res["merge_commit_sha"] == "6ba5f04123456789"
            assert res["base_ref"] == "main"

    # 模拟 gh 未安装
    with patch("shutil.which", return_value=None):
        res_no_gh = query_pr_status("42")
        assert res_no_gh["error"] == "gh_cli_not_found"


@pytest.fixture
def mock_pr_board_env(tmp_path):
    """构建包含【已阻塞】任务卡的测试环境"""
    proj_dir = tmp_path / "pr_test_project"
    proj_dir.mkdir()
    user_data = proj_dir / "user_data"
    user_data.mkdir()

    board_cards = [
        {
            "id": "T0010",
            "seq": 10,
            "wbs": "1.2.1",
            "stage": "S1",
            "name": "核心业务组件开发",
            "status": "已阻塞",
            "assignee": "李开发",
            "handler": "李开发",
            "type": "A",
            "remarks": "【阻断】等待 PR #42 (https://github.com/org/repo/pull/42) 审查合并入库",
        },
        {
            "id": "T0011",
            "seq": 11,
            "wbs": "1.2.2",
            "stage": "S1",
            "name": "前端交互组件",
            "status": "已阻塞",
            "assignee": "马前端",
            "handler": "马前端",
            "type": "A",
            "remarks": "【阻断】等待 PR #43 合并",
        }
    ]
    with open(user_data / "board.json", "w", encoding="utf-8") as f:
        json.dump(board_cards, f, ensure_ascii=False)

    # transition_task_pipeline 走 get_board_adapter → resolve_runtime_config 解析链,
    # 需要项目内 runtime 配置（等价于 init_skill.sh step 4 生成的宿主配置）。
    # 模板为 local provider,与 CI 干净环境兼容（本地 config/workflow.config.yaml
    # 为 gitignored 文件,不能作为测试依赖）。
    cfg_candidates = [
        os.path.join(PROJECT_ROOT, "config", "workflow.config.template.yaml"),
        os.path.join(PROJECT_ROOT, "config", "workflow.config.yaml"),
    ]
    cfg_src = next((c for c in cfg_candidates if os.path.isfile(c)), None)
    assert cfg_src, "找不到 workflow 配置或模板"
    shutil.copy(cfg_src, user_data / "workflow.config.yaml")

    return str(proj_dir)


def test_sync_blocked_prs_auto_unblock(mock_pr_board_env):
    """测试检测到 PR MERGED 后自动解除阻塞推进至【已完成】并记录审计"""
    # 模拟 PR #42 已合并，PR #43 处于 OPEN
    def mock_query(pr_ref, repo=None, project_dir=None):
        if str(pr_ref) == "42":
            return {
                "number": "42",
                "state": "MERGED",
                "is_merged": True,
                "merge_commit_sha": "6ba5f04abcdef",
                "title": "feat: 业务组件",
                "url": "https://github.com/org/repo/pull/42",
                "base_ref": "main",
            }
        else:
            return {
                "number": "43",
                "state": "OPEN",
                "is_merged": False,
                "title": "feat: 前端组件",
                "url": "https://github.com/org/repo/pull/43",
                "base_ref": "main",
            }

    with patch("sync_pr_status.query_pr_status", side_effect=mock_query):
        report = sync_blocked_prs(project_dir=mock_pr_board_env)
        assert report["success"] is True
        assert len(report["unblocked_tasks"]) == 1
        assert report["unblocked_tasks"][0]["id"] == "T0010"
        assert len(report["pending_tasks"]) == 1
        assert report["pending_tasks"][0]["id"] == "T0011"

        # 检查看板卡片物理更新状态
        board_file = os.path.join(mock_pr_board_env, "user_data", "board.json")
        with open(board_file, "r", encoding="utf-8") as f:
            updated_cards = json.load(f)

        t10 = next(c for c in updated_cards if c["id"] == "T0010")
        assert t10["status"] == "已完成"
        assert t10["handler"] == "严经理"
        assert "【解除】PR #42" in t10["remarks"]
        assert "6ba5f04" in t10["remarks"]

        # 检查通知格式化
        assert len(report["pm_notifications"]) == 1
        notify_card = format_pm_notification_card(report["pm_notifications"])
        assert "【GitHub PR 合流自动解阻与 PM 验收通知】" in notify_card
        assert "T0010" in notify_card
        assert "严经理" in notify_card


def test_sync_blocked_prs_closed_auto_reject(mock_pr_board_env):
    """测试检测到 PR CLOSED 后自动退回为【已退回】"""
    def mock_query(pr_ref, repo=None, project_dir=None):
        return {
            "number": str(pr_ref),
            "state": "CLOSED",
            "is_merged": False,
            "title": "feat: 被关闭的 PR",
            "url": "https://github.com/org/repo/pull/42",
            "base_ref": "main",
        }

    with patch("sync_pr_status.query_pr_status", side_effect=mock_query):
        report = sync_blocked_prs(project_dir=mock_pr_board_env, auto_reject_closed=True)
        assert report["success"] is True
        assert len(report["rejected_tasks"]) == 2

        board_file = os.path.join(mock_pr_board_env, "user_data", "board.json")
        with open(board_file, "r", encoding="utf-8") as f:
            updated_cards = json.load(f)

        t10 = next(c for c in updated_cards if c["id"] == "T0010")
        assert t10["status"] == "已退回"
        assert "【打回】" in t10["remarks"]
