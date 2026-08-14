#!/usr/bin/env python3
"""
一键门控流转管道命令 (Transition Task Pipeline)
物理级硬防错：Fail-Closed 并发排他文件锁 + 门控断言 + 完整 Adapter/Schema 检验 + 物理原子补偿回滚 + 结构化审计日志 + 真实的 --dry-run 预检。
"""

import sys
import os
import argparse
import logging
from typing import Dict, Any, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from validate_transition import validate, validate_delegation_authority
from board_adapter_factory import get_board_adapter
from audit_logger import record_audit_event

# 容错型日志格式化类，防 traceback 泄漏
class SafeTaskFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, "task_id"):
            record.task_id = "SYSTEM"
        return super().format(record)

handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(SafeTaskFormatter("%(asctime)s [%(levelname)s] [Task: %(task_id)s] %(message)s"))

logger = logging.getLogger("transition_pipeline")
logger.setLevel(logging.INFO)
logger.addHandler(handler)


import time

def cleanup_stale_locks(ttl_seconds: int = 300):
    """自动清理超过 ttl_seconds (默认5分钟) 的旧垃圾锁文件"""
    now = time.time()
    for entry in os.listdir(SCRIPT_DIR):
        if entry.startswith(".lock_") and entry.endswith(".lock"):
            full_p = os.path.join(SCRIPT_DIR, entry)
            try:
                if os.path.isfile(full_p) and (now - os.path.getmtime(full_p)) > ttl_seconds:
                    os.remove(full_p)
            except Exception:
                pass


def acquire_concurrency_lock(task_id: str):
    """获取物理排他并发锁 (Fail-Closed：冲突则直接返回 None, None 阻断)"""
    cleanup_stale_locks(300)
    lock_file = os.path.join(SCRIPT_DIR, f".lock_{task_id}.lock")
    try:
        f = open(lock_file, "w")
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f, lock_file
    except Exception:
        # Fail-Closed: 锁竞争失败或不支持，绝对返回 None！
        return None, None


def release_concurrency_lock(lock_tuple):
    if not lock_tuple or not lock_tuple[0]:
        return
    f, lock_file = lock_tuple
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        f.close()
        if os.path.exists(lock_file):
            os.remove(lock_file)
    except Exception:
        pass


def transition_task_pipeline(
    config_path: str,
    task_id: str = "",
    record_id: str = None,
    current_role: str = "",
    from_status: str = "",
    to_status: str = "",
    assignee: str = "",
    task_type: str = "A",
    end_time: str = None,
    remarks: str = None,
    dry_run: bool = False,
    active_dev_count: int = 1,
    task_name: str = None,
    stage: str = None,
    wp: str = None,
    wbs: str = None,
    owner: str = None,
    delegated_by: str = "",
    delegation_reason: str = "",
) -> bool:
    resolved_task_id = task_id or "AUTO"
    extra_log = {"task_id": resolved_task_id}
    logger.info(f"[SECURITY]  触发防错门控校验 ({from_status} -> {to_status}, 模式: {'DRY-RUN' if dry_run else 'REAL'})...", extra=extra_log)

    # 0. 提权代行白名单预检(Fail-Closed):在 validate 前阻断非法代行
    #    无代行声明(delegated_by 为空)时直接跳过,交由原 validate 权限矩阵处理
    if not validate_delegation_authority(current_role, delegated_by):
        logger.error(f"[FAILED]  [代行未授权] 角色 {current_role} 不接受来自 {delegated_by} 的代行授权,硬阻断！", extra=extra_log)
        record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, False, f"代行未授权阻断: {delegated_by} 代行 {current_role}", delegated_by=delegated_by, delegation_reason=delegation_reason)
        return False

    # 1. 尝试获取并发独占锁 (Fail-Closed 硬拦截)
    #    AUTO 场景使用全局建单锁，特定 task_id 使用 per-task 锁
    lock_key = resolved_task_id if resolved_task_id != "AUTO" else "auto_create_global"
    lock_tuple = acquire_concurrency_lock(lock_key)
    if not lock_tuple or not lock_tuple[0]:
        logger.error(f"[FAILED]  [并发锁排他硬拦截] 任务 {resolved_task_id} (锁标识: {lock_key}) 当前正被另一个进程独占写卡中，物理阻断！", extra=extra_log)
        record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, False, "物理并发排他锁硬拦截", delegated_by=delegated_by, delegation_reason=delegation_reason)
        return False

    try:
        # 2. 完整加载看板 Adapter 与配置文件格式断言 (dry-run 模式下也不跳过校验)
        import yaml
        try:
            adapter = get_board_adapter(config_path)
            with open(config_path, "r", encoding="utf-8") as cfg_f:
                cfg_data = yaml.safe_load(cfg_f)
                field_mapping = cfg_data.get("board", {}).get("fields", {})
        except Exception as e:
            logger.error(f"[FAILED]  看板配置文件/Schema 校验断言失败: {e}，硬阻断！", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, f"配置文件校验失败: {e}", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return False

        if not adapter:
            logger.error("[FAILED]  适配器未正确初始化，拦截落库", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "适配器缺失", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return False

        # 从配置与现有工单解析 task_name 与 max_parallel_tasks
        role_cfg = cfg_data.get("roles", {}).get(current_role.upper(), {})
        max_parallel = role_cfg.get("max_parallel_tasks", 3)

        effective_task_name = task_name or ""
        if resolved_task_id != "AUTO":
            existing_rec = adapter.get_record(resolved_task_id)
            if existing_rec:
                f_data = existing_rec.get("fields", {})
                board_task_name = f_data.get("task_name") or f_data.get("name") or ""
                # 针对已存在看板卡片，防 CLI 伪造 [HOTFIX]，校验强制以看板记录的真实名称为准
                if board_task_name:
                    effective_task_name = board_task_name

        # 动态解析活跃进行中任务数，防隐式逃逸并发限制
        effective_active_dev_count = active_dev_count
        if to_status == "进行中" and current_role.upper() in ["DEV", "FRONTEND"]:
            try:
                status_k = field_mapping.get("status", "status")
                assignee_k = field_mapping.get("assignee", "assignee")
                recs = adapter.list_records(limit=1000)
                board_active_count = 0
                for r in recs:
                    f = r.get("fields", {})
                    st_val = str(f.get(status_k) or f.get("status") or "")
                    as_val = str(f.get(assignee_k) or f.get("assignee") or "")
                    if st_val == "进行中" and (as_val == assignee or as_val == current_role):
                        board_active_count += 1
                effective_active_dev_count = max(active_dev_count, board_active_count)
            except Exception:
                pass

        # 3. 强制运行防护门控 (并发上限与 HOTFIX 特权透传，未通过则直接抛错中断！)
        is_valid = validate(
            role=current_role,
            from_status=from_status,
            to_status=to_status,
            assignee=assignee,
            end_time=end_time or "",
            active_dev_count=effective_active_dev_count,
            task_type=task_type,
            task_name=effective_task_name,
            max_parallel=max_parallel,
            remarks=remarks or "",
            delegated_by=delegated_by or "",
            delegation_reason=delegation_reason or "",
        )

        if not is_valid:
            logger.error("[FAILED]  门控物理拦截失败！阻止落库更新", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "门控规则校验未通过", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return False

        logger.info("[SUCCESS]  防错规则核验成功", extra=extra_log)

        # 物理硬阻断: 若执行状态流转（from_status 不是待开始/新建），强制要求必须提供 --task-id
        if not task_id and from_status not in ["待开始", "新建"]:
            logger.error(f"[FAILED]  [Fail-Closed 物理硬拦截] 执行状态流转 ({from_status} -> {to_status}) 时必须通过 --task-id 提供原任务编号，严禁无任务 ID 隐式创建新卡片！", extra=extra_log)
            record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, False, "流转缺失task_id", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return False

        # 4. 动态读取 Key 映射
        status_key = field_mapping.get("status", "status")
        assignee_key = field_mapping.get("assignee", "assignee")
        end_time_key = field_mapping.get("end_time", "end_time")

        # 5. 任务存在性检查：不存在则自动创建（所有专家角色均可操作）
        #    dry-run 模式不落库，仅提示正式执行时的行为
        if dry_run:
            if task_id:
                existing = adapter.get_record(task_id)
                if existing is None:
                    logger.info(f"ℹ [DRY-RUN] 任务 {task_id} 在看板中不存在，正式执行时将自动创建后再流转", extra=extra_log)
            logger.info(" [DRY-RUN] 配置文件与 Schema 检验完全通过！模拟预检不触发物理网络写卡", extra=extra_log)
            record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, True, "DRY-RUN 完整校验测试通过", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return True

        ROLE_NAME_MAP = {
            "PM": "严经理", "ARCHITECT": "钱架构", "DEV": "李开发",
            "FRONTEND": "马前端", "REVIEWER": "周审查", "QA": "章测试",
            "DOCS": "李文通", "DEVOPS": "吕改特"
        }
        assignee = ROLE_NAME_MAP.get(assignee, assignee)

        resolved_record_id = record_id or task_id
        existing = adapter.get_record(resolved_record_id) if resolved_record_id else None
        
        # 物理硬阻断：对于 A 类常规开发任务，若看板中尚无此任务，绝对禁止直接新建为【已完成/审查中】！
        # 强迫 A 类开发任务必须分两步执行：任务开始时先调 CLI 初始化建单为【进行中】，完成后再提交！
        if existing is None:
            is_valid_creation = (from_status in ["待开始", "新建"]) or (to_status == "进行中") or (task_type in ["B", "C", "D", "E", "F", "G"])
            if not is_valid_creation:
                logger.error(f"[FAILED]  [物理硬阻断] 看板中尚无此任务，绝对禁止直接新建为【{to_status}】！你必须首先在任务开始时调用 CLI 初始化建单为【进行中】！", extra=extra_log)
                record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, False, f"拒绝直接新建为{to_status}", delegated_by=delegated_by, delegation_reason=delegation_reason)
                return False

            import datetime
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            initial_status = "已验收" if (task_type == "E" and to_status == "已验收") else "进行中"
            create_fields = {
                "task_id": task_id,
                "task_name": task_name or "工作包任务",
                "status": initial_status,
                "assignee": assignee,
                "owner": owner or current_role,
                "stage": stage or "-",
                "workpackage": wp or "-",
                "wbs_id": wbs or "-",
                "start_date": now_str,
                "process": remarks or None,
                "remarks": remarks or None,
            }
            created_id = adapter.create_record(create_fields)
            if not created_id:
                logger.error(f"[FAILED]  任务自动创建失败（编号冲突或写入失败），硬阻断流转！", extra=extra_log)
                record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, False, "任务自动创建失败", delegated_by=delegated_by, delegation_reason=delegation_reason)
                return False
            if not task_id:
                task_id = created_id
            resolved_record_id = task_id
            extra_log = {"task_id": task_id}
            logger.info(f" 任务 {task_id} 在看板中不存在，已成功初始化建单为【{initial_status}】(负责人: {assignee})", extra=extra_log)
            record_audit_event(task_id, current_role, "新建", initial_status, assignee, True, "任务自动初始化建单", delegated_by=delegated_by, delegation_reason=delegation_reason)
        else:
            resolved_record_id = existing.get("record_id") or resolved_record_id

        # 6. 执行物理原子写入
        update_fields = {status_key: to_status, assignee_key: assignee}
        if end_time: update_fields[end_time_key] = end_time
        if stage: update_fields[field_mapping.get("stage", "stage")] = stage
        if wp: update_fields[field_mapping.get("workpackage", "workpackage")] = wp
        if wbs: update_fields[field_mapping.get("wbs_id", "wbs_id")] = wbs
        if task_name: update_fields[field_mapping.get("task_name", "task_name")] = task_name

        orig_assignee = (existing.get("fields", {}).get(assignee_key) if existing else None) or current_role

        try:
            success = adapter.update_record(resolved_record_id, update_fields)
            if not success:
                logger.error("[FAILED]  物理 API 写入失败，硬阻断流转！", extra=extra_log)
                record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "看板状态 API 写入失败", delegated_by=delegated_by, delegation_reason=delegation_reason)
                return False
            if remarks:
                adapter.append_remarks(resolved_record_id, "remarks", remarks)
        except Exception as e:
            logger.error(f"[FAILED]  物理 API 调用抛出异常 ({e})，硬阻断！", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, f"API 抛出异常: {e}", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return False

        # 6. 追加备注与补偿回滚
        remarks_key = field_mapping.get("remarks", "remarks")
        if remarks:
            try:
                rem_ok = adapter.append_remarks(resolved_record_id, remarks_key, remarks)
                if not rem_ok:
                    logger.warning("[WARN]  结构化缺陷备注追加失败，准备执行物理原子补偿回滚...", extra=extra_log)
                    rollback_fields = {status_key: from_status, assignee_key: orig_assignee}
                    # 回滚必须写回 resolved_record_id（auto-create 场景 record_id 为 None，原实现回滚静默失效）
                    adapter.update_record(resolved_record_id, rollback_fields)
                    logger.error("[SYNC]  状态已物理回滚还原至原状态，拒绝非原子性中间态落库！", extra=extra_log)
                    record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "追加备注失败触发状态原子补偿回滚", delegated_by=delegated_by, delegation_reason=delegation_reason)
                    return False
            except Exception as e:
                logger.error(f"[WARN]  备注追加抛出异常 ({e})，执行物理原子补偿回滚...", extra=extra_log)
                adapter.update_record(resolved_record_id, {status_key: from_status, assignee_key: orig_assignee})
                record_audit_event(task_id, current_role, from_status, to_status, assignee, False, f"备注异常回滚: {e}", delegated_by=delegated_by, delegation_reason=delegation_reason)
                return False

        logger.info(f" 看板 {task_id} 已成功推至【{to_status}】，处理人: {assignee}", extra=extra_log)
        record_audit_event(task_id, current_role, from_status, to_status, assignee, True, "流转全量物理落库成功", delegated_by=delegated_by, delegation_reason=delegation_reason)
        return True

    finally:
        release_concurrency_lock(lock_tuple)


def main():
    parser = argparse.ArgumentParser(description="一键门控任务流转管道工具")
    parser.add_argument("--config", default="config/workflow.config.yaml", help="配置文件路径")
    parser.add_argument("--task-id", default="", help="任务编号 (如 T0001)；不传则自动分配最大编号+1 (并发安全)")
    parser.add_argument("--record-id", default=None, help="看板内部记录 ID (离线看板默认等于任务编号，可省略)")
    parser.add_argument("--task-name", default=None, help="任务名称 (任务不存在自动创建时必填建议项)")
    parser.add_argument("--stage", default=None, help="项目阶段 (自动创建时写入)")
    parser.add_argument("--wp", default=None, help="工作包 (自动创建时写入)")
    parser.add_argument("--wbs", default=None, help="WBS 编号 (自动创建时写入)")
    parser.add_argument("--owner", default=None, help="负责人/验收人 (自动创建时写入 handler)")
    parser.add_argument("--role", required=True, help="当前触发者角色 (PM/DEV/REVIEWER/QA 等)")
    parser.add_argument("--from-status", required=True, help="原状态")
    parser.add_argument("--to-status", required=True, help="目标状态")
    parser.add_argument("--assignee", required=True, help="同步更新的处理人")
    parser.add_argument("--type", default="A", help="任务类型 (A-G)")
    parser.add_argument("--end-time", help="结束时间 (完成/验收必填)")
    parser.add_argument("--remarks", help="追加结构化缺陷或备注描述")
    parser.add_argument("--active-dev-count", type=int, default=1, help="当前开发人员'进行中'任务数 (并发上限校验用)")
    parser.add_argument("--dry-run", action="store_true", help="开启预检测试模式而不物理写卡")
    parser.add_argument("--delegated-by", default="", help="提权代行来源角色 (如 PM/USER),留痕到 audit,需在白名单内")
    parser.add_argument("--delegation-reason", default="", help="提权代行理由 (人类用户显式授权时必填)")

    args = parser.parse_args()

    ok = transition_task_pipeline(
        config_path=args.config,
        task_id=args.task_id,
        record_id=args.record_id,
        current_role=args.role,
        from_status=args.from_status,
        to_status=args.to_status,
        assignee=args.assignee,
        task_type=args.type,
        end_time=args.end_time,
        remarks=args.remarks,
        dry_run=args.dry_run,
        active_dev_count=args.active_dev_count,
        task_name=args.task_name,
        stage=args.stage,
        wp=args.wp,
        wbs=args.wbs,
        owner=args.owner,
        delegated_by=args.delegated_by,
        delegation_reason=args.delegation_reason,
    )

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
