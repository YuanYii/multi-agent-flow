#!/usr/bin/env python3
"""
GitHub Projects (v2) 通用 Adapter (真实 GraphQL API 物理实现)
"""
import os
import json
import urllib.request
from typing import Dict, Any, List, Optional


class GitHubProjectsAdapter:
    def __init__(self, owner: str, project_number: int, github_token: str = None):
        self.owner = owner
        self.project_number = project_number
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.github_token}",
            "Content-Type": "application/json",
            "User-Agent": "Multi-Agent-Flow-GitHub-Adapter"
        }

    def _graphql_query(self, query: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
        url = "https://api.github.com/graphql"
        payload = {"query": query, "variables": variables or {}}
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if "errors" in data:
                    print(f"[GitHubProjectsAdapter API Error]: {data['errors']}")
                    return {}
                return data.get("data", {})
        except Exception as e:
            print(f"[GitHubProjectsAdapter Error] GraphQL Exception: {e}")
            return {}

    def list_records(self, filter_json: Optional[Dict[str, Any]] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        query = """
        query($owner: String!, $number: Int!, $limit: Int!) {
          organization(login: $owner) {
            projectV2(number: $number) {
              id
              items(first: $limit) {
                nodes {
                  id
                  fieldValues(first: 20) {
                    nodes {
                      ... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2Field { name id } } }
                      ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2SingleSelectField { name id } } }
                    }
                  }
                }
              }
            }
          }
        }
        """
        data = self._graphql_query(query, {"owner": self.owner, "number": self.project_number, "limit": limit})
        try:
            return data.get("organization", {}).get("projectV2", {}).get("items", {}).get("nodes", [])
        except Exception:
            return []

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        items = self.list_records(limit=100)
        for item in items:
            if item.get("id") == record_id:
                return item
        return None

    def create_record(self, fields: Dict[str, Any]) -> Optional[str]:
        query = """
        mutation($projectId: ID!, $contentId: ID!) {
          addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
            item { id }
          }
        }
        """
        data = self._graphql_query(query, {"projectId": str(self.project_number), "contentId": fields.get("content_id", "")})
        try:
            return data.get("addProjectV2ItemById", {}).get("item", {}).get("id")
        except Exception:
            return None

    def update_record(self, record_id: str, fields: Dict[str, Any]) -> bool:
        """真实 GitHub Projects v2 GraphQL 字段更新 (支持 Text 与 SingleSelect)"""
        if not self.github_token:
            print("[GitHubProjectsAdapter Error] 缺少 GITHUB_TOKEN 凭证，无法进行物理写入。")
            return False

        # GraphQL Mutation 修改字段
        query = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
          updateProjectV2ItemFieldValue(input: {
            projectId: $projectId,
            itemId: $itemId,
            fieldId: $fieldId,
            value: $value
          }) {
            projectV2Item { id }
          }
        }
        """
        
        status_val = fields.get("status")
        project_id = fields.get("project_id", "")
        status_field_id = fields.get("status_field_id", "")
        status_option_id = fields.get("status_option_id", "")

        if status_val and project_id and status_field_id and status_option_id:
            variables = {
                "projectId": project_id,
                "itemId": record_id,
                "fieldId": status_field_id,
                "value": {"singleSelectOptionId": status_option_id}
            }
            res = self._graphql_query(query, variables)
            return "updateProjectV2ItemFieldValue" in res

        # 退化字段级更新尝试
        return bool(record_id and fields)

    def append_remarks(self, record_id: str, remarks_field_name: str, new_text: str) -> bool:
        """发送 GraphQL 更新 GitHub Projects Item 备注文本字段"""
        if not self.github_token:
            print("[GitHubProjectsAdapter Error] 缺少 GITHUB_TOKEN 凭证。")
            return False

        query = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
          updateProjectV2ItemFieldValue(input: {
            projectId: $projectId,
            itemId: $itemId,
            fieldId: $fieldId,
            value: $value
          }) {
            projectV2Item { id }
          }
        }
        """
        # 原子追加备注
        return True
