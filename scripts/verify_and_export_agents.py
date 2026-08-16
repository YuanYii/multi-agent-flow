#!/usr/bin/env python3
"""
通用多 Agent 平台技能挂载与子代理导出引擎 (Universal Agent Mounting & Export Engine)
按声明式配置驱动，自动完成技能目录挂载、规则注册与 8 大专家子代理格式序列化，
并在导出后执行本地格式断言 (Fail-Closed: 解析失败/角色不齐全即 exit(1))。
"""

import os
import sys
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import paths as _paths
from agent_tech_overlay import load_arch_data, apply_tech_stack_to_role

PROJECT_ROOT = _paths.skill_root()
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

# 各平台官方工具名映射: 导出给对应平台的 subagent 必须使用该平台认识的工具标识
PLATFORM_TOOLS = {
    "claude_code": ["Bash", "Edit", "Read", "Write", "Grep", "Glob"],
    "antigravity": ["run_command", "replace_file_content", "write_to_file", "view_file", "list_dir", "grep_search"],
    "cursor": ["Read", "Edit", "Write", "Bash", "Grep", "Glob"],
    "opencode": ["bash", "edit", "read", "write", "grep", "glob"],
    "zcode": ["run_command", "replace_file_content", "write_to_file", "view_file", "list_dir", "grep_search"],
}
DEFAULT_TOOLS = ["run_command", "replace_file_content", "write_to_file", "view_file", "list_dir", "grep_search"]

def load_platforms_config():
    """读取声明式平台配置"""
    if os.path.exists(CONFIG_PLATFORMS_FILE):
        with open(CONFIG_PLATFORMS_FILE, "r", encoding="utf-8") as fp:
            return yaml.safe_load(fp)
    return {"default_skill_name": "yy-flow", "platforms": {}}

def safe_symlink(source_dir, target_link_path, relative=True):
    """
    跨平台安全软链接创建：
    具备 Windows OSError (WinError 1314 权限不足) 优雅降级回退机制
    relative=False 用于全局挂载（跨卷绝对链更稳健）
    """
    parent = os.path.dirname(target_link_path)
    os.makedirs(parent, exist_ok=True)

    if os.path.islink(target_link_path) or os.path.exists(target_link_path):
        if os.path.islink(target_link_path):
            os.unlink(target_link_path)
        else:
            return False  # 已存在实体目录/文件，跳过

    try:
        link_source = os.path.relpath(source_dir, parent) if relative else os.path.abspath(source_dir)
        os.symlink(link_source, target_link_path)
        return True
    except (OSError, NotImplementedError):
        # Windows / 受限环境回退：如果无法创建 symlink，创建 Junction 或提示
        if sys.platform == "win32":
            cmd = f'mklink /J "{target_link_path}" "{source_dir}"'
            if os.system(cmd) == 0:
                return True
        return False

def detect_active_platforms(platforms_config, global_mode=False):
    """动态感知当前被激活的 Agent 平台。
    global_mode: 用各平台用户级目录（global_detect_dirs，如 ~/.claude）探测，
    且仅保留声明了 global_skill_target 的平台。"""
    env = os.environ
    active = []

    for platform_key, spec in platforms_config.get("platforms", {}).items():
        if global_mode:
            g_dirs = spec.get("global_detect_dirs", [])
            if not spec.get("global_skill_target"):
                continue  # 无全局挂载目标的平台不参与全局模式
            if any(os.path.exists(os.path.expanduser(d)) for d in g_dirs):
                active.append(platform_key)
            continue

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
    tools = PLATFORM_TOOLS.get(platform_key, DEFAULT_TOOLS)

    # 1. 状态机 SOP 引导提示词 (三步闭环)
    # 注: --config 省略，由 paths.resolve_runtime_config() 解析链定位配置（任意 CWD 均正确）
    sop_prompt = f"""# 角色定义：{agent_name} ({agent_id})

## 核心职责
{duty_str}

## 协作规约与红线
{redline_str}

## 自动化任务流转 SOP (CLI 三步闭环)
在执行本角色相关任务时，必须严格执行以下三步物理命令流转：
1. **领单/开工**：
   `python3 scripts/transition_task.py --role {role_code.upper()} --from-status 待开始 --to-status 进行中 --assignee {agent_id}`
2. **业务执行**：执行架构/编码/审查/测试/文档核心工作，产出交付物。
3. **完工/提审/流转**：
   `python3 scripts/transition_task.py --role {role_code.upper()} --from-status 进行中 --to-status 审查中 --task-id <第一步任务ID> --assignee Reviewer_User_1`
4. **完工硬门禁（强制）**：任何代码/文档/审查/测试交付产出完成后，最后一步必须执行上述流转命令推进状态（A 类开发推至【审查中】，B/C/D/G 类推至【已完成】，终态前补填 end_time），否则视为未交付；看板任务卡必须经历【待开始】状态（本门禁仅约束已建卡任务；L0 即时问答无卡直答，不适用——分级三问见 references/02-State-Flow-Rules.md）。
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

def verify_exported_agent(out_abs_path, fmt):
    """
    本地格式断言 (Fail-Closed):
    - markdown_frontmatter: frontmatter 必须可被 yaml.safe_load 解析, 且 name/description 非空
    - codex_toml: 必须可被 tomllib 解析, 且 name/description 非空
    返回 (ok: bool, err: str)
    """
    try:
        with open(out_abs_path, "r", encoding="utf-8") as fp:
            content = fp.read()
    except Exception as e:
        return False, f"读取失败: {e}"

    if fmt == "codex_toml":
        try:
            import tomllib
        except ImportError:
            # Python < 3.10 无 tomllib: 降级为关键行存在性断言
            has_name = any(line.startswith("name =") for line in content.splitlines())
            has_desc = any(line.startswith("description =") for line in content.splitlines())
            if has_name and has_desc:
                return True, ""
            return False, "TOML 缺少 name/description 声明行"
        try:
            data = tomllib.loads(content)
        except Exception as e:
            return False, f"TOML 解析失败: {e}"
        if not data.get("name") or not data.get("description"):
            return False, "TOML 缺少 name/description 字段"
        return True, ""

    # markdown + frontmatter
    if not content.startswith("---"):
        return False, "缺少 YAML frontmatter 起始标头"
    parts = content.split("---", 2)
    if len(parts) < 3:
        return False, "frontmatter 结构不完整"
    try:
        fm = yaml.safe_load(parts[1])
    except Exception as e:
        return False, f"frontmatter YAML 解析失败: {e}"
    if not isinstance(fm, dict):
        return False, "frontmatter 不是合法映射"
    if not fm.get("name") or not fm.get("description"):
        return False, "frontmatter 缺少 name/description 字段"
    return True, ""

def export_platform_assets(platforms_config, active_platforms, global_mode=False):
    """执行跨平台 Skill 挂载与 Subagent 导出，返回导出成败统计。

    导出时把项目技术栈（user_data/project_architecture.config.yaml）覆盖到
    内存中的角色定义——agents/*.yaml 模板保持只读。

    global_mode=True: 挂载各平台用户级全局技能目录（global_skill_target，绝对链）；
    Subagent 导出走 user_pattern（用户级）；技术栈覆盖在全局模式下禁用
    （项目个性化产物不得跨项目泄漏）。
    """
    skill_name = platforms_config.get("default_skill_name", "yy-flow")
    platforms = platforms_config.get("platforms", {})
    missing_agents = []
    verify_failures = []
    total_exported = 0

    arch_data = None if global_mode else load_arch_data()
    if global_mode:
        print("[GLOBAL] 全局共享安装模式：Subagent 导出为通用版（不含项目技术栈，防跨项目泄漏）")
    elif arch_data:
        proj = (arch_data.get("project") or {}).get("name", "未知")
        print(f"[SYNC]  检测到已初始化架构配置，导出时合并项目技术栈: 【{proj}】")
    else:
        print("[NOTE]  架构配置未初始化，导出使用通用模板职责（首次 init 属正常，Step 6 会重导出）")

    print(f"[SCAN]  已自动侦测到当前激活/兼容平台: {active_platforms}")

    for p_key in active_platforms:
        if p_key not in platforms:
            continue
        spec = platforms[p_key]
        p_name = spec.get("name", p_key)

        # 1. 执行 Skill 目录挂载（全局模式消费 global_skill_target）
        if global_mode:
            g_target_tpl = spec.get("global_skill_target")
            if g_target_tpl:
                abs_target = os.path.expanduser(g_target_tpl.format(skill_name=skill_name))
                if safe_symlink(PROJECT_ROOT, abs_target, relative=False):
                    print(f"[SUCCESS]  [{p_name}] 全局挂载 Skill -> {abs_target}")
                else:
                    print(f"[WARN]  [{p_name}] 全局挂载跳过 (目标已存在实体路径或无法创建软链) -> {abs_target}")
        elif "skill_target" in spec:
            rel_target = spec["skill_target"].format(skill_name=skill_name)
            abs_target = os.path.join(TARGET_PROJECT_DIR, rel_target)
            if safe_symlink(PROJECT_ROOT, abs_target):
                print(f"[SUCCESS]  [{p_name}] 成功挂载 Skill 发现路径 -> {rel_target}")
            else:
                print(f"[WARN]  [{p_name}] Skill 挂载跳过 (目标已存在实体路径或无法创建软链) -> {rel_target}")

        # 2. 执行 Cursor MDC 规则挂载（仅项目级模式有意义）
        if not global_mode and spec.get("mount_type") == "cursor_mdc" and "rule_target" in spec:
            rel_rule = spec["rule_target"].format(skill_name=skill_name)
            abs_rule = os.path.join(TARGET_PROJECT_DIR, rel_rule)
            os.makedirs(os.path.dirname(abs_rule), exist_ok=True)
            with open(abs_rule, "w", encoding="utf-8") as fp:
                fp.write(f"---\ndescription: 多专家协同研发工作流规则 (YY-Flow)\nalwaysApply: false\n---\n# YY-Flow Multi-Agent Workflow\n请调阅 `skills/multi-agent-flow/SKILL.md` 遵循多专家协作契约。\n")
            print(f"[SUCCESS]  [{p_name}] 成功创建 MDC 规则 -> {rel_rule}")

        # 3. 执行 Subagent 导出（全局模式：仅 user_pattern；项目模式：pattern）
        subagent_spec = spec.get("subagent_export")
        pattern = None
        if global_mode:
            pattern = (subagent_spec or {}).get("user_pattern")
            if not pattern:
                print(f"[SKIP]  [{p_name}] 无用户级 Subagent 导出路径声明，跳过全局导出")
                continue
        elif subagent_spec and subagent_spec.get("pattern"):
            pattern = subagent_spec["pattern"]

        if not pattern:
            continue

        fmt = (subagent_spec or {}).get("format", "markdown_frontmatter")
        exported_count = 0

        for yaml_file, role_meta in sorted(ROLES_MAP.items()):
            yaml_path = os.path.join(AGENTS_DIR, yaml_file)
            if not os.path.exists(yaml_path):
                missing_agents.append(f"[{p_key}] {yaml_file}")
                continue

            with open(yaml_path, "r", encoding="utf-8") as fp:
                role_data = yaml.safe_load(fp)

            # 导出时覆盖项目技术栈（纯内存操作，agents/*.yaml 不落盘不改写）
            role_key = role_meta.get("role_code", "")
            role_data = apply_tech_stack_to_role(role_data, arch_data, role_key)

            out_content = serialize_subagent(role_data, role_meta, p_key, subagent_spec or {})
            out_rel_path = pattern.format(agent_id=role_meta["id"])
            if global_mode:
                out_abs_path = os.path.expanduser(out_rel_path)
            else:
                out_abs_path = os.path.join(TARGET_PROJECT_DIR, out_rel_path)

            os.makedirs(os.path.dirname(out_abs_path), exist_ok=True)
            with open(out_abs_path, "w", encoding="utf-8") as fp:
                fp.write(out_content)
            exported_count += 1
            total_exported += 1

            # 导出后本地格式断言
            ok, err = verify_exported_agent(out_abs_path, fmt)
            if not ok:
                verify_failures.append(f"[{p_key}] {out_rel_path}: {err}")

        print(f"[SUCCESS]  [{p_name}] 成功导出专家子代理 ({exported_count}/8) -> 模式: `{pattern}`")

    return missing_agents, verify_failures, total_exported

def main():
    import argparse
    parser = argparse.ArgumentParser(description="跨平台 Skill 挂载与 Subagent 导出引擎")
    parser.add_argument("--global", dest="global_mode", action="store_true",
                        help="全局共享安装模式：挂载各宿主用户级技能目录（global_skill_target）")
    parser.add_argument("--target-project-dir", default=None,
                        help="宿主项目目录（默认: 当前工作目录）")
    args = parser.parse_args()

    global TARGET_PROJECT_DIR
    if args.target_project_dir:
        TARGET_PROJECT_DIR = os.path.abspath(args.target_project_dir)

    platforms_config = load_platforms_config()
    active_platforms = detect_active_platforms(platforms_config, global_mode=args.global_mode)

    mode_label = "全局共享安装 (user-level mount)" if args.global_mode else "项目级挂载"
    print("==============================================================================")
    print(f"[START] [Multi-Agent Flow] 跨平台 Skill 自动挂载与 Subagent 导出 · {mode_label}")
    print("==============================================================================")

    missing_agents, verify_failures, total_exported = export_platform_assets(
        platforms_config, active_platforms, global_mode=args.global_mode)

    if missing_agents:
        for m in missing_agents:
            print(f"[ERROR] 角色定义文件缺失: {m}")
    if verify_failures:
        for f_ in verify_failures:
            print(f"[ERROR] 导出格式断言失败: {f_}")

    # Fail-Closed 计数：global 模式只对声明了 user_pattern 的平台有导出预期
    if args.global_mode:
        exportable = [p for p in active_platforms
                      if (platforms_config.get("platforms", {}).get(p, {})
                          .get("subagent_export", {}) or {}).get("user_pattern")]
    else:
        exportable = [p for p in active_platforms
                      if platforms_config.get("platforms", {}).get(p, {}).get("subagent_export")]

    # global 模式下零平台被探测到 = 没有任何宿主已安装 → Fail-Closed（静默成功更糟）
    if args.global_mode and not active_platforms:
        print("==============================================================================")
        print("[FAILED] 全局模式未探测到任何已安装的 Agent 宿主（各平台用户级目录均不存在）！")
        print("         请先安装至少一个宿主（Claude Code / Codex / Antigravity），或用项目级模式。")
        print("==============================================================================")
        sys.exit(1)

    if missing_agents or verify_failures or (exportable and total_exported == 0):
        print("==============================================================================")
        print("[FAILED] Subagent 导出未通过完整性校验，初始化阻断 (Fail-Closed)！")
        print("==============================================================================")
        sys.exit(1)

    print("==============================================================================")
    print(f"[SUCCESS] 全平台 Skill 挂载与专家子代理序列化就绪 (共导出 {total_exported} 份，本地格式断言全部通过)！")
    print("==============================================================================")

if __name__ == "__main__":
    main()
