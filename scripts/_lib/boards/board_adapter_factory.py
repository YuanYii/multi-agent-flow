#!/usr/bin/env python3
"""
看板适配器统一工厂 (Board Adapter Factory)
严格贯彻 Fail-Closed 原则：当配置文件不存在时拒绝隐式 fallback，物理抛出 FileNotFoundError！
"""
import os
import json
import yaml
from typing import Any
import paths
from _lib.boards.feishu_base_adapter import FeishuBaseAdapter
from _lib.boards.jira_adapter import JiraAdapter
from _lib.boards.github_projects_adapter import GitHubProjectsAdapter
from _lib.boards.offline_board_adapter import OfflineBoardAdapter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

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

def get_board_adapter(config_file: str = None) -> Any:
    """根据 workflow.config.yaml 自动创建并返回适配器实例。

    config_file=None 时走 paths.resolve_runtime_config() 解析链：
    显式路径 > <data_root>/user_data/workflow.config.yaml > <skill>/config/workflow.config.yaml (legacy)
    """
    if config_file is None:
        config_file = paths.resolve_runtime_config()
    if not os.path.exists(config_file):
        raise FileNotFoundError(
            f"[FAILED]  [Fail-Closed 物理拦截] 无法找到指定的看板配置文件: '{config_file}'！\n"
            f"解析链已尝试: <data_root>/user_data/workflow.config.yaml 与 <skill>/config/workflow.config.yaml。\n"
            f"请先执行初始化 (init_skill.sh step 4) 生成宿主配置，或显式传 --config。"
        )

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 物理硬校验：调用 config.schema.json 执行 Schema 格式验证
    schema_file = os.path.join(paths.skill_root(), "config", "config.schema.json")
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
        # 离线看板：相对路径锚定 data_root（宿主项目根 / legacy skill 拷贝），不再锚定 skill_root
        raw_board_file = board_cfg.get("board_file", "user_data/board.json")
        if not os.path.isabs(raw_board_file):
            data_root = paths.resolve_data_root()
            board_file = os.path.abspath(os.path.join(data_root, raw_board_file))
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
