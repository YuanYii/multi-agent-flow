#!/usr/bin/env python3
"""
项目配置与技术栈全自动更新工具 (Update Project Profile CLI)

功能：
1. 文档目录定制 (--docs-dir)：更新 workflow.config.yaml 中的 paths.docs_root，支持项目文档目录变更为任意自定义路径。
2. 技术栈显式定制 (--languages, --backend, --frontend, --db, --test-framework)：安全持久化至 project_architecture.config.yaml。
3. 执行态新技术全自动静默采纳 (策略 B, --auto-detect)：自动嗅探工程依赖与构建特征，增量合并至项目架构配置中，不阻塞开发流程。
"""
import os
import sys
import json
import argparse
import yaml
from typing import Dict, Any, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import paths as _paths
from _lib.discovery.stack_scanner import scan_project_stack
from _lib.discovery.arch_persister import clean_list, save_architecture_config


def update_docs_directory(new_docs_dir: str, silent: bool = False) -> bool:
    """更新当前项目工作流配置中的文档根目录路径"""
    if not new_docs_dir:
        return True
    
    cfg_file = _paths.resolve_runtime_config()
    os.makedirs(os.path.dirname(cfg_file), exist_ok=True)

    data = {}
    if os.path.isfile(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            if not silent:
                sys.stderr.write(f"[WARN] 读取现有工作流配置失败，将创建新配置: {e}\n")
            data = {}

    if "paths" not in data or not isinstance(data["paths"], dict):
        data["paths"] = {}
    data["paths"]["docs_root"] = new_docs_dir.strip()

    tmp_file = cfg_file + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp_file, cfg_file)

    # 确保目标实体物理目录就绪
    target_full_path = _paths.docs_root(docs_dir=new_docs_dir)
    os.makedirs(target_full_path, exist_ok=True)
    os.makedirs(os.path.join(target_full_path, "D04-研发过程", "D01-任务"), exist_ok=True)

    if not silent:
        print(f"[SUCCESS] 项目文档目录已更新为: {new_docs_dir} (物理路径: {target_full_path})")
    return True


def load_or_init_arch_config() -> Dict[str, Any]:
    """读取宿主架构配置；若未初始化，读取模板"""
    cfg_path = _paths.arch_config_path()
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                d = yaml.safe_load(f) or {}
                if isinstance(d, dict) and d.get("tech_stack"):
                    return d
        except Exception:
            pass

    # 读取 template 作为基础骨架
    tmpl_path = os.path.join(_paths.skill_root(), "config", "project_architecture.template.yaml")
    if os.path.isfile(tmpl_path):
        with open(tmpl_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    return {
        "meta": {"initialized": False},
        "project": {"name": os.path.basename(_paths.project_root()), "version": "1.0.0"},
        "tech_stack": {
            "languages": [],
            "backend_frameworks": [],
            "frontend_frameworks": [],
            "databases_and_storage": [],
            "testing": {"framework": "pytest", "min_coverage_percent": 80}
        }
    }


def merge_detected_tech_stack(arch_dict: Dict[str, Any], detected_info: Dict[str, Any], silent: bool = False) -> List[str]:
    """将物理扫描出的新技术静默增量合并至既有架构字典中（策略 B 核心逻辑）"""
    added_items = []
    tech = arch_dict.get("tech_stack", {}) or {}
    if not isinstance(tech, dict):
        tech = {}
        arch_dict["tech_stack"] = tech

    def merge_string_list(existing_list, new_items):
        nonlocal added_items
        exist_names = set()
        for item in existing_list:
            if isinstance(item, dict):
                exist_names.add(str(item.get("name", "")).strip().lower())
            elif item:
                exist_names.add(str(item).strip().lower())

        for ni in new_items:
            ni_str = str(ni).strip()
            if ni_str and ni_str.lower() not in exist_names:
                existing_list.append(ni_str)
                exist_names.add(ni_str.lower())
                added_items.append(ni_str)

    # 1. 语言合并
    if "languages" not in tech or not isinstance(tech["languages"], list):
        tech["languages"] = []
    merge_string_list(tech["languages"], detected_info.get("languages", []))

    # 2. 后端框架合并
    if "backend_frameworks" not in tech or not isinstance(tech["backend_frameworks"], list):
        tech["backend_frameworks"] = []
    merge_string_list(tech["backend_frameworks"], detected_info.get("backend_frameworks", []))

    # 3. 前端框架合并
    if "frontend_frameworks" not in tech or not isinstance(tech["frontend_frameworks"], list):
        tech["frontend_frameworks"] = []
    merge_string_list(tech["frontend_frameworks"], detected_info.get("frontend_frameworks", []))

    # 4. 存储与数据库合并
    if "databases_and_storage" not in tech or not isinstance(tech["databases_and_storage"], list):
        tech["databases_and_storage"] = []
    merge_string_list(tech["databases_and_storage"], detected_info.get("storage", []))

    # 5. 测试框架探测
    if detected_info.get("testing_framework") and detected_info["testing_framework"] != "pytest":
        testing = tech.get("testing", {}) or {}
        testing["framework"] = detected_info["testing_framework"]
        tech["testing"] = testing

    # 6. 项目名称自动校正
    proj = arch_dict.get("project", {}) or {}
    if proj.get("name") in ("project_name", "未知应用", "Sample-Project", "") and detected_info.get("project_name"):
        proj["name"] = detected_info["project_name"]
        arch_dict["project"] = proj

    return added_items


def main():
    parser = argparse.ArgumentParser(description="项目配置与技术栈全自动更新工具 (策略 B 支持)")
    parser.add_argument("--docs-dir", help="自定义项目文档目录相对路径 (如 documentation / wiki)")
    parser.add_argument("--name", help="项目名称")
    parser.add_argument("--version", help="项目版本")
    parser.add_argument("--languages", help="主要编程语言 (逗号分隔)")
    parser.add_argument("--backend", help="核心后端框架 (逗号分隔)")
    parser.add_argument("--frontend", help="核心前端框架 (逗号分隔)")
    parser.add_argument("--db", help="数据库与存储 (逗号分隔)")
    parser.add_argument("--test-framework", help="测试框架 (如 pytest / jest / go test)")
    parser.add_argument("--auto-detect", action="store_true", help="策略 B: 自动嗅探并静默增量合并新技术栈")
    parser.add_argument("--silent", action="store_true", help="静默模式，减少日志输出")
    parser.add_argument("--skip-export", action="store_true", default=True, help="跳过生成平台中间产物 (默认跳过以保持仓库干净)")

    args = parser.parse_args()

    # 1. 检查文档目录更新
    if args.docs_dir:
        update_docs_directory(args.docs_dir, silent=args.silent)

    # 2. 检查技术栈更新
    needs_arch_update = bool(
        args.auto_detect or args.name or args.languages or
        args.backend or args.frontend or args.db or args.test_framework or args.version
    )

    if needs_arch_update:
        arch_data = load_or_init_arch_config()
        tech = arch_data.get("tech_stack", {}) or {}
        proj = arch_data.get("project", {}) or {}

        if args.name:
            proj["name"] = args.name.strip()
        if args.version:
            proj["version"] = args.version.strip()
        arch_data["project"] = proj

        if args.languages:
            tech["languages"] = clean_list(args.languages)
        if args.backend:
            tech["backend_frameworks"] = clean_list(args.backend)
        if args.frontend:
            tech["frontend_frameworks"] = clean_list(args.frontend)
        if args.db:
            tech["databases_and_storage"] = clean_list(args.db)
        if args.test_framework:
            testing = tech.get("testing", {}) or {}
            testing["framework"] = args.test_framework.strip()
            tech["testing"] = testing

        arch_data["tech_stack"] = tech

        # 策略 B: 自动嗅探并增量合并
        added = []
        if args.auto_detect:
            detected = scan_project_stack(_paths.project_root())
            added = merge_detected_tech_stack(arch_data, detected, silent=args.silent)

        ok = save_architecture_config(arch_data, skip_export=args.skip_export)
        if not ok:
            sys.exit(1)

        if not args.silent:
            if added:
                print(f"[AUTO-DETECT] 策略 B 静默合并新识别技术: {', '.join(added)}")
            print("[SUCCESS] 项目架构与专家技术栈已同步更新至运行态配置。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
