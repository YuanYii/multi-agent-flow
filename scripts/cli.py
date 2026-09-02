#!/usr/bin/env python3
"""
Multi-Agent Flow 统一现代 CLI 总入口 (Unified CLI Gateway)
支持子命令分发：task, kanban, status, ccp, help
"""
import sys
import os
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


def cmd_task(args):
    """转发至 quick_task / transition_task"""
    from quick_task import main as quick_main
    quick_main()


def cmd_kanban(args):
    """启动看板"""
    from start_kanban_server import main as kanban_main
    kanban_main()


def cmd_status(args):
    """巡检状态"""
    from heartbeat import main as heartbeat_main
    heartbeat_main()


def cmd_help(args):
    """查看全景帮助手册"""
    from show_help import main as help_main
    help_main()


def cmd_ccp(args):
    """CCP 协议子命令"""
    from _lib.ccp.validators.pipeline import check_continuity_gate
    task_id = args.task_id
    stage = args.stage or "审查中"
    print(f"[*] 正在为任务 {task_id} 执行连续性门禁校验 (目标阶段: {stage})...")
    report = check_continuity_gate(task_id, stage)
    print(f"[+] 门禁校验结果状态: {report.status}")
    if report.missing_fields:
        print(f"[-] 缺失必填字段: {report.missing_fields}")
    if report.blocking_unknowns:
        print(f"[!] 存在阻断未知项: {report.blocking_unknowns}")


def main():
    parser = argparse.ArgumentParser(
        prog="yy-flow",
        description="Multi-Agent Team Workflow (YY-Flow) 统一命令行工具",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="子命令")

    # task
    task_parser = subparsers.add_parser("task", help="任务管理与创建")

    # kanban
    kanban_parser = subparsers.add_parser("kanban", help="启动 Web 可视化看板")

    # status
    status_parser = subparsers.add_parser("status", help="大盘全局健康度巡检")

    # help
    help_parser = subparsers.add_parser("help", help="输出全景指令帮助手册")

    # ccp
    ccp_parser = subparsers.add_parser("ccp", help="上下文连续性协议门禁操作")
    ccp_parser.add_argument("--task-id", required=True, help="任务卡 ID (如 T0001)")
    ccp_parser.add_argument("--stage", default="审查中", help="目标流转阶段")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    if args.subcommand == "task":
        cmd_task(args)
    elif args.subcommand == "kanban":
        cmd_kanban(args)
    elif args.subcommand == "status":
        cmd_status(args)
    elif args.subcommand == "help":
        cmd_help(args)
    elif args.subcommand == "ccp":
        cmd_ccp(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
