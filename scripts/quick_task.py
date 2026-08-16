#!/usr/bin/env python3
"""
极简任务包装命令 (Quick Task CLI)
零心智极简操作，内部完整复用 transition_task 门控/锁/审计管线（不旁路）。

用法:
  # 建卡【待开始】并分配处理人（PM 可派发任意；非 PM 仅可自建）
  python3 scripts/quick_task.py create --name "用户登录接口" --role PM --assignee 李开发
  python3 scripts/quick_task.py create --name "文档审查" --role DOCS

  # 推进任务到目标状态
  python3 scripts/quick_task.py complete --task-id T0001 --role DEV \
      --from-status 待开始 --to-status 进行中 --assignee 李开发
"""
import sys
import os
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from transition_task import transition_task_pipeline, ROLE_NAME_MAP


def main():
    parser = argparse.ArgumentParser(description="极简任务包装命令 (Quick Task CLI)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="建卡【待开始】并分配处理人")
    p_create.add_argument("--config", default=None, help="配置文件路径")
    p_create.add_argument("--name", required=True, help="任务名称")
    p_create.add_argument("--role", required=True, help="建卡角色 (PM 可派发任意；非 PM 仅可自建)")
    p_create.add_argument("--assignee", default=None, help="处理人 (缺省=角色本人)")
    p_create.add_argument("--stage", default=None, help="项目阶段")
    p_create.add_argument("--wp", default=None, help="工作包")
    p_create.add_argument("--wbs", default=None, help="WBS 编号")
    p_create.add_argument("--owner", default=None, help="负责人 (缺省=建卡角色)")
    p_create.add_argument("--type", default="A", help="任务类型 (A-G)")
    p_create.add_argument("--force", action="store_true", help="重复任务校验命中时强制创建")
    p_create.add_argument("--no-dup-check", action="store_true", help="跳过重复任务校验")

    p_complete = sub.add_parser("complete", help="推进任务到目标状态")
    p_complete.add_argument("--config", default=None, help="配置文件路径")
    p_complete.add_argument("--task-id", required=True, help="任务编号 (如 T0001)")
    p_complete.add_argument("--role", required=True, help="执行角色")
    p_complete.add_argument("--from-status", required=True, help="原状态")
    p_complete.add_argument("--to-status", required=True, help="目标状态")
    p_complete.add_argument("--assignee", required=True, help="同步更新的处理人")
    p_complete.add_argument("--type", default="A", help="任务类型 (A-G)")
    p_complete.add_argument("--end-time", default=None, help="结束时间 (终态必填)")
    p_complete.add_argument("--remarks", default=None, help="备注 (打回/阻断等结构化信息)")
    p_complete.add_argument("--delegated-by", default="", help="代行来源 (如 USER/PM)")
    p_complete.add_argument("--delegation-reason", default="", help="代行理由")

    args = parser.parse_args()

    if args.command == "create":
        assignee = args.assignee or ROLE_NAME_MAP.get(args.role.upper(), args.role)
        ok = transition_task_pipeline(
            config_path=args.config,
            current_role=args.role,
            assignee=assignee,
            task_name=args.name,
            task_type=args.type,
            stage=args.stage,
            wp=args.wp,
            wbs=args.wbs,
            owner=args.owner,
            create_only=True,
            force=args.force,
            no_dup_check=args.no_dup_check,
        )
    else:
        ok = transition_task_pipeline(
            config_path=args.config,
            task_id=args.task_id,
            current_role=args.role,
            from_status=args.from_status,
            to_status=args.to_status,
            assignee=args.assignee,
            task_type=args.type,
            end_time=args.end_time,
            remarks=args.remarks,
            delegated_by=args.delegated_by,
            delegation_reason=args.delegation_reason,
        )

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
