"""
通过真实 Git 工作区执行器自动提取确定性物理变更，杜绝大模型自述虚报。
内置非 Git 环境防护与优雅降级。
"""
import subprocess
import os
from typing import Dict, Any, List
from ..interfaces import IDeltaExtractor


class GitWorkspaceDeltaExtractor(IDeltaExtractor):
    def extract_physical(self, workspace_path: str) -> Dict[str, Any]:
        empty_res = {"files_modified": [], "lines_added": 0, "lines_deleted": 0}
        if not workspace_path or not os.path.isdir(workspace_path):
            return empty_res

        # 检查是否为合法的 Git 工作树
        git_dir = os.path.join(workspace_path, ".git")
        if not os.path.exists(git_dir):
            return empty_res

        try:
            # 1. 获取变更文件简表
            status_res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                check=False
            )
            if status_res.returncode != 0:
                return empty_res

            files = []
            for line in status_res.stdout.splitlines():
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    files.append(parts[1])

            # 2. 获取行数增删统计
            diff_res = subprocess.run(
                ["git", "diff", "--shortstat"],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                check=False
            )
            added = 0
            deleted = 0
            stat_text = diff_res.stdout.strip()
            if stat_text:
                for segment in stat_text.split(","):
                    seg = segment.strip()
                    if "insertion" in seg:
                        try:
                            added = int(seg.split()[0])
                        except Exception:
                            pass
                    elif "deletion" in seg:
                        try:
                            deleted = int(seg.split()[0])
                        except Exception:
                            pass

            return {
                "files_modified": files,
                "lines_added": added,
                "lines_deleted": deleted,
            }
        except Exception:
            return empty_res

    def extract_cognitive(self, raw_model_response: str) -> Dict[str, Any]:
        """认知增量提取基线实现"""
        return {
            "added_decisions": [],
            "discoveries": [],
            "assumptions_validated": [],
            "new_unresolved_unknowns": []
        }
