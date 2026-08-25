#!/usr/bin/env python3
"""
看板状态巡检脚本 (Kanban Heartbeat CLI)
实现 rules/HEARTBEAT.md 描述的各项巡检,输出结构化告警,支持阈值可配置。

巡检规则与告警代码规范：
  1. 滞留任务检查: 进行中 > 24h 未更新 / 审查中或测试中 > 12h 未流转 (STALE_IN_PROGRESS / STALE_REVIEW_OR_TEST)
  2. 并发上限核验: DEV/FRONTEND 进行中任务数是否超出上限 (DEV_CONCURRENCY_EXCEEDED / FRONTEND_CONCURRENCY_EXCEEDED)
  3. 状态-处理人一致性核验: 审查中应设 REVIEWER;测试中应设 QA;已完成/已验收 应设 PM (ASSIGNEE_MISMATCH_*)
  4. 终态结束时间必填强校验: 已完成/已验收 是否遗漏 end_date (MISSING_END_DATE)
  5. 孤儿产出检测: 近 orphan_output_hours (默认 48h) 新增交付文件无对应卡片 (ORPHAN_OUTPUT)。
     提示指引：若为 L0 纯文本即时问答产出，归档至 草稿箱/ ；若有代码/文档交付物，升级为 L1/L2 建卡。
  6. 交付前置周期 (Lead Time) 与防冲卡: 校验开工与结束时间 (TIME_SKEW_INSTANT)

典型用法:
  python3 scripts/heartbeat.py
  python3 scripts/heartbeat.py --config config/workflow.config.yaml --json
  python3 scripts/heartbeat.py --stale-in-progress-hours 12
"""
import os
import sys
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.boards.board_adapter_factory import get_board_adapter
from _lib.metrics.heartbeat_engine import (
    DEFAULT_THRESHOLDS,
    _get_status_entry_time,
    _parse_dt,
    _now,
    _normalize_record,
    run_heartbeat,
    format_progress_bar,
)


def main():
    parser = argparse.ArgumentParser(description="看板全局大盘与健康巡检 (Status & Health Check)")
    parser.add_argument("--config", default=None, help="看板配置文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--sync-pr", action="store_true", help="自动同步并解除已合入 PR 的阻塞状态")
    parser.add_argument("--stale-in-progress-hours", type=int, help="覆盖默认 24h 滞留阈值")
    parser.add_argument("--stale-review-or-test-hours", type=int, help="覆盖默认 12h 审查/测试滞留阈值")
    args = parser.parse_args()

    # 1. 若指定 --sync-pr，优先执行 PR 状态同步与解阻
    if args.sync_pr:
        try:
            from sync_pr_status import sync_blocked_prs, format_terminal_summary
            pr_report = sync_blocked_prs(config_path=args.config)
            if not args.json:
                print(format_terminal_summary(pr_report))
                print("\n" + "=" * 80)
        except Exception as e:
            sys.stderr.write(f"[WARN]  PR 状态同步跳过: {e}\n")

    thresholds = dict(DEFAULT_THRESHOLDS)
    if args.stale_in_progress_hours is not None:
        thresholds["stale_in_progress_hours"] = args.stale_in_progress_hours
    if args.stale_review_or_test_hours is not None:
        thresholds["stale_review_or_test_hours"] = args.stale_review_or_test_hours

    try:
        adapter = get_board_adapter(args.config)
    except Exception as e:
        sys.stderr.write(f"[FAILED]  [Heartbeat] 加载看板适配器失败: {e}\n")
        sys.exit(2)

    result = run_heartbeat(adapter, thresholds=thresholds)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        m = result.get("metrics", {})
        print("=" * 80)
        print("       YY-Flow 看板全局大盘与健康巡检 (Status & Health Check)")
        print("=" * 80)
        print(f" 巡检时间: {result['checked_at']}        任务总数: {result['total_tasks']} 项")
        print(f" 总体进度: {format_progress_bar(m.get('completion_rate_pct', 0.0))} (已验收/完成: {m.get('completed', 0)} / 进行中: {m.get('in_progress', 0)} / 已阻塞: {m.get('blocked', 0)})")
        if m.get("avg_lead_time_hours", 0) > 0:
            print(f" 平均交付周期: {m.get('avg_lead_time_hours')} 小时 (Lead Time)")
        print("-" * 80)
        print(" 专家角色在手负载:")
        role_items = [f"{r}: 进{data['in_progress']}/完{data['completed']}" for r, data in sorted(m.get("role_workload", {}).items()) if r != "未分配"]
        for i in range(0, len(role_items), 4):
            print("   " + "   |   ".join(role_items[i:i+4]))
        print("-" * 80)
        print(f"[WARN]   异常告警统计: critical={result['summary']['critical']}  warning={result['summary']['warning']}  info={result['summary']['info']}")
        if not result["alerts"]:
            print(" [SUCCESS]  全部通过, 当前无流转卡点与风险告警")
        else:
            display_limit = 10
            for a in result["alerts"][:display_limit]:
                icon = {"critical": "[CRITICAL] ", "warning": "[WARN] ", "info": ""}.get(a["severity"], "")
                print(f"  {icon} [{a['code']}] {a['message']}")
            if len(result["alerts"]) > display_limit:
                print(f"  ... 剩余 {len(result['alerts']) - display_limit} 项告警已收起，可运行 /yy-flow kanban 在 Web 看板或添加 --json 参数查看全量明细")
        print("=" * 80)

    # 退出码: 0=无告警, 1=有告警, 2=致命错误
    if result["summary"]["critical"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
