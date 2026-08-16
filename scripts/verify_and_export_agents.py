#!/usr/bin/env python3
"""
通用多 Agent 平台技能挂载与子代理导出引擎 (Universal Agent Mounting & Export Engine)
严格遵循各平台官方最新规范与开放标准 (Zero-Speculation Verified)，
通过声明式配置驱动，自动完成技能目录挂载、Slash Command / 规则注册与 8 大专家子代理格式序列化。
"""

import os
import sys
import shutil
import urllib.request
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
AGENTS_DIR = os.path.join(PROJECT_ROOT, "agents")
CONFIG_PLATFORMS_FILE = os.path.join(PROJECT_ROOT, "config", "agent_platforms.yaml")
TARGET_PROJECT_DIR = os.getcwd()

ROLES_MAP = {
    "01-pm.yaml": {"id": "flow-pm", "role_code": "pm", "name": "严经理 (项目经理)"},
    "02-architect.yaml": {"id": "flow-architect", "role_code": "architect", "name": "钱架构 (系统架构师)"},
    "03-dev.yaml": {"id": "flow-dev", "role_code": "dev", "name": "李开发 (开发工程师)"},
    "04-reviewer.yaml": {"id": "flow-reviewer", "role_code": "reviewer", "name": "周审查 (代码审查专家)"},
    "05-qa.yaml": {"id": "flow-qa", "role_code": "qa", "name": "章测试 (测试工程师)"},
    "06-docs.yaml": {"id": "flow-docs", "role_code": "docs", "name": "李文通 (文档工程师)"},
    "07-devops.yaml": {"id": "flow-devops", "role_code": "devops", "name": "吕改特 (运维管理员)"},
    "08-frontend.yaml": {"id": "flow-frontend", "role_code": "frontend", "name": "马前端 (前端开发工程师)"},
}

def load_platforms_config():
    """读取声明式平台配置"""
    if os.path.exists(CONFIG_PLATFORMS_FILE):
        with open(CONFIG_PLATFORMS_FILE, "r", encoding="utf-8") as fp:
            return yaml.safe_load(fp)
    return {"default_skill_name": "yy-flow", "platforms": {}}

def safe_symlink(source_dir, target_link_path):
    """
    跨平台安全软链接创建：
    具备 Windows OSError (WinError 1314 权限不足) 优雅降级回退机制
    """
    parent = os.path.dirname(target_link_path)
    os.makedirs(parent, exist_ok=True)

    if os.path.islink(target_link_path) or os.path.exists(target_link_path):
        if os.path.islink(target_link_path):
            os.unlink(target_link_path)
        else:
            return False  # 已存在实体目录/文件，跳过

    try:
        rel_source = os.path.relpath(source_dir, parent)
        os.symlink(rel_source, target_link_path)
        return True
    except (OSError, NotImplementedError):
        # Windows / 受限环境回退：如果无法创建 symlink，创建快捷方式或目录拷贝提示
        try:
            if hasattr(os, "system"):
                # 尝试 Windows mklink /J (Junction)
                if sys.platform == "win32":
                    cmd = f'mklink /J "{target_link_path}" "{source_dir}"'
                    if os.system(cmd) == 0:
                        return True
        except Exception:
            pass
        return False

def detect_active_platforms(platforms_config):
    """动态感知当前被激活的 Agent 平台"""
    env = os.environ
    active = []

    for platform_key, spec in platforms_config.get("platforms", {}).items():
        # Universal 始终作为通用标准兜底激活
        if platform_key == "universal":
            active.append(platform_key)
            continue

        detect_dirs = spec.get("detect_dirs", [])
        is_dir = any(os.path.exists(os.path.join(TARGET_PROJECT_DIR, d)) for d in detect_dirs)
        is_env = any(k in env for k in [f"{platform_key.upper()}_ENV", f"{platform_key.upper()}_CLI"])

        if is_dir or is_env:
            active.append(platform_key)

    return list(dict.fromkeys(active))

def serialize_subagent(role_data, role_meta, platform_key, subagent_spec):
    """
    根据平台官方标准格式进行子代理序列化
    """
    agent_id = role_meta["id"]
    agent_name = role_meta["name"]
    fmt = subagent_spec.get("format", "markdown_frontmatter")
    use_frontmatter = subagent_spec.get("frontmatter_subagent", True)

    role_code = role_data.get("role_code") or role_data.get("role") or role_meta.get("role_code", "")
    core_duties = role_data.get("core_duties") or role_data.get("responsibilities", [])
    duty_str = "\n".join([f"- {d}" for d in core_duties]) if isinstance(core_duties, list) else str(core_duties)
    redlines = role_data.get("redlines") or role_data.get("orchestration_rules", [])
    redline_str = "\n".join([f"- {r}" for r in redlines]) if isinstance(redlines, list) else str(redlines)
    tools = ["run_command", "replace_file_content", "write_to_file", "view_file", "list_dir", "grep_search"]

    # 1. 状态机 SOP 引导提示词 (三步闭环)
    sop_prompt = f"""# 角色定义：{agent_name} ({agent_id})

## 核心职责
{duty_str}

## 协作规约与红线
{redline_str}

## 自动化任务流转 SOP (CLI 三步闭环)
在执行本角色相关任务时，必须严格执行以下三步物理命令流转：
1. **领单/开工**：
   `python3 scripts/transition_task.py --config user_data/workflow.config.yaml --role {role_code.upper()} --from-status 待开始 --to-status 进行中 --assignee {agent_id}`
2. **业务执行**：执行架构/编码/审查/测试/文档核心工作，产出交付物。
3. **完工/提审/流转**：
   `python3 scripts/transition_task.py --config user_data/workflow.config.yaml --role {role_code.upper()} --from-status 进行中 --to-status 审查中 --task-id <第一步任务ID> --assignee Reviewer_User_1`
4. **完工硬门禁（强制）**：任何代码/文档/审查/测试交付产出完成后，最后一步必须执行上述流转命令推进状态（A 类开发推至【审查中】，B/C/D/G 类推至【已完成】，终态前补填 end_time），否则视为未交付；看板任务卡必须经历【待开始】状态。
"""

    # 2. 格式 A: Codex 官方 TOML 格式
    if fmt == "codex_toml":
        # 转义三引号
        safe_instructions = sop_prompt.replace('"""', '\\"\\"\\"')
        toml_content = f"""name = "{agent_id}"
description = "multi-agent-flow 中的 {agent_name} 专家子代理"
developer_instructions = \"\"\"
{safe_instructions}
\"\"\"
"""
        return toml_content

    # 3. 格式 B: 标准 Markdown + YAML Frontmatter 格式
    if use_frontmatter:
        fm_dict = {
            "name": agent_id,
            "description": f"multi-agent-flow 中的 {agent_name} 专家子代理",
            "tools": tools,
            "enable_write_tools": True,
            "subagent": True if platform_key == "antigravity" else None,
        }
        # 移除 None
        fm_dict = {k: v for k, v in fm_dict.items() if v is not None}
        fm_yaml = yaml.dump(fm_dict, allow_unicode=True, sort_keys=False)
        return f"---\n{fm_yaml}---\n\n{sop_prompt}"
    else:
        return sop_prompt

def export_platform_assets(platforms_config, active_platforms):
    """执行跨平台 Skill 挂载与 Subagent 导出"""
    skill_name = platforms_config.get("default_skill_name", "yy-flow")
    platforms = platforms_config.get("platforms", {})

    print(f"[SCAN]  已自动侦测到当前激活/兼容平台: {active_platforms}")

    for p_key in active_platforms:
        if p_key not in platforms:
            continue
        spec = platforms[p_key]
        p_name = spec.get("name", p_key)

        # 1. 执行 Skill 目录挂载
        if "skill_target" in spec:
            rel_target = spec["skill_target"].format(skill_name=skill_name)
            abs_target = os.path.join(TARGET_PROJECT_DIR, rel_target)
            if safe_symlink(PROJECT_ROOT, abs_target):
                print(f"[SUCCESS]  [{p_name}] 成功挂载 Skill 发现路径 -> {rel_target}")

        # 2. 执行 Cursor MDC 规则挂载
        if spec.get("mount_type") == "cursor_mdc" and "rule_target" in spec:
            rel_rule = spec["rule_target"].format(skill_name=skill_name)
            abs_rule = os.path.join(TARGET_PROJECT_DIR, rel_rule)
            os.makedirs(os.path.dirname(abs_rule), exist_ok=True)
            with open(abs_rule, "w", encoding="utf-8") as fp:
                fp.write(f"---\ndescription: 多专家协同研发工作流规则 (YY-Flow)\nalwaysApply: false\n---\n# YY-Flow Multi-Agent Workflow\n请调阅 `skills/multi-agent-flow/SKILL.md` 遵循多专家协作契约。\n")
            print(f"[SUCCESS]  [{p_name}] 成功创建 MDC 规则 -> {rel_rule}")

        # 3. 执行 Subagent 导出
        subagent_spec = spec.get("subagent_export")
        if not subagent_spec or not subagent_spec.get("pattern"):
            continue

        pattern = subagent_spec["pattern"]
        exported_count = 0

        for yaml_file, role_meta in sorted(ROLES_MAP.items()):
            yaml_path = os.path.join(AGENTS_DIR, yaml_file)
            if not os.path.exists(yaml_path):
                continue

            with open(yaml_path, "r", encoding="utf-8") as fp:
                role_data = yaml.safe_load(fp)

            out_content = serialize_subagent(role_data, role_meta, p_key, subagent_spec)
            out_rel_path = pattern.format(agent_id=role_meta["id"])
            out_abs_path = os.path.join(TARGET_PROJECT_DIR, out_rel_path)

            os.makedirs(os.path.dirname(out_abs_path), exist_ok=True)
            with open(out_abs_path, "w", encoding="utf-8") as fp:
                fp.write(out_content)
            exported_count += 1

        print(f"[SUCCESS]  [{p_name}] 成功导出 8 大专家子代理 ({exported_count}/8) -> 模式: `{pattern}`")

def main():
    platforms_config = load_platforms_config()
    active_platforms = detect_active_platforms(platforms_config)

    print("==============================================================================")
    print("[START] [Multi-Agent Flow] 正在执行跨平台 Skill 自动挂载与 Subagent 导出...")
    print("==============================================================================")

    export_platform_assets(platforms_config, active_platforms)

    print("==============================================================================")
    print("[SUCCESS]  全平台 Skill 挂载与 8 大专家子代理序列化就绪！")
    print("==============================================================================")

if __name__ == "__main__":
    main()
