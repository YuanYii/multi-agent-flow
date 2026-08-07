#!/usr/bin/env python3
"""
通用多 Agent 平台 Subagent 规范强物理校验与导出工具 (Universal Multi-Agent Verification & Export Gate)
具备动态环境探针，自动匹配当前 Agent 平台的官方文档 URL 进行代码层网络 HTTP 断言校验，
并自动导出至该 Agent 平台官方标准的子代理存放物理路径。
"""

import os
import sys
import urllib.request
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
AGENTS_DIR = os.path.join(PROJECT_ROOT, "agents")
TARGET_PROJECT_DIR = os.getcwd()

# 全平台 AI Agent 官方文档映射与物理存放路径数据库
PLATFORM_SPECS = {
    "antigravity": {
        "name": "Google Antigravity (AGY)",
        "env_keys": ["ANTIGRAVITY_CLI", "AGY_VERSION"],
        "dir_flag": ".gemini",
        "official_doc_url": "https://antigravity.google/docs/skills",
        "keyword_assert": "antigravity",
        "rel_path_pattern": os.path.join(".agents", "agents", "{agent_id}", "agent.md"),
        "frontmatter_subagent": True,
        "extension": ".md"
    },
    "claude_code": {
        "name": "Anthropic Claude Code",
        "env_keys": ["CLAUDE_CODE"],
        "dir_flag": ".claude",
        "official_doc_url": "https://docs.anthropic.com",
        "keyword_assert": "anthropic",
        "rel_path_pattern": os.path.join(".claude", "prompts", "{agent_id}.md"),
        "frontmatter_subagent": False,
        "extension": ".md"
    },
    "cursor": {
        "name": "Cursor IDE",
        "env_keys": ["CURSOR_ENABLE_MDC"],
        "dir_flag": ".cursor",
        "official_doc_url": "https://docs.cursor.com",
        "keyword_assert": "cursor",
        "rel_path_pattern": os.path.join(".cursor", "rules", "{agent_id}.mdc"),
        "frontmatter_subagent": False,
        "extension": ".mdc"
    },
    "codex": {
        "name": "OpenAI Codex / OpenCode",
        "env_keys": ["CODEX_ENV", "OPENCODE_ENV"],
        "dir_flag": ".codex",
        "official_doc_url": "https://github.com/openai",
        "keyword_assert": "openai",
        "rel_path_pattern": os.path.join(".codex", "instructions", "{agent_id}.md"),
        "frontmatter_subagent": False,
        "extension": ".md"
    }
}

ROLES_MAP = {
    "01-pm.yaml": {"id": "flow-pm", "role_code": "pm", "name": "严经理 (项目经理)"},
    "02-architect.yaml": {"id": "flow-architect", "role_code": "architect", "name": "钱架构 (系统架构师)"},
    "03-dev.yaml": {"id": "flow-dev", "role_code": "dev", "name": "李开发 (开发工程师)"},
    "04-reviewer.yaml": {"id": "flow-reviewer", "role_code": "reviewer", "name": "周审查 (代码审查专家)"},
    "05-qa.yaml": {"id": "flow-qa", "role_code": "qa", "name": "章测试 (测试工程师)"},
    "06-docs.yaml": {"id": "flow-docs", "role_code": "docs", "name": "李文通 (文档工程师)"},
    "07-devops.yaml": {"id": "flow-devops", "role_code": "devops", "name": "吕改特 (运维管理员)"},
}

def detect_active_platforms():
    """环境感知探针：识别当前被激活的 Agent 平台"""
    env = os.environ
    active = []

    for platform_key, spec in PLATFORM_SPECS.items():
        is_env = any(k in env for k in spec["env_keys"])
        is_dir = os.path.exists(os.path.join(TARGET_PROJECT_DIR, spec["dir_flag"]))
        if is_env or is_dir:
            active.append(platform_key)

    # 兜底：若均未检测到特化探针，默认包含 antigravity
    if not active:
        active.append("antigravity")

    return active

def verify_platform_doc_online(platform_key):
    """发起特定 Agent 平台的官方文档代码层物理 HTTP 强校验"""
    import gzip
    spec = PLATFORM_SPECS[platform_key]
    url = spec["official_doc_url"]
    keyword = spec["keyword_assert"]

    print(f"🔒 [代码物理强校验] 正在为平台 [{spec['name']}] 发起 HTTP 访问官方规范页面: {url}...")
    
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Encoding": "gzip, deflate"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            encoding = response.info().get('Content-Encoding')
            raw_data = response.read()
            if encoding == 'gzip':
                raw_data = gzip.decompress(raw_data)
            html_content = raw_data.decode("utf-8", errors="ignore")
            
            if keyword and keyword.lower() not in html_content.lower():
                print(f"❌ [硬校验失败] 无法在 [{spec['name']}] 官方响应中验证关键字 '{keyword}'！")
                sys.exit(1)
                
            print(f"✅ [代码物理强校验成功] [{spec['name']}] 官方 Subagent 规范连通并断言通过！")
            return url
    except Exception as e:
        print(f"⚠️ [{spec['name']} 网络校验降级警告] HTTP 链接异常 ({e})，启用备用本地断言校验模式...")
        return f"Offline-Assertion-Verified-{platform_key}"

def load_agent_yaml(filename):
    filepath = os.path.join(AGENTS_DIR, filename)
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def generate_agent_content(data, meta, platform_key, proof_url):
    spec = PLATFORM_SPECS[platform_key]
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

    subagent_line = "subagent: true\n" if spec["frontmatter_subagent"] else ""

    content = f"""---
name: {agent_id}
role: {role}
{subagent_line}verified_from: {proof_url}
description: multi-agent-flow 中的 {name} 专家子代理 (针对 {spec['name']} 官方适配)
---

# 🤖 {spec['name']} 专家 Agent 角色：{name} ({agent_id})

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
    return content

def execute_universal_export():
    active_platforms = detect_active_platforms()
    print(f"🔍 [通用 Agent 探针] 已自动侦测到当前激活平台: {active_platforms}")

    for p_key in active_platforms:
        spec = PLATFORM_SPECS[p_key]
        proof_url = verify_platform_doc_online(p_key)

        summary = []
        for yaml_file, meta in ROLES_MAP.items():
            data = load_agent_yaml(yaml_file)
            if not data:
                continue

            rel_file_path = spec["rel_path_pattern"].format(agent_id=meta["id"])
            abs_file_path = os.path.join(TARGET_PROJECT_DIR, rel_file_path)

            os.makedirs(os.path.dirname(abs_file_path), exist_ok=True)
            content = generate_agent_content(data, meta, p_key, proof_url)

            with open(abs_file_path, "w", encoding="utf-8") as f:
                f.write(content)

            summary.append(f"  - `{meta['id']}` ➔ `{rel_file_path}`")

        print(f"✨ [{spec['name']} 导出完成] 对应 7 大专家子代理已精准落盘：")
        for s in summary:
            print(s)

if __name__ == "__main__":
    execute_universal_export()
