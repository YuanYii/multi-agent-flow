#!/usr/bin/env python3
"""
自动初始化并校验看板字段映射与环境配置
"""
import os
import json
import argparse
import subprocess


def discover_feishu_fields(base_token: str, table_id: str) -> dict:
    """自动调取飞书 CLI 检索字段列表并建立字段名到 ID 的映射。"""
    cmd = [
        "npx", "--yes", "@larksuite/cli", "base", "+field-list",
        "--base-token", base_token,
        "--table-id", table_id,
        "--as", "user",
        "--format", "json"
    ]
    print(f"[INFO] 正在扫描飞书 Base 表格字段: token={base_token}, table={table_id}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[WARN] 无法调取 @larksuite/cli: {res.stderr}")
        return {}

    try:
        data = json.loads(res.stdout)
        items = data.get("data", {}).get("items", [])
        field_mapping = {item.get("field_name"): item.get("field_id") for item in items}
        print(f"[SUCCESS] 找到 {len(field_mapping)} 个有效看板字段。")
        return field_mapping
    except Exception as e:
        print(f"[ERROR] 解析字段 JSON 失败: {e}")
        return {}


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
