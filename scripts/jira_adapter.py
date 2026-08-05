#!/usr/bin/env python3
"""
Jira 数据看板通用适配器实现
"""
import os
import json
import urllib.request
import urllib.parse
import base64
from typing import Dict, Any, List, Optional

class JiraAdapter:
    def __init__(self, domain: str, project_key: str, user_email: Optional[str] = None, api_token: Optional[str] = None):
        self.domain = domain.rstrip('/')
        self.project_key = project_key
        self.user_email = user_email or os.environ.get("JIRA_USER_EMAIL", "")
        self.api_token = api_token or os.environ.get("JIRA_API_TOKEN", "")

    def _get_headers(self) -> Dict[str, str]:
        auth_str = f"{self.user_email}:{self.api_token}"
        b64_auth = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
        return {
            "Authorization": f"Basic {b64_auth}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def list_records(self, filter_json: Optional[Dict[str, Any]] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """按 JQL 查询 Jira 问题列表"""
        jql = f"project = '{self.project_key}'"
        if filter_json and "conditions" in filter_json:
            for cond in filter_json["conditions"]:
                f_name = cond.get("field_name")
                val = cond.get("value", [""])[0]
                if f_name and val:
                    jql += f" AND '{f_name}' = '{val}'"
        
        url = f"{self.domain}/rest/api/3/search?jql={urllib.parse.quote(jql)}&startAt={offset}&maxResults={limit}"
        req = urllib.request.Request(url, headers=self._get_headers())
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get("issues", [])
        except Exception as e:
            print(f"[JiraAdapter Error] list_records failed: {e}")
            return []

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """获取指定 issue_id 的记录"""
        url = f"{self.domain}/rest/api/3/issue/{record_id}"
        req = urllib.request.Request(url, headers=self._get_headers())
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f"[JiraAdapter Error] get_record failed: {e}")
            return None

    def update_record(self, record_id: str, fields: Dict[str, Any]) -> bool:
        """更新 Jira issue 字段"""
        url = f"{self.domain}/rest/api/3/issue/{record_id}"
        payload = json.dumps({"fields": fields}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers=self._get_headers(), method="PUT")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status in (200, 204)
        except Exception as e:
            print(f"[JiraAdapter Error] update_record failed: {e}")
            return False

    def create_record(self, fields: Dict[str, Any]) -> Optional[str]:
        """新建 Jira Issue"""
        url = f"{self.domain}/rest/api/3/issue"
        fields["project"] = {"key": self.project_key}
        payload = json.dumps({"fields": fields}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers=self._get_headers(), method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get("key") or data.get("id")
        except Exception as e:
            print(f"[JiraAdapter Error] create_record failed: {e}")
            return None
