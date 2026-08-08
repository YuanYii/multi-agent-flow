#!/usr/bin/env python3
"""
只读归档迁移脚本 (Migrate Legacy Docs CLI)
严格遵循“不修改原文档任何内容”红线，识别散落历史文档并只读镜像拷贝放入 docs/{category}/原项目文档/。
结合父目录上下文语义与文件内容权重进行分类判定。
"""

import os
import sys
import shutil
from typing import Dict, List, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DOCS_ROOT = os.path.join(PROJECT_ROOT, "docs")

EXCLUDE_DIRS = {
    ".git", ".idea", "__pycache__", "venv", ".venv", "node_modules",
    "docs", "rules", "templates", "references", "agents", "config", "scripts", ".agents", ".claude", ".cursor", ".codex"
}

CATEGORY_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "01-architecture": {
        "dir_keywords": ["arch", "architecture", "design", "system", "spec"],
        "text_keywords": ["架构", "系统设计", "architecture", "adr", "接口规范", "数据模型"]
    },
    "02-modules": {
        "dir_keywords": ["module", "component", "subsystem", "service"],
        "text_keywords": ["模块设计", "组件", "服务设计", "module", "subsystem"]
    },
    "03-operations": {
        "dir_keywords": ["ops", "deploy", "operation", "guide", "manual", "report"],
        "text_keywords": ["运维指南", "部署手册", "操作手册", "troubleshooting", "排查指南", "测试报告"]
    },
    "04-standards": {
        "dir_keywords": ["standard", "rule", "convention", "guide"],
        "text_keywords": ["规范", "代码标准", "命名规约", "standard", "convention"]
    },
    "05-templates": {
        "dir_keywords": ["template", "tpl", "example"],
        "text_keywords": ["模板", "template", "样例"]
    }
}


def classify_document(filepath: str) -> str:
    fname = os.path.basename(filepath).lower()
    parent_dir = os.path.basename(os.path.dirname(filepath)).lower()
    content = ""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(2048).lower()
    except Exception:
        pass

    scores: Dict[str, int] = {cat: 0 for cat in CATEGORY_KEYWORDS}

    for cat, kw_dict in CATEGORY_KEYWORDS.items():
        # 1. 父目录语义权重最高 (权重: +10)
        for dkw in kw_dict["dir_keywords"]:
            if dkw in parent_dir:
                scores[cat] += 10

        # 2. 文件名匹配 (权重: +5)
        for tkw in kw_dict["text_keywords"]:
            if tkw in fname:
                scores[cat] += 5

        # 3. 文本内容匹配 (权重: +1)
        for tkw in kw_dict["text_keywords"]:
            if tkw in content:
                scores[cat] += 1

    best_cat = max(scores, key=scores.get)
    if scores[best_cat] > 0:
        return best_cat
    return "02-modules"


def scan_and_migrate_legacy_docs(target_project_dir: str = PROJECT_ROOT):
    print("🔍 [原项目文档识别] 正在结合目录语义扫描工程中散落的历史文档...")

    migrated_files: List[Tuple[str, str]] = []

    for root, dirs, files in os.walk(target_project_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]

        for file in files:
            if not file.endswith((".md", ".txt", ".pdf", ".docx", ".puml", ".drawio")):
                continue

            src_path = os.path.join(root, file)
            category = classify_document(src_path)

            dest_dir = os.path.join(DOCS_ROOT, category, "原项目文档")
            os.makedirs(dest_dir, exist_ok=True)

            dest_path = os.path.join(dest_dir, file)

            if not os.path.exists(dest_path):
                shutil.copy2(src_path, dest_path)
                migrated_files.append((src_path, dest_path))

    if migrated_files:
        print(f"✅ [原项目文档归档完成] 已以只读方式分类镜像拷贝 {len(migrated_files)} 份历史文档：")
        for src, dest in migrated_files:
            rel_src = os.path.relpath(src, target_project_dir)
            rel_dest = os.path.relpath(dest, target_project_dir)
            print(f"  - [{rel_src}] ➔ [{rel_dest}]")
    else:
        print("💡 [未发现散落旧文档] 当前项目根路径下无新增需要迁移的历史文档。")


if __name__ == "__main__":
    scan_and_migrate_legacy_docs()
