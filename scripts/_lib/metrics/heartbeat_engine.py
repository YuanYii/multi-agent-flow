"""
心跳巡检核心分析引擎模块
"""
import os
import sys
import json
import re as _re
from datetime import datetime, timezone
from collections import defaultdict
from typing import Any, Dict, List, Optional

import paths as _paths
from enums import normalize_role


DEFAULT_THRESHOLDS = {
    "stale_in_progress_hours": 24,   # 进行中滞留阈值
    "stale_review_or_test_hours": 12, # 审查中/测试中滞留阈值
    "dev_max_parallel": 3,           # 开发人员并发上限
    "frontend_max_parallel": 3,      # 前端开发人员并发上限
    "orphan_output_hours": 48,       # 孤儿产出检测窗口（近 N 小时新增交付文件无对应卡片）
}


def _get_status_entry_time(t: Dict[str, Any], status: str) -> Optional[datetime]:
    """从任务 process 节点中倒序解析进入当前 status 的时间戳；无节点时回退至 start_date / start_time"""
    process = t.get("process")
    if process and isinstance(process, str):
        lines = [line.strip() for line in process.split("\n") if line.strip()]
        # 行首锚定正则：严格匹配状态段，支持标准双轨格式与历史存量格式，免疫说明中偶现的状态词
        node_regex = _re.compile(
            r"^\[(?:T\d+-N\d+|[^\]]+)\]\s+\[(?P<ts>\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}(?::\d{2})?)\]\s+"
            r"(?:状态[:：]\s*【[^】]+】\s*->\s*|状态由【[^】]+】更新至|初始状态)【(?P<target>[^】]+)】"
        )
        for line in reversed(lines):
            m = node_regex.match(line)
            if m and m.group("target") == status:
                dt = _parse_dt(m.group("ts"))
                if dt:
                    return dt
            # 兼容极简历史旧格式: "[2026-08-01 10:00:00] [待开始] ..."
            m_simple = _re.match(r"^\[(?P<ts>\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}(?::\d{2})?)\]\s+\[(?P<target>[^\]]+)\]", line)
            if m_simple and m_simple.group("target") == status:
                dt = _parse_dt(m_simple.group("ts"))
                if dt:
                    return dt
            # 兼容旧式单行拖拽联动: "[2026-08-01 10:00:00] [看板拖拽联动] 将状态由【待开始】更新至【进行中】"
            m_drag = _re.search(r"^\[(?P<ts>\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}(?::\d{2})?)\].*?更新至【(?P<target>[^】]+)】", line)
            if m_drag and m_drag.group("target") == status:
                dt = _parse_dt(m_drag.group("ts"))
                if dt:
                    return dt
    # 兜底：新任务卡或无节点历史时，回退至 start_date / start_time
    start_date = t.get("start_date") or t.get("start_time")
    return _parse_dt(start_date)


def _parse_dt(s: Any) -> Optional[datetime]:
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
    thresholds: Optional[Dict[str, int]] = None,
    now: Optional[datetime] = None,
    doc_dirs_override: Optional[list] = None,
) -> Dict[str, Any]:
    """
    执行 4 项巡检,返回结构化告警结果。
    doc_dirs_override: 孤儿产出巡检目录覆盖（测试注入用；默认 data_root/docs/04-研发过程/{报告,任务}）
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

    # ---- 巡检 5: 孤儿产出检测 ----
    try:
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
        handler = t.get("handler") or assignee
        start_date = t.get("start_date") or t.get("start_time")
        end_date = t.get("end_date") or t.get("end_time")
        start_dt = _parse_dt(start_date)
        end_dt = _parse_dt(end_date)
        status_entry_dt = _get_status_entry_time(t, status)

        # ---- 巡检 0: 日期格式合规性与数据清洗提醒 ----
        for dt_field_name, raw_val in [("start_date", start_date), ("end_date", end_date)]:
            if raw_val and str(raw_val).strip() not in ("", "-"):
                if not _parse_dt(raw_val):
                    alerts.append({
                        "severity": "warning",
                        "code": "INVALID_DATE_FORMAT",
                        "task_id": tid,
                        "message": f"任务 {tid} 的 {dt_field_name} 格式异常 ({raw_val})，建议执行数据清洗以确保时序度量合规",
                    })

        # ---- 巡检 1: 滞留任务 ----
        if status == "进行中" and status_entry_dt:
            hours = (now - status_entry_dt).total_seconds() / 3600
            if hours > thresholds["stale_in_progress_hours"]:
                alerts.append({
                    "severity": "warning",
                    "code": "STALE_IN_PROGRESS",
                    "task_id": tid,
                    "message": f"任务 {tid} 已进行中 {hours:.1f}h (阈值 {thresholds['stale_in_progress_hours']}h),处理人 {handler}",
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
            norm_who = normalize_role(handler)
            who = handler if norm_who == "未分配" else norm_who
            role_hint = (t.get("role_hint") or "").upper()
            if "前端" in who or "frontend" in str(handler).lower() or role_hint == "FRONTEND" or who == "马前端":
                fe_active_count[who] += 1
            else:
                dev_active_count[who] += 1

        # ---- 巡检 3: 状态-处理人一致性 ----
        handler_str = str(handler).strip().upper()
        if status == "审查中" and not any(k in handler_str for k in ["REVIEWER", "周审查", "审查"]):
            alerts.append({
                "severity": "critical",
                "code": "ASSIGNEE_MISMATCH_REVIEW",
                "task_id": tid,
                "message": f"任务 {tid} 处于【审查中】,处理人应为 REVIEWER,当前为 {handler}",
            })
        elif status == "测试中" and not any(k in handler_str for k in ["QA", "章测试", "测试"]):
            alerts.append({
                "severity": "critical",
                "code": "ASSIGNEE_MISMATCH_TEST",
                "task_id": tid,
                "message": f"任务 {tid} 处于【测试中】,处理人应为 QA,当前为 {handler}",
            })
        elif status in ("已完成", "已验收") and not any(k in handler_str for k in ["PM", "严经理", "经理"]):
            alerts.append({
                "severity": "info",
                "code": "ASSIGNEE_MISMATCH_TERMINAL",
                "task_id": tid,
                "message": f"任务 {tid} 处于【{status}】,处理人建议收敛为 PM(严经理),当前为 {handler}",
            })

        # ---- 巡检 4: 终态结束时间强校验 (E 类用户自执行/审批任务豁免) ----
        t_type = (t.get("type") or "A").upper()
        if status in ("已完成", "已验收") and not end_date and t_type != "E":
            alerts.append({
                "severity": "critical",
                "code": "MISSING_END_DATE",
                "task_id": tid,
                "message": f"任务 {tid} 处于【{status}】但缺少结束时间 (end_date),违反流转不变量",
            })

        # ---- 巡检 5: 交付前置周期 (Lead Time) 真实性与防冲卡 ----
        if status in ("已完成", "已验收") and start_dt and end_dt and t_type != "E":
            lead_time_seconds = (end_dt - start_dt).total_seconds()
            if lead_time_seconds <= 1.0:
                alerts.append({
                    "severity": "warning",
                    "code": "TIME_SKEW_INSTANT",
                    "task_id": tid,
                    "message": f"任务 {tid} 交付前置周期为 0 秒 (start_date == end_date: {start_date})，疑似瞬时冲卡或未记录真实开工时间",
                })

    # 并发上限核验告警
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
    effective_lead_times = [lt for lt in lead_times if lt > (1.0 / 60.0)]
    effective_avg_lead_time = (sum(effective_lead_times) / len(effective_lead_times)) if effective_lead_times else avg_lead_time
    instant_count = sum(1 for lt in lead_times if lt <= (1.0 / 60.0))

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
            "effective_avg_lead_time_hours": round(effective_avg_lead_time, 1),
            "instant_tasks_count": instant_count,
            "role_workload": dict(role_workload),
        },
        "alerts": alerts,
        "summary": summary,
    }


def format_progress_bar(pct: float, width: int = 15) -> str:
    filled = int(round(width * (pct / 100.0)))
    filled = max(0, min(width, filled))
    return f"[{'█' * filled}{'░' * (width - filled)}] {pct:.1f}%"
