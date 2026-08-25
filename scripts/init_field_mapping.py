#!/usr/bin/env python3
"""
自动初始化并校验看板字段映射与环境配置 (Field Mapping CLI)
"""
import os
import sys
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.discovery.field_mapper import discover_feishu_fields


def main():
    parser = argparse.ArgumentParser(description="Skill 配置初始化与字段自动映射脚本")
    parser.add_argument("--base-token", help="飞书 Base Token")
    parser.add_argument("--table-id", help="飞书 Table ID")
    args = parser.parse_args()

    token = args.base_token or os.environ.get("FEISHU_BASE_TOKEN", "")
    table = args.table_id or os.environ.get("FEISHU_TABLE_ID", "")

    if token and table:
        mapping = discover_feishu_fields(token, table)
        print("\n--- 动态扫描获取的字段映射矩阵 ---")
        print(json.dumps(mapping, ensure_ascii=False, indent=2))
    else:
        print("[NOTICE] 未提供 base-token 和 table-id，请设置环境变量或传入参数。")


if __name__ == "__main__":
    main()
