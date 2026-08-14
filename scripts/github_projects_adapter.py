#!/usr/bin/env python3
"""
GitHub Projects (v2) 通用 Adapter (严格 Fail-Closed 原则真实 GraphQL API 物理实现)
彻底拔除任何硬编码 return True 或退化判成功逻辑，未配置 Token 或 GraphQL 发送失败强行返回 False！
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
        if not self.github_token:
            print("[GitHubProjectsAdapter Error] 缺少 GITHUB_TOKEN 凭证，拒绝对 GitHub 执行物理 GraphQL 操作。")
            return {}

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
        content_id = fields.get("content_id")
        project_id = fields.get("project_id")
        if not content_id or not project_id:
            print("[GitHubProjectsAdapter Error] create_record 缺少必要的 content_id 或 project_id。")
            return None

        query = """
        mutation($projectId: ID!, $contentId: ID!) {
          addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
            item { id }
          }
        }
        """
        data = self._graphql_query(query, {"projectId": project_id, "contentId": content_id})
        try:
            return data.get("addProjectV2ItemById", {}).get("item", {}).get("id")
        except Exception:
            return None

    def update_record(self, record_id: str, fields: Dict[str, Any]) -> bool:
        """物理级 GraphQL 状态更新，贯彻 Fail-Closed：若缺少参数或 Mutation 失败严格 return False"""
        project_id = fields.get("project_id") or os.environ.get("GITHUB_PROJECT_ID", "")
        status_field_id = fields.get("status_field_id")
        status_option_id = fields.get("status_option_id")

        if not project_id or not status_field_id or not status_option_id:
            print(f"[GitHubProjectsAdapter Error] update_record 缺少必需参数 (project_id, status_field_id, status_option_id)。拦截假成功更新！")
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
        variables = {
            "projectId": project_id,
            "itemId": record_id,
            "fieldId": status_field_id,
            "value": {"singleSelectOptionId": status_option_id}
        }
        res = self._graphql_query(query, variables)
        success = "updateProjectV2ItemFieldValue" in res
        if not success:
            print(f"[GitHubProjectsAdapter Error] updateProjectV2ItemFieldValue Mutation 物理执行未返回成功状态。")
        return success

    def append_remarks(self, record_id: str, remarks_field_name: str, new_text: str) -> bool:
        """真实物理级追加描述/缺陷备注 GraphQL 写入，贯彻 Fail-Closed 原则"""
        # 注意：若未配置项目 ID 和字段 ID 参数，坚决硬拦截返回 False，决不隐式假成功放行！
        project_id = os.environ.get("GITHUB_PROJECT_ID")
        remarks_field_id = os.environ.get("GITHUB_REMARKS_FIELD_ID")

        if not project_id or not remarks_field_id:
            print(f"[GitHubProjectsAdapter Error] append_remarks 缺少 GITHUB_PROJECT_ID 或 GITHUB_REMARKS_FIELD_ID 环境变量凭据。已阻断写入！")
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
        variables = {
            "projectId": project_id,
            "itemId": record_id,
            "fieldId": remarks_field_id,
            "value": {"text": f"[SYNC]  [多专家工作流追加] {new_text}"}
        }
        res = self._graphql_query(query, variables)
        success = "updateProjectV2ItemFieldValue" in res
        if not success:
            print(f"[GitHubProjectsAdapter Error] append_remarks 物理写卡失败。")
        return success
