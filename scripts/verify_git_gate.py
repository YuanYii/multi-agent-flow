#!/usr/bin/env python3
"""
Git 提交与阶段结项强校验门禁脚本 (Verify Git Gate CLI)
严格贯彻 Fail-Closed 原则：在 DevOps 吕改特执行代码 Git 提交、PR 合流或阶段结项前，
强制校验当前阶段或关联代码涉及的所有任务卡必须全部处于【已验收】（或【已取消】）终态。
若存在任务处于【已完成】（待人类验收）或进行中/审查中/测试中，物理硬拦截！
"""
import sys
import os
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.gates.git_gate_verifier import verify_git_gate


def main():
    parser = argparse.ArgumentParser(description="Git 提交与阶段结项强校验门禁脚本")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--stage", default=None, help="指定校验的项目阶段")
    args = parser.parse_args()

    ok = verify_git_gate(config_path=args.config, stage=args.stage)
    if not ok:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
