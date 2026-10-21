#!/usr/bin/env python3
"""
Multi-Agent Flow (YY-Flow) 定版发布全量质量准出流水线总控引擎 (Release Gate Runner)

本总控引擎串联执行以下五道定版发布质量门禁，严格遵循 Fail-Closed 原则：
- Gate 1: 静态 Schema 与双轨一致性门禁 (Static Consistency Gate)
- Gate 2: 核心库与 CLI 契约单元测试门禁 (Unit & Contract Gate)
- Gate 3: 10 大核心执行链路沙盒业务树仿真门禁 (Workflow E2E Simulation Gate)
- Gate 4: 看板后端 API、多源适配器与并发写锁门禁 (Kanban Backend & Concurrency Gate)
- Gate 5: 看板前端 UI 全控件无头浏览器自动化门禁 (Kanban UI Playwright Gate)

使用方法:
    python3 scripts/run_release_gates.py
    python3 scripts/run_release_gates.py --suite 108
    python3 scripts/run_release_gates.py --skip-ui
    python3 scripts/run_release_gates.py --json
"""

import os
import sys
import time
import json
import shutil
import argparse
import subprocess
from datetime import datetime
from typing import Dict, Any, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from check_static_consistency import StaticConsistencyChecker


class ReleaseGateRunner:
    def __init__(self, suite: str = "52", skip_ui: bool = False, report_dir: str = None):
        self.suite = suite
        self.skip_ui = skip_ui
        self.report_dir = report_dir or os.path.join(PROJECT_ROOT, "test-reports")
        self.results: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "suite": self.suite,
            "skip_ui": self.skip_ui,
            "gates": {},
            "passed": False,
            "total_duration_sec": 0.0,
        }

    def log(self, msg: str):
        print(f"[*] {msg}")

    def error(self, msg: str):
        print(f"[!] {msg}", file=sys.stderr)

    def success(self, msg: str):
        print(f"[+] {msg}")

    def run_gate1_static(self) -> bool:
        """Gate 1: 静态 Schema 与双轨一致性门禁"""
        self.log("正在执行 Gate 1: 静态 Schema 与双轨一致性检查...")
        t0 = time.time()
        checker = StaticConsistencyChecker(PROJECT_ROOT)
        res = checker.run_all()
        elapsed = round(time.time() - t0, 2)

        gate_record = {
            "name": "Gate 1: 静态 Schema 与双轨一致性",
            "passed": res["passed"],
            "duration_sec": elapsed,
            "details": res,
        }
        self.results["gates"]["gate_1"] = gate_record

        if res["passed"]:
            self.success(f"Gate 1 通过 ({elapsed}s, 检查 {res['total_items_checked']} 项资产)")
            return True
        else:
            self.error(f"Gate 1 阻断! 发现 {res['violations_count']} 项违规:")
            for v in res["violations"]:
                self.error(f"    - [{v['gate']}] {v['file']}: {v['message']}")
            return False

    def run_gate2_units(self) -> bool:
        """Gate 2: 核心库与 CLI 契约单元测试门禁"""
        self.log("正在执行 Gate 2: 核心库与 CLI 契约单元测试 (pytest)...")
        t0 = time.time()
        cmd = [
            sys.executable, "-m", "pytest", "tests/",
            "-k", "not e2e and not slow and not test_adapters_and_concurrency",
            "-q", "--tb=short"
        ]
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        elapsed = round(time.time() - t0, 2)

        passed = res.returncode == 0
        gate_record = {
            "name": "Gate 2: 核心库与 CLI 契约单测",
            "passed": passed,
            "duration_sec": elapsed,
            "stdout_tail": "\n".join(res.stdout.splitlines()[-5:]),
            "stderr": res.stderr.strip(),
        }
        self.results["gates"]["gate_2"] = gate_record

        if passed:
            self.success(f"Gate 2 通过 ({elapsed}s)")
            return True
        else:
            self.error(f"Gate 2 阻断! 测试套件执行失败:\n{res.stdout}\n{res.stderr}")
            return False

    def run_gate3_simulation(self) -> bool:
        """Gate 3: 业务执行链路沙盒端到端演练门禁"""
        self.log(f"正在执行 Gate 3: 沙盒业务树全链路端到端仿真演练 (--suite {self.suite})...")
        t0 = time.time()
        cmd = [sys.executable, "scripts/run_simulation.py", "--suite", self.suite]
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        elapsed = round(time.time() - t0, 2)

        passed = res.returncode == 0
        gate_record = {
            "name": f"Gate 3: 沙盒端到端业务树仿真 (Suite {self.suite})",
            "passed": passed,
            "duration_sec": elapsed,
            "stdout_tail": "\n".join(res.stdout.splitlines()[-10:]),
        }
        self.results["gates"]["gate_3"] = gate_record

        if passed:
            self.success(f"Gate 3 通过 ({elapsed}s)")
            return True
        else:
            self.error(f"Gate 3 阻断! 仿真演练未通过:\n{res.stdout}\n{res.stderr}")
            return False

    def run_gate4_backend(self) -> bool:
        """Gate 4: 看板后端 API、适配器与并发写锁门禁"""
        self.log("正在执行 Gate 4: 看板后端 API、适配器与并发写锁压测...")
        t0 = time.time()
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/test_adapters_and_concurrency.py",
            "tests/test_kanban_api_v2.py",
            "-q", "--tb=short"
        ]
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        elapsed = round(time.time() - t0, 2)

        passed = res.returncode == 0
        gate_record = {
            "name": "Gate 4: 看板后端 API 与多源适配器并发压测",
            "passed": passed,
            "duration_sec": elapsed,
            "stdout_tail": "\n".join(res.stdout.splitlines()[-5:]),
        }
        self.results["gates"]["gate_4"] = gate_record

        if passed:
            self.success(f"Gate 4 通过 ({elapsed}s)")
            return True
        else:
            self.error(f"Gate 4 阻断! 适配器或看板 API 测试失败:\n{res.stdout}\n{res.stderr}")
            return False

    def run_gate5_ui(self) -> bool:
        """Gate 5: 看板前端 UI 全控件无头浏览器自动化门禁"""
        self.log("正在执行 Gate 5: 看板前端 UI 全控件无头浏览器自动化 (Playwright)...")
        if self.skip_ui:
            self.log("[!] 收到 --skip-ui 参数，降级跳过 UI 浏览器测试。")
            self.results["gates"]["gate_5"] = {
                "name": "Gate 5: 看板前端 UI 全控件自动化",
                "passed": True,
                "skipped": True,
                "duration_sec": 0.0,
                "reason": "显式 --skip-ui 降级",
            }
            return True

        # 环境嗅探: 检查 node 与 npm
        if not shutil.which("npm") or not shutil.which("node"):
            self.log("[!] 当前宿主环境未探测到 node/npm，自动降级记录 Warning 并跳过 UI 门禁。")
            self.results["gates"]["gate_5"] = {
                "name": "Gate 5: 看板前端 UI 全控件自动化",
                "passed": True,
                "skipped": True,
                "duration_sec": 0.0,
                "reason": "环境缺失 Node.js 运行时，优雅降级",
            }
            return True

        t0 = time.time()
        cmd = ["npm", "test"]
        e2e_dir = os.path.join(PROJECT_ROOT, "e2e")
        res = subprocess.run(cmd, cwd=e2e_dir, capture_output=True, text=True)
        elapsed = round(time.time() - t0, 2)

        passed = res.returncode == 0
        gate_record = {
            "name": "Gate 5: 看板前端 UI 全控件自动化",
            "passed": passed,
            "skipped": False,
            "duration_sec": elapsed,
            "stdout_tail": "\n".join(res.stdout.splitlines()[-10:]),
        }
        self.results["gates"]["gate_5"] = gate_record

        if passed:
            self.success(f"Gate 5 通过 ({elapsed}s)")
            return True
        else:
            self.error(f"Gate 5 阻断! UI 自动化回归失败:\n{res.stdout}\n{res.stderr}")
            return False

    def write_reports(self):
        """生成结构化准出审计报告 (JSON + Markdown)"""
        os.makedirs(self.report_dir, exist_ok=True)
        json_path = os.path.join(self.report_dir, "release_audit_report.json")
        md_path = os.path.join(self.report_dir, "release_audit_report.md")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

        lines = [
            "# YY-Flow 技能定版发布质量准出审计报告",
            "",
            f"- **执行时间**: {self.results['timestamp']}",
            f"- **准出判定**: {'【通过 / PASSED】' if self.results['passed'] else '【阻断 / BLOCKED】'}",
            f"- **总耗时**: {self.results['total_duration_sec']} 秒",
            f"- **仿真套件**: Suite {self.suite}",
            "",
            "## 门禁分项核验明细",
            "",
            "| 门禁代号 | 门禁名称 | 状态 | 耗时 (s) | 备注 |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for gid, ginfo in self.results["gates"].items():
            st = "PASSED" if ginfo.get("passed") else "FAILED"
            if ginfo.get("skipped"):
                st = "SKIPPED (降级)"
            lines.append(f"| {gid.upper()} | {ginfo.get('name')} | {st} | {ginfo.get('duration_sec', 0)} | {ginfo.get('reason', '-')} |")

        lines.extend([
            "",
            "---",
            "*本报告由 scripts/run_release_gates.py 自动化生成，严格遵循 Fail-Closed 门禁原则。*",
        ])

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self.log(f"准出审计报告已写入:\n    - {json_path}\n    - {md_path}")

    def run_all(self) -> bool:
        start_time = time.time()
        print("=" * 70)
        print("  Multi-Agent Flow (YY-Flow) 定版发布全量质量准出流水线")
        print("=" * 70)

        pipeline = [
            ("gate_1", self.run_gate1_static),
            ("gate_2", self.run_gate2_units),
            ("gate_3", self.run_gate3_simulation),
            ("gate_4", self.run_gate4_backend),
            ("gate_5", self.run_gate5_ui),
        ]

        overall_passed = True
        for gid, step_fn in pipeline:
            passed = step_fn()
            if not passed:
                overall_passed = False
                self.error(f"[X] 流水线在 {gid.upper()} 触发 Fail-Closed 熔断阻断，后续门禁终止执行。")
                break

        self.results["passed"] = overall_passed
        self.results["total_duration_sec"] = round(time.time() - start_time, 2)

        self.write_reports()

        print("=" * 70)
        if overall_passed:
            self.success(f"定版全量门禁流水线全部通过! 总耗时: {self.results['total_duration_sec']}s")
        else:
            self.error(f"定版全量门禁流水线未通过! 阻断耗时: {self.results['total_duration_sec']}s")
        print("=" * 70)

        return overall_passed


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Flow 定版发布全量门禁调度总控")
    parser.add_argument("--suite", choices=["52", "108"], default="52", help="Gate 3 沙盒仿真深度 (默认 52 业务树)")
    parser.add_argument("--skip-ui", action="store_true", help="显式跳过 Gate 5 Playwright UI 浏览器测试")
    parser.add_argument("--json", action="store_true", help="终端仅输出最终 JSON 结果")
    parser.add_argument("--report-dir", help="自定义测试报告落盘目录")
    args = parser.parse_args()

    runner = ReleaseGateRunner(suite=args.suite, skip_ui=args.skip_ui, report_dir=args.report_dir)
    passed = runner.run_all()

    if args.json:
        print(json.dumps(runner.results, ensure_ascii=False, indent=2))

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
