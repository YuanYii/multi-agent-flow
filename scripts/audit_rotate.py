#!/usr/bin/env python3
"""
审计日志轮转 CLI (Audit Log Rotation CLI)
按日切分 + 单文件超 max_size_mb 二次切 + 旧文件 gzip 归档至 logs/archive/。

典型用法:
  # 默认 50MB 阈值,日切分
  python3 scripts/audit_rotate.py

  # 自定义阈值
  python3 scripts/audit_rotate.py --max-size-mb 20

  # dry-run
  python3 scripts/audit_rotate.py --dry-run
"""
import os
import sys
import argparse
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.audit.audit_logger import rotate_if_needed, get_audit_log_file


def main():
    parser = argparse.ArgumentParser(description="审计日志轮转 CLI (日切分 + 大小切分)")
    parser.add_argument("--max-size-mb", type=int, default=50, help="单文件最大体积 (MB, 默认 50)")
    parser.add_argument("--dry-run", action="store_true", help="只预判,不动盘")
    args = parser.parse_args()

    if args.dry_run:
        from _lib.audit.audit_logger import _current_log_date
        audit_log_file = get_audit_log_file()
        if not os.path.exists(audit_log_file):
            print(f"[DRY-RUN] 日志文件不存在: {audit_log_file}")
            return
        size_mb = os.path.getsize(audit_log_file) / (1024 * 1024)
        log_date = _current_log_date()
        from datetime import date
        today = date.today().strftime("%Y%m%d")
        reasons = []
        if log_date is None:
            reasons.append(f"日切分触发 (无日期后缀, 今天={today})")
        if size_mb >= args.max_size_mb:
            reasons.append(f"大小切分触发 ({size_mb:.1f}MB >= {args.max_size_mb}MB)")
        if not reasons:
            print(f"[DRY-RUN] 不需轮转: 当前文件 {size_mb:.2f}MB, 日期 {log_date or '无后缀'}")
        else:
            print(f"[DRY-RUN] 需轮转: {'; '.join(reasons)}")
        return

    result = rotate_if_needed(max_size_mb=args.max_size_mb)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
