#!/usr/bin/env python3
"""
阿里千问办公 (QwenWork) 专家套件自动化打包与合规校验脚本 (Qwen Packager CLI)
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, SCRIPT_DIR)

from _lib.export.qwen_packager import (
    validate_icon,
    validate_manifest,
    package_plugin,
)


def main():
    print("========================================================================")
    print("        [QWEN-BUILD]   Multi-Agent Workflow · 阿里千问套件打包校验")
    print("========================================================================")

    ok = package_plugin(PROJECT_ROOT)
    if not ok:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
