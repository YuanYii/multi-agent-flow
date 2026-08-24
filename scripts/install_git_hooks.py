#!/usr/bin/env python3
"""
Git Hooks 自动安装脚本 (Install Git Hooks CLI)
将 scripts/hooks/ 下的钩子脚本自动安装至当前 Git 仓库的 .git/hooks/ 中，
实现本地 `git commit` 时自动调用 verify_git_gate.py 进行强校验与拦截。
"""
import os
import sys
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
HOOKS_SRC_DIR = os.path.join(SCRIPT_DIR, "hooks")
GIT_HOOKS_DIR = os.path.join(PROJECT_ROOT, ".git", "hooks")


def install_hooks() -> bool:
    if not os.path.exists(os.path.join(PROJECT_ROOT, ".git")):
        print(f"[ERROR] 当前目录未检测到 .git 目录 ({PROJECT_ROOT})，无法安装 Git Hooks！")
        return False

    if not os.path.exists(HOOKS_SRC_DIR):
        print(f"[ERROR] 未找到钩子源目录: {HOOKS_SRC_DIR}")
        return False

    os.makedirs(GIT_HOOKS_DIR, exist_ok=True)
    installed = []

    for item in os.listdir(HOOKS_SRC_DIR):
        src_path = os.path.join(HOOKS_SRC_DIR, item)
        if os.path.isfile(src_path) and not item.startswith("."):
            dst_path = os.path.join(GIT_HOOKS_DIR, item)
            shutil.copyfile(src_path, dst_path)
            # 赋予可执行权限
            st = os.stat(dst_path)
            os.chmod(dst_path, st.st_mode | 0o111)
            installed.append(item)

    if installed:
        print(f"[SUCCESS]  🎉 成功安装 Git 门禁钩子至 .git/hooks/: {', '.join(installed)}")
        print("  💡 后续执行 `git commit` 时将自动运行 verify_git_gate.py 进行未验收任务强校验拦截！")
    else:
        print("[WARN]  未发现可安装的钩子文件。")

    return True


if __name__ == "__main__":
    ok = install_hooks()
    sys.exit(0 if ok else 1)
