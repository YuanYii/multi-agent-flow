#!/usr/bin/env python3
"""
审计日志查询 CLI (Audit Query CLI)
按 task_id / role / success / 时间范围 查询 logs/audit_trail.log (含归档)。

典型用法:
  # 查某个任务的所有流转
  python3 scripts/audit_query.py --task-id T0001

  # 查所有失败事件
  python3 scripts/audit_query.py --failed

  # 查某角色在时间窗内的事件
  python3 scripts/audit_query.py --role DEV --since 2026-08-10 --until 2026-08-13

  # 查代行记录
  python3 scripts/audit_query.py --delegated-by USER
"""
import os
import sys
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.audit.audit_logger import query_events


def main():
    parser = argparse.ArgumentParser(description="审计日志查询 CLI (含归档)")
    parser.add_argument("--task-id", help="按任务编号过滤 (忽略大小写)")
    parser.add_argument("--role", help="按角色过滤 (PM/DEV/REVIEWER/QA/...)")
    parser.add_argument("--delegated-by", help="查代行记录 (按代行来源过滤)")
    parser.add_argument("--failed", action="store_true", help="只显示失败事件 (success=false)")
    parser.add_argument("--success", action="store_true", help="只显示成功事件 (success=true)")
    parser.add_argument("--since", help="起始时间 (ISO 字符串, 如 2026-08-10T00:00:00)")
    parser.add_argument("--until", help="结束时间 (ISO 字符串)")
    parser.add_argument("--no-archive", action="store_true", help="不查询历史归档")
    parser.add_argument("--limit", type=int, help="限制返回条数 (按时间倒序截断)")
    parser.add_argument("--format", choices=["json", "table"], default="table", help="输出格式")

    args = parser.parse_args()

    success_filter = None
    if args.failed:
        success_filter = False
    elif args.success:
        success_filter = True

    events = query_events(
        task_id=args.task_id,
        role=args.role,
        success=success_filter,
        since=args.since,
        until=args.until,
        include_archive=not args.no_archive,
        limit=args.limit,
    )

    if args.delegated_by:
        events = [e for e in events if e.get("delegated_by", "").upper() == args.delegated_by.upper()]

    if args.format == "json":
        print(json.dumps(events, ensure_ascii=False, indent=2))
        return

    # table 格式
    if not events:
        print("(无匹配事件)")
        return
    print(f" 共 {len(events)} 条审计事件")
    print("-" * 110)
    for e in events:
        ts = e.get("timestamp", "?")
        tid = e.get("task_id", "?")
        role = e.get("role", "?")
        transition = f"{e.get('from_status', '?')} -> {e.get('to_status', '?')}"
        ok = "[SUCCESS] " if e.get("success") else "[FAILED] "
        who = e.get("assignee", "-")
        delegated = ""
        if e.get("delegated_by"):
            delegated = f" [代行: {e.get('delegated_by')} | {e.get('delegation_reason', '')}]"
        details = e.get("details", "")[:50]
        print(f"{ts}  {ok}  {tid:8s}  {role:10s}  {transition:18s}  -> {who:10s}{delegated}  | {details}")
    print("-" * 110)


if __name__ == "__main__":
    main()
