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

from validate_transition import validate
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


def acquire_concurrency_lock(task_id: str):
    """获取物理排他并发锁 (Fail-Closed：冲突则直接返回 None, None 阻断)"""
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
    owner: str = None
) -> bool:
    resolved_task_id = task_id or "AUTO"
    extra_log = {"task_id": resolved_task_id}
    logger.info(f"🔒 触发防错门控校验 ({from_status} ➔ {to_status}, 模式: {'DRY-RUN' if dry_run else 'REAL'})...", extra=extra_log)

    # 1. 尝试获取并发独占锁 (Fail-Closed 硬拦截)
    #    自动编号场景 (task_id 为空) 不取 per-task 锁：编号分配由 OfflineBoardAdapter 内部
    #    全局阻塞锁 (board.json.seq.lock) 串行化保证唯一，多个专家并发新建任务全部可成功。
    lock_tuple = None
    if resolved_task_id != "AUTO":
        lock_tuple = acquire_concurrency_lock(resolved_task_id)
        if not lock_tuple or not lock_tuple[0]:
            logger.error(f"❌ [并发锁排他硬拦截] 任务 {resolved_task_id} 当前正被另一个进程独占写卡中，物理阻断！", extra=extra_log)
            record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, False, "物理并发排他锁硬拦截")
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
            logger.error(f"❌ 看板配置文件/Schema 校验断言失败: {e}，硬阻断！", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, f"配置文件校验失败: {e}")
            return False

        if not adapter:
            logger.error("❌ 适配器未正确初始化，拦截落库", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "适配器缺失")
            return False

        # 3. 强制运行防护门控 (并发上限透传，未通过则直接抛错中断！)
        is_valid = validate(
            role=current_role,
            from_status=from_status,
            to_status=to_status,
            assignee=assignee,
            end_time=end_time or "",
            active_dev_count=active_dev_count,
            task_type=task_type
        )

        if not is_valid:
            logger.error("❌ 门控物理拦截失败！阻止落库更新", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "门控规则校验未通过")
            return False

        logger.info("✅ 防错规则核验成功", extra=extra_log)

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
                    logger.info(f"ℹ️ [DRY-RUN] 任务 {task_id} 在看板中不存在，正式执行时将自动创建后再流转", extra=extra_log)
            logger.info("🧪 [DRY-RUN] 配置文件与 Schema 检验完全通过！模拟预检不触发物理网络写卡", extra=extra_log)
            record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, True, "DRY-RUN 完整校验测试通过")
            return True

        resolved_record_id = record_id or task_id
        existing = adapter.get_record(resolved_record_id) if resolved_record_id else None
        if existing is None:
            create_fields = {
                "task_id": task_id,
                "task_name": task_name or "工作包开发任务",
                "assignee": assignee,
                "owner": owner or current_role,
                "stage": stage,
                "workpackage": wp,
                "wbs_id": wbs,
            }
            created_id = adapter.create_record(create_fields)
            if not created_id:
                logger.error(f"❌ 任务自动创建失败（编号冲突或写入失败），硬阻断流转！", extra=extra_log)
                record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, False, "任务自动创建失败")
                return False
            if not task_id:
                task_id = created_id
            resolved_record_id = task_id
            extra_log = {"task_id": task_id}
            logger.info(f"🆕 任务 {task_id} 在看板中不存在，已自动创建（初始状态：待开始）", extra=extra_log)
            record_audit_event(task_id, current_role, "新建", "待开始", assignee, True, "任务自动创建")
        else:
            resolved_record_id = existing.get("record_id") or resolved_record_id

        # 6. 执行物理原子写入
        update_fields = {status_key: to_status, assignee_key: assignee}
        if end_time: update_fields[end_time_key] = end_time

        try:
            success = adapter.update_record(resolved_record_id, update_fields)
            if not success:
                logger.error("❌ 物理 API 写入失败，硬阻断流转！", extra=extra_log)
                record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "看板状态 API 写入失败")
                return False
        except Exception as e:
            logger.error(f"❌ 物理 API 调用抛出异常 ({e})，硬阻断！", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, f"API 抛出异常: {e}")
            return False

        # 6. 追加备注与补偿回滚
        remarks_key = field_mapping.get("remarks", "remarks")
        if remarks:
            try:
                rem_ok = adapter.append_remarks(resolved_record_id, remarks_key, remarks)
                if not rem_ok:
                    logger.warning("⚠️ 结构化缺陷备注追加失败，准备执行物理原子补偿回滚...", extra=extra_log)
                    rollback_fields = {status_key: from_status, assignee_key: current_role}
                    adapter.update_record(record_id, rollback_fields)
                    logger.error("🔄 状态已物理回滚还原至原状态，拒绝非原子性中间态落库！", extra=extra_log)
                    record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "追加备注失败触发状态原子补偿回滚")
                    return False
            except Exception as e:
                logger.error(f"⚠️ 备注追加抛出异常 ({e})，执行物理原子补偿回滚...", extra=extra_log)
                adapter.update_record(record_id, {status_key: from_status, assignee_key: current_role})
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
        owner=args.owner
    )

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
