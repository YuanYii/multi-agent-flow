#!/usr/bin/env python3
"""
原项目文档归档与分类迁移脚本 (Legacy Docs Migration Script)
在初始化项目时，自动识别工程中散落的旧文档，并在 docs/ 对应规范分类下创建【原项目文档/】子目录进行拷贝归档。
"""

import os
import sys
import shutil
import glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TARGET_PROJECT_DIR = os.getcwd()

DOCS_ROOT = os.path.join(TARGET_PROJECT_DIR, "docs")

# 忽略归档的特定文件/目录
IGNORE_FILES = {"README.md", "CONTRIBUTING.md", "LICENSE", "CHANGELOG.md", "SKILL.md"}
IGNORE_DIRS = {
    ".git", ".idea", ".vscode", "node_modules", "venv", "env", "__pycache__",
    "skills", "multi-agent-flow", "docs", ".drafts", ".cursor", ".claude",
    ".codex", ".pi", ".opencode", ".windsurf", ".github", ".agents",
    "rules", "templates", "references", "agents", "config"
}

# 规则分类关键词映射表
CLASSIFICATION_RULES = {
    "01-architecture": ["architecture", "设计", "架构", "选型", "接口", "数据结构", "schema", "adr", "技术方案"],
    "02-modules": ["module", "模块", "组件", "log", "parser", "troubleshooting", "踩坑", "排查"],
    "03-operations": ["operation", "task", "report", "guide", "部署", "操作", "手册", "任务", "测试报告", "审查报告", "总结"],
    "04-standards": ["standard", "coding", "git", "规范", "流程", "标准", "守则"],
    "05-templates": ["template", "模板", "样板"]
}

def classify_doc(filename, filepath):
    """根据文件名与文章前几行内容判定存放目录"""
    fname_lower = filename.lower()
    
    # 优先读文件头部内容判定
    content_snippet = ""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content_snippet = "".join([f.readline().lower() for _ in range(20)])
    except Exception:
        pass

    text_to_search = f"{fname_lower} {content_snippet}"

    for category, keywords in CLASSIFICATION_RULES.items():
        if any(kw in text_to_search for kw in keywords):
            return category

    return "general"  # 无法精准归类的通用旧文档

def migrate_legacy_docs():
    print("🔍 [原项目文档识别] 正在扫描工程中散落的历史文档...")

    migrated_count = 0
    migrated_summary = []

    # 在 docs/ 各分类下以及顶层准备【原项目文档/】目录
    target_legacy_dirs = {
        "01-architecture": os.path.join(DOCS_ROOT, "01-architecture", "原项目文档"),
        "02-modules": os.path.join(DOCS_ROOT, "02-modules", "原项目文档"),
        "03-operations": os.path.join(DOCS_ROOT, "03-operations", "原项目文档"),
        "04-standards": os.path.join(DOCS_ROOT, "04-standards", "原项目文档"),
        "05-templates": os.path.join(DOCS_ROOT, "05-templates", "原项目文档"),
        "general": os.path.join(DOCS_ROOT, "原项目文档")
    }

    for root, dirs, files in os.walk(TARGET_PROJECT_DIR):
        # 过滤忽略的文件夹
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

        for file in files:
            if file in IGNORE_FILES:
                continue
            
            # 支持对 .md, .txt, .pdf, .docx 等文档格式归档
            if file.endswith((".md", ".txt", ".pdf", ".docx", ".xmind")):
                src_path = os.path.join(root, file)

                # 避免死循环：如果文件已经在 docs/ 里面则跳过
                rel_to_target = os.path.relpath(src_path, TARGET_PROJECT_DIR)
                if rel_to_target.startswith("docs/") or rel_to_target.startswith("skills/"):
                    continue

                category = classify_doc(file, src_path)
                dest_dir = target_legacy_dirs[category]
                os.makedirs(dest_dir, exist_ok=True)

                dest_path = os.path.join(dest_dir, file)
                
                # 执行安全拷贝
                shutil.copy2(src_path, dest_path)
                migrated_count += 1
                migrated_summary.append(f"  - `{rel_to_target}` ➔ 归档至 `{os.path.relpath(dest_path, TARGET_PROJECT_DIR)}`")

    if migrated_count > 0:
        print(f"✅ [历史文档归档完成] 成功识别并分类拷贝了 {migrated_count} 份原项目文档：")
        for s in migrated_summary:
            print(s)
        print("🛡️  [只读安全保障] 原路径下的源文档已 100% 完整保留，未进行任何修改、剪切或删除。")
    else:
        print("💡 [未发现散落旧文档] 当前项目根路径下无需要迁移的历史文档。")

if __name__ == "__main__":
    migrate_legacy_docs()
