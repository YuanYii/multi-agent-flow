#!/usr/bin/env python3
"""
结构化审计日志落盘记录器 (Audit Logger)
将所有状态变更的"时间戳、触发角色、任务ID、原状态、目标状态、处理人、成功状态"结构化落盘至 logs/audit_trail.log。

提供:
- record_audit_event: 追加一条结构化事件 (NDJSON, 物理 flock 守护并发安全)
- query_events: 按 task_id / role / success / time 范围查询
- rotate_if_needed: 按日切分 + 单文件超 50MB 二次切 + 旧文件 gzip 归档
"""
import os
import sys
import json
import gzip
import shutil
import time
import re
import glob
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
AUDIT_LOG_FILE = os.path.join(LOGS_DIR, "audit_trail.log")
ARCHIVE_DIR = os.path.join(LOGS_DIR, "archive")


def record_audit_event(
    task_id: str,
    role: str,
    from_status: str,
    to_status: str,
    assignee: str,
    success: bool,
    details: str = "",
    delegated_by: str = "",
    delegation_reason: str = ""
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
        "details": details,
        "delegated_by": delegated_by or "",
        "delegation_reason": delegation_reason or "",
    }
    
    import time
    for attempt in range(1, 4):
        try:
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f, fcntl.LOCK_EX)

                f.write(json.dumps(event, ensure_ascii=False) + "\n")

                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f, fcntl.LOCK_UN)
                break
        except Exception as e:
            if attempt == 3:
                sys.stderr.write(f"[AuditLogger Error] 审计日志落盘失败 (已重试 {attempt} 次): {e}\n")
            time.sleep(0.05 * attempt)


if __name__ == "__main__":
    record_audit_event("T0000", "TEST", "待开始", "进行中", "TESTER", True, "审计日志测试事件")
    print(f"✅ [AuditLogger] 测试审计日志已写入: {AUDIT_LOG_FILE}")


# =============================================================================
# 查询与轮转工具函数 (供 audit_query.py / audit_rotate.py 复用)
# =============================================================================

def _read_ndjson(path: str) -> List[Dict[str, Any]]:
    """读取 NDJSON 文件为 list[dict],逐行解析,坏行跳过。"""
    out: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return out
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        sys.stderr.write(f"[AuditLogger] 读取 {path} 失败: {e}\n")
    return out


def _read_archive_ndjson(archive_glob_pattern: str) -> List[Dict[str, Any]]:
    """读取归档目录下所有 .gz NDJSON,合并返回。"""
    out: List[Dict[str, Any]] = []
    for gz in sorted(glob.glob(archive_glob_pattern)):
        try:
            with gzip.open(gz, "rt", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            sys.stderr.write(f"[AuditLogger] 读取归档 {gz} 失败: {e}\n")
    return out


def query_events(
    task_id: Optional[str] = None,
    role: Optional[str] = None,
    success: Optional[bool] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    include_archive: bool = True,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    按条件过滤审计事件。

    参数:
      task_id / role: 精确匹配 (忽略大小写)
      success: True / False / None (None = 不过滤)
      since / until: ISO 格式时间字符串,闭区间 ["since", "until"]
      include_archive: 是否合并 logs/archive/*.log.gz 历史归档
      limit: 限制返回条数 (按时间倒序截断)

    返回: 匹配的事件列表 (按 timestamp 升序)
    """
    def _match(ev: Dict[str, Any]) -> bool:
        if task_id and str(ev.get("task_id", "")).upper() != str(task_id).upper():
            return False
        if role and str(ev.get("role", "")).upper() != str(role).upper():
            return False
        if success is not None and bool(ev.get("success")) != bool(success):
            return False
        ts = str(ev.get("timestamp", ""))
        if since and ts < str(since):
            return False
        if until and ts > str(until):
            return False
        return True

    events = _read_ndjson(AUDIT_LOG_FILE)
    if include_archive:
        events.extend(_read_archive_ndjson(os.path.join(ARCHIVE_DIR, "audit_trail-*.log.gz")))

    matched = [e for e in events if _match(e)]
    matched.sort(key=lambda e: e.get("timestamp", ""))
    if limit is not None and limit > 0:
        matched = matched[-limit:]
    return matched


def _today_str() -> str:
    return date.today().strftime("%Y%m%d")


def _current_log_date() -> Optional[str]:
    """从文件名后缀解析当前 audit_trail.log 所属日期 (YYYYMMDD);若文件未带日期后缀,返回 None。"""
    name = os.path.basename(AUDIT_LOG_FILE)
    m = re.search(r"-(\d{8})(?:\.log)?$", name)
    return m.group(1) if m else None


def rotate_if_needed(max_size_mb: int = 50) -> Dict[str, Any]:
    """
    按日切分 + 单文件超 max_size_mb 二次切。
    1) 若当前 audit_trail.log 文件名不带日期后缀 且 不属于今天 → 归档并新建 audit_trail-YYYYMMDD.log
    2) 若当前 audit_trail.log 大小 >= max_size_mb → 归档为 audit_trail-YYYYMMDD-HHMMSS.log.gz + 新建空文件
    3) 归档文件移至 logs/archive/

    返回 {"rotated": bool, "reason": str, "archived_to": str|None}
    """
    if not os.path.exists(AUDIT_LOG_FILE):
        return {"rotated": False, "reason": "no_log_file", "archived_to": None}

    size_mb = os.path.getsize(AUDIT_LOG_FILE) / (1024 * 1024)
    today = _today_str()
    log_date = _current_log_date()

    should_rotate_daily = (log_date is None)
    should_rotate_size = (size_mb >= max_size_mb)

    if not should_rotate_daily and not should_rotate_size:
        return {"rotated": False, "reason": "no_rotation_needed", "archived_to": None}

    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    try:
        lock_f = open(AUDIT_LOG_FILE, "a+", encoding="utf-8")
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock_f.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_f, fcntl.LOCK_EX)

            if should_rotate_daily:
                archive_name = f"audit_trail-{today}.log.gz"
                reason = "daily_rotation"
            else:
                ts = datetime.now().strftime("%H%M%S")
                archive_name = f"audit_trail-{log_date}-{ts}.log.gz"
                reason = f"size_limit_{size_mb:.1f}MB>={max_size_mb}MB"

            archive_path = os.path.join(ARCHIVE_DIR, archive_name)
            with open(AUDIT_LOG_FILE, "rb") as src, gzip.open(archive_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
        finally:
            if sys.platform == "win32":
                import msvcrt
                try:
                    msvcrt.locking(lock_f.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
            else:
                import fcntl
                try:
                    fcntl.flock(lock_f, fcntl.LOCK_UN)
                except Exception:
                    pass
            lock_f.close()

        if os.path.exists(AUDIT_LOG_FILE):
            os.remove(AUDIT_LOG_FILE)

        return {
            "rotated": True,
            "reason": reason,
            "archived_to": archive_path,
        }
    except Exception as e:
        return {"rotated": False, "reason": f"rotation_failed: {e}", "archived_to": None}
