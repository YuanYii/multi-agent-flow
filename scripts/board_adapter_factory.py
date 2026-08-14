#!/usr/bin/env python3
"""
看板适配器统一工厂 (Board Adapter Factory)
严格贯彻 Fail-Closed 原则：当配置文件不存在时拒绝隐式 fallback，物理抛出 FileNotFoundError！
"""
import os
import json
import yaml
from typing import Any
from feishu_base_adapter import FeishuBaseAdapter
from jira_adapter import JiraAdapter
from github_projects_adapter import GitHubProjectsAdapter
from offline_board_adapter import OfflineBoardAdapter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "..", "config", "workflow.config.yaml")

def exponential_backoff_retry(max_retries: int = 3, initial_delay: float = 1.0):
    """通用 API 请求指数退避重试装饰器"""
    import time
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries:
                        raise e
                    print(f"[WARN]  [网络重试退避] 第 {attempt} 次请求失败 ({e})，将在 {delay} 秒后发起重试...")
                    time.sleep(delay)
                    delay *= 2
        return wrapper
    return decorator

def get_board_adapter(config_file: str = CONFIG_PATH) -> Any:
    """根据 workflow.config.yaml 自动创建并返回适配器实例"""
    if not os.path.exists(config_file):
        raise FileNotFoundError(
            f"[FAILED]  [Fail-Closed 物理拦截] 无法找到指定的看板配置文件: '{config_file}'！\n"
            f"请核验路径是否正确，或先从 config/workflow.config.template.yaml 复制生成对应配置。"
        )

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 物理硬校验：调用 config.schema.json 执行 Schema 格式验证
    schema_file = os.path.join(SCRIPT_DIR, "..", "config", "config.schema.json")
    if os.path.exists(schema_file):
        try:
            import jsonschema
            with open(schema_file, "r", encoding="utf-8") as sf:
                schema_data = json.load(sf)
            jsonschema.validate(instance=config, schema=schema_data)
        except ImportError:
            pass
        except Exception as se:
            raise ValueError(f"[FAILED]  [Schema 物理断言拦截] 看板配置违反 config.schema.json 规范: {se}")

    board_cfg = config.get("board", {})
    provider = board_cfg.get("provider", "feishu_base").lower()

    if provider == "local":
        # 离线看板：默认持久化在宿主工程 user_data/ 目录下，解耦静态代码
        raw_board_file = board_cfg.get("board_file", "user_data/board.json")
        if not os.path.isabs(raw_board_file):
            skill_root = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
            board_file = os.path.abspath(os.path.join(skill_root, raw_board_file))
        else:
            board_file = raw_board_file
        os.makedirs(os.path.dirname(board_file), exist_ok=True)
        return OfflineBoardAdapter(board_file=board_file, field_map=board_cfg.get("fields", {}))

    elif provider == "feishu_base":
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
