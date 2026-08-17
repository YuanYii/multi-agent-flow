#!/usr/bin/env python3
"""
multi-agent-flow 工作流 v2 功能测试套件（阶段 6）
覆盖：建卡 / 领取流转 / 重复任务校验 / auto 全类型链 / 任意节点续跑 / 阻断前置验证 /
挂起态恢复 / 幂等并发 / quick 命令 / 协议层。合计 41 个用例（含参数化）。
运行：python3 -m pytest tests/test_workflow_v2.py -q
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


@pytest.fixture()
def env(tmp_path):
    """每用例独立临时看板 + 配置。"""
    board = tmp_path / "board.json"
    cfg = tmp_path / "workflow.config.yaml"
    with open(os.path.join(REPO_ROOT, "config", "workflow.config.yaml"), encoding="utf-8") as f:
        base = yaml.safe_load(f)
    base["board"]["board_file"] = str(board)
    cfg.write_text(yaml.safe_dump(base, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"board": board, "cfg": cfg, "tmp": tmp_path}


def run(env, *args, expect=0):
    """运行 scripts 下脚本，断言退出码。返回 CompletedProcess。
    quick_task 子命令先行，--config 置于子命令之后；其余脚本 --config 紧跟脚本名。"""
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


def cards(env):
    if not env["board"].exists():
        return []
    d = json.loads(env["board"].read_text(encoding="utf-8"))
    return d if isinstance(d, list) else d.get("cards", [])


def find(env, tid):
    for c in cards(env):
        if c.get("id") == tid:
            return c
    return None


def status_of(env, tid):
    c = find(env, tid)
    return c.get("status") if c else None


def set_status_direct(env, tid, status, name="直接落库任务", assignee="李开发"):
    """绕过 CLI 直接写看板（测试挂起态/终态场景）。"""
    data = cards(env)
    if not any(c.get("id") == tid for c in data):
        data.append({"id": tid, "name": name, "status": status, "assignee": assignee, "seq": len(data) + 1})
    else:
        for c in data:
            if c.get("id") == tid:
                c["status"] = status
    env["board"].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# =====================================================================
# 组 1 · 建卡（--create）6 用例
# =====================================================================
class TestCreate:
    def test_pm_create_card(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "登录接口",
            "--assignee", "李开发")
        assert status_of(env, "T0001") == "待开始"
        assert find(env, "T0001")["assignee"] == "李开发"
        assert not find(env, "T0001").get("start_date")

    def test_role_self_create(self, env):
        run(env, "transition_task.py", "--role", "DEV", "--create", "--task-name", "数据库设计",
            "--assignee", "李开发")
        assert status_of(env, "T0001") == "待开始"

    def test_role_cannot_delegate(self, env):
        run(env, "transition_task.py", "--role", "DEV", "--create", "--task-name", "越权派发",
            "--assignee", "吕改特", expect=1)

    def test_create_missing_name(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--assignee", "李开发", expect=1)

    def test_create_dup_task_id(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-id", "T0100",
            "--task-name", "A", "--assignee", "李开发")
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-id", "T0100",
            "--task-name", "B", "--assignee", "李开发", expect=1)

    def test_create_explicit_id(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-id", "T0100",
            "--task-name", "显式编号", "--assignee", "李开发")
        assert status_of(env, "T0100") == "待开始"


# =====================================================================
# 组 2 · 领取与流转 4 用例
# =====================================================================
class TestClaim:
    def test_claim_to_in_progress(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "任务X",
            "--assignee", "李开发")
        run(env, "transition_task.py", "--role", "DEV", "--from-status", "待开始", "--to-status",
            "进行中", "--assignee", "李开发", "--task-id", "T0001")
        assert status_of(env, "T0001") == "进行中"
        assert find(env, "T0001").get("start_date")

    def test_autocreate_fallback(self, env):
        run(env, "transition_task.py", "--role", "DEV", "--from-status", "待开始", "--to-status",
            "进行中", "--assignee", "李开发", "--task-name", "兜底任务")
        assert status_of(env, "T0001") == "进行中"  # 先建待开始再流转

    def test_e_class_direct_accept(self, env):
        run(env, "transition_task.py", "--role", "PM", "--from-status", "待开始", "--to-status",
            "已验收", "--assignee", "严经理", "--task-name", "审批事项", "--type", "E")
        assert status_of(env, "T0001") == "已验收"

    def test_blocked_requires_remark(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "任务B",
            "--assignee", "李开发")
        run(env, "transition_task.py", "--role", "DEV", "--from-status", "待开始", "--to-status",
            "进行中", "--assignee", "李开发", "--task-id", "T0001")
        run(env, "transition_task.py", "--role", "DEV", "--from-status", "进行中", "--to-status",
            "已阻塞", "--assignee", "李开发", "--task-id", "T0001", expect=1)  # 无阻断原因


# =====================================================================
# 组 3 · 重复任务校验 8 用例
# =====================================================================
class TestDuplicate:
    def test_l1_exact(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "用户登录接口",
            "--assignee", "李开发")
        r = run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "用户登录接口",
                "--assignee", "李开发", expect=1)
        assert "DUPLICATE_TASK" in r.stdout and "完全一致" in r.stdout

    def test_l2_contains(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "用户登录接口",
            "--assignee", "李开发")
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name",
            "用户登录接口与JWT鉴权", "--assignee", "李开发", expect=1)

    def test_l3_similarity(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name",
            "用户登录接口与JWT鉴权", "--assignee", "李开发")
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name",
            "用户登录接口和 JWT 鉴权", "--assignee", "李开发", expect=1)

    def test_force_creates(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "用户登录接口",
            "--assignee", "李开发")
        run(env, "transition_task.py", "--role", "PM", "--create", "--force", "--task-name",
            "用户登录接口", "--assignee", "李开发")
        assert len(cards(env)) == 2

    def test_limit_config(self, env):
        for i, n in enumerate(["任务甲", "任务乙", "任务丙"]):
            run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", n,
                "--assignee", "李开发")
        env["cfg"].write_text(env["cfg"].read_text(encoding="utf-8").replace(
            "limit: 10", "limit: 2"), encoding="utf-8")
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "任务甲",
            "--assignee", "李开发")  # 第 1 条（任务甲）超出 limit=2 范围 → 不拦截
        assert len(cards(env)) == 4

    def test_disabled(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "任务D",
            "--assignee", "李开发")
        env["cfg"].write_text(env["cfg"].read_text(encoding="utf-8").replace(
            "enabled: true", "enabled: false"), encoding="utf-8")
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "任务D",
            "--assignee", "李开发")

    def test_no_dup_check_flag(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "任务E",
            "--assignee", "李开发")
        run(env, "transition_task.py", "--role", "PM", "--create", "--no-dup-check", "--task-name",
            "任务E", "--assignee", "李开发")

    def test_fallback_dup_blocked(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "任务F",
            "--assignee", "李开发")
        run(env, "transition_task.py", "--role", "DEV", "--from-status", "待开始", "--to-status",
            "进行中", "--assignee", "李开发", "--task-name", "任务F", expect=1)  # 兜底自动建单重复


# =====================================================================
# 组 4 · auto 全类型链 5 用例
# =====================================================================
class TestAutoChains:
    def test_a_full_chain(self, env):
        run(env, "auto_task.py", "--task-name", "自动开发任务", "--role", "DEV", "--type", "A")
        assert status_of(env, "T0001") == "已验收"

    def test_b_short_chain(self, env):
        run(env, "auto_task.py", "--task-name", "自动架构选型", "--role", "ARCHITECT", "--type", "B")
        assert status_of(env, "T0001") == "已验收"

    def test_f_chain(self, env):
        run(env, "auto_task.py", "--task-name", "阶段总结", "--role", "PM", "--type", "F")
        assert status_of(env, "T0001") == "已验收"

    def test_e_chain(self, env):
        run(env, "auto_task.py", "--task-name", "自执行事项", "--role", "PM", "--type", "E")
        assert status_of(env, "T0001") == "已验收"

    def test_simulate_no_write(self, env):
        run(env, "auto_task.py", "--task-name", "模拟任务", "--simulate")
        assert cards(env) == []


# =====================================================================
# 组 5 · 任意节点续跑 5 用例
# =====================================================================
class TestAutoResume:
    @pytest.mark.parametrize("pre", ["进行中", "审查中", "测试中", "已完成"])
    def test_resume_from_state(self, env, pre):
        run(env, "auto_task.py", "--task-name", "续跑任务", "--role", "DEV", "--type", "A")
        # 直接改回目标前置状态（模拟已推进到中途）
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-id", "T0100",
            "--task-name", "独立续跑任务", "--assignee", "李开发", "--no-dup-check")
        tid = "T0100"
        set_status_direct(env, tid, pre)
        run(env, "auto_task.py", "--task-id", tid, "--type", "A")
        assert status_of(env, tid) == "已验收"

    def test_idempotent_accepted(self, env):
        run(env, "auto_task.py", "--task-name", "幂等任务", "--role", "DEV", "--type", "A")
        run(env, "auto_task.py", "--task-id", "T0001", "--type", "A")
        assert status_of(env, "T0001") == "已验收"


# =====================================================================
# 组 6 · 阻断前置验证 5 用例
# =====================================================================
class TestBlocked:
    def _make_blocked(self, env, tid, remark):
        data = cards(env)
        for c in data:
            if c.get("id") == tid:
                c["status"] = "已阻塞"
                c["remarks"] = remark
        env["board"].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_unresolved_stop(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-id", "T0100",
            "--task-name", "阻断任务", "--assignee", "李开发")
        self._make_blocked(env, "T0100", "【阻断】等待SDK")
        r = run(env, "auto_task.py", "--task-id", "T0100", "--type", "A", expect=1)
        assert "阻断未解除" in r.stdout
        assert status_of(env, "T0100") == "已阻塞"  # 零变更

    def test_resolved_resume(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-id", "T0100",
            "--task-name", "阻断恢复任务", "--assignee", "李开发")
        self._make_blocked(env, "T0100", "【阻断】等待SDK\n【解除】SDK已就绪")
        run(env, "auto_task.py", "--task-id", "T0100", "--type", "A")
        assert status_of(env, "T0100") == "已验收"

    def test_clear_before_block_invalid(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-id", "T0100",
            "--task-name", "时序任务", "--assignee", "李开发")
        self._make_blocked(env, "T0100", "【解除】先行解除\n【阻断】之后阻塞")
        run(env, "auto_task.py", "--task-id", "T0100", "--type", "A", expect=1)

    def test_cancelled_reject(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-id", "T0100",
            "--task-name", "取消任务", "--assignee", "李开发")
        set_status_direct(env, "T0100", "已取消")
        run(env, "auto_task.py", "--task-id", "T0100", "--type", "A", expect=1)

    def test_rejected_resume(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-id", "T0100",
            "--task-name", "退回任务", "--assignee", "李开发")
        set_status_direct(env, "T0100", "已退回")
        run(env, "auto_task.py", "--task-id", "T0100", "--type", "A")
        assert status_of(env, "T0100") == "已验收"


# =====================================================================
# 组 7 · 门控/quick/并发 5 用例
# =====================================================================
class TestGateAndQuick:
    def test_gate_violation_stop(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-id", "T0100",
            "--task-name", "越权任务", "--assignee", "李开发")
        set_status_direct(env, "T0100", "进行中")
        r = run(env, "transition_task.py", "--role", "DEV", "--from-status", "进行中", "--to-status",
                "已完成", "--assignee", "李开发", "--task-id", "T0100", "--end-time", "2026-08-16 12:00:00",
                expect=1)  # A 类越权直推已完成
        assert "越权" in r.stdout or "越权" in r.stderr

    def test_quick_create(self, env):
        run(env, "quick_task.py", "create", "--name", "快速建卡", "--role", "PM", "--assignee", "李开发")
        assert status_of(env, "T0001") == "待开始"

    def test_quick_complete(self, env):
        run(env, "quick_task.py", "create", "--name", "快速流转", "--role", "PM", "--assignee", "李开发")
        run(env, "quick_task.py", "complete", "--task-id", "T0001", "--role", "DEV",
            "--from-status", "待开始", "--to-status", "进行中", "--assignee", "李开发")
        assert status_of(env, "T0001") == "进行中"

    def test_auto_chain_lock_released(self, env):
        run(env, "auto_task.py", "--task-name", "锁测试甲", "--role", "DEV", "--type", "A")
        run(env, "auto_task.py", "--task-name", "锁测试乙", "--role", "DEV", "--type", "A")  # 顺序执行锁正常释放
        assert status_of(env, "T0002") == "已验收"

    def test_no_direct_complete_for_a(self, env):
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-id", "T0100",
            "--task-name", "直推任务", "--assignee", "李开发")
        run(env, "transition_task.py", "--role", "DEV", "--from-status", "待开始", "--to-status",
            "进行中", "--assignee", "李开发", "--task-id", "T0100")
        run(env, "transition_task.py", "--role", "DEV", "--from-status", "进行中", "--to-status",
            "审查中", "--assignee", "李开发", "--task-id", "T0100")  # A 类正确提交路径


# =====================================================================
# 组 8 · 协议层 3 用例
# =====================================================================
class TestProtocol:
    def test_agents_yaml_gate(self):
        for fn in glob.glob(os.path.join(REPO_ROOT, "agents", "*.yaml")):
            with open(fn, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            rules = data.get("orchestration_rules", [])
            assert any("完工硬门禁" in r for r in rules), fn

    def test_export_template_gate(self):
        src = open(os.path.join(SCRIPTS, "verify_and_export_agents.py"), encoding="utf-8").read()
        assert "完工硬门禁" in src

    def test_heartbeat_orphan_check(self):
        src = open(os.path.join(SCRIPTS, "heartbeat.py"), encoding="utf-8").read()
        assert "ORPHAN_OUTPUT" in src and "orphan_output_hours" in src


# =====================================================================
# 组 9 · 任务分级系统 (L0/L1/L2) 9 用例
# =====================================================================
class TestTaskTiers:
    def test_l1_docs_short_chain(self, env):
        """L1 轻量任务走短链：待开始->进行中->已完成->已验收，绝不经过审查中/测试中。"""
        run(env, "auto_task.py", "--task-name", "文档更新检查", "--role", "DOCS", "--type", "C")
        c = find(env, "T0001")
        assert c is not None and c.get("status") == "已验收"
        proc = str(c.get("process", ""))
        assert "进行中" in proc and "已完成" in proc
        assert "审查中" not in proc and "测试中" not in proc

    def test_l2_a_chain_has_review_test(self, env):
        """L2 标准任务走全链：必须经历审查中与测试中。"""
        run(env, "auto_task.py", "--task-name", "用户核心接口开发", "--role", "DEV", "--type", "A")
        c = find(env, "T0001")
        assert c is not None and c.get("status") == "已验收"
        proc = str(c.get("process", ""))
        assert "审查中" in proc and "测试中" in proc

    def test_dup_label_no_l_prefix(self, env):
        """重复任务检测标签已释放 L 命名空间（避免与 L0/L1/L2 分级混淆）。"""
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "用户登录接口", "--assignee", "李开发")
        r = run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "用户登录接口", "--assignee", "李开发", expect=1)
        assert "L1 完全一致" not in r.stdout
        assert "完全一致" in r.stdout

    def test_pm_yaml_triage_present(self):
        """PM YAML 必须显式包含任务分级三问与 L0 职责。"""
        with open(os.path.join(REPO_ROOT, "agents", "01-pm.yaml"), encoding="utf-8") as f:
            data = yaml.safe_load(f)
        text = yaml.safe_dump(data, allow_unicode=True)
        assert "L0" in text and "分级" in text and "三问" in text

    def test_agents_yaml_l0_carveout(self):
        """所有 8 个角色的完工硬门禁规则均包含 L0 豁免条款。"""
        for fn in glob.glob(os.path.join(REPO_ROOT, "agents", "*.yaml")):
            with open(fn, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            rules = data.get("orchestration_rules", [])
            assert any("L0" in r and "完工硬门禁" in r for r in rules), f"{fn} 缺少 L0 完工硬门禁豁免"

    def test_exporter_sop_l0_carveout(self):
        """导出器 SOP 模板与导出的子代理必须包含 L0 豁免说明。"""
        src = open(os.path.join(SCRIPTS, "verify_and_export_agents.py"), encoding="utf-8").read()
        assert "L0" in src and "完工硬门禁" in src

    def test_build_context_dispatch(self, env):
        """build_agent_context dispatch 动作输出三问、分级与硬红线。"""
        cmd = [sys.executable, os.path.join(SCRIPTS, "build_agent_context.py"), "--role", "PM", "--action", "dispatch"]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
        assert r.returncode == 0
        assert "L0" in r.stdout and "三问" in r.stdout and "L1" in r.stdout and "L2" in r.stdout

    def test_rules_l0_carveout_docs(self):
        """rules/AGENTS.md 和 rules/IDENTITY.md 必须包含 L0 豁免说明。"""
        agents_md = open(os.path.join(REPO_ROOT, "rules", "AGENTS.md"), encoding="utf-8").read()
        identity_md = open(os.path.join(REPO_ROOT, "rules", "IDENTITY.md"), encoding="utf-8").read()
        assert "L0" in agents_md and "分级三问" in agents_md
        assert "L0" in identity_md

    def test_heartbeat_orphan_l0_hint(self):
        """heartbeat.py 孤儿产出提示必须包含草稿箱与 L0 提示。"""
        src = open(os.path.join(SCRIPTS, "heartbeat.py"), encoding="utf-8").read()
        assert "草稿箱" in src and "L0" in src


# =====================================================================
# 组 10 · 负责人 (Owner) 与处理人 (Handler) 语义与生命周期
# =====================================================================
class TestOwnerAndHandlerSemantics:
    def test_pm_create_assigns_owner_and_handler_to_worker(self, env):
        """PM 派单未指定 --owner 时，负责人与初始处理人均正确赋予实际执行人(李开发)，而非 PM。"""
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "责任人测试任务", "--assignee", "flow-dev")
        c = find(env, "T0001")
        assert c is not None
        assert c.get("assignee") == "李开发"  # 负责人
        assert c.get("handler") == "李开发"   # 处理人

    def test_owner_stable_across_lifecycle_and_handler_shifts(self, env):
        """流转过程中负责人保持恒定不变，处理人随节点流转并在终态收敛至严经理。"""
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "流转经办人测试", "--assignee", "DEV")
        # 1. 待开始 -> 进行中
        run(env, "transition_task.py", "--role", "DEV", "--from-status", "待开始", "--to-status", "进行中", "--assignee", "DEV", "--task-id", "T0001")
        c = find(env, "T0001")
        assert c.get("assignee") == "李开发" and c.get("handler") == "李开发"

        # 2. 进行中 -> 审查中
        run(env, "transition_task.py", "--role", "DEV", "--from-status", "进行中", "--to-status", "审查中", "--assignee", "flow-reviewer", "--task-id", "T0001")
        c = find(env, "T0001")
        assert c.get("assignee") == "李开发"   # 负责人不变
        assert c.get("handler") == "周审查"    # 处理人移交周审查

        # 3. 审查中 -> 测试中
        run(env, "transition_task.py", "--role", "REVIEWER", "--from-status", "审查中", "--to-status", "测试中", "--assignee", "flow-qa", "--task-id", "T0001")
        c = find(env, "T0001")
        assert c.get("assignee") == "李开发"   # 负责人不变
        assert c.get("handler") == "章测试"    # 处理人移交章测试

        # 4. 测试中 -> 已完成
        now_str = "2026-08-16 23:00:00"
        run(env, "transition_task.py", "--role", "QA", "--from-status", "测试中", "--to-status", "已完成", "--assignee", "PM", "--task-id", "T0001", "--end-time", now_str)
        c = find(env, "T0001")
        assert c.get("assignee") == "李开发"   # 负责人不变
        assert c.get("handler") == "严经理"    # 处理人收敛至严经理

        # 5. 已完成 -> 已验收
        run(env, "transition_task.py", "--role", "PM", "--from-status", "已完成", "--to-status", "已验收", "--assignee", "PM", "--task-id", "T0001", "--end-time", now_str)
        c = find(env, "T0001")
        assert c.get("assignee") == "李开发"   # 负责人不变
        assert c.get("handler") == "严经理"    # 处理人终态为严经理

    def test_reject_returns_handler_to_owner(self, env):
        """打回时处理人精确退回给原负责人。"""
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "退回测试任务", "--assignee", "DEV")
        run(env, "transition_task.py", "--role", "DEV", "--from-status", "待开始", "--to-status", "进行中", "--assignee", "DEV", "--task-id", "T0001")
        run(env, "transition_task.py", "--role", "DEV", "--from-status", "进行中", "--to-status", "审查中", "--assignee", "REVIEWER", "--task-id", "T0001")
        # 周审查打回
        run(env, "transition_task.py", "--role", "REVIEWER", "--from-status", "审查中", "--to-status", "已退回", "--assignee", "DEV", "--task-id", "T0001", "--remarks", "DEF-T0001-1 修复代码")
        c = find(env, "T0001")
        assert c.get("assignee") == "李开发"
        assert c.get("handler") == "李开发"


# =====================================================================
# 组 11 · 虚拟角色与外部通信边界 (Virtual Agent vs External IM)
# =====================================================================
class TestVirtualAgentNotificationBoundary:
    def test_handover_protocol_contains_virtual_agent_rules(self):
        """06-Inter-Agent-Handover-Protocol.md 必须包含虚拟专家与外部 IM 边界规约。"""
        src = open(os.path.join(REPO_ROOT, "references", "06-Inter-Agent-Handover-Protocol.md"), encoding="utf-8").read()
        assert "虚拟角色边界" in src
        assert "虚拟专家身份定界" in src
        assert "看板任务卡指派即通知" in src

    def test_agents_rule_contains_redline_seven(self):
        """rules/AGENTS.md 必须包含红线 7：虚拟专家身份与外部通信铁律。"""
        src = open(os.path.join(REPO_ROOT, "rules", "AGENTS.md"), encoding="utf-8").read()
        assert "虚拟专家身份与外部通信铁律" in src
        assert "严禁" in src and "通讯录" in src


# =====================================================================
# 组 12 · 独立专家任务与自定义字段映射安全 (Independent Tasks & Field Map Safety)
# =====================================================================
class TestIndependentTasksAndFieldMappingSafety:
    def test_reviewer_independent_review_task(self, env):
        """周审查独立专项审查任务：待开始 -> 进行中 -> 已完成 -> 已验收，负责人恒为周审查。"""
        # 1. PM 分派专项审查任务给周审查
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "代码规范与安全专项审计", "--assignee", "REVIEWER", "--type", "B")
        c = find(env, "T0001")
        assert c.get("assignee") == "周审查"
        assert c.get("handler") == "周审查"

        # 2. 周审查自领取开工: 待开始 -> 进行中
        out = run(env, "transition_task.py", "--role", "REVIEWER", "--from-status", "待开始", "--to-status", "进行中", "--assignee", "REVIEWER", "--task-id", "T0001", "--type", "B")
        assert out.returncode == 0
        c = find(env, "T0001")
        assert c.get("status") == "进行中"
        assert c.get("assignee") == "周审查"
        assert c.get("handler") == "周审查"

        # 3. 周审查完工提交 PM 验收: 进行中 -> 已完成
        out = run(env, "transition_task.py", "--role", "REVIEWER", "--from-status", "进行中", "--to-status", "已完成", "--assignee", "PM", "--task-id", "T0001", "--type", "B", "--end-time", "2026-08-17 10:00:00")
        assert out.returncode == 0
        c = find(env, "T0001")
        assert c.get("status") == "已完成"
        assert c.get("assignee") == "周审查"  # 负责人仍为周审查
        assert c.get("handler") == "严经理"   # 处理人收敛至严经理

        # 4. PM 验收: 已完成 -> 已验收
        out = run(env, "transition_task.py", "--role", "PM", "--from-status", "已完成", "--to-status", "已验收", "--assignee", "PM", "--task-id", "T0001", "--type", "B", "--end-time", "2026-08-17 10:00:00")
        assert out.returncode == 0
        c = find(env, "T0001")
        assert c.get("status") == "已验收"
        assert c.get("assignee") == "周审查"  # 负责人终态依然为周审查！
        assert c.get("handler") == "严经理"

    def test_qa_independent_testcase_task(self, env):
        # 1. PM 分派用例编写任务给 QA
        run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "全链路用例设计与梳理", "--assignee", "QA", "--type", "C")
        # 2. QA 开工
        out = run(env, "transition_task.py", "--role", "QA", "--from-status", "待开始", "--to-status", "进行中", "--assignee", "QA", "--task-id", "T0001", "--type", "C")
        assert out.returncode == 0
        c = find(env, "T0001")
        assert c.get("status") == "进行中"
        assert c.get("assignee") == "章测试"
        assert c.get("handler") == "章测试"

        # QA 完工
        out = run(env, "transition_task.py", "--role", "QA", "--from-status", "进行中", "--to-status", "已完成", "--assignee", "PM", "--task-id", "T0001", "--type", "C", "--end-time", "2026-08-17 10:00:00")
        assert out.returncode == 0
        c = find(env, "T0001")
        assert c.get("status") == "已完成"
        assert c.get("assignee") == "章测试"
        assert c.get("handler") == "严经理"

        # PM 验收
        out = run(env, "transition_task.py", "--role", "PM", "--from-status", "已完成", "--to-status", "已验收", "--assignee", "PM", "--task-id", "T0001", "--type", "C", "--end-time", "2026-08-17 10:00:00")
        assert out.returncode == 0
        c = find(env, "T0001")
        assert c.get("status") == "已验收"
        assert c.get("assignee") == "章测试"
        assert c.get("handler") == "严经理"


# =====================================================================
# 组 13 · 任务流转标签状态与领域枚举固化 (Workflow Enums Solidification)
# =====================================================================
class TestWorkflowEnumsSolidification:
    def test_task_status_enum_completeness(self):
        """TaskStatus 必须包含 9 大标准状态枚举。"""
        from enums import TaskStatus
        expected = ["待开始", "进行中", "审查中", "测试中", "已完成", "已验收", "已退回", "已阻塞", "已取消"]
        assert TaskStatus.all_values() == expected
        assert TaskStatus.terminal_statuses() == {"已完成", "已验收", "已取消"}
        assert TaskStatus.active_statuses() == {"进行中", "审查中", "测试中"}

    def test_task_type_enum_completeness(self):
        """TaskType 必须包含 A-G 7 类标准任务类型。"""
        from enums import TaskType
        assert TaskType.all_values() == ["A", "B", "C", "D", "E", "F", "G"]
        assert TaskType.short_chain_types() == {"B", "C", "D", "F", "G"}

    def test_role_enum_and_normalization(self):
        """RoleEnum 必须包含 8 大 AI 专家角色及用户规范中文名，并支持别名归一化。"""
        from enums import RoleEnum, normalize_role
        assert len(RoleEnum.expert_roles()) == 8
        assert normalize_role("flow-dev") == "李开发"
        assert normalize_role("DEV") == "李开发"
        assert normalize_role("dev_user_1") == "李开发"
        assert normalize_role("flow-reviewer") == "周审查"
        assert normalize_role("pm") == "严经理"
        assert normalize_role(None) == "未分配"

    def test_enums_json_metadata_export(self):
        """enums.json 必须成功导出并包含完整字段元数据。"""
        from enums import dump_enums_dict, export_enums_json
        data = dump_enums_dict()
        assert len(data["task_statuses"]) == 9
        assert len(data["task_types"]) == 7
        assert len(data["roles"]) == 9
        assert "已退回" in [s["key"] for s in data["task_statuses"]]

        exported_file = export_enums_json()
        assert os.path.exists(exported_file)
        with open(exported_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert len(loaded["task_statuses"]) == 9


# =====================================================================
# 组 14 · 真人操作者/创建人自动捕获与流转不可变性 (Task Creator Tracking)
# =====================================================================
class TestTaskCreatorTracking:
    def test_auto_detect_creator_on_create(self, env):
        """新建任务时未指定 creator 自动捕获当前 OS/Git 用户名。"""
        from offline_board_adapter import get_current_os_user
        expected_user = get_current_os_user()

        out = run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "创建人自动捕获测试", "--assignee", "DEV")
        assert out.returncode == 0
        c = find(env, "T0001")
        assert c.get("creator") == expected_user

        # 历经流转: DEV 开工 -> 提审
        out = run(env, "transition_task.py", "--role", "DEV", "--from-status", "待开始", "--to-status", "进行中", "--assignee", "DEV", "--task-id", "T0001")
        assert out.returncode == 0
        c = find(env, "T0001")
        assert c.get("creator") == expected_user  # 流转后 creator 依然不可变！

    def test_explicit_creator_override(self, env):
        """显式传入 --creator 时精确记录并持久化。"""
        out = run(env, "transition_task.py", "--role", "PM", "--create", "--task-name", "自定义创建人测试", "--assignee", "DEV", "--creator", "alice_developer")
        assert out.returncode == 0
        c = find(env, "T0001")
        assert c.get("creator") == "alice_developer"



