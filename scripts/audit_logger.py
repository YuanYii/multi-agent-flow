#!/usr/bin/env python3
"""
结构化审计日志落盘记录器 (Audit Logger)
将所有状态变更的“时间戳、触发角色、任务ID、原状态、目标状态、处理人、成功状态”结构化落盘至 logs/audit_trail.log。
"""
import os
import sys
import json
import logging
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
AUDIT_LOG_FILE = os.path.join(LOGS_DIR, "audit_trail.log")


def record_audit_event(
    task_id: str,
    role: str,
    from_status: str,
    to_status: str,
    assignee: str,
    success: bool,
    details: str = ""
):
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    event = {
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id,
        "role": role,
        "from_status": from_status,
        "to_status": to_status,
        "assignee": assignee,
        "success": success,
        "details": details
    }
    
    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        sys.stderr.write(f"[AuditLogger Error] 审计日志落盘失败: {e}\n")


if __name__ == "__main__":
    record_audit_event("T0000", "TEST", "待开始", "进行中", "TESTER", True, "审计日志测试事件")
    print(f"✅ [AuditLogger] 测试审计日志已写入: {AUDIT_LOG_FILE}")
