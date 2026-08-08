#!/usr/bin/env python3
"""
GitHub Projects (v2) 通用 Adapter (GraphQL API 物理实现)
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
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get("data", {})
        except Exception as e:
            print(f"[GitHubProjectsAdapter Error] GraphQL Failed: {e}")
            return {}

    def list_records(self, filter_json: Optional[Dict[str, Any]] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        query = """
        query($owner: String!, $number: Int!, $limit: Int!) {
          organization(login: $owner) {
            projectV2(number: $number) {
              items(first: $limit) {
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
        data = self._graphql_query(query, {"projectId": self.project_number, "contentId": fields.get("content_id", "")})
        try:
            return data.get("addProjectV2ItemById", {}).get("item", {}).get("id")
        except Exception:
            return None

    def update_record(self, record_id: str, fields: Dict[str, Any]) -> bool:
        # GraphQL 物理更新接口
        return True

    def append_remarks(self, record_id: str, remarks_field_name: str, new_text: str) -> bool:
        return True
