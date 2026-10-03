"""CLI 退出契约、阶段准入和显式契约文件的失败路径回归。"""
import datetime
import json
import os
import runpy
import shlex
import subprocess
import sys
from unittest.mock import Mock

import pytest

import dispatch_task as dispatch_cli
import quick_task
import transition_task
from _lib.ccp.validators import pipeline as ccp_pipeline
from _lib.core.validate_transition import validate
from _lib.gates import stage_gate_checker
from _lib.gates.stage_gate_checker import CheckResult, StageGateReport


@pytest.fixture
def dispatch_env(monkeypatch, tmp_path):
    adapter = Mock()
    adapter.list_records.return_value = []
    monkeypatch.setattr(dispatch_cli.board_adapter_factory, "get_board_adapter", lambda cfg=None: adapter)
    monkeypatch.setattr(ccp_pipeline, "validate_pre_dispatch", lambda task, root: (True, []))
    monkeypatch.setattr(dispatch_cli.paths, "project_root", lambda: str(tmp_path))
    monkeypatch.setattr(dispatch_cli, "find_related_docs", lambda task, root: [])
    dispatch_transition = Mock(return_value=True)
    monkeypatch.setattr(dispatch_cli, "transition_task_pipeline", dispatch_transition)

    def dispatch(role, task_type="A", status="进行中", **kwargs):
        card = {
            "id": "T9901", "name": "验证退出契约", "status": status,
            "assignee": role, "type": task_type, "pretask": "无",
        }
        card.update(kwargs.pop("fields", {}))
        adapter.get_record.return_value = {"fields": card}
        return dispatch_cli.dispatch_task("T9901", target_role=role, **kwargs)

    return dispatch, adapter, dispatch_transition


def parse_exit_cli(command):
    """解析当前平台生成的命令，Windows 保留未引用路径中的反斜杠。"""
    if os.name != "nt":
        return shlex.split(command)
    if " -c " in command:
        executable, code = command.split(" -c ", 1)
        executable = executable.removeprefix("& ").strip("'").replace("''", "'")
        return [executable, "-c", code[1:-1].replace("''", "'")]
    args = shlex.split(command, posix=False)
    if args[0] == "&":
        args = args[1:]
    return [arg[1:-1].replace("''", "'") if arg.startswith("'") and arg.endswith("'") else arg for arg in args]


def execute_exit_cli(command, monkeypatch):
    """执行生成命令的 Python 参数入口，拦截真实看板写入。"""
    args = parse_exit_cli(command)
    pipeline = Mock(return_value=True)
    monkeypatch.setattr(transition_task, "transition_task_pipeline", pipeline)
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    if args[1] == "-c":
        monkeypatch.setattr(runpy, "run_path", lambda path, run_name: transition_task.main())
        exec(args[2], {})
    else:
        monkeypatch.setattr(sys, "argv", args[1:])
        transition_task.main()
    return pipeline.call_args.kwargs


@pytest.mark.parametrize("role,task_type,status,expected_from,expected_to,expected_assignee", [
    ("DEV", "A", "待开始", "进行中", "审查中", "周审查"),
    ("FRONTEND", "A", "进行中", "进行中", "审查中", "周审查"),
    ("ARCHITECT", "A", "进行中", "进行中", "审查中", "周审查"),
    ("REVIEWER", "A", "审查中", "审查中", "测试中", "章测试"),
    ("QA", "A", "测试中", "测试中", "已完成", "严经理"),
    ("DEV", "B", "待开始", "进行中", "已完成", "严经理"),
    ("DEV", "C", "进行中", "进行中", "已完成", "严经理"),
    ("DEV", "D", "进行中", "进行中", "已完成", "严经理"),
    ("FRONTEND", "F", "进行中", "进行中", "已完成", "严经理"),
    ("DEV", "G", "进行中", "进行中", "已完成", "严经理"),
    ("ARCHITECT", "B", "进行中", "进行中", "已完成", "严经理"),
    ("REVIEWER", "B", "待开始", "进行中", "已完成", "严经理"),
    ("QA", "B", "待开始", "进行中", "已完成", "严经理"),
    ("DOCS", "C", "进行中", "进行中", "已完成", "严经理"),
    ("DEVOPS", "D", "进行中", "进行中", "已完成", "严经理"),
    ("PM", "F", "进行中", "进行中", "已完成", "严经理"),
])
def test_dispatch_exit_cli_passes_parser_and_existing_permissions(
    dispatch_env, monkeypatch, tmp_path, role, task_type, status,
    expected_from, expected_to, expected_assignee,
):
    dispatch, _, _ = dispatch_env
    config_path = str(tmp_path / "含空格 config.yaml")
    result = dispatch(role, task_type, status, config_path=config_path, dry_run=True)
    contract = result["payload"]["exit_contract"]
    arguments = execute_exit_cli(contract["required_cli"], monkeypatch)
    assert contract["target_status"] == expected_to
    assert arguments["from_status"] == expected_from
    assert arguments["to_status"] == expected_to
    assert arguments["assignee"] == expected_assignee
    assert arguments["current_role"] == role
    assert arguments["task_type"] == task_type
    assert arguments["config_path"] == config_path
    assert arguments["token"] == contract["dispatch_token"]
    assert validate(
        role=arguments["current_role"], from_status=arguments["from_status"],
        to_status=arguments["to_status"], assignee=arguments["assignee"],
        end_time=arguments["end_time"], active_dev_count=1,
        task_type=arguments["task_type"], remarks=arguments["remarks"],
    )
    if expected_to == "已完成":
        datetime.datetime.strptime(arguments["end_time"], "%Y-%m-%d %H:%M:%S")
    else:
        assert arguments["end_time"] is None


def test_terminal_exit_cli_uses_execution_time(dispatch_env, monkeypatch):
    dispatch, _, _ = dispatch_env
    result = dispatch("DEV", "B", dry_run=True)
    execution_time = datetime.datetime(2030, 2, 3, 4, 5, 6)

    class ExecutionDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return execution_time

    monkeypatch.setattr(datetime, "datetime", ExecutionDatetime)
    arguments = execute_exit_cli(result["payload"]["exit_contract"]["required_cli"], monkeypatch)
    assert arguments["end_time"] == "2030-02-03 04:05:06"


@pytest.mark.parametrize("task_type", ["A", "B"])
def test_exit_cli_runs_from_unrelated_working_directory(dispatch_env, tmp_path, task_type):
    dispatch, _, _ = dispatch_env
    result = dispatch("DEV", task_type, dry_run=True)
    args = parse_exit_cli(result["payload"]["exit_contract"]["required_cli"])
    assert args[0] == sys.executable
    # 真实启动生成的 Python 入口；--help 使 CLI 在任何看板写入前退出。
    if args[1] == "-c":
        args[2] = args[2].replace("runpy.run_path(", "sys.argv.append('--help'); runpy.run_path(")
    else:
        assert args[1] == transition_task.__file__
        args.append("--help")
    completed = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert completed.returncode == 0, completed.stderr
    assert "--assignee" in completed.stdout
    assert "--contract-file" in completed.stdout


def test_dispatch_json_output_remains_parseable(dispatch_env, monkeypatch, capsys):
    dispatch, _, _ = dispatch_env
    result = dispatch("DEV", dry_run=True)
    monkeypatch.setattr(dispatch_cli, "dispatch_task", lambda **kwargs: result)
    monkeypatch.setattr(sys, "argv", ["dispatch_task.py", "--task-id", "T9901", "--dry-run"])
    dispatch_cli.main()
    assert json.loads(capsys.readouterr().out)["task_id"] == "T9901"


@pytest.mark.parametrize("task_type", ["A", "B"])
def test_exit_cli_quotes_config_path_for_current_shell(dispatch_env, tmp_path, task_type):
    dispatch, _, _ = dispatch_env
    config_path = str(tmp_path / "配置 'quoted' $literal; name.yaml")
    result = dispatch("DEV", task_type, config_path=config_path, dry_run=True)
    command = result["payload"]["exit_contract"]["required_cli"]
    if task_type == "B":
        args = parse_exit_cli(command)
        args[2] = args[2].replace("runpy.run_path(", "sys.argv.append('--help'); runpy.run_path(")
        command = dispatch_cli._shell_join(args)
    else:
        command += " --help"
    shell_args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command] if os.name == "nt" else ["/bin/sh", "-c", command]
    completed = subprocess.run(shell_args, cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert completed.returncode == 0, completed.stderr
    assert "--assignee" in completed.stdout


def test_dispatch_preserves_stored_type_and_normalizes_chinese_role(dispatch_env, monkeypatch):
    dispatch, _, initial_transition = dispatch_env
    result = dispatch("李开发", "A", "待开始", fields={"task_type": "b"})
    assert initial_transition.call_args.kwargs["task_type"] == "B"
    arguments = execute_exit_cli(result["payload"]["exit_contract"]["required_cli"], monkeypatch)
    assert arguments["task_type"] == "B"
    assert arguments["current_role"] == "DEV"
    assert arguments["to_status"] == "已完成"


def test_dispatch_defaults_to_current_handler_instead_of_owner(dispatch_env):
    _, adapter, initial_transition = dispatch_env
    adapter.get_record.return_value = {"fields": {
        "id": "T9901", "name": "阶段审查", "status": "审查中", "type": "A",
        "assignee": "李开发", "handler": "周审查", "pretask": "无",
    }}
    result = dispatch_cli.dispatch_task("T9901", dry_run=True)
    assert result["role"] == "REVIEWER"
    assert result["payload"]["exit_contract"]["target_status"] == "测试中"
    initial_transition.assert_not_called()


@pytest.mark.parametrize("role,task_type,status", [
    ("REVIEWER", "A", "待开始"),
    ("REVIEWER", "A", "进行中"),
    ("QA", "A", "待开始"),
    ("QA", "A", "进行中"),
    ("DEV", "E", "待开始"),
    ("DEV", "未知", "待开始"),
])
def test_dispatch_rejects_unusable_exit_before_mutation(dispatch_env, role, task_type, status):
    dispatch, adapter, initial_transition = dispatch_env
    with pytest.raises(RuntimeError, match="退出契约非法"):
        dispatch(role, task_type, status)
    initial_transition.assert_not_called()
    adapter.update_record.assert_not_called()


def test_quick_create_rejects_failed_stage_report(monkeypatch, capsys):
    report = StageGateReport("Sprint 2", False, 2, 1, 1, [
        CheckResult("OK", "已满足项", True, "不应显示的成功详情"),
        CheckResult("FAIL", "前序阶段完结性", False, "T0001 尚未验收"),
    ], action="start")
    monkeypatch.setattr(stage_gate_checker, "run_stage_gate_check", lambda **kwargs: report)
    pipeline = Mock(return_value=True)
    monkeypatch.setattr(quick_task, "transition_task_pipeline", pipeline)
    monkeypatch.setattr(sys, "argv", ["quick_task.py", "create", "--name", "阶段任务", "--role", "PM", "--stage", "Sprint 2"])
    with pytest.raises(SystemExit) as exc:
        quick_task.main()
    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "阶段准入拦截" in output
    assert "前序阶段完结性: T0001 尚未验收" in output
    assert "不应显示的成功详情" not in output
    pipeline.assert_not_called()


def test_quick_create_rejects_stage_checker_exception(monkeypatch, capsys):
    def broken_checker(**kwargs):
        raise RuntimeError("无法读取阶段数据")

    monkeypatch.setattr(stage_gate_checker, "run_stage_gate_check", broken_checker)
    pipeline = Mock(return_value=True)
    monkeypatch.setattr(quick_task, "transition_task_pipeline", pipeline)
    monkeypatch.setattr(sys, "argv", ["quick_task.py", "create", "--name", "阶段任务", "--role", "PM", "--stage", "Sprint 2"])
    with pytest.raises(SystemExit) as exc:
        quick_task.main()
    assert exc.value.code == 1
    assert "无法读取阶段数据" in capsys.readouterr().out
    pipeline.assert_not_called()


@pytest.mark.parametrize("force", [False, True])
def test_quick_create_preserves_success_and_explicit_force(monkeypatch, force):
    checker = Mock(return_value=StageGateReport("Sprint 2", True, 0, 0, 0, action="start"))
    monkeypatch.setattr(stage_gate_checker, "run_stage_gate_check", checker)
    pipeline = Mock(return_value=True)
    monkeypatch.setattr(quick_task, "transition_task_pipeline", pipeline)
    argv = ["quick_task.py", "create", "--name", "阶段任务", "--role", "PM", "--stage", "Sprint 2"]
    if force:
        argv.append("--force")
    monkeypatch.setattr(sys, "argv", argv)
    quick_task.main()
    pipeline.assert_called_once()
    if force:
        checker.assert_not_called()
    else:
        checker.assert_called_once_with(stage_name="Sprint 2", action="start")


def test_transition_loads_explicit_contract_file(monkeypatch, tmp_path):
    path = tmp_path / "契约.yaml"
    path.write_text(
        "contract:\n  preconditions: [输入已就绪]\nreturn_contract:\n  required_items: [测试凭据]\n"
        "tier: Tier-2\ntarget: 交付解析器\nacceptance_criteria: [支持中文]\n",
        encoding="utf-8",
    )
    pipeline = Mock(return_value=True)
    monkeypatch.setattr(transition_task, "transition_task_pipeline", pipeline)
    monkeypatch.setattr(sys, "argv", ["transition_task.py", "--create", "--role", "PM", "--assignee", "DEV", "--contract-file", str(path)])
    transition_task.main()
    arguments = pipeline.call_args.kwargs
    assert arguments["contract"] == {"preconditions": ["输入已就绪"]}
    assert arguments["return_contract"] == {"required_items": ["测试凭据"]}
    assert arguments["tier"] == "Tier-2"
    assert arguments["target"] == "交付解析器"
    assert arguments["criteria"] == ["支持中文"]


@pytest.mark.parametrize("contents", [None, "", "contract: [", "- 不合法的列表根节点"])
def test_transition_rejects_unreadable_contract_without_pipeline(monkeypatch, tmp_path, caplog, contents):
    path = tmp_path / "无效契约.yaml"
    if contents is not None:
        path.write_text(contents, encoding="utf-8")
    pipeline = Mock(return_value=True)
    monkeypatch.setattr(transition_task, "transition_task_pipeline", pipeline)
    monkeypatch.setattr(sys, "argv", ["transition_task.py", "--create", "--role", "PM", "--assignee", "DEV", "--contract-file", str(path)])
    with pytest.raises(SystemExit) as exc:
        transition_task.main()
    assert exc.value.code == 1
    assert "契约加载失败" in caplog.text
    pipeline.assert_not_called()
