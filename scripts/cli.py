#!/usr/bin/env python3
"""
Multi-Agent Flow 统一现代 CLI 总入口 (Unified CLI Gateway)
支持子命令透明转发与分发：task, kanban, status, ccp, help
"""
import sys
import os
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


def print_usage():
    print("""usage: yy-flow [-h] {task,dispatch,kanban,status,help,ccp} ...

Multi-Agent Team Workflow (YY-Flow) 统一命令行工具

subcommands:
  task      任务管理与流转 (透明转发至 quick_task / transition_task)
  dispatch  代码化任务派发 (透明转发至 dispatch_task，生成 Subagent 载荷)
  kanban    启动 Web 可视化看板 (透明转发至 start_kanban_server)
  status    大盘全局健康度巡检 (透明转发至 heartbeat)
  help      输出全景指令帮助手册 (透明转发至 show_help)
  ccp       上下文连续性协议门禁操作

示例:
  yy-flow task create --name "实现新接口" --type A --assignee 李开发
  yy-flow dispatch --task-id T0001
  yy-flow task accept --task-id T0001
  yy-flow kanban --port 32886
  yy-flow status --json
  yy-flow ccp --task-id T0001 --stage 审查中
""")


def cmd_task(extra_args):
    """透明转发至 quick_task (支持 create, accept, complete, status 等)"""
    from quick_task import main as quick_main
    sys.argv = [sys.argv[0]] + extra_args
    quick_main()


def cmd_dispatch(extra_args):
    """透明转发至 dispatch_task"""
    from dispatch_task import main as dispatch_main
    sys.argv = [sys.argv[0]] + extra_args
    dispatch_main()


def cmd_kanban(extra_args):
    """透明转发至 start_kanban_server"""
    from start_kanban_server import main as kanban_main
    sys.argv = [sys.argv[0]] + extra_args
    kanban_main()


def cmd_status(extra_args):
    """透明转发至 heartbeat"""
    from heartbeat import main as heartbeat_main
    sys.argv = [sys.argv[0]] + extra_args
    heartbeat_main()


def cmd_help(extra_args):
    """透明转发至 show_help"""
    from show_help import main as help_main
    sys.argv = [sys.argv[0]] + extra_args
    help_main()


def cmd_ccp(extra_args):
    """CCP 协议子命令"""
    from _lib.ccp.validators.pipeline import check_continuity_gate
    parser = argparse.ArgumentParser(prog="yy-flow ccp", description="上下文连续性协议门禁操作")
    parser.add_argument("--task-id", required=True, help="任务卡 ID (如 T0001)")
    parser.add_argument("--stage", default="审查中", help="目标流转阶段")
    args = parser.parse_args(extra_args)
    task_id = args.task_id
    stage = args.stage
    print(f"[*] 正在为任务 {task_id} 执行连续性门禁校验 (目标阶段: {stage})...")
    report = check_continuity_gate(task_id, stage)
    print(f"[+] 门禁校验结果状态: {report.status}")
    if report.missing_fields:
        print(f"[-] 缺失必填字段: {report.missing_fields}")
    if report.blocking_unknowns:
        print(f"[!] 存在阻断未知项: {report.blocking_unknowns}")


def main():
    if len(sys.argv) == 1:
        print_usage()
        sys.exit(0)

    subcommand = sys.argv[1]
    extra_args = sys.argv[2:]

    if subcommand in ["-h", "--help"]:
        print_usage()
        sys.exit(0)

    handlers = {
        "task": cmd_task,
        "dispatch": cmd_dispatch,
        "kanban": cmd_kanban,
        "status": cmd_status,
        "help": cmd_help,
        "ccp": cmd_ccp,
    }

    if subcommand in handlers:
        handlers[subcommand](extra_args)
    else:
        print(f"未知子命令: {subcommand}\n")
        print_usage()
        sys.exit(2)


if __name__ == "__main__":
    main()
