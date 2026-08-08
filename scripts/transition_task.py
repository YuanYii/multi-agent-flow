#!/usr/bin/env python3
"""
一键门控流转管道命令 (Transition Task Pipeline)
将 4 道安全防错门控 (validate_transition) 与看板写入 (board_adapter) 物理绑定。
贯彻 Fail-Closed (故障即拦截) 原则：未通过门控或 API 写入失败绝对返回 False，杜绝伪假成功！
"""

import sys
import os
import argparse
from typing import Dict, Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from validate_transition import validate
from board_adapter_factory import get_board_adapter


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
    remarks: str = None
) -> bool:
    print(f"🔒 [Step 1/2] 触发防错门控强校验 (Task: {task_id}, {from_status} ➔ {to_status})...")

    # 1. 强制运行防护门控，未通过则直接抛错中断！
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
        print(f"❌ [门控物理拦截失败] 阻止落库更新！原因: 校验未通过")
        return False

    print(f"✅ [门控通过] 防错规则核验成功，开始写卡落库...")

    # 2. 获取看板 Adapter 物理更新（贯彻 Fail-Closed 原则，拿不到 Adapter 直接报错拦截）
    try:
        adapter = get_board_adapter(config_path)
    except Exception as e:
        print(f"❌ [看板配置异常] 无法加载看板 Adapter ({e})，阻止假成功更新！")
        return False

    if not adapter:
        print(f"❌ [看板更新失败] 适配器未正确初始化，严格拦截落库操作。")
        return False

    # 3. 执行状态与处理人原子写入
    update_fields = {
        "status": to_status,
        "assignee": assignee
    }
    if end_time:
        update_fields["end_time"] = end_time

    try:
        success = adapter.update_record(record_id, update_fields)
        if not success:
            print(f"❌ [物理 API 写入失败] 看板未动，硬阻断流转结果！")
            return False
    except Exception as e:
        print(f"❌ [物理 API 调用异常] 看板更新过程抛出错误 ({e})，物理阻断！")
        return False

    # 4. 若有追加备注 (如缺陷结构化信息 DEF-TXXX-N)
    if remarks:
        try:
            rem_ok = adapter.append_remarks(record_id, "remarks", remarks)
            if not rem_ok:
                print(f"⚠️ [警告] 状态已原子更新，但结构化缺陷备注追加失败，请检查卡片设置。")
        except Exception as e:
            print(f"⚠️ [警告] 结构化缺陷备注追加触发异常 ({e})。")

    print(f"🎉 [流转物理闭环成功] 看板 {task_id} 已成功推至【{to_status}】，处理人: {assignee}")
    return True


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
        remarks=args.remarks
    )

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
