"""
散落历史文档分类、只读拓扑感知与元数据索引核心模块 (discovery 域)
严格遵循“无侵入/零移动/零复制”红线，识别散落历史文档并生成虚拟语义索引清单。
"""
import os
import sys
import json
import shutil
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timezone

import paths as _paths

EXCLUDE_DIRS = {
    ".git", ".idea", "__pycache__", "venv", ".venv", "node_modules",
    "docs", "rules", "templates", "references", "agents", "config", "scripts",
    ".agents", ".claude", ".cursor", ".codex",
    ".yy-flow", ".yy-flow-shared",
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
    """
    根据文件路径和正文关键词，自动推断并归类历史文档的目标标准目录。

    参数:
        filepath (str): 文档路径。

    返回:
        str: 目标分类目录标识。
    """
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


def build_doc_catalog(project_root: str = None) -> Dict[str, Any]:
    """
    只读扫描项目目录下的文档资产，提取相对路径与分类打标，生成虚拟文档拓扑索引清单。
    严格不执行任何物理文件移动或复制。

    返回:
        Dict[str, Any]: 包含文档元数据列表与扫描时间的字典。
    """
    if not project_root:
        project_root = _paths.project_root()
    project_root = os.path.abspath(project_root)

    target_docs_root = os.path.abspath(_paths.docs_root())
    custom_name = _paths.custom_docs_name()

    documents: List[Dict[str, Any]] = []

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [
            d for d in dirs
            if d not in EXCLUDE_DIRS
            and not d.startswith(".")
            and d != custom_name
            and os.path.abspath(os.path.join(root, d)) != target_docs_root
        ]

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in (".md", ".txt", ".docx", ".pdf"):
                continue
            if file in ("README.md", "CHANGELOG.md", "LICENSE.md", "CONTRIBUTING.md", "SKILL.md", "AGENTS.md"):
                continue

            src_path = os.path.join(root, file)
            category = classify_document(src_path)
            rel_path = os.path.relpath(src_path, project_root).replace("\\", "/")

            mtime = 0
            try:
                mtime = int(os.path.getmtime(src_path))
            except Exception:
                pass

            documents.append({
                "path": rel_path,
                "category": category,
                "filename": file,
                "extension": ext,
                "mtime": mtime
            })

    # 按相对路径稳定排序
    documents.sort(key=lambda d: d["path"])

    return {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "project_root": project_root,
        "total_documents": len(documents),
        "documents": documents
    }


def save_doc_catalog(catalog: Dict[str, Any], project_root: str = None) -> str:
    """
    将文档元数据索引清单持久化至框架隔离区 (.yy-flow/user_data/doc_catalog.json)。

    返回:
        str: 索引持久化文件绝对路径。
    """
    if not project_root:
        project_root = _paths.project_root()

    data_root = _paths.resolve_data_root()
    user_data_dir = os.path.join(data_root, "user_data")
    os.makedirs(user_data_dir, exist_ok=True)

    catalog_path = os.path.join(user_data_dir, "doc_catalog.json")
    tmp_path = catalog_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, catalog_path)
    return catalog_path


def scan_and_migrate_legacy_docs(
    project_root: str = None,
    copy_physical: bool = False
) -> List[Tuple[str, str]]:
    """
    扫描项目目录下的遗留文档。
    默认模式 (copy_physical=False)：只读生成虚拟文档索引并保存至 user_data，不移动或复制任何文件。
    显式模式 (copy_physical=True)：执行存量物理镜像拷贝放入 docs/{category}/原项目文档/。

    返回:
        List[Tuple[str, str]]: (文件路径, 类别或目标路径) 列表。
    """
    if not project_root:
        project_root = _paths.project_root()
    project_root = os.path.abspath(project_root)

    catalog = build_doc_catalog(project_root)
    save_doc_catalog(catalog, project_root)

    migrated: List[Tuple[str, str]] = []

    if not copy_physical:
        # 只读模式：返回 (源文件绝对路径, 推断分类) 供上层调阅，零物理写入
        for item in catalog["documents"]:
            abs_src = os.path.join(project_root, item["path"])
            migrated.append((abs_src, item["category"]))
        return migrated

    # 显式物理复制模式 (仅供 CLI 显式参数调用)
    target_docs_root = os.path.abspath(_paths.docs_root())
    for item in catalog["documents"]:
        src_path = os.path.join(project_root, item["path"])
        category = item["category"]
        dest_dir = os.path.join(target_docs_root, category, "原项目文档")
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, item["filename"])

        if not os.path.exists(dest_path):
            try:
                shutil.copy2(src_path, dest_path)
                migrated.append((src_path, dest_path))
            except Exception as e:
                print(f"[WARN] 迁移历史文档失败 {src_path}: {e}")

    return migrated
