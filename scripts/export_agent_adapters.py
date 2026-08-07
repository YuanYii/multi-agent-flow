#!/usr/bin/env python3
"""
通用动态 Agent 专家构建器 (Universal Dynamic Agent Subagent Builder)
解耦写死的平台配置。在初始化时动态探测/感知当前运行的 Agent 环境，
仅为检测到的当前 Agent 按需创建对应的子 Agent 规则目录与 Prompt，杜绝预建无关文件夹污染根目录。
"""

import os
import sys
import yaml
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
AGENTS_DIR = os.path.join(PROJECT_ROOT, "agents")
TARGET_PROJECT_DIR = os.getcwd()

ROLES_MAP = {
    "01-pm.yaml": {"id": "flow-pm", "role_code": "pm", "name": "项目经理"},
    "02-architect.yaml": {"id": "flow-architect", "role_code": "architect", "name": "系统架构师"},
    "03-dev.yaml": {"id": "flow-dev", "role_code": "dev", "name": "开发工程师"},
    "04-reviewer.yaml": {"id": "flow-reviewer", "role_code": "reviewer", "name": "代码审查员"},
    "05-qa.yaml": {"id": "flow-qa", "role_code": "qa", "name": "测试工程师"},
    "06-docs.yaml": {"id": "flow-docs", "role_code": "docs", "name": "文档工程师"},
    "07-devops.yaml": {"id": "flow-devops", "role_code": "devops", "name": "运维管理员"},
}

def inspect_active_agent_environment():
    """
    通用环境探针：结合环境变量与工作区已有配置特征，
    动态推导当前项目实际启用的 Agent 环境与目标子 Agent 规则输出规范。
    """
    env = os.environ
    active_targets = {}

    # 1. 通用规则映射集 (通用探针字典)
    spec_rules = [
        {"env_keys": ["CLAUDE_CODE", "CLAUDE_PROJECT_DIR"], "dir_flag": ".claude", "rel_path": os.path.join(".claude", "prompts"), "ext": ".md", "syntax": "/"},
        {"env_keys": ["CURSOR_BUILD", "CURSOR_PROJECT_DIR"], "dir_flag": ".cursor", "rel_path": os.path.join(".cursor", "rules"), "ext": ".mdc", "syntax": "@"},
        {"env_keys": ["CODEX_SESSION_ID", "CODEX_CLI"], "dir_flag": ".codex", "rel_path": os.path.join(".codex", "agents"), "ext": ".md", "syntax": "/"},
        {"env_keys": ["PI_DEV", "PI_HOME"], "dir_flag": ".pi", "rel_path": os.path.join(".pi", "agents"), "ext": ".md", "syntax": "/"},
        {"env_keys": ["OPENCODE_ENV", "OPENCODE"], "dir_flag": ".opencode", "rel_path": os.path.join(".opencode", "agents"), "ext": ".md", "syntax": "/"},
        {"env_keys": ["WINDSURF_WORKSPACE"], "dir_flag": ".windsurf", "rel_path": os.path.join(".windsurf", "rules"), "ext": ".md", "syntax": "@"},
        {"env_keys": ["COPILOT_WORKSPACE"], "dir_flag": ".github", "rel_path": os.path.join(".github", "prompts"), "ext": ".prompt.md", "syntax": "/"},
    ]

    # 2. 依次评估每一个 Agent 探针
    for spec in spec_rules:
        is_env_active = any(k in env for k in spec["env_keys"])
        is_dir_active = os.path.exists(os.path.join(TARGET_PROJECT_DIR, spec["dir_flag"]))
        
        # 只要环境变量符合，或工作区中已存在该 Agent 的配置文件夹，才认为处于激活态
        if is_env_active or is_dir_active:
            target_dir = os.path.join(TARGET_PROJECT_DIR, spec["rel_path"])
            active_targets[spec["dir_flag"]] = {
                "dir": target_dir,
                "ext": spec["ext"],
                "syntax": spec["syntax"]
            }

    # 3. 兜底逻辑：若没有任何特定的 Agent 环境被检测激活，则仅在 .agents/ 下创建通用副本
    if not active_targets:
        active_targets[".agents"] = {
            "dir": os.path.join(TARGET_PROJECT_DIR, ".agents"),
            "ext": ".md",
            "syntax": "/ 或 @"
        }

    return active_targets

def load_agent_yaml(filename):
    filepath = os.path.join(AGENTS_DIR, filename)
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def generate_agent_prompt(data, meta):
    role = data.get("role", meta["role_code"].upper())
    name = data.get("name", meta["name"])
    agent_id = meta["id"]

    responsibilities = data.get("responsibilities", [])
    tech_stack = data.get("tech_stack", {})
    boundaries = data.get("boundaries", {})
    allowed_transitions = data.get("allowed_transitions", [])

    resp_str = "\n".join([f"- {r}" for r in responsibilities])
    tech_str = "\n".join([f"- **{k}**: {v}" for k, v in tech_stack.items()])
    trans_str = "\n".join([f"- `{t}`" for t in allowed_transitions])

    prompt = f"""---
name: {agent_id}
role: {role}
description: multi-agent-flow 中的 {name} 专家子 Agent 人设与职责定义 (命令: {agent_id})
---

# 🤖 专家 Agent 角色：{name} ({agent_id})

## 🎯 核心职责
{resp_str}

## 🛠️ 当前技术栈配置
{tech_str}

## ⚡ 允许推导的状态流转矩阵
{trans_str}

## 🚫 行为边界与红线
- 允许编码 (can_code): {boundaries.get('can_code', False)}
- 允许直接审批终态 (can_approve): {boundaries.get('can_approve', False)}
- 遵守项目通用规范：路径深度≤3，Markdown 附带 Frontmatter 标头，过程草稿存入 `.drafts/`。
"""
    return prompt

def build_subagents_on_demand(explicit_agent=None, custom_dir=None, custom_syntax="/"):
    print("🔍 [动态 Agent 探针] 开始自动感知当前运行环境...")

    active_targets = {}

    if custom_dir:
        active_targets["custom"] = {
            "dir": os.path.abspath(custom_dir),
            "ext": ".md",
            "syntax": custom_syntax
        }
    else:
        active_targets = inspect_active_agent_environment()

    mounted_summary = []

    for name, info in active_targets.items():
        target_dir = info["dir"]
        ext = info["ext"]
        syntax = info["syntax"]

        os.makedirs(target_dir, exist_ok=True)

        for yaml_file, meta in ROLES_MAP.items():
            data = load_agent_yaml(yaml_file)
            if not data:
                continue
            
            content = generate_agent_prompt(data, meta)
            filename = f"{meta['id']}{ext}"
            out_path = os.path.join(target_dir, filename)

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)

        mounted_summary.append(f"  - 激活环境 [{name}]: 写出至 `{target_dir}` (调用语法: `{syntax}{ROLES_MAP['03-dev.yaml']['id']}`) ")

    print("✅ [子 Agent 规则构建完毕] 已按需为您当前环境创建子 Agent 配置：")
    for s in mounted_summary:
        print(s)

def main():
    parser = argparse.ArgumentParser(description="通用动态 Agent 专家构建器")
    parser.add_argument("--agent", help="显式指定目标 Agent 名称", default=None)
    parser.add_argument("--custom-dir", help="手动指定自定义子 Agent 存放目录", default=None)
    parser.add_argument("--syntax", help="指定调用语法 (如 / 或 @)", default="/")
    args = parser.parse_args()

    build_subagents_on_demand(explicit_agent=args.agent, custom_dir=args.custom_dir, custom_syntax=args.syntax)

if __name__ == "__main__":
    main()
