"""
Git 提交与阶段结项强校验门禁实现模块
"""
import os
import sys
from typing import List, Dict, Optional

import paths
from _lib.boards.board_adapter_factory import get_board_adapter


def verify_git_gate(config_path: Optional[str] = None, stage: Optional[str] = None) -> bool:
    """核验当前阶段或活动任务是否已全部获得人类最终验收"""
    try:
        adapter = get_board_adapter(config_path)
        records = adapter.list_records(limit=1000)
    except Exception as e:
        print(f"[FAIL-CLOSED 拦截] 无法读取看板数据，门禁拒绝放行: {e}")
        return False

    unaccepted_completed = []
    in_progress_tasks = []

    for r in records:
        f = r.get("fields", {})
        tid = str(f.get("id") or r.get("record_id") or "未知ID")
        name = str(f.get("name") or f.get("task_name") or "未命名任务")
        status = str(f.get("status") or "").strip()
        stg = str(f.get("stage") or "").strip()
        handler = str(f.get("handler") or f.get("assignee") or "未分配").strip()

        # 若指定了阶段，过滤非目标阶段任务
        if stage and stage.lower() not in stg.lower():
            continue

        if status == "已完成":
            unaccepted_completed.append({"id": tid, "name": name, "handler": handler, "stage": stg})
        elif stage and status not in ("已验收", "已取消"):
            in_progress_tasks.append({"id": tid, "name": name, "status": status, "handler": handler, "stage": stg})

    if unaccepted_completed:
        print("=" * 75)
        print("[FAIL-CLOSED 拦截] 🛑 Git 提交与结项门禁未通过：存在待人类用户验收的任务！")
        print(f"共有 {len(unaccepted_completed)} 个任务已由 Agent 研发测试完毕（处于【已完成】），尚未获得人类用户最终验收：")
        for u in unaccepted_completed[:10]:
            print(f"  - [{u['id']}] {u['name']} (处理人: {u['handler']})")
        if len(unaccepted_completed) > 10:
            print(f"  ... 等共 {len(unaccepted_completed)} 条任务")
        print("-" * 75)
        print("💡 解决指引：请人类用户审阅代码后执行验收操作：")
        print("  1. 单任务验收: python3 scripts/quick_task.py accept --task-id <TASK_ID>")
        if stage:
            print(f"  2. 阶段批量验收: python3 scripts/quick_task.py accept-all --stage \"{stage}\"")
        else:
            print("  2. 全局批量验收: python3 scripts/quick_task.py accept-all")
        print("=" * 75)
        return False

    if in_progress_tasks:
        print("=" * 75)
        print("[FAIL-CLOSED 拦截] 🛑 Git 提交与结项门禁未通过：存在未完工的在手任务！")
        for p in in_progress_tasks[:5]:
            print(f"  - [{p['id']}] {p['name']} (当前状态: 【{p['status']}】 - 经办人: {p['handler']})")
        print("=" * 75)
        return False

    print("[PASS 门禁通过] ✅ 所有关联任务均已处于终态【已验收】或【已取消】，准予 Git 提交与阶段结项！")
    return True
