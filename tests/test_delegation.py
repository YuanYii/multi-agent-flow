"""
修复 ② 回归测试:验证提权代行代码门控。

覆盖:
- validate_delegation_authority 白名单 (PM 收口 / 同级互代行禁止 / USER 最高)
- validate() 默认参数向后兼容 (旧测试不传 delegated_by 不破)
- transition_task.py 真实 CLI 调用,白名单拒绝→ exit(1),合法→ exit(0)
- audit_trail.log 事件包含 delegated_by / delegation_reason 字段
"""
import os
import json
import subprocess
import sys
import time
import pytest

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
CONFIG = os.path.join(PROJECT_ROOT, "config", "workflow.config.yaml")
if not os.path.exists(CONFIG):
    CONFIG = os.path.join(PROJECT_ROOT, "config", "workflow.config.template.yaml")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
AUDIT_LOG = os.path.join(LOGS_DIR, "audit_trail.log")

sys.path.insert(0, SCRIPTS_DIR)
from validate_transition import validate_delegation_authority, validate, DELEGATION_ALLOW_MATRIX  # noqa: E402


# ---------- 单元:白名单 ----------

def test_delegation_empty_means_no_delegation():
    """空 delegated_by 表示无代行声明,直接放行(交给 validate 权限矩阵)"""
    assert validate_delegation_authority("DEV", "") is True
    assert validate_delegation_authority("DEV", None) is True
    assert validate_delegation_authority("DEV", "   ") is True


def test_delegation_pm_accepts_any_role():
    """PM 是收口角色,任何角色代行 PM 应被接受"""
    for src in ["PM", "ARCHITECT", "DEV", "FRONTEND", "REVIEWER", "QA", "DOCS", "DEVOPS", "USER"]:
        assert validate_delegation_authority("PM", src) is True, f"PM 应接受 {src} 代行"


def test_delegation_pm_accepts_user():
    """USER 代行任何目标角色均应被接受"""
    for target in ["PM", "DEV", "REVIEWER", "QA", "DOCS", "DEVOPS", "ARCHITECT", "FRONTEND"]:
        assert validate_delegation_authority(target, "USER") is True, f"USER 代行 {target} 应被接受"


def test_delegation_dev_rejects_devoips():
    """执行类角色(DEV)不接受 DEVOPS 代行(防止跨职能隐式越权)"""
    assert validate_delegation_authority("DEV", "DEVOPS") is False
    assert validate_delegation_authority("QA", "DEVOPS") is False
    assert validate_delegation_authority("REVIEWER", "DEVOPS") is False


def test_delegation_dev_rejects_qa():
    """同级跨职能(DEV 代行 QA)应被拒绝"""
    assert validate_delegation_authority("QA", "DEV") is False
    assert validate_delegation_authority("REVIEWER", "DEV") is False


def test_delegation_case_insensitive():
    """代行来源大小写不敏感"""
    assert validate_delegation_authority("PM", "dev") is True
    assert validate_delegation_authority("PM", "USER") is True


def test_delegation_matrix_has_all_8_roles():
    """白名单必须覆盖全部 8 角色"""
    expected = {"PM", "ARCHITECT", "DEV", "FRONTEND", "REVIEWER", "QA", "DOCS", "DEVOPS"}
    actual = set(DELEGATION_ALLOW_MATRIX.keys())
    assert expected == actual, f"白名单角色集合应为 {expected}, 实际为 {actual}"


# ---------- 单元:validate 默认参数向后兼容 ----------

def test_validate_accepts_delegation_kwargs_without_break():
    """validate() 增加 delegated_by / delegation_reason kwargs,默认空不影响旧调用"""
    res = validate(
        role="PM", from_status="已完成", to_status="已验收",
        assignee="严经理", end_time="2026-08-13 12:00:00",
        active_dev_count=0, task_type="A", max_parallel=99,
    )
    assert res is True


def test_validate_passes_delegation_to_pass_log(capsys):
    """validate() 通过时,PASS 消息应附加代行声明后缀(便于审计日志读)"""
    validate(
        role="PM", from_status="已完成", to_status="已验收",
        assignee="严经理", end_time="2026-08-13 12:00:00",
        active_dev_count=0, task_type="A", max_parallel=99,
        delegated_by="DEV", delegation_reason="用户授权",
    )
    out = capsys.readouterr().out
    assert "代行声明" in out
    assert "DEV 代行 PM" in out


# ---------- 集成:CLI 真实子进程 ----------

def _run_cli(args, expect_exit_code=None):
    """运行 transition_task.py CLI,返回 (returncode, stdout, stderr)"""
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, "transition_task.py")] + args,
        capture_output=True, text=True, timeout=30,
    )
    if expect_exit_code is not None:
        assert proc.returncode == expect_exit_code, (
            f"CLI exit={proc.returncode}, 期望 {expect_exit_code}\n"
            f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )
    return proc


def test_cli_legal_delegation_passes_dry_run():
    """合法代行(DEV 代行 PM 验收)DRY-RUN 应通过"""
    proc = _run_cli([
        "--config", CONFIG,
        "--role", "PM", "--from-status", "已完成", "--to-status", "已验收",
        "--assignee", "严经理", "--task-id", "T0099", "--type", "A",
        "--end-time", "2026-08-13 23:50:00",
        "--delegated-by", "DEV", "--delegation-reason", "用户授权",
        "--dry-run",
    ], expect_exit_code=0)
    assert "代行声明" in proc.stdout


def test_cli_illegal_delegation_rejected():
    """非法代行(DEV 代行 QA)DRY-RUN 应被硬拦截,exit=1"""
    proc = _run_cli([
        "--config", CONFIG,
        "--role", "QA", "--from-status", "测试中", "--to-status", "已完成",
        "--assignee", "章测试", "--task-id", "T0097", "--type", "A",
        "--end-time", "2026-08-13 23:50:00",
        "--delegated-by", "DEV", "--delegation-reason", "test",
        "--dry-run",
    ], expect_exit_code=1)
    combined = proc.stdout + proc.stderr
    assert "代行未授权" in combined


def test_cli_user_delegation_highest_priority():
    """USER 代行(最高优先级)即使在严格白名单内也应通过"""
    proc = _run_cli([
        "--config", CONFIG,
        "--role", "DEVOPS", "--from-status", "进行中", "--to-status", "已完成",
        "--assignee", "吕改特", "--task-id", "T0096", "--type", "A",
        "--end-time", "2026-08-13 23:50:00",
        "--delegated-by", "USER", "--delegation-reason", "用户授权",
        "--dry-run",
    ], expect_exit_code=0)


# ---------- 集成:audit_trail.log 落盘 ----------

def _read_last_audit_event():
    """读取 audit_trail.log 最后一行 JSON 事件"""
    if not os.path.exists(AUDIT_LOG):
        return None
    with open(AUDIT_LOG, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.readlines() if ln.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def test_audit_log_contains_delegation_fields():
    """audit 事件应包含 delegated_by / delegation_reason 字段(新增字段)"""
    # 触发一次合法代行
    _run_cli([
        "--config", CONFIG,
        "--role", "PM", "--from-status", "已完成", "--to-status", "已验收",
        "--assignee", "严经理", "--task-id", "T0099", "--type", "A",
        "--end-time", "2026-08-13 23:50:00",
        "--delegated-by", "DOCS", "--delegation-reason", "回归测试",
        "--dry-run",
    ])
    ev = _read_last_audit_event()
    assert ev is not None, "audit_trail.log 末条事件缺失"
    assert "delegated_by" in ev, "audit 事件未包含 delegated_by 字段"
    assert "delegation_reason" in ev, "audit 事件未包含 delegation_reason 字段"
    assert ev.get("delegated_by") == "DOCS"
    assert ev.get("delegation_reason") == "回归测试"
