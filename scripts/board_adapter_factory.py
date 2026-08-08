#!/usr/bin/env python3
"""
看板适配器统一工厂 (Board Adapter Factory)
严格贯彻 Fail-Closed 原则：当配置文件不存在时拒绝隐式 fallback，物理抛出 FileNotFoundError！
"""
import os
import yaml
from typing import Any
from feishu_base_adapter import FeishuBaseAdapter
from jira_adapter import JiraAdapter
from github_projects_adapter import GitHubProjectsAdapter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "..", "config", "workflow.config.yaml")

def get_board_adapter(config_file: str = CONFIG_PATH) -> Any:
    """根据 workflow.config.yaml 自动创建并返回适配器实例"""
    if not os.path.exists(config_file):
        raise FileNotFoundError(
            f"❌ [Fail-Closed 物理拦截] 无法找到指定的看板配置文件: '{config_file}'！\n"
            f"请核验路径是否正确，或先从 config/workflow.config.template.yaml 复制生成对应配置。"
        )

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    board_cfg = config.get("board", {})
    provider = board_cfg.get("provider", "feishu_base").lower()

    if provider == "feishu_base":
        base_token = board_cfg.get("base_token", "")
        table_id = board_cfg.get("table_id", "")
        return FeishuBaseAdapter(base_token=base_token, table_id=table_id)

    elif provider == "jira":
        domain = board_cfg.get("domain", "https://your-domain.atlassian.net")
        project_key = board_cfg.get("project_key", "PROJ")
        return JiraAdapter(domain=domain, project_key=project_key)

    elif provider == "github_projects":
        owner = board_cfg.get("owner", "org")
        project_number = int(board_cfg.get("project_number", 1))
        return GitHubProjectsAdapter(owner=owner, project_number=project_number)

    else:
        raise ValueError(f"不支持的看板提供商: {provider}")

if __name__ == "__main__":
    try:
        adapter = get_board_adapter()
        print(f"[BoardAdapterFactory SUCCESS] 已成功加载适配器: {adapter.__class__.__name__}")
    except Exception as e:
        print(f"[BoardAdapterFactory ERROR]: {e}")
