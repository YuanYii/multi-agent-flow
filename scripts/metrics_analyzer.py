#!/usr/bin/env python3
"""
看板效能度量与流转诊断分析器 (Kanban Metrics Analyzer CLI)
"""
import os
import sys
import json
import argparse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.boards.board_adapter_factory import get_board_adapter
from _lib.metrics.metrics_calculator import (
    parse_datetime,
    MetricsCalculator,
    TerminalRenderer,
)


def main():
    parser = argparse.ArgumentParser(description="看板效能度量与流转诊断工具")
    parser.add_argument("--config", default=None, help="看板配置文件")
    parser.add_argument("--format", choices=["table", "json", "markdown"], default="table", help="输出格式")
    parser.add_argument("--output", help="输出报告文件路径")
    parser.add_argument("--stale-in-progress-hours", type=int, default=24, help="进行中滞留阈值(小时)")
    parser.add_argument("--stale-review-test-hours", type=int, default=12, help="审查/测试滞留阈值(小时)")

    args = parser.parse_args()

    adapter = get_board_adapter(args.config)
    records = adapter.list_records(limit=1000)

    calc = MetricsCalculator(records)
    summary = calc.compute_summary()
    workload = calc.compute_role_workload()
    bottlenecks = calc.detect_bottlenecks(
        stale_in_progress_hours=args.stale_in_progress_hours,
        stale_review_test_hours=args.stale_review_test_hours
    )

    if args.format == "json":
        result = {
            "summary": summary,
            "workload": workload,
            "bottlenecks": bottlenecks,
            "generated_at": datetime.now().isoformat(),
        }
        content = json.dumps(result, ensure_ascii=False, indent=2)
    elif args.format == "markdown":
        content = TerminalRenderer.render_markdown_report(summary, workload, bottlenecks)
    else:
        content = TerminalRenderer.render_terminal_dashboard(summary, workload, bottlenecks)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[SUCCESS]  度量报告已成功导出至: {args.output}")
    else:
        print(content)


if __name__ == "__main__":
    main()
