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
sys.path.insert(0, SCRIPT_DIR)

import paths as _paths

EXCLUDE_DIRS = {
    ".git", ".idea", "__pycache__", "venv", ".venv", "node_modules",
    "docs", "rules", "templates", "references", "agents", "config", "scripts",
    ".agents", ".claude", ".cursor", ".codex",
    # 数据/运行目录不参与"历史文档"识别
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
        # 1. 父目录语义权重最高 (权重: +10)
        for dkw in kw_dict["dir_keywords"]:
            if dkw in parent_dir:
                scores[cat] += 10

        # 2. 文件名匹配 (权重: +5，若为完整命中的架构关键词加给 02-架构设计 +8)
        for tkw in kw_dict["text_keywords"]:
            if tkw in fname:
                scores[cat] += 5
                if cat == "02-架构设计" and ("design" in fname or "arch" in fname):
                    scores[cat] += 3

        # 3. 文本内容匹配 (权重: +1)
        for tkw in kw_dict["text_keywords"]:
            if tkw in content:
                scores[cat] += 1

    best_cat = max(scores, key=scores.get)
    if scores[best_cat] > 0:
        return best_cat
    return "03-业务模块"


def scan_and_migrate_legacy_docs(target_project_dir: str = None):
    """扫描 target_project_dir（默认 data_root=宿主项目）散落文档，镜像归档至其 docs/。
    宿主内嵌 skill 目录（per-project 安装）整棵剪枝，防止把技能包文档当历史文档归档。"""
    if target_project_dir is None:
        target_project_dir = _paths.resolve_data_root()
    docs_root = os.path.join(target_project_dir, "docs")

    print("[SCAN]  [原项目文档识别] 正在结合目录语义扫描工程中散落的历史文档...")

    migrated_files: List[Tuple[str, str]] = []

    # skill 根若在扫描树内则整棵剪枝（per-project 安装: <host>/skills/multi-agent-flow）
    skill_root = _paths.skill_root()

    for root, dirs, files in os.walk(target_project_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        # 防相对路径剪枝失效：按绝对路径比对
        dirs[:] = [d for d in dirs
                   if os.path.abspath(os.path.join(root, d)) != skill_root]

        for file in files:
            if not file.endswith((".md", ".txt", ".pdf", ".docx", ".puml", ".drawio")):
                continue

            src_path = os.path.join(root, file)
            category = classify_document(src_path)

            dest_dir = os.path.join(docs_root, category, "原项目文档")
            os.makedirs(dest_dir, exist_ok=True)

            dest_path = os.path.join(dest_dir, file)

            if not os.path.exists(dest_path):
                shutil.copy2(src_path, dest_path)
                migrated_files.append((src_path, dest_path))

    if migrated_files:
        print(f"[SUCCESS]  [原项目文档归档完成] 已以只读方式分类镜像拷贝 {len(migrated_files)} 份历史文档：")
        for src, dest in migrated_files:
            rel_src = os.path.relpath(src, target_project_dir)
            rel_dest = os.path.relpath(dest, target_project_dir)
            print(f"  - [{rel_src}] -> [{rel_dest}]")
    else:
        print("[NOTE]  [未发现散落旧文档] 当前项目根路径下无新增需要迁移的历史文档。")


if __name__ == "__main__":
    scan_and_migrate_legacy_docs()
