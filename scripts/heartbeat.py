#!/usr/bin/env python3
"""
看板状态巡检脚本 (Kanban Heartbeat)
实现 rules/HEARTBEAT.md 描述的 4 项巡检,输出结构化告警,支持阈值可配置。

巡检项:
  1. 滞留任务检查: 进行中 > 24h 未更新 / 审查中或测试中 > 12h 未流转
  2. 并发上限核验: DEV/FRONTEND 进行中任务数是否超出上限
  3. 状态-处理人一致性核验: 审查中应设 REVIEWER;测试中应设 QA;已完成/已验收 应设 PM
  4. 终态结束时间必填强校验: 已完成/已验收 是否遗漏 end_date

典型用法:
  python3 scripts/heartbeat.py
  python3 scripts/heartbeat.py --config config/workflow.config.yaml --json
  python3 scripts/heartbeat.py --stale-in-progress-hours 12
"""
import os
import sys
import json
import argparse
from datetime import datetime, timezone
from collections import defaultdict
from typing import Any, Dict, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.boards.board_adapter_factory import get_board_adapter
from enums import normalize_role


def _get_status_entry_time(t: Dict[str, Any], status: str) -> datetime | None:
    """从任务 process 节点中倒序解析进入当前 status 的时间戳；无节点时回退至 start_date / start_time"""
    import re as _re
    process = t.get("process")
    if process and isinstance(process, str):
        lines = [line.strip() for line in process.split("\n") if line.strip()]
        for line in reversed(lines):
            if f"更新至【{status}】" in line:
                m = _re.search(r"\[(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}(?::\d{2})?)", line)
                if m:
                    dt = _parse_dt(m.group(1))
                    if dt:
                        return dt
    # 兜底：新任务卡或无节点历史时，回退至 start_date / start_time
    start_date = t.get("start_date") or t.get("start_time")
    return _parse_dt(start_date)


# 默认阈值 (可被 workflow.config.yaml 的 heartbeat 段覆盖)
DEFAULT_THRESHOLDS = {
    "stale_in_progress_hours": 24,   # 进行中滞留阈值
    "stale_review_or_test_hours": 12, # 审查中/测试中滞留阈值
    "dev_max_parallel": 3,           # 开发人员并发上限
    "frontend_max_parallel": 3,      # 前端开发人员并发上限
    "orphan_output_hours": 48,       # 孤儿产出检测窗口（近 N 小时新增交付文件无对应卡片）
}


def _parse_dt(s: Any) -> datetime | None:
    if not s:
        return None
    s_clean = str(s).strip()
    try:
        iso_str = s_clean.replace("Z", "+00:00")
        return datetime.fromisoformat(iso_str)
    except Exception:
        pass
    fmts = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]
    for fmt in fmts:
        try:
            return datetime.strptime(s_clean, fmt)
        except Exception:
            pass
    return None


def _now() -> datetime:
    return datetime.now()


def _normalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """统一 record 字段,兼容 list_records 返回结构 {record_id, fields:{...}}"""
    if "fields" in rec and isinstance(rec["fields"], dict):
        out = dict(rec["fields"])
        if "record_id" not in out and "record_id" in rec:
            out["record_id"] = rec["record_id"]
        return out
    return rec


def run_heartbeat(
    adapter: Any,
    thresholds: Dict[str, int] = None,
    now: datetime = None,
    doc_dirs_override: list = None,
) -> Dict[str, Any]:
    """
    执行 4 项巡检,返回结构化告警结果。
    doc_dirs_override: 孤儿产出巡检目录覆盖（测试注入用；默认 data_root/docs/04-研发过程/{报告,任务}）

    返回结构:
    {
      "checked_at": "...",
      "total_tasks": N,
      "alerts": [ {severity, code, task_id, message}, ... ],
      "summary": {critical: N, warning: N, info: N}
    }
    """
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    now = now or _now()
    alerts: List[Dict[str, Any]] = []

    try:
        records = adapter.list_records(limit=1000)
    except Exception as e:
        return {
            "checked_at": now.isoformat(),
            "total_tasks": 0,
            "alerts": [{"severity": "critical", "code": "ADAPTER_ERROR", "task_id": "-", "message": str(e)}],
            "summary": {"critical": 1, "warning": 0, "info": 0},
        }

    tasks = [_normalize_record(r) for r in records]
    total = len(tasks)

    # ---- 巡检 5: 孤儿产出检测（交付目录近 N 小时新增文件，名称未命中任何看板任务 → 标黄） ----
    try:
        import re as _re
        import paths as _paths
        data_root = _paths.resolve_data_root()
        doc_dirs = doc_dirs_override or [
            os.path.join(data_root, "docs", "D04-研发过程", "D02-报告"),
            os.path.join(data_root, "docs", "D04-研发过程", "D01-任务"),
            os.path.join(data_root, "docs", "04-研发过程", "02-报告"),
            os.path.join(data_root, "docs", "04-研发过程", "01-任务"),
            os.path.join(data_root, "docs", "04-研发过程", "报告"),
            os.path.join(data_root, "docs", "04-研发过程", "任务"),
        ]
        card_names = [str(t.get("name") or t.get("task_name") or "") for t in tasks]
        def _norm(s):
            return _re.sub(r"[\s\u3000，,。.;；:：()（）\[\]【】\-\_/\\|]", "", str(s)).lower()
        norms = [_norm(n) for n in card_names if _norm(n)]
        orphan_hours = float(thresholds.get("orphan_output_hours", 48))
        cutoff = now.timestamp() - orphan_hours * 3600
        for base_dir in doc_dirs:
            if not os.path.isdir(base_dir):
                continue
            for root, _dirs, files in os.walk(base_dir):
                for fn in files:
                    if not fn.lower().endswith((".md", ".html", ".txt", ".json")):
                        continue
                    fp = os.path.join(root, fn)
                    try:
                        if os.path.getmtime(fp) < cutoff:
                            continue
                    except Exception:
                        continue
                    nb = _norm(os.path.splitext(fn)[0])
                    if nb and not any(nb in c or c in nb for c in norms):
                        alerts.append({
                            "severity": "warning",
                            "code": "ORPHAN_OUTPUT",
                            "task_id": "-",
                            "message": f"孤儿成果: {fp} (近 {orphan_hours:.0f}h 新增但看板无对应任务，建议补录；若为 L0 即时问答产出：归档至 草稿箱/ 或升级为 L1 建卡)",
                        })
    except Exception:
        pass

    # 任务按 assignee (开发人员) 分组
    dev_active_count: Dict[str, int] = defaultdict(int)
    fe_active_count: Dict[str, int] = defaultdict(int)

    for t in tasks:
        tid = t.get("record_id") or t.get("id") or "?"
        status = t.get("status", "")
        assignee = t.get("assignee", "")
        start_date = t.get("start_date") or t.get("start_time")
        end_date = t.get("end_date") or t.get("end_time")
        start_dt = _parse_dt(start_date)
        end_dt = _parse_dt(end_date)
        status_entry_dt = _get_status_entry_time(t, status)

        # ---- 巡检 1: 滞留任务 ----
        if status == "进行中" and status_entry_dt:
            hours = (now - status_entry_dt).total_seconds() / 3600
            if hours > thresholds["stale_in_progress_hours"]:
                alerts.append({
                    "severity": "warning",
                    "code": "STALE_IN_PROGRESS",
                    "task_id": tid,
                    "message": f"任务 {tid} 已进行中 {hours:.1f}h (阈值 {thresholds['stale_in_progress_hours']}h),处理人 {assignee}",
                })
        elif status in ("审查中", "测试中") and status_entry_dt:
            hours = (now - status_entry_dt).total_seconds() / 3600
            if hours > thresholds["stale_review_or_test_hours"]:
                alerts.append({
                    "severity": "warning",
                    "code": "STALE_REVIEW_OR_TEST",
                    "task_id": tid,
                    "message": f"任务 {tid} 处于 {status} 已 {hours:.1f}h (阈值 {thresholds['stale_review_or_test_hours']}h)",
                })

        # ---- 巡检 2: 并发上限 (累计) ----
        if status == "进行中":
            norm_who = normalize_role(assignee)
            who = assignee if norm_who == "未分配" else norm_who
            role_hint = (t.get("role_hint") or "").upper()
            if "前端" in who or "frontend" in str(assignee).lower() or role_hint == "FRONTEND" or who == "马前端":
                fe_active_count[who] += 1
            else:
                dev_active_count[who] += 1

        # ---- 巡检 3: 状态-处理人一致性 ----
        assignee_str = str(assignee).strip().upper()
        if status == "审查中" and not any(k in assignee_str for k in ["REVIEWER", "周审查", "审查"]):
            alerts.append({
                "severity": "critical",
                "code": "ASSIGNEE_MISMATCH_REVIEW",
                "task_id": tid,
                "message": f"任务 {tid} 处于【审查中】,处理人应为 REVIEWER,当前为 {assignee}",
            })
        if status == "测试中" and not any(k in assignee_str for k in ["QA", "章测试", "测试"]):
            alerts.append({
                "severity": "critical",
                "code": "ASSIGNEE_MISMATCH_TEST",
                "task_id": tid,
                "message": f"任务 {tid} 处于【测试中】,处理人应为 QA,当前为 {assignee}",
            })
        if status in ("已完成", "已验收", "已取消") and not any(k in assignee_str for k in ["PM", "严经理", "经理"]):
            alerts.append({
                "severity": "warning",
                "code": "ASSIGNEE_MISMATCH_TERMINAL",
                "task_id": tid,
                "message": f"任务 {tid} 处于终态【{status}】,处理人应为 PM,当前为 {assignee}",
            })

        # ---- 巡检 4: 终态结束时间必填 ----
        if status in ("已完成", "已验收", "已取消") and not end_dt:
            alerts.append({
                "severity": "critical",
                "code": "MISSING_END_TIME",
                "task_id": tid,
                "message": f"任务 {tid} 处于终态【{status}】但缺失 end_date 字段",
            })

    # ---- 巡检 2 后置: 并发上限检查 ----
    for who, cnt in dev_active_count.items():
        if cnt > thresholds["dev_max_parallel"]:
            alerts.append({
                "severity": "critical",
                "code": "DEV_CONCURRENCY_EXCEEDED",
                "task_id": "-",
                "message": f"开发人员 {who} 进行中任务数 {cnt} 超出上限 {thresholds['dev_max_parallel']}",
            })
    for who, cnt in fe_active_count.items():
        if cnt > thresholds["frontend_max_parallel"]:
            alerts.append({
                "severity": "critical",
                "code": "FRONTEND_CONCURRENCY_EXCEEDED",
                "task_id": "-",
                "message": f"前端开发 {who} 进行中任务数 {cnt} 超出上限 {thresholds['frontend_max_parallel']}",
            })

    # ---- 巡检 6: 阻塞 PR 状态巡检与合流解阻感知 ----
    try:
        from sync_pr_status import extract_pr_identifiers, query_pr_status
        for t in tasks:
            if str(t.get("status", "")).strip() == "已阻塞":
                tid = t.get("record_id") or t.get("id") or "?"
                remarks = str(t.get("remarks") or "")
                process = str(t.get("process") or "")
                pr_list = extract_pr_identifiers(f"{remarks}\n{process}")
                if pr_list:
                    pr_ref = pr_list[0]["number"]
                    repo = pr_list[0].get("repo")
                    pr_info = query_pr_status(pr_ref, repo=repo)
                    if pr_info and not pr_info.get("error"):
                        if pr_info.get("is_merged"):
                            alerts.append({
                                "severity": "warning",
                                "code": "PR_MERGED_READY_UNBLOCK",
                                "task_id": tid,
                                "message": f"任务 {tid} 绑定的 PR #{pr_ref} 已成功合入，建议运行 sync_pr_status.py 自动解阻并移交 PM 严经理验收",
                            })
                        elif pr_info.get("state") == "CLOSED":
                            alerts.append({
                                "severity": "critical",
                                "code": "PR_CLOSED_UNMERGED",
                                "task_id": tid,
                                "message": f"任务 {tid} 绑定的 PR #{pr_ref} 已被关闭且未合并，请原开发者重新排查！",
                            })
    except Exception:
        pass

    # ---- 统计指标与大盘度量 (Metrics Overview) ----
    completed_count = sum(1 for t in tasks if t.get("status") in ("已完成", "已验收"))
    in_progress_count = sum(1 for t in tasks if t.get("status") == "进行中")
    blocked_count = sum(1 for t in tasks if t.get("status") == "已阻塞")
    completion_rate = (completed_count / total * 100) if total > 0 else 0.0

    lead_times = []
    role_workload = defaultdict(lambda: {"in_progress": 0, "completed": 0, "total": 0})
    for t in tasks:
        st = t.get("status", "")
        who = normalize_role(t.get("assignee", "")) or "未分配"
        role_workload[who]["total"] += 1
        if st == "进行中":
            role_workload[who]["in_progress"] += 1
        elif st in ("已完成", "已验收"):
            role_workload[who]["completed"] += 1

        s_dt = _parse_dt(t.get("start_date") or t.get("start_time"))
        e_dt = _parse_dt(t.get("end_date") or t.get("end_time"))
        if s_dt and e_dt and e_dt >= s_dt:
            lead_times.append((e_dt - s_dt).total_seconds() / 3600)

    avg_lead_time = (sum(lead_times) / len(lead_times)) if lead_times else 0.0

    summary = {"critical": 0, "warning": 0, "info": 0}
    for a in alerts:
        sev = a.get("severity", "info")
        if sev in summary:
            summary[sev] += 1

    return {
        "checked_at": now.strftime("%Y-%m-%d %H:%M:%S") if isinstance(now, datetime) else str(now),
        "thresholds": thresholds,
        "total_tasks": total,
        "metrics": {
            "completed": completed_count,
            "in_progress": in_progress_count,
            "blocked": blocked_count,
            "completion_rate_pct": round(completion_rate, 1),
            "avg_lead_time_hours": round(avg_lead_time, 1),
            "role_workload": dict(role_workload),
        },
        "alerts": alerts,
        "summary": summary,
    }


def format_progress_bar(pct: float, width: int = 15) -> str:
    filled = int(round(width * (pct / 100.0)))
    filled = max(0, min(width, filled))
    return f"[{'█' * filled}{'░' * (width - filled)}] {pct:.1f}%"


def main():
    parser = argparse.ArgumentParser(description="看板全局大盘与健康巡检 (Status & Health Check)")
    parser.add_argument("--config", default=None, help="看板配置文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--sync-pr", action="store_true", help="自动同步并解除已合入 PR 的阻塞状态")
    parser.add_argument("--stale-in-progress-hours", type=int, help="覆盖默认 24h 滞留阈值")
    parser.add_argument("--stale-review-or-test-hours", type=int, help="覆盖默认 12h 审查/测试滞留阈值")
    args = parser.parse_args()

    # 1. 若指定 --sync-pr，优先执行 PR 状态同步与解阻
    if args.sync_pr:
        try:
            from sync_pr_status import sync_blocked_prs, format_terminal_summary
            pr_report = sync_blocked_prs(config_path=args.config)
            if not args.json:
                print(format_terminal_summary(pr_report))
                print("\n" + "=" * 80)
        except Exception as e:
            sys.stderr.write(f"[WARN]  PR 状态同步跳过: {e}\n")

    thresholds = dict(DEFAULT_THRESHOLDS)
    if args.stale_in_progress_hours is not None:
        thresholds["stale_in_progress_hours"] = args.stale_in_progress_hours
    if args.stale_review_or_test_hours is not None:
        thresholds["stale_review_or_test_hours"] = args.stale_review_or_test_hours

    try:
        adapter = get_board_adapter(args.config)
    except Exception as e:
        sys.stderr.write(f"[FAILED]  [Heartbeat] 加载看板适配器失败: {e}\n")
        sys.exit(2)

    result = run_heartbeat(adapter, thresholds=thresholds)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        m = result.get("metrics", {})
        print("=" * 80)
        print("       YY-Flow 看板全局大盘与健康巡检 (Status & Health Check)")
        print("=" * 80)
        print(f" 巡检时间: {result['checked_at']}        任务总数: {result['total_tasks']} 项")
        print(f" 总体进度: {format_progress_bar(m.get('completion_rate_pct', 0.0))} (已验收/完成: {m.get('completed', 0)} / 进行中: {m.get('in_progress', 0)} / 已阻塞: {m.get('blocked', 0)})")
        if m.get("avg_lead_time_hours", 0) > 0:
            print(f" 平均交付周期: {m.get('avg_lead_time_hours')} 小时 (Lead Time)")
        print("-" * 80)
        print(" 专家角色在手负载:")
        role_items = [f"{r}: 进{data['in_progress']}/完{data['completed']}" for r, data in sorted(m.get("role_workload", {}).items()) if r != "未分配"]
        # 每行 4 个角色
        for i in range(0, len(role_items), 4):
            print("   " + "   |   ".join(role_items[i:i+4]))
        print("-" * 80)
        print(f"[WARN]   异常告警统计: critical={result['summary']['critical']}  warning={result['summary']['warning']}  info={result['summary']['info']}")
        if not result["alerts"]:
            print(" [SUCCESS]  全部通过, 当前无流转卡点与风险告警")
        else:
            display_limit = 10
            for a in result["alerts"][:display_limit]:
                icon = {"critical": "[CRITICAL] ", "warning": "[WARN] ", "info": ""}.get(a["severity"], "")
                print(f"  {icon} [{a['code']}] {a['message']}")
            if len(result["alerts"]) > display_limit:
                print(f"  ... 剩余 {len(result['alerts']) - display_limit} 项告警已收起，可运行 /yy-flow kanban 在 Web 看板或添加 --json 参数查看全量明细")
        print("=" * 80)

    # 退出码: 0=无告警, 1=有告警, 2=致命错误
    if result["summary"]["critical"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
