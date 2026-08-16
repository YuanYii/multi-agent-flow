#!/usr/bin/env python3
"""
自动任务编排引擎 (Auto Task CLI) — /yy-flow auto 底层实现

能力:
  1. 全类型链定义: A 类六步 / B/C/D/G 特权短链 / F 类 / E 类直验，统一终点【已验收】;
  2. 任意节点续跑: 读取当前状态, 计算剩余链逐节点执行; 任务不存在时先建卡【待开始】;
  3. 挂起态处理: 已退回→处理 DEF 后恢复; 已阻塞→必须先通过阻断解除前置验证
     (备注含【解除】记录且晚于【阻断】) 才能恢复; 已取消→拒绝恢复; 已验收→幂等完成;
  4. 代行注入: 链内各步骤以 --delegated-by USER --delegation-reason auto 代行执行,
     复用现有代行白名单, 不绕过五层门控/并发锁/审计;
  5. --simulate: 复用 dry-run 语义, 不落库仅演示; 链级锁防多链/人工并发; 任一步失败整链停止。

用法:
  # 任务不存在: 建卡待开始后自动跑完整生命周期
  python3 scripts/auto_task.py --task-name "用户登录接口" --role DEV --type A

  # 任务已存在: 从当前状态续跑至已验收
  python3 scripts/auto_task.py --task-id T0007 --type A

  # 演示模式（不落库）
  python3 scripts/auto_task.py --task-name "演示任务" --simulate
"""
import sys
import os
import re
import time
import argparse
from typing import Dict, List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from transition_task import transition_task_pipeline, ROLE_NAME_MAP, check_duplicate_tasks
from board_adapter_factory import get_board_adapter
import paths

CHAIN_A = ["待开始", "进行中", "审查中", "测试中", "已完成", "已验收"]
CHAIN_SHORT = ["待开始", "进行中", "已完成", "已验收"]
CHAIN_E = ["待开始", "已验收"]

# 类型 → 主执行角色（短链/建卡使用；A 类链固定角色见 CHAIN_ROLES_A）
MAIN_ROLE_BY_TYPE = {
    "A": "DEV", "B": "ARCHITECT", "C": "DOCS",
    "D": "DEVOPS", "E": "PM", "F": "PM", "G": "DEVOPS",
}

# A 类链: 每段转换的 (执行角色, 处理人)
CHAIN_ROLES_A = [
    ("待开始", "进行中", "DEV", "李开发"),
    ("进行中", "审查中", "DEV", "李开发"),
    ("审查中", "测试中", "REVIEWER", "周审查"),
    ("测试中", "已完成", "QA", "章测试"),
    ("已完成", "已验收", "PM", "严经理"),
]

# 短链 (B/C/D/G/F): 主执行角色完成到已完成，PM 验收
def short_chain_roles(main_role: str) -> List[tuple]:
    main_assignee = ROLE_NAME_MAP.get(main_role, main_role)
    return [
        ("待开始", "进行中", main_role, main_assignee),
        ("进行中", "已完成", main_role, main_assignee),
        ("已完成", "已验收", "PM", "严经理"),
    ]

# E 类: PM 直验
CHAIN_ROLES_E = [
    ("待开始", "已验收", "PM", "严经理"),
]


def resolve_chain(task_type: str, main_role: str) -> tuple:
    """返回 (状态链, 步骤角色表)。"""
    t = task_type.upper()
    if t == "A":
        return CHAIN_A, CHAIN_ROLES_A
    if t == "E":
        return CHAIN_E, CHAIN_ROLES_E
    return CHAIN_SHORT, short_chain_roles(main_role)


def parse_block_markers(text: str) -> tuple:
    """解析备注中的【阻断】/【解除】标记，返回 (最近阻断位置, 最近解除位置)，无则 -1。"""
    block_pos, clear_pos = -1, -1
    for m in re.finditer(r"【阻断】", text):
        block_pos = m.start()
    for m in re.finditer(r"【解除】", text):
        clear_pos = m.start()
    return block_pos, clear_pos


def check_block_resolved(fields: Dict) -> bool:
    """已阻塞前置验证：存在【解除】记录且晚于【阻断】记录 → 已解除。"""
    remarks = str(fields.get("remarks") or fields.get("process") or "")
    block_pos, clear_pos = parse_block_markers(remarks)
    if block_pos < 0:
        # 无阻断标记但有阻塞状态（历史数据）：保守视为未解除
        return False
    return clear_pos > block_pos


def main():
    parser = argparse.ArgumentParser(description="自动任务编排引擎 (auto_task)")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--task-id", default="", help="任务编号；缺省且提供 --task-name 时自动建卡")
    parser.add_argument("--task-name", default="", help="任务名称（建卡时必填）")
    parser.add_argument("--role", default="", help="主执行角色 (DEV/ARCHITECT/DOCS/DEVOPS/PM；缺省按类型推导)")
    parser.add_argument("--type", default="A", help="任务类型 (A-G)")
    parser.add_argument("--stage", default="", help="建卡时写入阶段")
    parser.add_argument("--wp", default="", help="建卡时写入工作包")
    parser.add_argument("--wbs", default="", help="建卡时写入 WBS")
    parser.add_argument("--delegated-by", default="USER", help="代行来源 (默认 USER)")
    parser.add_argument("--delegation-reason", default="auto", help="代行理由")
    parser.add_argument("--simulate", action="store_true", help="模拟模式：不落库仅演示流转")
    parser.add_argument("--force", action="store_true", help="建卡重复校验命中时强制创建")
    parser.add_argument("--no-dup-check", action="store_true", help="跳过建卡重复校验")
    args = parser.parse_args()

    if not args.task_id and not args.task_name:
        parser.error("必须提供 --task-id 或 --task-name")

    task_type = args.type.upper()
    main_role = (args.role or MAIN_ROLE_BY_TYPE.get(task_type, "DEV")).upper()
    chain, step_roles = resolve_chain(task_type, main_role)
    extra_log = {"task_id": args.task_id or "AUTO"}
    delegated_by = args.delegated_by or ""
    delegation_reason = args.delegation_reason or "auto"

    # 链级互斥锁（防多链/人工并发改同一任务）；锁落 data_root/user_data/locks/
    chain_lock = None
    try:
        import fcntl
        locks_dir = paths.locks_dir()
        os.makedirs(locks_dir, exist_ok=True)
        lock_path = os.path.join(locks_dir, ".lock_auto_chain.lock")
        chain_lock = open(lock_path, "a+b")
        fcntl.flock(chain_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        print("[FAILED]  另一条自动链正在执行或锁不可用，物理阻断！")
        sys.exit(1)

    try:
        adapter = get_board_adapter(args.config)
        import yaml
        with open(args.config, "r", encoding="utf-8") as cf:
            cfg_data = yaml.safe_load(cf)
        dup_cfg = (cfg_data or {}).get("duplicate_check", {}) or {}

        task_id = args.task_id
        current_status = ""
        board_name = args.task_name

        # 1. 任务解析：不存在 → 建卡【待开始】（simulate 模式不建卡，仅演示）
        if task_id:
            rec = adapter.get_record(task_id)
            if rec:
                fields = rec.get("fields", {})
                current_status = str(fields.get("status") or "")
                board_name = board_name or str(fields.get("name") or fields.get("task_name") or "")
        if not task_id or current_status == "":
            if not args.task_name:
                print("[FAILED]  任务不存在且未提供 --task-name，无法建卡！")
                sys.exit(1)
            if args.simulate:
                print(f"[AUTO][SIMULATE] 将建卡【待开始】: {args.task_name} (角色 {main_role})")
                task_id = "SIM"
                current_status = "待开始"
                board_name = args.task_name
            else:
                # 建卡：走 transition_task --create（含重复校验/权限/审计）
                ok = transition_task_pipeline(
                    config_path=args.config,
                    current_role=main_role,
                    assignee=ROLE_NAME_MAP.get(main_role, main_role),
                    task_name=args.task_name,
                    task_type=task_type,
                    stage=args.stage or None,
                    wp=args.wp or None,
                    wbs=args.wbs or None,
                    create_only=True,
                    force=args.force,
                    no_dup_check=args.no_dup_check,
                )
                if not ok:
                    sys.exit(1)
                rec = adapter.get_record(task_id) if task_id else None
                if rec is None:
                    # 自动编号建卡后回查最新卡片（追加在列表末尾）
                    recs = adapter.list_records(limit=5)
                    if not recs:
                        print("[FAILED]  建卡后未找到任务！")
                        sys.exit(1)
                    rec = recs[-1]
                task_id = str(rec.get("record_id") or rec.get("fields", {}).get("id"))
                current_status = str(rec.get("fields", {}).get("status") or "待开始")
                board_name = str(rec.get("fields", {}).get("name") or args.task_name)
                print(f"[AUTO]  已建卡 {task_id}【{current_status}】")

        print(f"[AUTO]  任务 {task_id} 当前状态【{current_status}】(类型 {task_type}, 主角色 {main_role})")

        # 2. 幂等：已验收
        if current_status == "已验收":
            print(f"[AUTO]  任务 {task_id} 生命周期已结束（已验收），幂等返回")
            sys.exit(0)

        # 3. 终态拒绝：已取消
        if current_status == "已取消":
            print(f"[FAILED]  任务 {task_id} 处于终态【已取消】，自动恢复被拒绝！")
            sys.exit(1)

        # 4. 挂起态恢复
        resume_from = current_status
        if current_status == "已阻塞":
            fields = adapter.get_record(task_id).get("fields", {})
            if not check_block_resolved(fields):
                remarks = str(fields.get("remarks") or fields.get("process") or "")
                print(f"[FAILED]  [阻断未解除] 任务 {task_id} 仍处于【已阻塞】且无有效【解除】记录，自动恢复被拒绝！")
                if remarks:
                    print(f"  [阻断内容] {remarks}")
                print("  请确认阻断内容已解除后，在看板备注追加【解除】<说明>，再重新执行 auto")
                sys.exit(1)
            print(f"[AUTO]  阻断已解除，从【已阻塞】恢复续跑")
            resume_from = "进行中"
        elif current_status == "已退回":
            print(f"[AUTO]  任务处于【已退回】，先恢复至【进行中】处理 DEF 缺陷后续跑")
            resume_from = "进行中"

        # 5. 计算剩余链
        if resume_from not in chain:
            print(f"[FAILED]  状态【{resume_from}】不在类型 {task_type} 的链定义中，无法续跑！")
            sys.exit(1)
        start_idx = chain.index(resume_from)
        remaining = chain[start_idx + 1:]

        # 挂起态恢复步骤：先推进到进行中
        if current_status in ("已阻塞", "已退回") and resume_from == "进行中":
            remaining = ["进行中"] + remaining

        print(f"[AUTO]  剩余链: {' -> '.join([current_status] + remaining)}")

        # 6. 逐节点执行
        prev = current_status
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        for target in remaining:
            # 查找该段转换的执行角色/处理人
            step_role, step_assignee = main_role, ROLE_NAME_MAP.get(main_role, main_role)
            for (f, t, r, a) in step_roles:
                if f == prev and t == target:
                    step_role, step_assignee = r, a
                    break
            need_end_time = target in ("已完成", "已验收") and task_type != "E"
            print(f"[AUTO]  执行: {prev} -> {target} (角色 {step_role}, 处理人 {step_assignee})")
            ok = transition_task_pipeline(
                config_path=args.config,
                task_id=task_id,
                current_role=step_role,
                from_status=prev,
                to_status=target,
                assignee=step_assignee,
                task_type=task_type,
                end_time=(now_str if need_end_time else None),
                dry_run=args.simulate,
                delegated_by=delegated_by,
                delegation_reason=delegation_reason,
            )
            if not ok:
                print(f"[FAILED]  自动链在第 {prev} -> {target} 步失败，整链停止！")
                sys.exit(1)
            prev = target

        print(f"[AUTO]  ✅ 任务 {task_id} 自动链完成，终态【{prev}】" if prev == "已验收" else f"[AUTO]  任务 {task_id} 到达【{prev}】")
        sys.exit(0)
    finally:
        if chain_lock:
            try:
                import fcntl
                fcntl.flock(chain_lock, fcntl.LOCK_UN)
            except Exception:
                pass
            chain_lock.close()


if __name__ == "__main__":
    main()
