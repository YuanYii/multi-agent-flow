#!/usr/bin/env python3
"""
check_stage_gate.py · YY-Flow 阶段门禁核验器 (Stage Gate Checker CLI)
"""
import os
import sys
import json
import argparse
from dataclasses import asdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from _lib.gates.stage_gate_checker import (
    CheckResult,
    StageGateReport,
    StageContext,
    check_board_tasks_status,
    check_wbs_reconciliation,
    check_arch_summary,
    check_pm_summary,
    records_are_non_tech,
    check_git_working_tree_cleanliness,
    check_stage_start_predecessors,
    STAGE_GATE_CHECKERS,
    STAGE_START_CHECKERS,
    run_stage_gate_check,
    format_terminal_report,
)


def main():
    parser = argparse.ArgumentParser(description="YY-Flow 阶段门禁核验器 (Stage Gate Checker)")
    parser.add_argument("--action", "-a", choices=["close", "start"], default="close", help="门禁类型: close (阶段结项准出) 或 start (阶段开工准入)")
    parser.add_argument("--stage", "-s", type=str, default="", help="目标核验阶段名称或代号 (如 S1, 'S1 需求分析')")
    parser.add_argument("--project-root", "-p", type=str, default=None, help="目标项目根目录路径 (默认自动推导)")
    parser.add_argument("--ignore-git", action="store_true", help="豁免 Git 工作区清洁度核验")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果供 CI 集成消费")

    args = parser.parse_args()

    config_override = {}
    if args.ignore_git:
        config_override["require_clean_git"] = False

    report = run_stage_gate_check(
        stage_name=args.stage,
        project_root_dir=args.project_root,
        config_override=config_override if config_override else None,
        action=args.action,
    )

    if args.json:
        out_dict = {
            "stage_name": report.stage_name,
            "action": report.action,
            "passed": report.passed,
            "total_checks": report.total_checks,
            "passed_checks": report.passed_checks,
            "failed_checks": report.failed_checks,
            "results": [asdict(r) for r in report.results],
        }
        print(json.dumps(out_dict, ensure_ascii=False, indent=2))
    else:
        print(format_terminal_report(report))

    if report.passed:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
