#!/usr/bin/env python3
"""
只读归档迁移脚本 (Migrate Legacy Docs CLI)
严格遵循“不修改原文档任何内容”红线，识别散落历史文档并只读镜像拷贝放入 docs/{category}/原项目文档/。
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.docs.legacy_migrator import (
    classify_document,
    scan_and_migrate_legacy_docs,
)


def main():
    target_dir = sys.argv[1] if len(sys.argv) > 1 else None
    scan_and_migrate_legacy_docs(target_dir)


if __name__ == "__main__":
    main()
