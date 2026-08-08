#!/usr/bin/env python3
"""
Jira 看板通用 Adapter (REST API 物理实现)
"""
import os
import json
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional


class JiraAdapter:
    def __init__(self, domain: str, project_key: str, user_email: str = None, api_token: str = None):
        self.domain = domain.rstrip('/')
        self.project_key = project_key
        self.user_email = user_email or os.environ.get("JIRA_USER_EMAIL", "")
        self.api_token = api_token or os.environ.get("JIRA_API_TOKEN", "")

    def _headers(self) -> Dict[str, str]:
        import base64
        auth_str = f"{self.user_email}:{self.api_token}"
        encoded_auth = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
        return {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def list_records(self, filter_json: Optional[Dict[str, Any]] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        jql = f"project = '{self.project_key}'"
        if filter_json and "jql" in filter_json:
            jql += f" AND ({filter_json['jql']})"

        url = f"{self.domain}/rest/api/3/search?jql={urllib.parse.quote(jql)}&maxResults={limit}&startAt={offset}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get("issues", [])
        except Exception as e:
            print(f"[JiraAdapter Error] list_records failed: {e}")
            return []

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        url = f"{self.domain}/rest/api/3/issue/{record_id}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f"[JiraAdapter Error] get_record failed: {e}")
            return None

    def create_record(self, fields: Dict[str, Any]) -> Optional[str]:
        url = f"{self.domain}/rest/api/3/issue"
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": fields.get("task_name", "New Task"),
                "issuetype": {"name": "Task"},
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": fields.get("process_desc", "")}]
                    }]
                }
            }
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get("key") or data.get("id")
        except Exception as e:
            print(f"[JiraAdapter Error] create_record failed: {e}")
            return None

    def update_record(self, record_id: str, fields: Dict[str, Any]) -> bool:
        url = f"{self.domain}/rest/api/3/issue/{record_id}"
        payload = {"fields": {}}
        if "task_name" in fields:
            payload["fields"]["summary"] = fields["task_name"]

        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=self._headers(), method="PUT")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status in [200, 204]
        except Exception as e:
            print(f"[JiraAdapter Error] update_record failed: {e}")
            return False

    def append_remarks(self, record_id: str, remarks_field_name: str, new_text: str) -> bool:
        """追加 Jira 结构化 Comment 注释"""
        url = f"{self.domain}/rest/api/3/issue/{record_id}/comment"
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": f"🔄 [多专家工作流追加] {new_text}"}]
                }]
            }
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status in [200, 201]
        except Exception as e:
            print(f"[JiraAdapter Error] append_remarks failed: {e}")
            return False
