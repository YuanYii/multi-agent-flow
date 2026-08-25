#!/usr/bin/env python3
"""
项目技术架构与专家技术栈安全定版工具 (Save Project Architecture CLI)
"""
import os
import sys
import json
import argparse
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.discovery.arch_persister import (
    clean_list,
    validate_schema,
    save_architecture_config,
)


def main():
    parser = argparse.ArgumentParser(description="项目技术架构与专家技术栈安全定版工具")
    parser.add_argument("--json-input", help="全量架构 JSON 字符串")
    parser.add_argument("--yaml-file", help="已填充的架构 YAML 配置文件路径")
    parser.add_argument("--name", help="项目名称")
    parser.add_argument("--version", default="0.1.0", help="项目版本")
    parser.add_argument("--app-type", default="fullstack", help="应用类型")
    parser.add_argument("--languages", help="编程语言 (逗号分隔)")
    parser.add_argument("--backend", help="后端框架 (逗号分隔)")
    parser.add_argument("--frontend", help="前端框架 (逗号分隔)")
    parser.add_argument("--db", help="数据库与存储 (逗号分隔)")
    parser.add_argument("--test-framework", help="测试框架")
    parser.add_argument("--min-coverage", type=int, default=80, help="最低测试覆盖率")

    args = parser.parse_args()

    arch_dict = {}

    if args.json_input:
        try:
            arch_dict = json.loads(args.json_input)
        except Exception as e:
            sys.stderr.write(f"[ERROR] JSON 解析失败: {e}\n")
            sys.exit(1)
    elif args.yaml_file:
        if not os.path.exists(args.yaml_file):
            sys.stderr.write(f"[ERROR] 文件不存在: {args.yaml_file}\n")
            sys.exit(1)
        with open(args.yaml_file, "r", encoding="utf-8") as f:
            arch_dict = yaml.safe_load(f) or {}
    else:
        if not args.name:
            sys.stderr.write("[ERROR] 必须指定 --name 或 --json-input / --yaml-file\n")
            sys.exit(1)

        arch_dict = {
            "project": {
                "name": args.name,
                "version": args.version,
                "app_type": args.app_type,
            },
            "tech_stack": {
                "languages": clean_list(args.languages),
                "backend_frameworks": clean_list(args.backend),
                "frontend_frameworks": clean_list(args.frontend),
                "databases_and_storage": clean_list(args.db),
                "testing": {
                    "framework": args.test_framework or "pytest",
                    "min_coverage_percent": args.min_coverage,
                },
            },
            "architecture_overview": {
                "pattern": "Modular Monolith",
                "entry_points": ["scripts/start_kanban_server.py"],
                "core_directories": {
                    "scripts/": "核心流转与自动化工具",
                    "agents/": "8大专家定义",
                    "docs/": "项目文档规范",
                },
            },
        }

    ok = save_architecture_config(arch_dict)
    if not ok:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
