import os
import sys
import tempfile
import json
import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(SCRIPT_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from _lib.gates.gate_pm_code_edit import check_tool_permission
from _lib.boards.weekly_board_adapter import WeeklyBoardAdapter
from dispatch_task import dispatch_task, ROLE_SUBAGENT_MAP


def test_gate_pm_code_edit_blocks_business_code():
    # 1. PM 主会话修改 src/ 业务代码 -> DENY
    res = check_tool_permission("write_to_file", "src/auth/login.py", is_subagent=False)
    assert res["decision"] == "deny"
    assert "GATE-PM-BLOCK" in res["reason"]

    # 2. PM 主会话修改 app/ 业务代码 -> DENY
    res2 = check_tool_permission("replace_file_content", "app/routes.py", is_subagent=False)
    assert res2["decision"] == "deny"


def test_gate_pm_code_edit_allows_docs_and_data():
    # 1. PM 修改 docs/ 文档 -> ALLOW
    res1 = check_tool_permission("write_to_file", "docs/D01-需求/01-spec.md", is_subagent=False)
    assert res1["decision"] == "allow"

    # 2. PM 修改 user_data/ 状态文件 -> ALLOW
    res2 = check_tool_permission("write_to_file", "user_data/2026-W36.yaml", is_subagent=False)
    assert res2["decision"] == "allow"

    # 3. PM 修改 config/ -> ALLOW
    res3 = check_tool_permission("replace_file_content", "config/project_architecture.template.yaml", is_subagent=False)
    assert res3["decision"] == "allow"


def test_gate_pm_code_edit_allows_subagents():
    # Subagent 专家无论修改何种业务源码均放行
    res = check_tool_permission("write_to_file", "src/core/parser.py", is_subagent=True)
    assert res["decision"] == "allow"


def test_dispatch_task_payload_assembly(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "user_data" / "tasks"
    tasks_dir.mkdir(parents=True)
    adapter = WeeklyBoardAdapter(tasks_dir=str(tasks_dir))

    # 预设一条测试任务卡 T9901
    adapter.create_record({
        "id": "T9901",
        "name": "实现核心解析引擎",
        "stage": "阶段三: 编码实现",
        "status": "待开始",
        "assignee": "李开发",
        "owner": "李开发",
        "type": "A",
        "est_hours": 4.0,
        "target": "编写高吞吐流式解析器",
        "acceptance_criteria": ["1. 覆盖 UTF-8 与 GBK", "2. 单测全部通过"],
        "pretask": "无",
        "week": "2026-W36"
    })

    # mock get_board_adapter 返回当前 adapter
    import _lib.boards.board_adapter_factory as baf
    monkeypatch.setattr(baf, "get_board_adapter", lambda cfg=None: adapter)

    # 模拟执行 dispatch
    res = dispatch_task(task_id="T9901", target_role="DEV", dry_run=True)

    assert res["task_id"] == "T9901"
    assert res["tool_name"] == "invoke_subagent"
    params = res["parameters"]
    assert "Subagents" in params
    subagent = params["Subagents"][0]
    assert subagent["TypeName"] == "flow-dev"
    assert "李开发" in subagent["Role"]
    prompt = subagent["Prompt"]
    assert "编写高吞吐流式解析器" in prompt
    assert "覆盖 UTF-8 与 GBK" in prompt
    assert "transition_task.py --task-id T9901" in prompt


def test_dispatch_task_dependency_gate_blocks_incomplete(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "user_data" / "tasks"
    tasks_dir.mkdir(parents=True)
    adapter = WeeklyBoardAdapter(tasks_dir=str(tasks_dir))

    # 前置卡 T9901 仍在进行中
    adapter.create_record({
        "id": "T9901",
        "name": "基础依赖构建",
        "status": "进行中",
        "assignee": "李开发",
        "week": "2026-W36"
    })
    # 后续卡 T9902 依赖 T9901
    adapter.create_record({
        "id": "T9902",
        "name": "上层业务编排",
        "status": "待开始",
        "assignee": "李开发",
        "pretask": "T9901",
        "week": "2026-W36"
    })

    import _lib.boards.board_adapter_factory as baf
    monkeypatch.setattr(baf, "get_board_adapter", lambda cfg=None: adapter)

    # 尝试派单 T9902 应当被前置依赖门禁拦截
    with pytest.raises(RuntimeError) as exc_info:
        dispatch_task(task_id="T9902", dry_run=True)
    assert "[REJECT 依赖未就绪]" in str(exc_info.value)


def test_dispatch_task_concurrency_gate_blocks_overload(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "user_data" / "tasks"
    tasks_dir.mkdir(parents=True)
    adapter = WeeklyBoardAdapter(tasks_dir=str(tasks_dir))

    # 李开发已有 3 个进行中任务
    for i in range(1, 4):
        adapter.create_record({
            "id": f"T991{i}",
            "name": f"在手任务-{i}",
            "status": "进行中",
            "assignee": "李开发",
            "week": "2026-W36"
        })

    # 第 4 个任务尝试派单
    adapter.create_record({
        "id": "T9914",
        "name": "超载任务",
        "status": "待开始",
        "assignee": "李开发",
        "pretask": "无",
        "week": "2026-W36"
    })

    import _lib.boards.board_adapter_factory as baf
    monkeypatch.setattr(baf, "get_board_adapter", lambda cfg=None: adapter)

    # 尝试派发第 4 个任务，应被并发门禁拦截
    with pytest.raises(RuntimeError) as exc_info:
        dispatch_task(task_id="T9914", max_parallel=3, dry_run=True)
    assert "[REJECT 并发超载]" in str(exc_info.value)
