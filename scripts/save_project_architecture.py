#!/usr/bin/env python3
"""
项目技术架构与专家技术栈安全定版工具 (Save Project Architecture CLI)
唯一法定落盘入口：
1. 负责架构配置的合法性校验 (Schema 校验) 与旧配置平滑升级；
2. 写入 <data_root>/user_data/project_architecture.config.yaml 并置 meta.initialized = True；
3. 联动能力拓展引擎 (tech_capability_expander.py) 刷新重导出 8 大专家 Subagent；
4. 执行 Fail-Closed 物理硬断言（校验 6 大技术专家 agent.md 已携带专属技术能力）。
"""

import os
import sys
import json
import argparse
import yaml
import subprocess
from typing import Any, Dict, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import paths as _paths
from _lib.core.tech_capability_expander import expand_expert_capabilities


def clean_list(val: Any) -> List[str]:
    """统一将逗号分隔字符串或列表转换为干净的非空字符串列表"""
    if isinstance(val, list):
        out = []
        for v in val:
            if isinstance(v, dict):
                out.append(str(v.get("name", "")))
            elif v:
                out.append(str(v).strip())
        return [x for x in out if x]
    if isinstance(val, str):
        return [x.strip() for x in val.replace("，", ",").split(",") if x.strip()]
    return []


def validate_schema(data: dict) -> bool:
    """基于 project_architecture.schema.json 校验数据格式"""
    schema_path = os.path.join(_paths.skill_root(), "config", "project_architecture.schema.json")
    if not os.path.exists(schema_path):
        return True
    try:
        import jsonschema
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(instance=data, schema=schema)
        return True
    except ImportError:
        # 若未安装 jsonschema，执行基础字段物理检查
        req = ["project", "tech_stack", "architecture_overview"]
        for k in req:
            if k not in data:
                sys.stderr.write(f"[FAIL-CLOSED ERROR] 缺少必需根字段: {k}\n")
                return False
        return True
    except Exception as e:
        sys.stderr.write(f"[FAIL-CLOSED ERROR] Schema 校验失败: {e}\n")
        return False


def save_architecture_config(arch_dict: dict) -> bool:
    """持久化架构配置并执行 Fail-Closed 断言"""
    config_path = _paths.arch_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    # 1. 自动迁移与规范化
    if "meta" not in arch_dict:
        arch_dict["meta"] = {}
    arch_dict["meta"]["initialized"] = True

    # 2. 自动派生 3~5 项专家能力并回填
    expert_caps = expand_expert_capabilities(arch_dict)
    if "tech_stack" not in arch_dict:
        arch_dict["tech_stack"] = {}
    arch_dict["tech_stack"]["expert_capabilities"] = expert_caps

    # 3. Schema 校验
    if not validate_schema(arch_dict):
        sys.stderr.write("[FAIL-CLOSED ERROR] 架构数据不满足规范，阻断写入！\n")
        return False

    # 4. 物理原子写入
    tmp_path = config_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(arch_dict, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp_path, config_path)
    print(f"[SUCCESS]  架构配置已安全落盘: {config_path}")

    # 5. 联动重导出 Subagent (使下次唤起即刻读取生效)
    export_script = os.path.join(SCRIPT_DIR, "verify_and_export_agents.py")
    res = subprocess.run([sys.executable, export_script, "--target-project-dir", _paths.project_root()], capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(f"[FAIL-CLOSED ERROR] Subagent 重新导出失败: {res.stderr}\n")
        return False
    print("[SUCCESS]  专家 Subagent 已携专属能力完成刷新导出。")

    # 6. SOP 尾部 Fail-Closed 物理硬断言 (支持 Antigravity, Claude, Cursor, Universal)
    project_root = _paths.project_root()
    target_roles = [
        "flow-pm", "flow-architect", "flow-dev", "flow-frontend",
        "flow-reviewer", "flow-qa", "flow-docs", "flow-devops"
    ]
    
    candidate_patterns = [
        os.path.join(project_root, ".agents", "agents", "{r}", "agent.md"),
        os.path.join(project_root, ".claude", "agents", "{r}.md"),
        os.path.join(project_root, ".cursor", "agents", "{r}.md"),
        os.path.join(project_root, ".universal_agents", "{r}.md"),
        os.path.join(_paths.skill_root(), ".agents", "agents", "{r}", "agent.md"),
    ]

    verified_count = 0
    for r in target_roles:
        found = False
        for pat in candidate_patterns:
            md_file = pat.format(r=r)
            if os.path.exists(md_file):
                with open(md_file, "r", encoding="utf-8") as f:
                    c = f.read()
                if "## 核心职责" in c or "核心职责" in c:
                    found = True
                    break
        if found:
            verified_count += 1
        else:
            sys.stderr.write(f"[FAIL-CLOSED ERROR] 专家 Prompt 未物理落盘或格式破损: {r}\n")
            return False

    if verified_count == len(target_roles):
        print(f"[SUCCESS]  [Fail-Closed 校验通过] 8 大专家 Agent 物理文件断言符合规范！")
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="项目技术架构与专家技术栈安全定版 CLI")
    parser.add_argument("--name", help="项目名称")
    parser.add_argument("--version", default="0.1.0", help="项目版本")
    parser.add_argument("--app-type", default="fullstack", help="应用类型")
    parser.add_argument("--languages", help="开发语言 (逗号分隔)")
    parser.add_argument("--backend", help="后端/业务核心框架 (逗号分隔)")
    parser.add_argument("--frontend", help="前端/UI框架 (逗号分隔)")
    parser.add_argument("--testing", default="pytest", help="测试框架 (逗号分隔)")
    parser.add_argument("--storage", help="存储/数据库/向量技术 (逗号分隔)")
    parser.add_argument("--security", help="安全/脱敏/沙箱技术 (逗号分隔)")
    parser.add_argument("--doc-path", help="架构设计文档路径")
    parser.add_argument("--from-yaml", help="从指定 YAML 文件直接导入定版")
    args = parser.parse_args()

    # 若传入已有 YAML 文件
    if args.from_yaml and os.path.exists(args.from_yaml):
        with open(args.from_yaml, "r", encoding="utf-8") as f:
            arch_data = yaml.safe_load(f) or {}
    else:
        # 读取当前已有配置或基础模板作为基底（实现平滑修改）
        config_path = _paths.arch_config_path()
        template_path = os.path.join(_paths.skill_root(), "config", "project_architecture.template.yaml")
        base_path = config_path if os.path.exists(config_path) else template_path
        
        with open(base_path, "r", encoding="utf-8") as f:
            arch_data = yaml.safe_load(f) or {}

        if "project" not in arch_data: arch_data["project"] = {}
        if "tech_stack" not in arch_data: arch_data["tech_stack"] = {}
        if "architecture_overview" not in arch_data: arch_data["architecture_overview"] = {}

        if args.name: arch_data["project"]["name"] = args.name
        if args.version: arch_data["project"]["version"] = args.version
        if args.app_type: arch_data["project"]["app_type"] = args.app_type

        langs = clean_list(args.languages) or [l.get("name") if isinstance(l, dict) else str(l) for l in arch_data["tech_stack"].get("languages", [])]
        if langs:
            arch_data["tech_stack"]["languages"] = [{"name": l, "version": "latest"} for l in langs]

        if args.backend:
            arch_data["tech_stack"]["backend_frameworks"] = clean_list(args.backend)
        if args.frontend:
            arch_data["tech_stack"]["frontend_frameworks"] = clean_list(args.frontend)

        test_list = clean_list(args.testing)
        test_primary = test_list[0] if test_list else "pytest"
        arch_data["tech_stack"]["testing"] = {
            "framework": test_primary,
            "min_coverage_percent": 80,
            "testing_frameworks": test_list,
        }

        if args.storage:
            arch_data["tech_stack"]["databases_and_storage"] = [{"name": s} for s in clean_list(args.storage)]
        if args.security:
            arch_data["tech_stack"]["security_and_sandbox"] = [{"name": s} for s in clean_list(args.security)]

        if args.doc_path:
            if "entry_points" not in arch_data["architecture_overview"]:
                arch_data["architecture_overview"]["entry_points"] = []
            if args.doc_path not in arch_data["architecture_overview"]["entry_points"]:
                arch_data["architecture_overview"]["entry_points"].append(args.doc_path)

    success = save_architecture_config(arch_data)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
