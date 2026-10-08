#!/usr/bin/env python3
"""
只读文档拓扑索引与历史文档迁移 CLI (Migrate Legacy Docs CLI)
默认遵循“无侵入/零移动/零复制”红线，扫描散落历史文档并建立虚拟索引至 user_data/doc_catalog.json。
仅在显式传入 --copy 时执行物理镜像归档。
"""
import os
import sys
import argparse
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.discovery.legacy_migrator import (
    classify_document,
    build_doc_catalog,
    save_doc_catalog,
    scan_and_migrate_legacy_docs,
)

__all__ = [
    "classify_document",
    "build_doc_catalog",
    "save_doc_catalog",
    "scan_and_migrate_legacy_docs",
    "main",
]


def main():
    """
    文档拓扑感知与历史文档索引 CLI 主入口。
    默认只读扫描并建立索引；支持 --copy 显式物理复制。
    """
    parser = argparse.ArgumentParser(description="只读文档拓扑感知与历史文档索引工具")
    parser.add_argument("target_dir", nargs="?", default=None,
                        help="目标工程根目录（默认当前工程根）")
    parser.add_argument("--copy", action="store_true",
                        help="显式开启物理镜像复制至 docs/{category}/原项目文档/（默认只读建立索引，零复制）")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出文档拓扑索引结果")
    args = parser.parse_args()

    target_dir = args.target_dir
    catalog = build_doc_catalog(target_dir)
    catalog_path = save_doc_catalog(catalog, target_dir)

    if args.copy:
        results = scan_and_migrate_legacy_docs(target_dir, copy_physical=True)
        print(f"[SUCCESS] 物理迁移完成，共归档 {len(results)} 篇历史文档至 原项目文档/ 隔离区。")
        return

    if args.json:
        print(json.dumps(catalog, ensure_ascii=False, indent=2))
        return

    print("==============================================================================")
    print(f"[DOCS-INDEX] Multi-Agent Flow · 项目工程文档拓扑只读索引完成")
    print("==============================================================================")
    print(f"• 扫描工程根目录: {catalog.get('project_root', '')}")
    print(f"• 嗅探历史文档数: {catalog.get('total_documents', 0)} 篇")
    print(f"• 索引清单持久化: {catalog_path}")
    print(f"• 物理操作状态: 只读索引 (Zero Relocation / Zero Copy)，宿主文件保持原状")
    print("==============================================================================")


if __name__ == "__main__":
    main()
