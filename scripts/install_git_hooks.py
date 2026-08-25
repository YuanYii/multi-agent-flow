#!/usr/bin/env python3
"""
Git Hooks 自动安装脚本 (Install Git Hooks CLI)
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, SCRIPT_DIR)

from _lib.gates.hooks_installer import install_hooks


def main():
    ok = install_hooks(PROJECT_ROOT)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
