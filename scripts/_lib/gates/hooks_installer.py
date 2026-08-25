"""
Git 提交拦截钩子自动安装模块
"""
import os
import sys
import shutil
from typing import Optional

import paths as _paths


def install_hooks(project_root: Optional[str] = None) -> bool:
    if project_root is None:
        project_root = _paths.project_root()
    skill_root = _paths.skill_root()
    hooks_src_dir = os.path.join(skill_root, "scripts", "hooks")
    git_hooks_dir = os.path.join(project_root, ".git", "hooks")

    if not os.path.exists(os.path.join(project_root, ".git")):
        print(f"[ERROR] 当前目录未检测到 .git 目录 ({project_root})，无法安装 Git Hooks！")
        return False

    if not os.path.exists(hooks_src_dir):
        print(f"[ERROR] 未找到钩子源目录: {hooks_src_dir}")
        return False

    os.makedirs(git_hooks_dir, exist_ok=True)
    installed = []

    for item in os.listdir(hooks_src_dir):
        src_path = os.path.join(hooks_src_dir, item)
        if os.path.isfile(src_path) and not item.startswith("."):
            dst_path = os.path.join(git_hooks_dir, item)
            shutil.copyfile(src_path, dst_path)
            st = os.stat(dst_path)
            os.chmod(dst_path, st.st_mode | 0o111)
            installed.append(item)

    if installed:
        print(f"[SUCCESS]  🎉 成功安装 Git 门禁钩子至 .git/hooks/: {', '.join(installed)}")
        print("  💡 后续执行 `git commit` 时将自动运行 verify_git_gate.py 进行未验收任务强校验拦截！")
    else:
        print("[WARN]  未发现可安装的钩子文件。")

    return True
