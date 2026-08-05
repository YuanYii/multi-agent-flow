#!/usr/bin/env python3
"""
GitHub Projects (v2) 数据看板通用适配器实现
"""
import os
import json
import urllib.request
from typing import Dict, Any, List, Optional

class GitHubProjectsAdapter:
    def __init__(self, owner: str, project_number: int, github_token: Optional[str] = None):
        self.owner = owner
        self.project_number = project_number
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.github_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def _graphql_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = "https://api.github.com/graphql"
        payload = json.dumps({"query": query, "variables": variables or {}}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers=self._get_headers(), method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f"[GitHubProjectsAdapter Error] GraphQL Query failed: {e}")
            return {}

    def list_records(self, filter_json: Optional[Dict[str, Any]] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """获取 GitHub Projects v2 项目卡片条目"""
        query = """
        query($owner: String!, $number: Int!, $first: Int) {
          user(login: $owner) {
            projectV2(number: $number) {
              items(first: $first) {
                nodes {
                  id
                  fieldValues(first: 20) {
                    nodes {
                      ... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2Field { name } } }
                      ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2SingleSelectField { name } } }
                    }
                  }
                }
              }
            }
          }
        }
        """
        data = self._graphql_query(query, {"owner": self.owner, "number": self.project_number, "first": limit})
        items = data.get("data", {}).get("user", {}).get("projectV2", {}).get("items", {}).get("nodes", [])
        return items

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """获取指定项目卡片详情"""
        records = self.list_records(limit=100)
        for r in records:
            if r.get("id") == record_id:
                return r
        return None

    def update_record(self, record_id: str, fields: Dict[str, Any]) -> bool:
        """更新项目卡片字段 (模拟示意)"""
        print(f"[GitHubProjectsAdapter] Updating record {record_id} with fields: {fields}")
        return True

    def create_record(self, fields: Dict[str, Any]) -> Optional[str]:
        """创建项目卡片 (模拟示意)"""
        print(f"[GitHubProjectsAdapter] Creating record with fields: {fields}")
        return "item_simulated_id"
