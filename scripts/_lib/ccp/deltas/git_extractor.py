"""
通过真实 Git 工作区执行器自动提取确定性物理变更，杜绝大模型自述虚报。
内置非 Git 环境防护与优雅降级。
"""
import subprocess
import os
import hashlib
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from ..interfaces import IDeltaExtractor

HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def get_worktree_fingerprint(repo_root: str = ".", fallback_files: Optional[List[str]] = None) -> str:
    """计算当前工作区代码快照指纹 (tree_hash)，包含未跟踪新建文件，非 Git 环境自动降级为 in_scope 文件 SHA256。"""
    try:
        head_tree = subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=repo_root, stderr=subprocess.DEVNULL, text=True
        ).strip()
        diff_bytes = subprocess.check_output(
            ["git", "diff", "HEAD"], cwd=repo_root, stderr=subprocess.DEVNULL
        )
        status_bytes = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo_root, stderr=subprocess.DEVNULL
        )
        digest = hashlib.sha256(head_tree.encode("utf-8") + b"\n" + diff_bytes + b"\n" + status_bytes).hexdigest()
        return f"git-tree:{digest[:16]}"
    except Exception:
        hasher = hashlib.sha256()
        for raw_item in sorted(fallback_files or []):
            rel_path = raw_item.split("#")[0].strip().replace("\\", "/")
            fp = Path(repo_root) / rel_path
            if fp.is_file():
                hasher.update(rel_path.encode("utf-8"))
                hasher.update(fp.read_bytes())
        return f"file-sha256:{hasher.hexdigest()[:16]}"


def extract_changed_line_ranges(repo_root: str = ".") -> List[str]:
    """解析 git diff -U0 HEAD 与未跟踪新建文件，自动生成精确到行号的变更区间列表。"""
    locations: List[str] = []
    try:
        diff_out = subprocess.check_output(
            ["git", "diff", "-U0", "HEAD"],
            cwd=repo_root, stderr=subprocess.DEVNULL, text=True, errors="replace"
        )
    except Exception:
        diff_out = ""

    current_file: Optional[str] = None
    for line in diff_out.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
        elif line.startswith("@@ ") and current_file:
            if m := HUNK_HEADER_RE.match(line):
                del_cnt = int(m.group(2) or "1")
                new_start = int(m.group(3))
                add_cnt = int(m.group(4) or "1")
                new_end = new_start + max(add_cnt - 1, 0)
                locations.append(f"{current_file}:{new_start}-{new_end} (+{add_cnt}, -{del_cnt})")

    # 补充扫描未跟踪新建文件 (git status --porcelain 中 ?? 标记)
    try:
        status_out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo_root, stderr=subprocess.DEVNULL, text=True, errors="replace"
        )
        for line in status_out.splitlines():
            if line.startswith("?? "):
                untracked_rel = line[3:].strip().strip('"')
                fp = Path(repo_root) / untracked_rel
                if fp.is_file():
                    line_cnt = len(fp.read_text(encoding="utf-8", errors="replace").splitlines())
                    locations.append(f"{untracked_rel}:1-{max(line_cnt, 1)} (+{line_cnt}, -0) [新增文件]")
    except Exception:
        pass

    return locations


def detect_out_of_scope_touches(repo_root: str, in_scope: List[str]) -> List[str]:
    """对比 git diff --name-only HEAD 及未跟踪文件与 contract.scope.in_scope，返回越界修改/新建文件列表。"""
    allowed = {item.split("#")[0].strip().replace("\\", "/") for item in (in_scope or []) if item.strip()}
    if not allowed:
        return []
    changed: Set[str] = set()
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD"], cwd=repo_root, stderr=subprocess.DEVNULL, text=True
        )
        for f in out.splitlines():
            if f.strip():
                changed.add(f.strip().replace("\\", "/"))
    except Exception:
        pass

    try:
        status_out = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo_root, stderr=subprocess.DEVNULL, text=True
        )
        for line in status_out.splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                changed.add(parts[1].strip().strip('"').replace("\\", "/"))
    except Exception:
        pass

    return [f for f in sorted(changed) if f not in allowed]



class GitWorkspaceDeltaExtractor(IDeltaExtractor):
    """Git 工作区物理代码变更差量提取器。"""
    def extract_physical(self, workspace_path: str) -> Dict[str, Any]:
        """
        调用 Git Diff 提取当前阶段产生的变更文件、增删行数及修改范围。

        返回:
            list[dict]: 物理变更文件列表。
        """
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
