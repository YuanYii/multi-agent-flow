#!/usr/bin/env python3
"""
敏感凭证与硬编码密钥安全扫描脚本 (Check Secrets CLI)
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
WORKFLOW_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

import paths as _paths
from _lib.gates.secrets_checker import SECRET_PATTERNS, scan_file, run_secrets_scan


def main():
    print("========================================================================")
    print("        [GUARD]   Multi-Agent Workflow · 敏感凭证与硬编码密钥安全扫描")
    print("========================================================================")

    data_root = _paths.resolve_data_root()
    total_issues = run_secrets_scan(WORKFLOW_ROOT, data_root)

    print("\n------------------------------------------------------------------------")
    if total_issues > 0:
        print(f"[FAIL] 扫描完成，共发现 {total_issues} 处潜在敏感凭证硬编码！请使用占位符或环境变量替换。")
        sys.exit(1)
    else:
        print("[PASS] 安全扫描通过，未检测到硬编码凭证与敏感私钥。")
        sys.exit(0)


if __name__ == "__main__":
    main()
