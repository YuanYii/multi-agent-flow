#!/usr/bin/env python3
"""
Multi-Agent Flow · 52 任务全场景仿真测试入口（向后兼容转发层）
本脚本已统一整合至 scripts/run_simulation.py，保留此入口用于完全兼容历史调用与自动化流水线。

运行命令: python3 scripts/run_52_tasks_simulation.py
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from run_simulation import run_52_main, SimulationRunner52, free_port


def main():
    """向前兼容执行 52 任务仿真。"""
    ok = run_52_main()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
