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

from transition_task import transition_task_pipeline, ROLE_NAME_MAP, normalize_role_name


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
    p_create.add_argument("--owner", default=None, help="负责人 (缺省=执行人)")
    p_create.add_argument("--type", default="A", help="任务类型 (A-G)")
    p_create.add_argument("--est-hours", type=float, default=0.0, help="预估工时 (小时)")
    p_create.add_argument("--pretask", default=None, help="前置依赖任务编号 (如 T0001)")
    p_create.add_argument("--start-time", default=None, help="开始时间 (格式 YYYY-MM-DD HH:MM:SS)")
    p_create.add_argument("--remarks", default=None, help="任务核心要点描述/备注 (建卡时记录核心设计、输入输出契约或排查要点)")
    p_create.add_argument("--target", default=None, help="任务核心目标说明")
    p_create.add_argument("--criteria", action="append", default=None, help="验收标准（支持传多次或用分号/换行分隔）")
    p_create.add_argument("--week", default=None, help="显式归属周口径 (如 2026-W36)")
    p_create.add_argument("--force", action="store_true", help="强制创建任务（跳过单一职责拦截与重复校验）")
    p_create.add_argument("--no-dup-check", action="store_true", help="跳过重复任务校验")

    p_accept = sub.add_parser("accept", help="人类用户专属验收命令（将已完成推进至已验收）")
    p_accept.add_argument("--config", default=None, help="配置文件路径")
    p_accept.add_argument("--task-id", required=True, help="任务编号 (如 T0001)")
    p_accept.add_argument("--remarks", default=None, help="验收说明/结论")
    p_accept.add_argument("--comment", default="人类用户核验代码与交付物合规，确认最终验收", help="流程说明")

    p_accept_all = sub.add_parser("accept-all", help="批量人类验收（将指定阶段所有已完成任务一键推进至已验收）")
    p_accept_all.add_argument("--config", default=None, help="配置文件路径")
    p_accept_all.add_argument("--stage", default=None, help="指定项目阶段 (如 'Sprint 1'，缺省为全部已完成)")
    p_accept_all.add_argument("--remarks", default=None, help="批量验收说明")

    p_complete = sub.add_parser("complete", help="推进任务到目标状态")
    p_complete.add_argument("--config", default=None, help="配置文件路径")
    p_complete.add_argument("--task-id", required=True, help="任务编号 (如 T0001)")
    p_complete.add_argument("--role", required=True, help="执行角色")
    p_complete.add_argument("--from-status", required=True, help="原状态")
    p_complete.add_argument("--to-status", required=True, help="目标状态")
    p_complete.add_argument("--assignee", required=True, help="同步更新的处理人")
    p_complete.add_argument("--type", default="A", help="任务类型 (A-G)")
    p_complete.add_argument("--ignore-pretask", action="store_true", help="忽略前置依赖未就绪拦截")
    p_complete.add_argument("--start-time", default=None, help="开始时间 (格式 YYYY-MM-DD HH:MM:SS)")
    p_complete.add_argument("--end-time", default=None, help="结束时间 (终态必填)")
    p_complete.add_argument("--remarks", default=None, help="备注 (打回/阻断等结构化信息)")
    p_complete.add_argument("--comment", default=None, help="操作说明/阶段交付总结 (写入流程节点)")
    p_complete.add_argument("--delegated-by", default="", help="代行来源 (如 USER/PM)")
    p_complete.add_argument("--delegation-reason", default="", help="代行理由")

    args = parser.parse_args()

    if args.command == "create":
        assignee = normalize_role_name(args.assignee or args.role)
        ok = transition_task_pipeline(
            config_path=args.config,
            current_role=args.role,
            assignee=assignee,
            task_name=args.name,
            task_type=args.type,
            est_hours=args.est_hours,
            pretask=args.pretask,
            start_time=getattr(args, "start_time", None),
            stage=args.stage,
            wp=args.wp,
            wbs=args.wbs,
            owner=args.owner,
            remarks=getattr(args, "remarks", None),
            target=getattr(args, "target", None),
            criteria=getattr(args, "criteria", None),
            week=getattr(args, "week", None),
            create_only=True,
            force=args.force,
            no_dup_check=args.no_dup_check,
        )
    elif args.command == "accept":
        import datetime
        import sys as _sys
        import os as _os
        # 安全加固 (2026-08-27): 人类验收专用命令 —— 物理拦截自动化静默调用
        # a) TTY 检测: 非交互终端(Agent 子进程/管道)直接阻断;
        # b) [y/N] 交互确认: 真人必须显式敲 y 二次确认;
        # c) 自动化仿真与 CI 环境: 支持检测环境变量 HUMAN_FORCE_TOKEN 静默旁路（不在报错中泄露变量名）;
        # d) 通过后仅注入 force_verify_operator=True (门控内完成真人确认标记),
        #    不再伪造 delegated_by="USER" 代行凭证。
        is_interactive = _sys.stdin.isatty()
        has_force_token = bool(_os.environ.get("HUMAN_FORCE_TOKEN"))
        if not is_interactive and not has_force_token:
            print("[REJECT 物理拦截] accept 命令禁止在非交互式/自动化子进程中执行！请在终端手动输入或在 Web 看板携带主控 Token 验收。")
            _sys.exit(1)
        if is_interactive:
            print(f"[SECURITY]  确认执行人类最终验收？任务 {args.task_id} 将永久流转至【已验收】终态 (不可逆)。")
            try:
                confirm = input("请输入 y 确认验收 (其他任意键取消): ").strip().lower()
            except EOFError:
                confirm = ""
            if confirm != "y":
                print("[CANCEL]  已取消验收，任务状态未变更。")
                _sys.exit(1)
        end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ok = transition_task_pipeline(
            config_path=args.config,
            task_id=args.task_id,
            current_role="PM",
            from_status="已完成",
            to_status="已验收",
            assignee="严经理",
            end_time=end_time,
            remarks=args.remarks,
            comment=args.comment,
            force_verify_operator=True,
        )
        if ok:
            print(f"[SUCCESS]  🎉 任务 {args.task_id} 已成功完成人类最终验收（已验收）！")
    elif args.command == "accept-all":
        import datetime
        import sys as _sys
        import os as _os
        from _lib.boards.board_adapter_factory import get_board_adapter
        adapter = get_board_adapter(args.config)
        recs = adapter.list_records(limit=1000)
        # 先扫描候选：无候选时直接提示退出，不触发 TTY 门禁（保持空跑可用）
        candidates = []
        for r in recs:
            f = r.get("fields", {})
            st = str(f.get("status") or "")
            tid = str(f.get("id") or r.get("record_id") or "")
            stg = str(f.get("stage") or "")
            if st == "已完成":
                if args.stage and str(args.stage).strip().lower() not in stg.lower():
                    continue
                candidates.append(tid)
        if not candidates:
            stage_hint = f"（阶段: {args.stage}）" if args.stage else ""
            print(f"[INFO]  💡 提示：当前未检索到处于【已完成】待人类验收的任务{stage_hint}。")
            return
        # 安全加固 (2026-08-27): 批量人类验收物理拦截自动化静默调用
        is_interactive = _sys.stdin.isatty()
        has_force_token = bool(_os.environ.get("HUMAN_FORCE_TOKEN"))
        if not is_interactive and not has_force_token:
            print("[REJECT 物理拦截] accept-all 命令禁止在非交互式/自动化子进程中执行！请在终端手动输入或在 Web 看板携带主控 Token 验收。")
            _sys.exit(1)
        if is_interactive:
            print(f"[SECURITY]  确认批量执行人类最终验收？共 {len(candidates)} 个任务将永久流转至【已验收】终态 (不可逆)。")
            try:
                confirm = input("请输入 y 确认批量验收 (其他任意键取消): ").strip().lower()
            except EOFError:
                confirm = ""
            if confirm != "y":
                print("[CANCEL]  已取消批量验收，任务状态未变更。")
                _sys.exit(1)
        accepted_count = 0
        now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for tid in candidates:
            r = adapter.get_record(tid) if tid else None
            if r is None:
                continue
            f = r.get("fields", {})
            t_type = str(f.get("task_type") or f.get("type") or "A")
            ok_single = transition_task_pipeline(
                config_path=args.config,
                task_id=tid,
                current_role="PM",
                from_status="已完成",
                to_status="已验收",
                assignee="严经理",
                task_type=t_type,
                end_time=now_time,
                remarks=args.remarks,
                comment="人类用户批量核验完成最终验收",
                force_verify_operator=True,
            )
            if ok_single:
                accepted_count += 1
                print(f"  [ACCEPTED] {tid} -> 已验收")
        if accepted_count > 0:
            print(f"[SUCCESS]  🎉 批量验收完成：共完成 {accepted_count} 个任务的最终验收！")
        else:
            print(f"[INFO]  💡 提示：候选任务均已处理完毕，无新增验收。")
        ok = True
    else:
        ok = transition_task_pipeline(
            config_path=args.config,
            task_id=args.task_id,
            current_role=args.role,
            from_status=args.from_status,
            to_status=args.to_status,
            assignee=args.assignee,
            task_type=args.type,
            ignore_pretask=getattr(args, "ignore_pretask", False),
            start_time=getattr(args, "start_time", None),
            end_time=args.end_time,
            remarks=args.remarks,
            comment=args.comment,
            delegated_by=args.delegated_by,
            delegation_reason=args.delegation_reason,
        )

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
