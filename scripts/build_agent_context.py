#!/usr/bin/env python3
"""
动态角色 Prompt 上下文裁剪合成器 (Build Agent Context CLI)
"""
import os
import sys
import yaml
import argparse
from typing import Dict, Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKFLOW_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
AGENTS_DIR = os.path.join(WORKFLOW_ROOT, "agents")
RULES_DIR = os.path.join(WORKFLOW_ROOT, "rules")
REFERENCES_DIR = os.path.join(WORKFLOW_ROOT, "references")

def load_role_yaml(role: str) -> Dict[str, Any]:
    role_map = {
        "PM": "01-pm.yaml",
        "ARCHITECT": "02-architect.yaml",
        "DEV": "03-dev.yaml",
        "REVIEWER": "04-reviewer.yaml",
        "QA": "05-qa.yaml",
        "DOCS": "06-docs.yaml",
        "DEVOPS": "07-devops.yaml"
    }
    file_name = role_map.get(role.upper())
    if not file_name:
        return {}
    file_path = os.path.join(AGENTS_DIR, file_name)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def read_markdown_section(filepath: str, max_lines: int = 40) -> str:
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            lines = [line for line in f if line.strip() and not line.startswith('# ')]
            return "".join(lines[:max_lines])
    return ""

def build_context(role: str, action: str = "general") -> str:
    role_upper = role.upper()
    role_data = load_role_yaml(role_upper)

    context_output = []
    context_output.append(f"# 🤖 动态 Agent 裁剪上下文 (Role: {role_upper} | Action: {action})\n")

    # 1. 专家角色专有规则
    if role_data:
        context_output.append("## 1. 专家身份与职责")
        context_output.append(f"- **角色代码**: {role_data.get('role')}")
        context_output.append(f"- **身份名称**: {role_data.get('name')}")
        context_output.append(f"- **并发上限**: {role_data.get('max_parallel_tasks')}")
        context_output.append(f"- **允许自领取**: {role_data.get('can_self_claim')}")
        
        tech = role_data.get("tech_stack", {})
        if tech:
            context_output.append(f"- **技术栈绑定**: {tech}")

        context_output.append("\n**职责清单**:")
        for resp in role_data.get("responsibilities", []):
            context_output.append(f"  - {resp}")

        context_output.append("\n**允许推动的状态流转**:")
        for trans in role_data.get("allowed_transitions", []):
            context_output.append(f"  - {trans}")
        context_output.append("\n")

    # 2. 团队红线（精简版）
    context_output.append("## 2. 团队协作 4 大防错红线 (来自 rules/AGENTS.md)")
    context_output.append("1. **绝对禁止越权修改状态**：未在授权角色集合内严禁推动状态；")
    context_output.append("2. **打回绝对禁止新建编号**：一律在原任务上置为 `已退回` 并追加 `DEF-TXXX-N` 备注；")
    context_output.append("3. **绝对禁止先干后补**：自领取任务必须先将看板状态更至 `进行中` 落库后再编码；")
    context_output.append("4. **绝对禁止孤儿报告**：复审/复测结论直接追加至原报告。")
    context_output.append("\n")

    # 3. 对应 Action 的极简门控提示
    context_output.append(f"## 3. 当前动作 [{action.upper()}] 防错要点")
    if action == "claim":
        context_output.append("- 确认并发任务数 ≤3；")
        context_output.append("- 先通过 API/CLI 更新看板为 `进行中` 并设置 Assignee 为自己。")
    elif action == "submit":
        context_output.append("- 生成/更新开发任务报告；")
        context_output.append("- 更新看板为 `审查中`，处理人同步更改为 `REVIEWER`。")
    elif action == "review":
        context_output.append("- 通关：更至 `测试中`，处理人移交 `QA`；")
        context_output.append("- 打回：更至 `已退回`，处理人改回原负责人，备注写入 `DEF-TXXX-N`。")
    elif action == "test":
        context_output.append("- 通关：更至 `已完成`，处理人移交 `PM`，强制写入结束时间；")
        context_output.append("- 打回：更至 `已退回`，处理人改回原负责人。")
    else:
        context_output.append("- 严格遵守【状态与处理人原子绑定】原则。")

    return "\n".join(context_output)

def main():
    parser = argparse.ArgumentParser(description="动态角色 Prompt 上下文裁剪合成器")
    parser.add_argument("--role", required=True, help="角色代码 (PM|ARCHITECT|DEV|REVIEWER|QA|DOCS|DEVOPS)")
    parser.add_argument("--action", default="general", help="当前动作 (claim|submit|review|test|approve|general)")

    args = parser.parse_args()

    context = build_context(role=args.role, action=args.action)
    print(context)

if __name__ == "__main__":
    main()
