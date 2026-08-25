"""
看板效能指标计算与渲染引擎核心模块
"""
import os
import sys
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List, Optional

import paths
from enums import normalize_role


def parse_datetime(val: Any) -> Optional[datetime]:
    if not val:
        return None
    s = str(val).strip()
    try:
        iso_str = s.replace("Z", "+00:00")
        return datetime.fromisoformat(iso_str)
    except Exception:
        pass
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


class MetricsCalculator:
    """看板效能指标计算引擎 (DEV 核心产出)"""

    def __init__(self, records: List[Dict[str, Any]], now: Optional[datetime] = None):
        self.raw_records = records
        self.now = now or datetime.now()
        self.tasks = [self._normalize(r) for r in records]

    def _normalize(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        if "fields" in rec and isinstance(rec["fields"], dict):
            out = dict(rec["fields"])
            if "record_id" not in out and "record_id" in rec:
                out["record_id"] = rec["record_id"]
            return out
        return rec

    @staticmethod
    def _get_status_entry_time(task: Dict[str, Any], status: str) -> Optional[datetime]:
        """从任务 process 节点中倒序解析进入当前 status 的时间戳；无节点时回退至 start_date / start_time"""
        import re as _re
        process = task.get("process")
        if process and isinstance(process, str):
            lines = [line.strip() for line in process.split("\n") if line.strip()]
            for line in reversed(lines):
                if f"更新至【{status}】" in line:
                    m = _re.search(r"\[(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}(?::\d{2})?)", line)
                    if m:
                        dt = parse_datetime(m.group(1))
                        if dt:
                            return dt
        # 兜底：新任务卡或无节点历史时，回退至 start_date / start_time
        start_date = task.get("start_date") or task.get("start_time")
        return parse_datetime(start_date)

    def compute_summary(self) -> Dict[str, Any]:
        total = len(self.tasks)
        status_counts = defaultdict(int)
        completed_count = 0
        lead_times_hours: List[float] = []

        for t in self.tasks:
            status = str(t.get("status", "待开始"))
            status_counts[status] += 1

            if status in ("已完成", "已验收"):
                completed_count += 1
                s_dt = parse_datetime(t.get("start_date") or t.get("start_time"))
                e_dt = parse_datetime(t.get("end_date") or t.get("end_time"))
                if s_dt and e_dt and e_dt >= s_dt:
                    lead_times_hours.append((e_dt - s_dt).total_seconds() / 3600)

        avg_lead_time = (sum(lead_times_hours) / len(lead_times_hours)) if lead_times_hours else 0.0
        effective_lead_times = [lt for lt in lead_times_hours if lt > (1.0 / 60.0)]
        effective_avg_lead_time = (sum(effective_lead_times) / len(effective_lead_times)) if effective_lead_times else avg_lead_time
        instant_count = sum(1 for lt in lead_times_hours if lt <= (1.0 / 60.0))
        instant_ratio = (instant_count / completed_count * 100) if completed_count > 0 else 0.0
        completion_rate = (completed_count / total * 100) if total > 0 else 0.0

        return {
            "total_tasks": total,
            "completed_tasks": completed_count,
            "in_progress_tasks": status_counts["进行中"],
            "reviewing_tasks": status_counts["审查中"],
            "testing_tasks": status_counts["测试中"],
            "blocked_tasks": status_counts["已阻塞"],
            "rejected_tasks": status_counts["已退回"],
            "completion_rate_percent": round(completion_rate, 1),
            "avg_lead_time_hours": round(avg_lead_time, 2),
            "effective_avg_lead_time_hours": round(effective_avg_lead_time, 2),
            "instant_tasks_count": instant_count,
            "instant_ratio_percent": round(instant_ratio, 1),
            "status_distribution": dict(status_counts),
        }

    def compute_role_workload(self) -> Dict[str, Dict[str, int]]:
        """统计各处理人/角色的负荷情况（自动通过 normalize_role 归一化聚合别名）"""
        workload = defaultdict(lambda: {"in_progress": 0, "completed": 0, "total": 0})
        for t in self.tasks:
            raw_assignee = t.get("assignee") or t.get("owner")
            norm = normalize_role(raw_assignee)
            assignee = raw_assignee if norm == "未分配" and raw_assignee else norm
            status = str(t.get("status", ""))
            workload[assignee]["total"] += 1
            if status == "进行中":
                workload[assignee]["in_progress"] += 1
            elif status in ("已完成", "已验收"):
                workload[assignee]["completed"] += 1
        return dict(workload)

    def detect_bottlenecks(self, stale_in_progress_hours: int = 24, stale_review_test_hours: int = 12) -> List[Dict[str, Any]]:
        """检测并定位流转卡点（基于节点入态时间精确计算）"""
        bottlenecks = []
        for t in self.tasks:
            tid = t.get("task_id") or t.get("record_id") or t.get("id") or "?"
            tname = t.get("task_name") or t.get("name") or "未命名任务"
            status = str(t.get("status", ""))
            assignee = str(t.get("assignee") or "未分配")
            status_entry_dt = self._get_status_entry_time(t, status)

            if not status_entry_dt:
                continue

            elapsed_hours = (self.now - status_entry_dt).total_seconds() / 3600
            if status == "进行中" and elapsed_hours > stale_in_progress_hours:
                bottlenecks.append({
                    "task_id": tid,
                    "task_name": tname,
                    "status": status,
                    "assignee": assignee,
                    "elapsed_hours": round(elapsed_hours, 1),
                    "threshold_hours": stale_in_progress_hours,
                    "type": "STALE_IN_PROGRESS",
                })
            elif status in ("审查中", "测试中") and elapsed_hours > stale_review_test_hours:
                bottlenecks.append({
                    "task_id": tid,
                    "task_name": tname,
                    "status": status,
                    "assignee": assignee,
                    "elapsed_hours": round(elapsed_hours, 1),
                    "threshold_hours": stale_review_test_hours,
                    "type": "STALE_REVIEW_TEST",
                })
        return bottlenecks


class TerminalRenderer:
    """终端与 Markdown 可视化渲染引擎 (FRONTEND 核心产出)"""

    @staticmethod
    def render_ascii_bar(percent: float, length: int = 20) -> str:
        filled = int(round(length * percent / 100))
        bar = "█" * filled + "░" * (length - filled)
        return f"[{bar}] {percent:.1f}%"

    @classmethod
    def render_terminal_dashboard(cls, summary: Dict[str, Any], workload: Dict[str, Dict[str, int]], bottlenecks: List[Dict[str, Any]]) -> str:
        lines = []
        lines.append("=" * 72)
        lines.append("  【看板效能度量与流转诊断仪表盘】")
        lines.append("=" * 72)
        lines.append(f"• 任务总数: {summary['total_tasks']:<6} • 完成任务: {summary['completed_tasks']:<6} • 进行中: {summary['in_progress_tasks']:<6}")
        lines.append(f"• 总体完成率: {cls.render_ascii_bar(summary['completion_rate_percent'])}")
        lines.append(f"• 平均交付周期: {summary['avg_lead_time_hours']} 小时")
        lines.append("-" * 72)
        lines.append(" 角色工作负荷分布:")
        for role, stats in sorted(workload.items()):
            lines.append(f"  - {role:<12}: 进行中={stats['in_progress']:<2} 已完成={stats['completed']:<2} (总计: {stats['total']})")
        lines.append("-" * 72)
        if bottlenecks:
            lines.append(f"[WARN]   检测到 {len(bottlenecks)} 个潜在流转卡点:")
            for b in bottlenecks:
                lines.append(f"  [CRITICAL]  [{b['task_id']}] {b['task_name']} ({b['status']}) - 滞留 {b['elapsed_hours']}h / 阈值 {b['threshold_hours']}h (处理人: {b['assignee']})")
        else:
            lines.append("[SUCCESS]  状态流转健康，未检测到超时滞留卡点。")
        lines.append("=" * 72)
        return "\n".join(lines)

    @classmethod
    def render_markdown_report(cls, summary: Dict[str, Any], workload: Dict[str, Dict[str, int]], bottlenecks: List[Dict[str, Any]]) -> str:
        md = []
        md.append("#  看板效能度量与诊断报告\n")
        md.append("## 1. 核心效能概览\n")
        md.append(f"| 指标项 | 统计值 |")
        md.append(f"| :--- | :--- |")
        md.append(f"| 任务总数 | {summary['total_tasks']} |")
        md.append(f"| 已完成/已验收 | {summary['completed_tasks']} |")
        md.append(f"| 完成率 | {summary['completion_rate_percent']}% |")
        md.append(f"| 平均交付前置周期 | {summary['avg_lead_time_hours']} 小时 |\n")
        md.append("## 2. 角色工作负荷矩阵\n")
        md.append("| 处理人/角色 | 进行中 | 已完成 | 任务总量 |")
        md.append("| :--- | :--- | :--- | :--- |")
        for role, stats in sorted(workload.items()):
            md.append(f"| {role} | {stats['in_progress']} | {stats['completed']} | {stats['total']} |")
        md.append("\n## 3. 卡点诊断清单\n")
        if bottlenecks:
            md.append("| 任务ID | 任务名称 | 当前状态 | 处理人 | 滞留时长 | 预警阈值 |")
            md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for b in bottlenecks:
                md.append(f"| {b['task_id']} | {b['task_name']} | {b['status']} | {b['assignee']} | {b['elapsed_hours']}h | {b['threshold_hours']}h |")
        else:
            md.append("> [SUCCESS]  当前所有任务流转顺畅，无滞留卡点。")
        return "\n".join(md)
