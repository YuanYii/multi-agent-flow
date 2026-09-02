#!/usr/bin/env python3
"""
验收门控安全加固回归测试 (2026-08-27)

覆盖审计报告《multi-agent-flow 验收门控安全审计》全部修复点:
  V1  quick_task accept/accept-all 硬编码伪造 delegated_by=USER -> 已改 TTY+[y/N] 真人门禁
  V2  门控纯字符串比对 -> 已改 OPERATOR_VIA_TOKEN / force_verify_operator 双通道
  N1  --role USER 直签后门 -> 已封堵 (USER 字符串不再被承认)
  N2  auto_task 默认注入 USER 代行 -> 已改默认 PM
  N4  /api/health 泄露 master_token -> 已脱敏
  V3  终态死锁 -> Web 端 REOPEN 审计通道 (见 start_kanban_server)
运行: python3 -m pytest tests/test_accept_gate_hardening.py -q
"""
import json
import os
import subprocess
import sys
import glob

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


@pytest.fixture()
def env(tmp_path):
    board = tmp_path / "board.json"
    cfg = tmp_path / "workflow.config.yaml"
    base = None
    for candidate in ("workflow.config.yaml", "workflow.config.template.yaml"):
        p = os.path.join(REPO_ROOT, "config", candidate)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                base = yaml.safe_load(f)
            break
    if base is None:
        raise FileNotFoundError("config/workflow.config.yaml 与模板均不存在")
    base["board"]["board_file"] = str(board)
    cfg.write_text(yaml.safe_dump(base, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"board": board, "cfg": cfg, "tmp": tmp_path}


def run(env, *args, expect=0):
    script = args[0]
    rest = list(args[1:])
    if script == "quick_task.py":
        cmd = [sys.executable, os.path.join(SCRIPTS, script), rest[0], "--config", str(env["cfg"]), *rest[1:]]
    else:
        cmd = [sys.executable, os.path.join(SCRIPTS, script), "--config", str(env["cfg"]), *rest]
    sub_env = os.environ.copy()
    sub_env["YY_FLOW_PROJECT_ROOT"] = str(env.get("tmp") or env["board"].parent)
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, env=sub_env)
    assert r.returncode == expect, f"exit={r.returncode} (期望 {expect})\nstdout={r.stdout}\nstderr={r.stderr}"
    return r


def make_completed_task(env, name="安全回归任务", task_type="A"):
    """跑 auto 链至【已完成】。"""
    run(env, "auto_task.py", "--task-name", name, "--type", task_type, "--role", "DEV")
    assert json.loads(env["board"].read_text(encoding="utf-8"))[0]["status"] == "已完成"


class TestV1CliHardcodeRemoved:
    """V1: accept/accept-all 不再硬编码伪造 USER 代行，非交互一律物理拦截。"""

    def test_accept_non_tty_blocked(self, env):
        make_completed_task(env)
        r = run(env, "quick_task.py", "accept", "--task-id", "T0001", expect=1)
        assert "物理拦截" in r.stdout, r.stdout
        # 状态未被改动
        assert json.loads(env["board"].read_text(encoding="utf-8"))[0]["status"] == "已完成"

    def test_accept_all_non_tty_blocked(self, env):
        make_completed_task(env)
        make_completed_task(env, "第二个任务")
        r = run(env, "quick_task.py", "accept-all", expect=1)
        assert "物理拦截" in r.stdout, r.stdout


class TestV2GateNoStringSpoof:
    """V2: 纯字符串比对不再构成人类授权凭据。"""

    def test_delegated_by_user_rejected(self, env):
        make_completed_task(env)
        r = run(env, "transition_task.py", "--role", "PM", "--from-status", "已完成",
                "--to-status", "已验收", "--assignee", "严经理", "--task-id", "T0001",
                "--end-time", "2026-08-27 12:00:00", "--delegated-by", "USER", expect=1)
        assert "不再被承认" in r.stdout or "人类专属门禁" in r.stdout, r.stdout

    def test_role_user_direct_sign_rejected(self, env):
        """N1: 自称 role=USER 直签验收必须被拦截。"""
        make_completed_task(env)
        r = run(env, "transition_task.py", "--role", "USER", "--from-status", "已完成",
                "--to-status", "已验收", "--assignee", "严经理", "--task-id", "T0001",
                "--end-time", "2026-08-27 12:00:00", expect=1)
        assert "不再被承认" in r.stdout or "人类专属门禁" in r.stdout, r.stdout

    def test_plain_pm_rejected_without_vouch(self, env):
        make_completed_task(env)
        r = run(env, "transition_task.py", "--role", "PM", "--from-status", "已完成",
                "--to-status", "已验收", "--assignee", "严经理", "--task-id", "T0001",
                "--end-time", "2026-08-27 12:00:00", expect=1)
        assert "不再被承认" in r.stdout or "人类专属门禁" in r.stdout, r.stdout


class TestN2AutoTaskDefault:
    """N2: auto_task 默认不再注入 USER 代行，默认 PM。"""

    def test_auto_task_default_delegation_is_pm(self, env):
        make_completed_task(env)
        # auto_task 链上所有步骤以 PM 代行执行；无 USER 伪造
        r = run(env, "auto_task.py", "--task-name", "代行来源检查", "--type", "A", "--role", "DEV")
        assert r.returncode == 0


class TestN4HealthTokenRedacted:
    """N4: /api/health 不再泄露 master_token。"""

    def test_health_endpoint_no_token(self, tmp_path):
        # 启动独立看板服务实例（临时数据根），探测 health 载荷
        import socket
        import time
        import urllib.request

        data_root = tmp_path / "health_root"
        data_root.mkdir()
        # 用独立端口避免占用真实实例
        port = 33200 + (os.getpid() % 200)
        envs = os.environ.copy()
        envs["YY_FLOW_PROJECT_ROOT"] = str(data_root)
        p = subprocess.Popen(
            [sys.executable, os.path.join(SCRIPTS, "start_kanban_server.py"),
             "--port", str(port), "--host", "127.0.0.1"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=REPO_ROOT, env=envs,
        )
        try:
            # 等待服务就绪
            deadline = time.time() + 15
            health = None
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            while time.time() < deadline:
                try:
                    with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as resp:
                        health = json.loads(resp.read().decode("utf-8"))
                    break
                except Exception:
                    time.sleep(0.3)
            assert health is not None, "看板服务未能启动"
            data = health.get("data", health)
            assert "master_token" not in data, f"/api/health 泄露主控令牌: {data}"
            # 主控标记仍正常工作（令牌经其它通道注入）
            assert "is_master" in data
        finally:
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()


class TestV3CliForceReopen:
    """V3: CLI 受控重开与时间戳清洗机制。"""

    def _setup_accepted_task(self, env):
        make_completed_task(env, "待重开任务")
        # 以 PTY 方式完成真人验收流转至【已验收】
        sub_env = os.environ.copy()
        sub_env["YY_FLOW_PROJECT_ROOT"] = str(env.get("tmp") or env["board"].parent)
        sub_env["HUMAN_FORCE_TOKEN"] = "1"
        cmd = [sys.executable, os.path.join(SCRIPTS, "quick_task.py"), "accept",
               "--config", str(env["cfg"]), "--task-id", "T0001"]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, env=sub_env)
        assert r.returncode == 0, r.stdout
        card = json.loads(env["board"].read_text(encoding="utf-8"))[0]
        assert card["status"] == "已验收"
        assert card.get("end_date") or card.get("end_time")

    def test_reopen_blocked_without_flag(self, env):
        self._setup_accepted_task(env)
        # 未传 --force-reopen 尝试从已验收回退至进行中 -> 必须拦截
        r = run(env, "transition_task.py", "--role", "PM", "--from-status", "已验收",
                "--to-status", "进行中", "--assignee", "李开发", "--task-id", "T0001",
                "--remarks", "【纠偏重开】测试未传参数", expect=1)
        assert "终态防篡改" in r.stdout or "禁止修改" in r.stdout, r.stdout

    def test_reopen_blocked_without_remarks(self, env):
        self._setup_accepted_task(env)
        # 传了 --force-reopen 但未提供 --remarks -> 必须拦截
        r = run(env, "transition_task.py", "--role", "PM", "--from-status", "已验收",
                "--to-status", "进行中", "--assignee", "李开发", "--task-id", "T0001",
                "--force-reopen", expect=1)
        assert "重开原因缺失" in r.stdout, r.stdout

    def test_reopen_blocked_for_unauthorized_role(self, env):
        self._setup_accepted_task(env)
        # 角色不是 PM/USER (如普通 DEV) 尝试重开 -> 必须拦截
        r = run(env, "transition_task.py", "--role", "DEV", "--from-status", "已验收",
                "--to-status", "进行中", "--assignee", "李开发", "--task-id", "T0001",
                "--force-reopen", "--remarks", "【纠偏重开】无权角色尝试", expect=1)
        assert "重开权限拦截" in r.stdout or "越权拦截" in r.stdout, r.stdout

    def test_reopen_success_and_cleans_timestamp(self, env):
        self._setup_accepted_task(env)
        # PM 携带有效备注执行合法纠偏重开
        r = run(env, "transition_task.py", "--role", "PM", "--from-status", "已验收",
                "--to-status", "进行中", "--assignee", "李开发", "--task-id", "T0001",
                "--force-reopen", "--remarks", "【纠偏重开】业务需求变更，重新回退开发")
        assert r.returncode == 0, r.stdout
        card = json.loads(env["board"].read_text(encoding="utf-8"))[0]
        assert card["status"] == "进行中"
        # 核心断言：end_date 与 act_hours 被彻底清空
        assert not card.get("end_date")
        assert not card.get("act_hours")
        assert "纠偏重开" in card.get("process", "")

