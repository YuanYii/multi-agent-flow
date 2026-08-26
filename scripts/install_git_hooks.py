#!/usr/bin/env python3
"""
Git Hooks 自动安装脚本 (Install Git Hooks CLI)
"""
import os
import sys
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.gates.hooks_installer import install_hooks
import paths as _paths


def main():
    parser = argparse.ArgumentParser(description="Git Hooks 自动安装脚本")
    parser.add_argument("--project-root", default=None,
                        help="目标项目根目录 (默认按 paths.project_root() 解析：YY_FLOW_PROJECT_ROOT / .yy-flow / legacy / CWD)")
    args = parser.parse_args()
    project_root = args.project_root or _paths.project_root()
    ok = install_hooks(project_root)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
