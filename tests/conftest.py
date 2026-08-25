"""
Pytest 全局配置与路径初始化 (tests/conftest.py)
"""
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

for p in [PROJECT_ROOT, SCRIPTS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)
