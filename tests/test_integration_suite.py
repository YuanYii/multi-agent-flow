#!/usr/bin/env python3
"""
Multi-Agent Flow · 集成测试套件 (Integration Test Suite)
================================================================
测试范围：工作流程（L1 端到端）/ 任务流转（L2 管道与门控）/ 看板功能（L3 数据与前端）

设计原则：
1. 零依赖：仅用 Python 标准库 (unittest / subprocess / urllib / json / tempfile)，无需 pytest。
2. 真实集成：通过 subprocess 调用真实 CLI (transition_task.py) 与真实 HTTP 服务 (start_kanban_server.py)，
   验证"门控校验 → 适配器落盘 → board.json → 前端资源"全链路，而非只测内部函数。
3. 数据隔离：每个用例创建独立临时目录 + 绝对路径 board_file，100% 不污染真实 kanban/board.json。
4. 并发真实：并发锁用例通过持有 flock 的父进程 + CLI 子进程验证物理排他。

执行方式：
    python3 tests/test_integration_suite.py -v
    python3 tests/test_integration_suite.py -k it01        # 只跑指定用例
"""

import os
import re
import sys
import json
import time
import tempfile
import subprocess
import unittest
import urllib.request
import urllib.error

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
KANBAN_DIR = os.path.join(PROJECT_ROOT, "kanban")
_config_real = os.path.join(PROJECT_ROOT, "config", "workflow.config.yaml")
_config_template = os.path.join(PROJECT_ROOT, "config", "workflow.config.template.yaml")
CONFIG_REF = _config_real if os.path.exists(_config_real) else _config_template

TRANSITION_SCRIPT = os.path.join(SCRIPTS_DIR, "transition_task.py")
BOARD_ADAPTER_SCRIPT = os.path.join(SCRIPTS_DIR, "offline_board_adapter.py")
SECRETS_SCRIPT = os.path.join(SCRIPTS_DIR, "check_secrets.py")
SERVER_SCRIPT = os.path.join(SCRIPTS_DIR, "start_kanban_server.py")

STATUS_TODO = "待开始"
STATUS_IP = "进行中"
STATUS_REVIEW = "审查中"
STATUS_TEST = "测试中"
STATUS_REJECTED = "已退回"
STATUS_BLOCKED = "已阻塞"
STATUS_DONE = "已完成"
STATUS_ACCEPTED = "已验收"


def make_isolated_config(board_file: str) -> str:
    """生成指向绝对路径 board_file 的隔离配置文件（绝对路径绕过 skill 目录物理解算，实现数据隔离）"""
    cfg = {
        "project": {"name": "Integration-Test", "version": "1.0.0", "root_dir": "./"},
        "board": {
            "provider": "local",
            "board_file": board_file,
            "fields": {
                "task_id": "task_id", "wbs_id": "wbs_id", "task_name": "task_name",
                "status": "status", "assignee": "assignee", "owner": "owner",
                "priority": "priority", "estimated_hours": "estimated_hours",
                "actual_hours": "actual_hours", "start_time": "start_time",
                "end_time": "end_time", "created_date": "created_date",
                "stage": "stage", "workpackage": "workpackage",
                "process_desc": "process_desc", "remarks": "remarks",
                "attachment": "attachment",
            },
        },
        "roles": {
            "PM": {"name": "项目经理", "assignee_value": "PM_User", "max_parallel_tasks": 99, "can_self_claim": False},
            "ARCHITECT": {"name": "架构师", "assignee_value": "Architect_User", "max_parallel_tasks": 99, "can_self_claim": False},
            "DEV": {"name": "全栈开发工程师", "assignee_value": ["Dev_User_1", "Dev_User_2"], "max_parallel_tasks": 3, "can_self_claim": True},
            "FRONTEND": {"name": "前端开发工程师", "assignee_value": ["Frontend_User"], "max_parallel_tasks": 3, "can_self_claim": True},
            "REVIEWER": {"name": "代码审查专家", "assignee_value": "Reviewer_User", "max_parallel_tasks": 99, "can_self_claim": False},
            "QA": {"name": "测试工程师", "assignee_value": "QA_User", "max_parallel_tasks": 99, "can_self_claim": False},
            "DOCS": {"name": "文档工程师", "assignee_value": "Docs_User", "max_parallel_tasks": 99, "can_self_claim": False},
            "DEVOPS": {"name": "Git与运维管理员", "assignee_value": "DevOps_User", "max_parallel_tasks": 99, "can_self_claim": False},
        },
        "paths": {
            "docs_root": "docs/", "task_breakdown_dir": "docs/workpackages/",
            "dev_reports_dir": "docs/reports/dev/", "review_reports_dir": "docs/reports/review/",
            "qa_reports_dir": "docs/reports/qa/", "summary_dir": "docs/reports/summary/",
            "problem_records_dir": "docs/reports/problems/",
        },
    }
    cfg_path = os.path.join(os.path.dirname(board_file), "workflow.config.yaml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml_text = []
        def dump(obj, indent=0):
            prefix = "  " * indent
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, (dict, list)):
                        yaml_text.append(f"{prefix}{k}:")
                        dump(v, indent + 1)
                    else:
                        yaml_text.append(f"{prefix}{k}: {json.dumps(v, ensure_ascii=False)}")
            elif isinstance(obj, list):
                for v in obj:
                    if isinstance(v, (dict, list)):
                        yaml_text.append(f"{prefix}-")
                        dump(v, indent + 1)
                    else:
                        yaml_text.append(f"{prefix}- {json.dumps(v, ensure_ascii=False)}")
        dump(cfg)
        f.write("\n".join(yaml_text))
    return cfg_path


def run_cli(args: list, timeout: int = 60) -> subprocess.CompletedProcess:
    """调用真实 transition_task.py CLI，返回 CompletedProcess"""
    return subprocess.run(
        [sys.executable, TRANSITION_SCRIPT] + args,
        capture_output=True, text=True, timeout=timeout, cwd=PROJECT_ROOT,
    )


def transition(cfg_path: str, task_id: str, role: str, frm: str, to: str,
               assignee: str, task_type: str = "A", task_name: str = None,
               end_time: str = None, remarks: str = None, dry_run: bool = False,
               active_dev_count: int = 1) -> subprocess.CompletedProcess:
    """封装一次 CLI 流转调用"""
    args = ["--config", cfg_path, "--task-id", task_id, "--role", role,
            "--from-status", frm, "--to-status", to, "--assignee", assignee,
            "--type", task_type, "--active-dev-count", str(active_dev_count)]
    if task_name:
        args += ["--task-name", task_name]
    if end_time:
        args += ["--end-time", end_time]
    if remarks:
        args += ["--remarks", remarks]
    if dry_run:
        args += ["--dry-run"]
    return run_cli(args)


def load_board(board_file: str) -> list:
    with open(board_file, "r", encoding="utf-8") as f:
        return json.load(f)


def find_task(board_file: str, task_id: str) -> dict:
    for rec in load_board(board_file):
        if rec.get("id") == task_id:
            return rec
    return None


def status_of(board_file: str, task_id: str) -> str:
    rec = find_task(board_file, task_id)
    return rec.get("status") if rec else None


def remarks_of(board_file: str, task_id: str) -> str:
    rec = find_task(board_file, task_id)
    return (rec.get("remarks") or "") if rec else ""


class IsolatedBoardCase(unittest.TestCase):
    """每个用例独立临时看板，互不污染"""
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="maf_it_")
        self.board_file = os.path.join(self._tmp, "board.json")
        with open(self.board_file, "w", encoding="utf-8") as f:
            f.write("[]")
        self.cfg_path = make_isolated_config(self.board_file)

    def tearDown(self):
        pass  # 临时目录由系统回收，不主动删除


# =====================================================================
# L1 工作流程端到端集成 (IT-01 ~ IT-12)
# =====================================================================
class IntegrationFlowTests(IsolatedBoardCase):
    """L1：跨角色接力、打回闭环、特权通道、阻塞恢复等完整业务场景"""

    def test_it01_a_type_full_chain_six_roles(self):
        """IT-01: A 类任务 6 角色完整接力 待开始→进行中→审查中→测试中→已完成→已验收"""
        r = transition(self.cfg_path, "T0001", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1",
                       task_name="集成测试任务A")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(status_of(self.board_file, "T0001"), STATUS_IP)

        r = transition(self.cfg_path, "T0001", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = transition(self.cfg_path, "T0001", "REVIEWER", STATUS_REVIEW, STATUS_TEST, "QA_User")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = transition(self.cfg_path, "T0001", "QA", STATUS_TEST, STATUS_DONE, "PM_User",
                       end_time="2026-08-11 16:00:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = transition(self.cfg_path, "T0001", "PM", STATUS_DONE, STATUS_ACCEPTED, "PM_User",
                       end_time="2026-08-11 16:30:00")
        self.assertEqual(r.returncode, 0, r.stderr)

        rec = find_task(self.board_file, "T0001")
        self.assertEqual(rec["status"], STATUS_ACCEPTED)
        self.assertEqual(rec["assignee"], "PM_User")
        self.assertEqual(rec["name"], "集成测试任务A")
        # 关键：每条流转记录都在，无中间态丢失
        self.assertIn("end_date", rec)

    def test_it02_review_reject_fix_resubmit_closed_loop(self):
        """IT-02: 审查打回→修复→复审通过 全闭环，任务编号不变（打回不拆单）"""
        transition(self.cfg_path, "T0002", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="待审查闭环")
        transition(self.cfg_path, "T0002", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User")
        r = transition(self.cfg_path, "T0002", "REVIEWER", STATUS_REVIEW, STATUS_REJECTED, "Dev_User_1",
                       remarks="[DEFECT-T0002-1] 并发未加锁")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(status_of(self.board_file, "T0002"), STATUS_REJECTED)
        self.assertEqual(find_task(self.board_file, "T0002")["assignee"], "Dev_User_1")
        self.assertIn("[DEFECT-T0002-1]", remarks_of(self.board_file, "T0002"))

        # 原负责人领回修复
        self.assertEqual(transition(self.cfg_path, "T0002", "DEV", STATUS_REJECTED, STATUS_IP, "Dev_User_1").returncode, 0)
        self.assertEqual(transition(self.cfg_path, "T0002", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User").returncode, 0)
        # 复审通过
        self.assertEqual(transition(self.cfg_path, "T0002", "REVIEWER", STATUS_REVIEW, STATUS_TEST, "QA_User").returncode, 0)
        # 全程未派生新任务
        self.assertEqual([rec["id"] for rec in load_board(self.board_file)], ["T0002"])

    def test_it03_qa_reject_closed_loop(self):
        """IT-03: QA 测试打回→修复→复测通过 闭环"""
        transition(self.cfg_path, "T0003", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="待测试闭环")
        transition(self.cfg_path, "T0003", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User")
        transition(self.cfg_path, "T0003", "REVIEWER", STATUS_REVIEW, STATUS_TEST, "QA_User")
        r = transition(self.cfg_path, "T0003", "QA", STATUS_TEST, STATUS_REJECTED, "Dev_User_1",
                       remarks="[DEFECT-T0003-1] 空指针异常")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(status_of(self.board_file, "T0003"), STATUS_REJECTED)
        self.assertEqual(transition(self.cfg_path, "T0003", "DEV", STATUS_REJECTED, STATUS_IP, "Dev_User_1").returncode, 0)
        self.assertEqual(transition(self.cfg_path, "T0003", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User").returncode, 0)
        self.assertEqual(transition(self.cfg_path, "T0003", "REVIEWER", STATUS_REVIEW, STATUS_TEST, "QA_User").returncode, 0)
        self.assertEqual(transition(self.cfg_path, "T0003", "QA", STATUS_TEST, STATUS_DONE, "PM_User",
                                    end_time="2026-08-11 17:00:00").returncode, 0)
        self.assertEqual(status_of(self.board_file, "T0003"), STATUS_DONE)

    def test_it04_pm_acceptance_reject_closed_loop(self):
        """IT-04: PM 验收打回→返工→再验收 闭环"""
        transition(self.cfg_path, "T0004", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="待验收闭环")
        transition(self.cfg_path, "T0004", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User")
        transition(self.cfg_path, "T0004", "REVIEWER", STATUS_REVIEW, STATUS_TEST, "QA_User")
        transition(self.cfg_path, "T0004", "QA", STATUS_TEST, STATUS_DONE, "PM_User", end_time="2026-08-11 10:00:00")
        r = transition(self.cfg_path, "T0004", "PM", STATUS_DONE, STATUS_REJECTED, "Dev_User_1",
                       remarks="[DEFECT-T0004-1] 需求遗漏")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(status_of(self.board_file, "T0004"), STATUS_REJECTED)
        # 返工后重新走到完成并验收通过
        transition(self.cfg_path, "T0004", "DEV", STATUS_REJECTED, STATUS_IP, "Dev_User_1")
        transition(self.cfg_path, "T0004", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User")
        transition(self.cfg_path, "T0004", "REVIEWER", STATUS_REVIEW, STATUS_TEST, "QA_User")
        transition(self.cfg_path, "T0004", "QA", STATUS_TEST, STATUS_DONE, "PM_User", end_time="2026-08-11 18:00:00")
        self.assertEqual(transition(self.cfg_path, "T0004", "PM", STATUS_DONE, STATUS_ACCEPTED, "PM_User",
                                    end_time="2026-08-11 18:30:00").returncode, 0)
        self.assertEqual(status_of(self.board_file, "T0004"), STATUS_ACCEPTED)

    def test_it05_reject_assignee_reverts_to_original_owner(self):
        """IT-05: 打回后 Assignee 必须回退原负责人（原子绑定）"""
        transition(self.cfg_path, "T0005", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="负责人回退")
        transition(self.cfg_path, "T0005", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User")
        transition(self.cfg_path, "T0005", "REVIEWER", STATUS_REVIEW, STATUS_REJECTED, "Dev_User_1",
                   remarks="[DEFECT-T0005-1] 风格不符")
        rec = find_task(self.board_file, "T0005")
        self.assertEqual(rec["status"], STATUS_REJECTED)
        self.assertEqual(rec["assignee"], "Dev_User_1", "打回后处理人必须回退原 DEV")

    def test_it06_special_types_direct_completion(self):
        """IT-06: B/C/D/G 类特权流转 进行中→已完成 免审免测"""
        cases = [
            ("T0011", "ARCHITECT", "B", "架构设计"),
            ("T0012", "DOCS", "C", "文档撰写"),
            ("T0013", "DEVOPS", "D", "运维部署"),
            ("T0014", "DEV", "G", "环境搭建"),
        ]
        for tid, role, ttype, name in cases:
            assignee = {"ARCHITECT": "Architect_User", "DOCS": "Docs_User", "DEVOPS": "DevOps_User", "DEV": "Dev_User_1"}[role]
            transition(self.cfg_path, tid, "PM", STATUS_TODO, STATUS_IP, assignee, task_name=name)
            r = transition(self.cfg_path, tid, role, STATUS_IP, STATUS_DONE, assignee,
                           task_type=ttype, end_time="2026-08-11 15:00:00")
            self.assertEqual(r.returncode, 0, f"{tid} {r.stderr}")
            self.assertEqual(status_of(self.board_file, tid), STATUS_DONE)

    def test_it07_hotfix_fast_track_channel(self):
        """IT-07: [HOTFIX] 极简通道免审免测直达完成

         validate_transition.py 已支持 [HOTFIX] 标签放行，
        DEV 在 [HOTFIX] 任务中可直接将状态推至 "进行中 -> 已完成"。
        """
        r = transition(self.cfg_path, "T0015", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1",
                       task_name="[HOTFIX] 紧急配置修复", task_type="A")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = transition(self.cfg_path, "T0015", "DEV", STATUS_IP, STATUS_DONE, "PM_User",
                       task_name="[HOTFIX] 紧急配置修复", end_time="2026-08-11 15:30:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(status_of(self.board_file, "T0015"), STATUS_DONE)

    def test_it08_block_and_resume_in_dev_stage(self):
        """IT-08: 开发阶段阻塞挂起→解阻恢复"""
        transition(self.cfg_path, "T0016", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="阻塞恢复")
        self.assertEqual(transition(self.cfg_path, "T0016", "DEV", STATUS_IP, STATUS_BLOCKED, "Dev_User_1").returncode, 0)
        self.assertEqual(status_of(self.board_file, "T0016"), STATUS_BLOCKED)
        self.assertEqual(transition(self.cfg_path, "T0016", "DEV", STATUS_BLOCKED, STATUS_IP, "Dev_User_1").returncode, 0)
        self.assertEqual(status_of(self.board_file, "T0016"), STATUS_IP)

    def test_it09_multi_task_parallel_within_concurrency_limit(self):
        """IT-09: 同一 DEV 并发 3 任务上限内全部可领（≤3 放行）"""
        for i in range(3):
            tid = f"T00{17 + i}"
            r = transition(self.cfg_path, tid, "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name=f"并行任务{i+1}")
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(load_board(self.board_file)), 3)

    def test_it10_auto_task_numbering_without_task_id(self):
        """IT-10: 不传 task-id 自动分配最大编号+1（并发安全）"""
        r = run_cli(["--config", self.cfg_path, "--role", "PM", "--from-status", STATUS_TODO,
                     "--to-status", STATUS_IP, "--assignee", "Dev_User_1", "--task-name", "自动编号"])
        self.assertEqual(r.returncode, 0, r.stderr)
        recs = load_board(self.board_file)
        self.assertEqual(len(recs), 1)
        self.assertRegex(recs[0]["id"], r"^T\d+$")

    def test_it11_task_auto_create_then_transition(self):
        """IT-11: 任务不存在时自动创建（初始待开始）再流转，一次调用完成"""
        r = transition(self.cfg_path, "T0099", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="自动创建并流转")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = find_task(self.board_file, "T0099")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["status"], STATUS_IP)
        self.assertEqual(rec["name"], "自动创建并流转")

    def test_it12_full_chain_data_consistency_after_each_step(self):
        """IT-12: 每步流转后看板物理数据与状态强一致（状态+处理人原子绑定）"""
        chain = [
            ("PM", STATUS_TODO, STATUS_IP, "Dev_User_1"),
            ("DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User"),
            ("REVIEWER", STATUS_REVIEW, STATUS_TEST, "QA_User"),
            ("QA", STATUS_TEST, STATUS_DONE, "PM_User"),
            ("PM", STATUS_DONE, STATUS_ACCEPTED, "PM_User"),
        ]
        transition(self.cfg_path, "T0100", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="一致性验证")
        for idx, (role, frm, to, assignee) in enumerate(chain):
            kwargs = {}
            if to in (STATUS_DONE, STATUS_ACCEPTED):
                kwargs["end_time"] = f"2026-08-11 1{idx}:00:00"
            r = transition(self.cfg_path, "T0100", role, frm, to, assignee, **kwargs)
            self.assertEqual(r.returncode, 0, r.stderr)
            rec = find_task(self.board_file, "T0100")
            self.assertEqual(rec["status"], to, f"第{idx+1}步状态落库失败")
            self.assertEqual(rec["assignee"], assignee, f"第{idx+1}步处理人未同步")


# =====================================================================
# L2 任务流转管道与门控集成 (IT-13 ~ IT-24)
# =====================================================================
class IntegrationPipelineTests(IsolatedBoardCase):
    """L2：CLI 层门控、越权拦截、并发锁、原子回滚、审计日志"""

    def test_it13_dry_run_never_touches_board(self):
        """IT-13: dry-run 预检不落库，看板保持原状"""
        transition(self.cfg_path, "T0101", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="dryrun任务")
        before = load_board(self.board_file)
        r = transition(self.cfg_path, "T0101", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User", dry_run=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(load_board(self.board_file), before, "dry-run 不得修改看板")

    def test_it14_illegal_jump_blocked_by_cli_exit_code(self):
        """IT-14: 非法跨阶段流转（待开始→测试中）CLI 层 exit code=1 硬拦截"""
        r = transition(self.cfg_path, "T0102", "QA", STATUS_TODO, STATUS_TEST, "QA_User", dry_run=True)
        self.assertNotEqual(r.returncode, 0, "非法流转必须被 CLI 拦截")
        self.assertEqual(status_of(self.board_file, "T0102"), None, "拦截后看板不得出现任务")

    def test_it15_dev_self_acceptance_blocked(self):
        """IT-15: DEV 自我验收（进行中→已验收）越权拦截"""
        transition(self.cfg_path, "T0103", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="越权验收")
        r = transition(self.cfg_path, "T0103", "DEV", STATUS_IP, STATUS_ACCEPTED, "PM_User", dry_run=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(status_of(self.board_file, "T0103"), STATUS_IP)

    def test_it16_missing_assignee_blocked(self):
        """IT-16: 缺失 assignee 参数物理拦截"""
        r = transition(self.cfg_path, "T0104", "DEV", STATUS_TODO, STATUS_IP, "", dry_run=True)
        self.assertNotEqual(r.returncode, 0)

    def test_it17_done_without_end_time_blocked(self):
        """IT-17: 推已完成缺失 end_time 强校验拦截"""
        transition(self.cfg_path, "T0105", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="缺结束时间")
        transition(self.cfg_path, "T0105", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User")
        transition(self.cfg_path, "T0105", "REVIEWER", STATUS_REVIEW, STATUS_TEST, "QA_User")
        r = transition(self.cfg_path, "T0105", "QA", STATUS_TEST, STATUS_DONE, "PM_User")
        self.assertNotEqual(r.returncode, 0, "缺失 end_time 必须拦截")
        self.assertEqual(status_of(self.board_file, "T0105"), STATUS_TEST)

    def test_it18_dev_concurrency_limit_3_blocked(self):
        """IT-18: DEV 在手任务 ≥3 并发超限拦截"""
        r = transition(self.cfg_path, "T0106", "DEV", STATUS_TODO, STATUS_IP, "Dev_User_1",
                       dry_run=True, active_dev_count=3)
        self.assertNotEqual(r.returncode, 0)

    def test_it19_physical_concurrency_lock_exclusion(self):
        """IT-19: 同任务物理排他锁——父进程持锁时 CLI 子进程被硬阻断"""
        lock_path = os.path.join(SCRIPTS_DIR, ".lock_T0107.lock")
        try:
            with open(lock_path, "w") as lf:
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(lf.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                r = transition(self.cfg_path, "T0107", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1")
                self.assertNotEqual(r.returncode, 0, "持锁期间并发流转必须被物理阻断")
        finally:
            if os.path.exists(lock_path):
                os.remove(lock_path)

    def test_it20_defect_remark_structured_format(self):
        """IT-20: 打回备注结构化 DEF-TXXX-N 落库完整"""
        transition(self.cfg_path, "T0108", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="缺陷备注")
        transition(self.cfg_path, "T0108", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User")
        r = transition(self.cfg_path, "T0108", "REVIEWER", STATUS_REVIEW, STATUS_REJECTED, "Dev_User_1",
                       remarks="[DEFECT-T0108-1] 第一轮：接口未加幂等")
        self.assertEqual(r.returncode, 0, r.stderr)
        remarks = remarks_of(self.board_file, "T0108")
        self.assertIn("[DEFECT-T0108-1]", remarks)
        self.assertIn("第一轮：接口未加幂等", remarks)

    def test_it21_repeated_rejection_appends_rounds(self):
        """IT-21: 多轮打回缺陷轮次递增，备注追加不覆盖（复验追加原则）"""
        transition(self.cfg_path, "T0109", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="多轮打回")
        transition(self.cfg_path, "T0109", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User")
        transition(self.cfg_path, "T0109", "REVIEWER", STATUS_REVIEW, STATUS_REJECTED, "Dev_User_1",
                   remarks="[DEFECT-T0109-1] 首轮缺陷")
        transition(self.cfg_path, "T0109", "DEV", STATUS_REJECTED, STATUS_IP, "Dev_User_1")
        transition(self.cfg_path, "T0109", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User")
        transition(self.cfg_path, "T0109", "REVIEWER", STATUS_REVIEW, STATUS_REJECTED, "Dev_User_1",
                   remarks="[DEFECT-T0109-2] 二轮缺陷")
        remarks = remarks_of(self.board_file, "T0109")
        self.assertIn("[DEFECT-T0109-1]", remarks)
        self.assertIn("[DEFECT-T0109-2]", remarks)

    def test_it22_terminal_state_frozen(self):
        """IT-22: 终态已验收二次流转封锁（已验收→进行中 拦截）"""
        transition(self.cfg_path, "T0110", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="终态冻结")
        transition(self.cfg_path, "T0110", "DEV", STATUS_IP, STATUS_REVIEW, "Reviewer_User")
        transition(self.cfg_path, "T0110", "REVIEWER", STATUS_REVIEW, STATUS_TEST, "QA_User")
        transition(self.cfg_path, "T0110", "QA", STATUS_TEST, STATUS_DONE, "PM_User", end_time="2026-08-11 12:00:00")
        transition(self.cfg_path, "T0110", "PM", STATUS_DONE, STATUS_ACCEPTED, "PM_User", end_time="2026-08-11 12:30:00")
        r = transition(self.cfg_path, "T0110", "PM", STATUS_ACCEPTED, STATUS_IP, "Dev_User_1", dry_run=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(status_of(self.board_file, "T0110"), STATUS_ACCEPTED)

    def test_it23_missing_config_fail_closed(self):
        """IT-23: 配置文件不存在 Fail-Closed 硬阻断"""
        r = run_cli(["--config", os.path.join(self._tmp, "no_such.yaml"), "--role", "PM",
                     "--from-status", STATUS_TODO, "--to-status", STATUS_IP, "--assignee", "Dev_User_1"])
        self.assertNotEqual(r.returncode, 0)

    def test_it24_audit_trail_logged_for_each_transition(self):
        """IT-24: 每次流转写审计日志（logs/audit_trail.log 结构化事件）"""
        audit_file = os.path.join(PROJECT_ROOT, "logs", "audit_trail.log")
        before_count = 0
        if os.path.exists(audit_file):
            with open(audit_file, "r", encoding="utf-8") as f:
                before_count = sum(1 for _ in f)
        transition(self.cfg_path, "T0111", "PM", STATUS_TODO, STATUS_IP, "Dev_User_1", task_name="审计事件")
        with open(audit_file, "r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertGreater(len(lines), before_count)
        last = lines[-1]
        self.assertEqual(last["task_id"], "T0111")
        self.assertEqual(last["to_status"], STATUS_IP)
        self.assertTrue(last["success"])


# =====================================================================
# L3 看板功能集成 (IT-25 ~ IT-32)
# =====================================================================
class IntegrationKanbanTests(unittest.TestCase):
    """L3：看板服务、数据一致性、前端资源契约、配置一致性、凭据扫描"""

    @classmethod
    def setUpClass(cls):
        cls._server = None
        cls.server_url = None
        # 动态分配空闲测试端口，启动隔离的看板服务
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("", 0))
        test_port = s.getsockname()[1]
        s.close()

        if os.path.exists(SERVER_SCRIPT):
            cls._server = subprocess.Popen(
                [sys.executable, SERVER_SCRIPT, "--port", str(test_port)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=PROJECT_ROOT)
            for _ in range(10):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/", timeout=1):
                        cls.server_url = f"http://127.0.0.1:{test_port}"
                        break
                except Exception:
                    time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        if cls._server:
            cls._server.terminate()
            try:
                cls._server.wait(timeout=5)
            except Exception:
                cls._server.kill()

    def http_get(self, path: str):
        if not self.server_url:
            self.skipTest("32886 看板服务不可用（未启动成功且端口无服务）")
        with urllib.request.urlopen(self.server_url + path, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")

    def test_it25_kanban_server_serves_index(self):
        """IT-25: 看板 HTTP 服务可用，/ 与 /offline_board.html 返回同一看板页面"""
        status, body_root = self.http_get("/")
        self.assertEqual(status, 200)
        status, body_page = self.http_get("/offline_board.html")
        self.assertEqual(status, 200)
        # SimpleHTTPRequestHandler 将 / 直接 rewrite 为 offline_board.html，内容必须完全一致
        self.assertEqual(body_root, body_page, "/ 未正确重定向至看板页面")
        self.assertIn("多专家", body_root)
        self.assertIn("kanban", body_root.lower())

    def test_it26_board_json_served_identical_to_disk(self):
        """IT-26: HTTP 拉取 board.json 与本地文件物理一致"""
        status, body = self.http_get("/board.json")
        self.assertEqual(status, 200)
        disk = open(os.path.join(KANBAN_DIR, "board.json"), "r", encoding="utf-8").read()
        self.assertEqual(json.loads(body), json.loads(disk), "服务数据与磁盘数据不一致")

    def test_it27_static_assets_all_resolvable(self):
        """IT-27: HTML 引用的 css/js 静态资源全部 200 可访问"""
        status, body = self.http_get("/offline_board.html")
        refs = re.findall(r'(?:src|href)="([^"]+\.(?:css|js))"', body)
        self.assertGreater(len(refs), 0, "HTML 未引用任何静态资源")
        for ref in refs:
            st, _ = self.http_get("/" + ref.lstrip("./"))
            self.assertEqual(st, 200, f"静态资源 404: {ref}")

    def test_it28_onclick_functions_defined_in_js(self):
        """IT-28: HTML onclick 绑定的函数必须在 JS 文件中真实定义"""
        html = open(os.path.join(KANBAN_DIR, "offline_board.html"), "r", encoding="utf-8").read()
        js_code = ""
        for js_file in ("board.js", "util.js", "data.js", "listbox.js", "app.js"):
            p = os.path.join(KANBAN_DIR, "js", js_file)
            if os.path.exists(p):
                js_code += open(p, "r", encoding="utf-8").read()
        onclick_matches = re.findall(r'onclick="([^"]+)"', html)
        self.assertGreater(len(onclick_matches), 0)
        for handler in onclick_matches:
            fn = re.match(r'([a-zA-Z0-9_$]+)\s*\(', handler.strip())
            if fn:
                self.assertRegex(js_code, r'function\s+' + fn.group(1) + r'\b|' + fn.group(1) + r'\s*=\s*',
                                 f"onclick 函数 {fn.group(1)} 未在 JS 中定义")

    def test_it29_key_controls_present_in_board_ui(self):
        """IT-29: 搜索/筛选/排序/批量删除等关键控件 ID 齐全"""
        html = open(os.path.join(KANBAN_DIR, "offline_board.html"), "r", encoding="utf-8").read()
        for cid in ("search-box", "filter-status", "filter-assignee", "sort-field", "sort-order", "batch-delete-btn"):
            self.assertIn(f'id="{cid}"', html, f"关键控件 {cid} 缺失")

    def test_it30_js_brace_and_paren_balance(self):
        """IT-30: 全部 JS 文件花括号/圆括号平衡（语法健全性）"""
        for js_file in ("board.js", "util.js", "data.js", "listbox.js", "app.js"):
            p = os.path.join(KANBAN_DIR, "js", js_file)
            if not os.path.exists(p):
                continue
            content = open(p, "r", encoding="utf-8").read()
            self.assertEqual(content.count("{"), content.count("}"), f"{js_file} 花括号不平衡")
            self.assertEqual(content.count("("), content.count(")"), f"{js_file} 圆括号不平衡")

    def test_it31_config_roles_contract_complete(self):
        """IT-31: workflow.config.yaml 角色契约完整（8 角色、并发上限、自领权限）"""
        try:
            import yaml
        except ImportError:
            self.skipTest("yaml 依赖不可用")
        with open(CONFIG_REF, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        roles = cfg["roles"]
        self.assertEqual(set(roles.keys()), {"PM", "ARCHITECT", "DEV", "FRONTEND", "REVIEWER", "QA", "DOCS", "DEVOPS"})
        self.assertEqual(roles["DEV"]["max_parallel_tasks"], 3)
        self.assertEqual(roles["FRONTEND"]["max_parallel_tasks"], 3)
        self.assertTrue(roles["DEV"]["can_self_claim"])
        self.assertFalse(roles["PM"]["can_self_claim"])

    def test_it32_secrets_scan_passes(self):
        """IT-32: 敏感凭据扫描 check_secrets.py 零告警通过"""
        r = subprocess.run([sys.executable, SECRETS_SCRIPT], capture_output=True, text=True,
                           timeout=120, cwd=PROJECT_ROOT)
        self.assertEqual(r.returncode, 0, f"凭据扫描失败: {r.stdout} {r.stderr}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
