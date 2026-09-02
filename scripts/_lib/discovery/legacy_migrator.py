"""
散落历史文档分类与只读镜像隔离归档核心模块 (已归口至 discovery 域)
"""
import os
import sys
import shutil
from typing import Dict, List, Tuple, Optional

import paths as _paths

EXCLUDE_DIRS = {
    ".git", ".idea", "__pycache__", "venv", ".venv", "node_modules",
    "docs", "rules", "templates", "references", "agents", "config", "scripts",
    ".agents", ".claude", ".cursor", ".codex",
    "user_data", "kanban", "tests", "logs",
    ".opencode", ".zcode", ".pi",
}

CATEGORY_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "D01-项目管理": {
        "dir_keywords": ["pm", "manage", "plan", "charter", "require", "risk", "change", "lesson", "status", "milestone", "需求", "计划", "章程", "风险", "变更", "复盘"],
        "text_keywords": ["项目章程", "需求规格", "项目计划", "风险登记", "变更日志", "经验教训", "里程碑", "状态报告", "charter", "requirement", "risk register"]
    },
    "D02-架构设计": {
        "dir_keywords": ["arch", "architecture", "design", "system", "spec"],
        "text_keywords": ["架构", "系统设计", "architecture", "adr", "接口规范", "数据模型"]
    },
    "D03-业务模块": {
        "dir_keywords": ["module", "component", "subsystem", "service"],
        "text_keywords": ["模块设计", "组件", "服务设计", "module", "subsystem"]
    },
    "D04-研发过程": {
        "dir_keywords": ["ops", "deploy", "operation", "guide", "manual", "report"],
        "text_keywords": ["运维指南", "部署手册", "操作手册", "troubleshooting", "排查指南", "测试报告"]
    },
    "D05-规范标准": {
        "dir_keywords": ["standard", "rule", "convention", "guide"],
        "text_keywords": ["规范", "代码标准", "命名规约", "standard", "convention"]
    },
    "D06-文档模板": {
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
        for dkw in kw_dict["dir_keywords"]:
            if dkw in parent_dir or dkw in fname:
                scores[cat] += 3
        for tkw in kw_dict["text_keywords"]:
            if tkw in content:
                scores[cat] += 1

    best_cat = max(scores, key=scores.get)
    if scores[best_cat] > 0:
        return best_cat
    return "D03-业务模块"


def scan_and_migrate_legacy_docs(project_root: str) -> List[Tuple[str, str]]:
    migrated: List[Tuple[str, str]] = []
    target_docs_root = _paths.docs_root()

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]

        for file in files:
            if not file.endswith((".md", ".txt", ".docx", ".pdf")):
                continue
            if file in ("README.md", "CHANGELOG.md", "LICENSE.md", "CONTRIBUTING.md", "SKILL.md", "AGENTS.md"):
                continue

            src_path = os.path.join(root, file)
            category = classify_document(src_path)

            dest_dir = os.path.join(target_docs_root, category, "原项目文档")
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, file)

            if not os.path.exists(dest_path):
                try:
                    shutil.copy2(src_path, dest_path)
                    migrated.append((src_path, dest_path))
                except Exception as e:
                    print(f"[WARN] 迁移历史文档失败 {src_path}: {e}")

    return migrated
