"""
散落历史文档分类与只读镜像隔离归档核心模块
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
            if dkw in parent_dir:
                scores[cat] += 10

        for tkw in kw_dict["text_keywords"]:
            if tkw in fname:
                scores[cat] += 5
                if cat == "D02-架构设计" and ("design" in fname or "arch" in fname):
                    scores[cat] += 3

        for tkw in kw_dict["text_keywords"]:
            if tkw in content:
                scores[cat] += 1

    best_cat = max(scores, key=scores.get)
    if scores[best_cat] > 0:
        return best_cat
    return "D03-业务模块"


def scan_and_migrate_legacy_docs(target_project_dir: Optional[str] = None) -> List[Tuple[str, str]]:
    if target_project_dir is None:
        target_project_dir = _paths.project_root()
    docs_root = _paths.docs_root() if target_project_dir == _paths.project_root() else os.path.join(target_project_dir, "docs")

    print("[SCAN]  [原项目文档识别] 正在结合目录语义扫描工程中散落的历史文档...")

    migrated_files: List[Tuple[str, str]] = []
    skill_root_abs = os.path.abspath(_paths.skill_root())

    for root, dirs, files in os.walk(target_project_dir):
        root_abs = os.path.abspath(root)
        if root_abs == skill_root_abs or root_abs.startswith(skill_root_abs + os.sep):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]

        for file in files:
            if file.endswith((".md", ".txt", ".pdf", ".docx")):
                if file.upper().startswith("README") or file.upper().startswith("CHANGELOG"):
                    continue
                if file.startswith("."):
                    continue

                full_path = os.path.join(root, file)
                cat = classify_document(full_path)
                dest_dir = os.path.join(docs_root, cat, "原项目文档")
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, file)

                if os.path.abspath(full_path) != os.path.abspath(dest_path) and not os.path.exists(dest_path):
                    shutil.copy2(full_path, dest_path)
                    migrated_files.append((full_path, dest_path))

    if migrated_files:
        print(f"[SUCCESS]  已只读镜像归档 {len(migrated_files)} 份历史文档至对应分类下的 `原项目文档/` 隔离区：")
        for src, dst in migrated_files[:10]:
            rel_src = os.path.relpath(src, target_project_dir)
            rel_dst = os.path.relpath(dst, target_project_dir)
            print(f"  - {rel_src} -> {rel_dst}")
        if len(migrated_files) > 10:
            print(f"  ... 等共 {len(migrated_files)} 份文档")
    else:
        print("[INFO]  未检测到需要迁移的散落历史文档。")
    return migrated_files
