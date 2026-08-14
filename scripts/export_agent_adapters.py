#!/usr/bin/env python3
"""
Antigravity 官方 Subagent 格式转换与导出脚本 (Official Subagent Exporter)
遵循 Google Antigravity 官方子代理标准路径规范：
项目级: {workspace}/.agents/agents/{agent_name}/agent.md
全局级: ~/.gemini/config/agents/{agent_name}/agent.md
Frontmatter 必须标记 subagent: true
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
    "01-pm.yaml": {"id": "flow-pm", "role_code": "pm", "name": "严经理 (项目经理)"},
    "02-architect.yaml": {"id": "flow-architect", "role_code": "architect", "name": "钱架构 (系统架构师)"},
    "03-dev.yaml": {"id": "flow-dev", "role_code": "dev", "name": "李开发 (开发工程师)"},
    "04-reviewer.yaml": {"id": "flow-reviewer", "role_code": "reviewer", "name": "周审查 (代码审查专家)"},
    "05-qa.yaml": {"id": "flow-qa", "role_code": "qa", "name": "章测试 (测试工程师)"},
    "06-docs.yaml": {"id": "flow-docs", "role_code": "docs", "name": "李文通 (文档工程师)"},
    "07-devops.yaml": {"id": "flow-devops", "role_code": "devops", "name": "吕改特 (运维管理员)"},
}

def load_agent_yaml(filename):
    filepath = os.path.join(AGENTS_DIR, filename)
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def generate_official_agent_md(data, meta):
    """按照 Antigravity 官方 Frontmatter 规范生成 agent.md 内容"""
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

    # 官方核心 Frontmatter 格式，必须包含 subagent: true
    content = f"""---
name: {agent_id}
role: {role}
subagent: true
description: multi-agent-flow 中的 {name} 专家子代理
---

#  Antigravity 官方专家 Agent 角色：{name} ({agent_id})

##  核心职责
{resp_str}

##  当前技术栈配置
{tech_str}

##  允许推导的状态流转矩阵
{trans_str}

##  行为边界与红线
- 允许编码 (can_code): {boundaries.get('can_code', False)}
- 允许直接审批终态 (can_approve): {boundaries.get('can_approve', False)}
- 遵守项目通用规范：路径深度≤3，Markdown 附带 Frontmatter 标头，过程草稿存入 `.drafts/`。
"""
    return content

def export_official_subagents(global_mode=False):
    if global_mode:
        home = os.path.expanduser("~")
        base_agents_dir = os.path.join(home, ".gemini", "config", "agents")
        mode_str = "全局级别 (~/.gemini/config/agents/)"
    else:
        base_agents_dir = os.path.join(TARGET_PROJECT_DIR, ".agents", "agents")
        mode_str = "项目工作区级别 ({workspace}/.agents/agents/)"

    print(f"[SCAN]  [Antigravity 官方 Subagent 导出器] 导出至 {mode_str}...")

    os.makedirs(base_agents_dir, exist_ok=True)
    summary = []

    for yaml_file, meta in ROLES_MAP.items():
        data = load_agent_yaml(yaml_file)
        if not data:
            continue

        agent_folder = os.path.join(base_agents_dir, meta["id"])
        os.makedirs(agent_folder, exist_ok=True)
        
        agent_file = os.path.join(agent_folder, "agent.md")
        content = generate_official_agent_md(data, meta)

        with open(agent_file, "w", encoding="utf-8") as f:
            f.write(content)

        summary.append(f"  - 子代理 `{meta['id']}` -> 写出至 `{os.path.relpath(agent_file, TARGET_PROJECT_DIR)}` (标头已声明 subagent: true)")

    print("[SUCCESS]  [Antigravity 官方规范导出完成] 包含 subagent: true 标头的 7 大专家已全量就绪：")
    for s in summary:
        print(s)

def main():
    parser = argparse.ArgumentParser(description="Antigravity 官方 Subagent 导出构建器")
    parser.add_argument("--global", dest="global_mode", action="store_true", help="导出至全局配置目录 ~/.gemini/config/agents/")
    args = parser.parse_args()

    export_official_subagents(global_mode=args.global_mode)

if __name__ == "__main__":
    main()
