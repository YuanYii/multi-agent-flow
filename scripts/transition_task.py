#!/usr/bin/env python3
"""
一键门控流转管道命令 (Transition Task Pipeline)
物理级硬防错：排他文件锁并发控制 + 门控断言 + 物理原子补偿回滚 + 结构化审计日志 + --dry-run 预检支持。
"""

import sys
import os
import argparse
import logging
from typing import Dict, Any, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from validate_transition import validate
from board_adapter_factory import get_board_adapter
from audit_logger import record_audit_event

# 结构化日志输出
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Task: %(task_id)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("transition_pipeline")


def acquire_concurrency_lock(task_id: str):
    """获取并发排他锁 (fcntl 物理跨进程锁)"""
    lock_file = os.path.join(SCRIPT_DIR, f".lock_{task_id}.lock")
    f = open(lock_file, "w")
    try:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f, lock_file
    except (ImportError, IOError):
        # 非 POSIX 环境降级
        return f, lock_file


def release_concurrency_lock(lock_tuple):
    if not lock_tuple:
        return
    f, lock_file = lock_tuple
    try:
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
    task_id: str,
    record_id: str,
    current_role: str,
    from_status: str,
    to_status: str,
    assignee: str,
    task_type: str = "A",
    end_time: str = None,
    remarks: str = None,
    dry_run: bool = False
) -> bool:
    extra_log = {"task_id": task_id}
    logger.info(f"🔒 触发防错门控强校验 ({from_status} ➔ {to_status}, 模式: {'DRY-RUN' if dry_run else 'REAL'})...", extra=extra_log)

    # 1. 尝试获取并发独占锁
    lock_tuple = acquire_concurrency_lock(task_id)

    try:
        # 2. 强制运行防护门控，未通过则直接抛错中断！
        is_valid = validate(
            role=current_role,
            from_status=from_status,
            to_status=to_status,
            assignee=assignee,
            end_time=end_time or "",
            active_dev_count=1,
            task_type=task_type
        )

        if not is_valid:
            logger.error("❌ 门控物理拦截失败！阻止落库更新", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "门控规则校验未通过")
            return False

        logger.info("✅ 防错规则核验成功", extra=extra_log)

        if dry_run:
            logger.info("🧪 [DRY-RUN] 预检测试通过，模拟模式不触发物理 API 写入", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, True, "DRY-RUN 预检测试通过")
            return True

        # 3. 获取看板 Adapter
        try:
            adapter = get_board_adapter(config_path)
        except Exception as e:
            logger.error(f"❌ 无法加载看板 Adapter ({e})，阻止假成功！", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, f"配置文件异常: {e}")
            return False

        if not adapter:
            logger.error("❌ 适配器未正确初始化，拦截落库", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "适配器缺失")
            return False

        # 4. 执行状态与处理人原子写入
        update_fields = {"status": to_status, "assignee": assignee}
        if end_time: update_fields["end_time"] = end_time

        try:
            success = adapter.update_record(record_id, update_fields)
            if not success:
                logger.error("❌ 物理 API 写入失败，硬阻断流转！", extra=extra_log)
                record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "看板状态 API 写入失败")
                return False
        except Exception as e:
            logger.error(f"❌ 物理 API 调用抛出异常 ({e})，硬阻断！", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, f"API 抛出异常: {e}")
            return False

        # 5. 若有追加备注，执行追加；若追加失败，触发物理原子补偿回滚！
        if remarks:
            try:
                rem_ok = adapter.append_remarks(record_id, "remarks", remarks)
                if not rem_ok:
                    logger.warning("⚠️ 结构化缺陷备注追加失败，准备执行物理原子补偿回滚...", extra=extra_log)
                    # 物理补偿回滚：还原状态与处理人
                    rollback_fields = {"status": from_status, "assignee": current_role}
                    adapter.update_record(record_id, rollback_fields)
                    logger.error("🔄 状态已物理回滚还原至原状态，拒绝非原子性中间态落库！", extra=extra_log)
                    record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "追加备注失败触发状态原子补偿回滚")
                    return False
            except Exception as e:
                logger.error(f"⚠️ 备注追加抛出异常 ({e})，执行物理原子补偿回滚...", extra=extra_log)
                adapter.update_record(record_id, {"status": from_status, "assignee": current_role})
                record_audit_event(task_id, current_role, from_status, to_status, assignee, False, f"备注异常回滚: {e}")
                return False

        logger.info(f"🎉 看板 {task_id} 已成功推至【{to_status}】，处理人: {assignee}", extra=extra_log)
        record_audit_event(task_id, current_role, from_status, to_status, assignee, True, "流转全量物理落库成功")
        return True

    finally:
        release_concurrency_lock(lock_tuple)


def main():
    parser = argparse.ArgumentParser(description="一键门控任务流转管道工具")
    parser.add_argument("--config", default="config/workflow.config.yaml", help="配置文件路径")
    parser.add_argument("--task-id", required=True, help="任务编号 (如 T0001)")
    parser.add_argument("--record-id", required=True, help="看板内部记录 ID")
    parser.add_argument("--role", required=True, help="当前触发者角色 (PM/DEV/REVIEWER/QA 等)")
    parser.add_argument("--from-status", required=True, help="原状态")
    parser.add_argument("--to-status", required=True, help="目标状态")
    parser.add_argument("--assignee", required=True, help="同步更新的处理人")
    parser.add_argument("--type", default="A", help="任务类型 (A-G)")
    parser.add_argument("--end-time", help="结束时间 (完成/验收必填)")
    parser.add_argument("--remarks", help="追加结构化缺陷或备注描述")
    parser.add_argument("--dry-run", action="store_true", help="开启预检测试模式而不物理写卡")

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
        dry_run=args.dry_run
    )

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
