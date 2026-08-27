#!/usr/bin/env python3
"""
sync_pr_status.py · YY-Flow GitHub PR 门控状态感知与自动解阻引擎

职责：
1. 扫描看板中所有【已阻塞】任务卡，提取备注与过程日志中的 PR 编号或 URL。
2. 调用 GitHub CLI (`gh pr view`) 获取 PR 实时状态 (MERGED, CLOSED, OPEN)。
3. 当检测到 PR 已合入 (MERGED)：
   - 自动调用状态流转引擎解除【已阻塞】，推进至【已完成】；
   - 经办人 (Assignee) 自动移交至 PM (严经理)；
   - 在过程记录中自动落盘 Merge Commit SHA、目标分支与合流审计凭据；
   - 输出结构化验收通知载荷，提醒 PM 严经理执行终态验收。
4. 当检测到 PR 已关闭未合入 (CLOSED)：
   - 产生高危告警，支持可选自动打回至【已退回】通知原开发者。
5. 具备离线与无 gh 环境优雅降级能力 (Fail-Soft)。
"""

import os
import sys
import json
import re
import shutil
import argparse
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from paths import resolve_data_root, project_root, runtime_config_path
from _lib.boards.board_adapter_factory import get_board_adapter
from _lib.boards.offline_board_adapter import OfflineBoardAdapter
from transition_task import transition_task_pipeline


def extract_pr_identifiers(text: str) -> List[Dict[str, str]]:
    """
    从文本中解析 PR 编号或完整 URL。
    支持格式：
    - [PR: https://github.com/owner/repo/pull/123]
    - https://github.com/owner/repo/pull/123
    - PR #123 / PR#123 / pull/123
    - 【阻断】等待 PR #123 合并入库
    """
    if not text or not isinstance(text, str):
        return []

    results = []
    seen = set()

    # 1. 匹配完整 GitHub PR URL
    url_pattern = r"https?://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)"
    for m in re.finditer(url_pattern, text, re.IGNORECASE):
        owner, repo, number = m.group(1), m.group(2), m.group(3)
        key = f"{owner}/{repo}#{number}"
        if key not in seen:
            seen.add(key)
            results.append({
                "raw": m.group(0),
                "number": number,
                "repo": f"{owner}/{repo}",
                "url": m.group(0),
            })

    # 2. 匹配 PR #123 或 PR#123 或 [PR: 123]
    pr_num_pattern = r"(?:PR|Pull Request|PR\s*:)\s*#?(\d+)"
    for m in re.finditer(pr_num_pattern, text, re.IGNORECASE):
        number = m.group(1)
        if number not in seen:
            seen.add(number)
            results.append({
                "raw": m.group(0),
                "number": number,
                "repo": None,
                "url": None,
            })

    return results


def query_pr_status(pr_ref: str, repo: Optional[str] = None, project_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    通过 gh CLI 查询 PR 状态。
    返回 dict: {number, state, merged, merge_commit_sha, title, url, base_ref, head_ref}
    """
    if not shutil.which("gh"):
        return {"error": "gh_cli_not_found", "message": "系统未安装 GitHub CLI (gh)"}

    cmd = [
        "gh", "pr", "view", str(pr_ref),
        "--json", "number,state,mergedAt,mergeCommit,url,title,headRefName,baseRefName",
    ]
    if repo:
        cmd.extend(["--repo", repo])

    cwd = project_dir or project_root()
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        if res.returncode != 0:
            err_msg = (res.stderr or res.stdout or "").strip()
            return {"error": "gh_query_failed", "message": err_msg}

        data = json.loads(res.stdout)
        state = str(data.get("state") or "").upper()
        merged_at = data.get("mergedAt")
        is_merged = state == "MERGED" or bool(merged_at)

        merge_commit = data.get("mergeCommit") or {}
        merge_sha = merge_commit.get("oid") if isinstance(merge_commit, dict) else str(merge_commit)
        if not merge_sha and is_merged:
            merge_sha = "MERGED"

        return {
            "number": str(data.get("number") or pr_ref),
            "state": "MERGED" if is_merged else state,
            "is_merged": is_merged,
            "merge_commit_sha": merge_sha or "-",
            "title": str(data.get("title") or ""),
            "url": str(data.get("url") or ""),
            "head_ref": str(data.get("headRefName") or ""),
            "base_ref": str(data.get("baseRefName") or ""),
        }
    except Exception as e:
        return {"error": "exception", "message": str(e)}


def sync_blocked_prs(
    config_path: Optional[str] = None,
    project_dir: Optional[str] = None,
    dry_run: bool = False,
    auto_reject_closed: bool = False,
) -> Dict[str, Any]:
    """
    扫描并同步所有处于【已阻塞】状态且绑定 PR 的任务卡。
    """
    if project_dir:
        os.environ["YY_FLOW_PROJECT_ROOT"] = os.path.abspath(project_dir)

    data_root = resolve_data_root(explicit=project_dir)
    board_file = os.path.join(data_root, "user_data", "board.json")

    if not config_path and os.path.isfile(board_file):
        adapter = OfflineBoardAdapter(board_file=board_file)
    else:
        adapter = get_board_adapter(config_path)

    try:
        records = adapter.list_records(limit=2000)
    except Exception as e:
        return {
            "success": False,
            "error": f"加载看板记录失败: {e}",
            "unblocked_tasks": [],
            "rejected_tasks": [],
            "pending_tasks": [],
        }

    blocked_tasks = []
    for r in records:
        f = r.get("fields", {}) if "fields" in r else r
        status = str(f.get("status") or "").strip()
        if status == "已阻塞":
            blocked_tasks.append(f)

    if not blocked_tasks:
        return {
            "success": True,
            "message": "看板中无处于【已阻塞】的任务卡",
            "blocked_count": 0,
            "unblocked_tasks": [],
            "rejected_tasks": [],
            "pending_tasks": [],
            "pm_notifications": [],
        }

    unblocked_tasks = []
    rejected_tasks = []
    pending_tasks = []
    pm_notifications = []

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for task in blocked_tasks:
        tid = task.get("id") or task.get("record_id") or "未知ID"
        name = task.get("name") or task.get("task_name") or "未命名任务"
        t_type = task.get("type") or "A"
        assignee = task.get("assignee") or task.get("handler") or "DEV"
        remarks = str(task.get("remarks") or "")
        process = str(task.get("process") or "")
        combined_text = f"{remarks}\n{process}"

        pr_list = extract_pr_identifiers(combined_text)
        if not pr_list:
            continue

        target_pr = pr_list[0]
        pr_ref = target_pr["number"]
        repo = target_pr.get("repo")

        status_info = query_pr_status(pr_ref, repo=repo, project_dir=project_dir)
        if not status_info or "error" in status_info:
            pending_tasks.append({
                "id": tid,
                "name": name,
                "pr_ref": pr_ref,
                "status": "QUERY_FAILED",
                "detail": status_info.get("message", "查询失败") if status_info else "无响应",
            })
            continue

        pr_state = status_info.get("state", "OPEN")
        merge_sha = status_info.get("merge_commit_sha", "-")
        base_ref = status_info.get("base_ref", "main")
        pr_title = status_info.get("title", "")
        pr_url = status_info.get("url") or f"PR #{pr_ref}"

        # 1. 状态为 MERGED -> 自动解阻推至【已完成】
        if status_info.get("is_merged"):
            short_sha = merge_sha[:7] if len(merge_sha) >= 7 else merge_sha
            unblock_remarks = f"【解除】PR #{pr_ref} 已成功合并至分支 {base_ref} (Merge SHA: {short_sha})，交付 PM 严经理验收"

            if not dry_run:
                ok = transition_task_pipeline(
                    config_path=config_path,
                    task_id=tid,
                    current_role="PM",
                    from_status="已阻塞",
                    to_status="已完成",
                    assignee="严经理",
                    task_type=t_type,
                    end_time=now_str,
                    remarks=unblock_remarks,
                    delegated_by="PM",
                    delegation_reason=f"AUTOMATION(PR_SYNC): PR #{pr_ref} 合流自动解阻 (非人类授权)",
                )
                if ok:
                    unblocked_tasks.append({
                        "id": tid,
                        "name": name,
                        "pr_ref": pr_ref,
                        "merge_sha": short_sha,
                        "base_ref": base_ref,
                    })
                    pm_notifications.append({
                        "task_id": tid,
                        "task_name": name,
                        "pr_number": pr_ref,
                        "pr_title": pr_title,
                        "pr_url": pr_url,
                        "merge_sha": short_sha,
                        "base_ref": base_ref,
                    })
            else:
                unblocked_tasks.append({
                    "id": tid,
                    "name": name,
                    "pr_ref": pr_ref,
                    "merge_sha": short_sha,
                    "base_ref": base_ref,
                    "simulated": True,
                })
                pm_notifications.append({
                    "task_id": tid,
                    "task_name": name,
                    "pr_number": pr_ref,
                    "pr_title": pr_title,
                    "pr_url": pr_url,
                    "merge_sha": short_sha,
                    "base_ref": base_ref,
                })

        # 2. 状态为 CLOSED 且未合并 -> PR 被拒绝
        elif pr_state == "CLOSED":
            if auto_reject_closed:
                reject_remarks = f"【打回】PR #{pr_ref} 已被关闭且未合并，请原开发者重新排查"
                if not dry_run:
                    ok = transition_task_pipeline(
                        config_path=config_path,
                        task_id=tid,
                        current_role="PM",
                        from_status="已阻塞",
                        to_status="已退回",
                        assignee=assignee,
                        task_type=t_type,
                        remarks=reject_remarks,
                        delegated_by="PM",
                        delegation_reason=f"AUTOMATION(PR_SYNC): PR #{pr_ref} 未合入关闭自动打回 (非人类授权)",
                    )
                    if ok:
                        rejected_tasks.append({
                            "id": tid,
                            "name": name,
                            "pr_ref": pr_ref,
                            "status": "REJECTED_TO_RETURNED",
                        })
            else:
                rejected_tasks.append({
                    "id": tid,
                    "name": name,
                    "pr_ref": pr_ref,
                    "status": "PR_CLOSED_UNMERGED",
                })

        # 3. 仍在 OPEN 状态
        else:
            pending_tasks.append({
                "id": tid,
                "name": name,
                "pr_ref": pr_ref,
                "state": pr_state,
                "base_ref": base_ref,
            })

    return {
        "success": True,
        "blocked_count": len(blocked_tasks),
        "unblocked_tasks": unblocked_tasks,
        "rejected_tasks": rejected_tasks,
        "pending_tasks": pending_tasks,
        "pm_notifications": pm_notifications,
    }


def format_pm_notification_card(notifications: List[Dict[str, Any]]) -> str:
    """生成结构化 PM 验收通知卡片"""
    if not notifications:
        return ""

    lines = []
    lines.append("=" * 64)
    lines.append("📢 【GitHub PR 合流自动解阻与 PM 验收通知】")
    lines.append("=" * 64)

    for idx, n in enumerate(notifications, 1):
        lines.append(f"{idx}. 任务卡: [{n['task_id']}] {n['task_name']}")
        lines.append(f"   • PR 详情: #{n['pr_number']} ({n['pr_title'] or n['pr_url']})")
        lines.append(f"   • 目标分支: {n['base_ref']} (Merge SHA: {n['merge_sha']})")
        lines.append(f"   • 状态变更: 【已阻塞】 ➔ 【已完成】 (经办人已收敛至 严经理)")

    lines.append("-" * 64)
    lines.append("🚀 请 PM 严经理 (@flow-pm) 审阅合流凭证与测试结果，执行终态【已验收】签署：")
    for n in notifications:
        lines.append(f"   python3 scripts/transition_task.py --role PM --task-id {n['task_id']} --from-status 已完成 --to-status 已验收 --assignee 严经理 --end-time \"$(date '+%Y-%m-%d %H:%M:%S')\"")
    lines.append("=" * 64)
    return "\n".join(lines)


def format_terminal_summary(report: Dict[str, Any]) -> str:
    """格式化终端报告"""
    lines = []
    lines.append("=" * 64)
    lines.append("       YY-Flow GitHub PR 状态监听与自动解阻巡检")
    lines.append("=" * 64)
    lines.append(f"• 扫描阻塞任务卡数: {report.get('blocked_count', 0)}")
    lines.append(f"• 成功合流解阻卡数: {len(report.get('unblocked_tasks', []))}")
    lines.append(f"• 异常/关闭卡数:     {len(report.get('rejected_tasks', []))}")
    lines.append(f"• 继续等待合流数:   {len(report.get('pending_tasks', []))}")

    if report.get("unblocked_tasks"):
        lines.append("-" * 64)
        lines.append("✅ 成功解阻推进至【已完成】的任务:")
        for t in report["unblocked_tasks"]:
            sim_str = " (模拟)" if t.get("simulated") else ""
            lines.append(f"   - [{t['id']}] {t['name']} (PR #{t['pr_ref']} -> {t['base_ref']}, SHA: {t['merge_sha']}){sim_str}")

    if report.get("rejected_tasks"):
        lines.append("-" * 64)
        lines.append("⚠️  检测到已关闭未合并的异常 PR:")
        for t in report["rejected_tasks"]:
            lines.append(f"   - [{t['id']}] {t['name']} (PR #{t['pr_ref']}, 状态: {t['status']})")

    if report.get("pending_tasks"):
        lines.append("-" * 64)
        lines.append("⏳ 正在等待审查与合流的 PR:")
        for t in report["pending_tasks"]:
            lines.append(f"   - [{t['id']}] {t['name']} (PR #{t['pr_ref']}, 当前状态: {t.get('state', 'OPEN')})")

    lines.append("=" * 64)

    if report.get("pm_notifications"):
        lines.append("\n" + format_pm_notification_card(report["pm_notifications"]))

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="YY-Flow GitHub PR 状态感知与自动解阻引擎")
    parser.add_argument("--config", default=None, help="看板配置文件路径")
    parser.add_argument("--project-root", default=None, help="项目根目录路径")
    parser.add_argument("--dry-run", action="store_true", help="模拟模式：不实际落盘修改状态")
    parser.add_argument("--auto-reject-closed", action="store_true", help="当 PR 被关闭且未合并时，自动将卡片打回为【已退回】")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")

    args = parser.parse_args()

    report = sync_blocked_prs(
        config_path=args.config,
        project_dir=args.project_root,
        dry_run=args.dry_run,
        auto_reject_closed=args.auto_reject_closed,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_terminal_summary(report))

    if not report.get("success", False):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
