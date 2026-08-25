"""
飞书等远程看板字段自动探测与映射核心模块
"""
import os
import json
import subprocess
from typing import Dict, Any


def discover_feishu_fields(base_token: str, table_id: str) -> Dict[str, str]:
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
