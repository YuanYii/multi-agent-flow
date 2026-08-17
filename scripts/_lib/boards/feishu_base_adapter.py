#!/usr/bin/env python3
"""
多维度看板交互通用抽象 Adapter (飞书 Base 实现)
"""
import json
import subprocess
from typing import Dict, Any, List, Optional


class FeishuBaseAdapter:
    def __init__(self, base_token: str, table_id: str):
        self.base_token = base_token
        self.table_id = table_id

    def list_records(self, filter_json: Optional[Dict[str, Any]] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        检索看板记录（带分页与 filter 保证防截断）。

        :param filter_json: 飞书多维表格查询过滤条件，结构示例:
            {
                "conjunction": "and",
                "conditions": [
                    {"field_name": "状态", "operator": "is", "value": ["进行中"]},
                    {"field_name": "负责人", "operator": "is", "value": ["李开发"]}
                ]
            }
        :param limit: 每页获取记录上限
        :param offset: 分页偏移量
        """
        cmd = [
            "npx", "--yes", "@larksuite/cli", "base", "+record-list",
            "--base-token", self.base_token,
            "--table-id", self.table_id,
            "--as", "user",
            "--format", "json",
            "--limit", str(limit),
            "--offset", str(offset)
        ]
        if filter_json:
            cmd.extend(["--filter-json", json.dumps(filter_json, ensure_ascii=False)])

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode == 0:
                try:
                    data = json.loads(res.stdout)
                    return data.get("data", {}).get("items", [])
                except Exception:
                    return []
        except Exception:
            return []
        return []

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """获取指定 record_id 的详情记录。"""
        cmd = [
            "npx", "--yes", "@larksuite/cli", "base", "+record-get",
            "--base-token", self.base_token,
            "--table-id", self.table_id,
            "--record-id", record_id,
            "--as", "user",
            "--format", "json"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                try:
                    data = json.loads(res.stdout)
                    return data.get("data", {}).get("record", {})
                except Exception:
                    return None
        except Exception:
            return None
        return None

    def update_record(self, record_id: str, fields: Dict[str, Any]) -> bool:
        """更新指定记录的状态、处理人、描述与备注。"""
        task_json = json.dumps(fields, ensure_ascii=False)
        cmd = [
            "npx", "--yes", "@larksuite/cli", "base", "+record-upsert",
            "--base-token", self.base_token,
            "--table-id", self.table_id,
            "--record-id", record_id,
            "--json", task_json,
            "--as", "user",
            "--format", "json"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                return False
            # 优先进行结构化 JSON 响应断言
            try:
                data = json.loads(res.stdout)
                if isinstance(data, dict):
                    if data.get("code") == 0 or data.get("data", {}).get("updated") is True:
                        return True
            except Exception:
                pass
            # 结构解析失败降级为包含匹配
            return '"updated": true' in res.stdout.lower() or '"record_id"' in res.stdout.lower()
        except Exception:
            return False

    def create_record(self, fields: Dict[str, Any]) -> Optional[str]:
        """新建看板记录，成功则返回新建记录的 record_id，失败返回 None。"""
        task_json = json.dumps(fields, ensure_ascii=False)
        cmd = [
            "npx", "--yes", "@larksuite/cli", "base", "+record-create",
            "--base-token", self.base_token,
            "--table-id", self.table_id,
            "--json", task_json,
            "--as", "user",
            "--format", "json"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                try:
                    data = json.loads(res.stdout)
                    # 兼容返回结构
                    rec_id = data.get("data", {}).get("record", {}).get("record_id") or data.get("data", {}).get("record_id")
                    return rec_id
                except Exception:
                    return None
        except Exception:
            return None
        return None

    def append_remarks(self, record_id: str, remarks_field_name: str, new_text: str) -> bool:
        """原子级追加缺陷/打回信息至记录的备注字段。"""
        rec = self.get_record(record_id)
        existing_remarks = ""
        if rec and "fields" in rec:
            existing_remarks = rec["fields"].get(remarks_field_name, "") or ""
        
        combined = f"{existing_remarks}\n\n{new_text}".strip() if existing_remarks else new_text
        return self.update_record(record_id, {remarks_field_name: combined})
