#!/usr/bin/env python3
"""
状态流转与角色门控强校验预检脚本 (Validate Transition CLI)
支持 A-G 全量 7 类任务类型 (task_type) 转换权限矩阵防越权物理硬拦截。
"""
import re
import sys
import os
import argparse
from typing import List, Dict, Any

from enums import TaskStatus, TaskType, RoleEnum, normalize_role

ROLE_BASE_PERMISSIONS: Dict[str, List[str]] = {
    "PM": [
        "待开始 -> 进行中",
        "待开始 -> 已完成",
        "待开始 -> 已验收",
        "待开始 -> 已取消",
        "进行中 -> 已验收",
        "进行中 -> 已完成",
        "进行中 -> 已取消",
        "审查中 -> 测试中",
        "审查中 -> 已退回",
        "审查中 -> 已取消",
        "测试中 -> 已完成",
        "测试中 -> 已退回",
        "测试中 -> 已取消",
        "已完成 -> 已验收",
        "已完成 -> 已退回",
        "已完成 -> 已取消",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中",
        "已阻塞 -> 已完成",
        "已阻塞 -> 已退回",
        "已阻塞 -> 已取消",
        "已退回 -> 进行中",
        "已退回 -> 已取消"
    ],
    "ARCHITECT": [
        "待开始 -> 进行中",
        "进行中 -> 已完成",
        "进行中 -> 审查中",
        "已退回 -> 进行中",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中",
        "已阻塞 -> 已完成",
        "已阻塞 -> 已退回"
    ],
    "DEV": [
        "待开始 -> 进行中",
        "进行中 -> 审查中",
        "已退回 -> 进行中",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中",
        "已阻塞 -> 已完成",
        "已阻塞 -> 已退回"
    ],
    "FRONTEND": [
        "待开始 -> 进行中",
        "进行中 -> 审查中",
        "已退回 -> 进行中",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中",
        "已阻塞 -> 已完成",
        "已阻塞 -> 已退回"
    ],
    "REVIEWER": [
        "待开始 -> 进行中",
        "进行中 -> 已完成",
        "已退回 -> 进行中",
        "审查中 -> 测试中",
        "审查中 -> 已退回",
        "审查中 -> 已阻塞",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中",
        "已阻塞 -> 审查中",
        "已阻塞 -> 已退回"
    ],
    "QA": [
        "待开始 -> 进行中",
        "进行中 -> 已完成",
        "已退回 -> 进行中",
        "测试中 -> 已完成",
        "测试中 -> 已退回",
        "测试中 -> 已阻塞",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中",
        "已阻塞 -> 测试中",
        "已阻塞 -> 已退回"
    ],
    "DOCS": [
        "待开始 -> 进行中",
        "进行中 -> 已完成",
        "已退回 -> 进行中",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中",
        "已阻塞 -> 已完成",
        "已阻塞 -> 已退回"
    ],
    "DEVOPS": [
        "待开始 -> 进行中",
        "进行中 -> 已完成",
        "已退回 -> 进行中",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中",
        "已阻塞 -> 已完成",
        "已阻塞 -> 已退回"
    ],
    "USER": [
        "待开始 -> 进行中",
        "待开始 -> 已验收",
        "待开始 -> 已取消",
        "进行中 -> 审查中",
        "进行中 -> 已完成",
        "进行中 -> 已验收",
        "进行中 -> 已取消",
        "审查中 -> 测试中",
        "审查中 -> 已完成",
        "审查中 -> 已退回",
        "审查中 -> 已取消",
        "测试中 -> 已完成",
        "测试中 -> 已退回",
        "测试中 -> 已取消",
        "已完成 -> 已验收",
        "已完成 -> 已退回",
        "已完成 -> 已取消",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中",
        "已阻塞 -> 已完成",
        "已阻塞 -> 已退回",
        "已阻塞 -> 已取消",
        "已退回 -> 进行中",
        "已退回 -> 已取消"
    ]
}


SPECIAL_DIRECT_COMPLETE_TYPES = sorted(list(TaskType.short_chain_types()))


# 代行白名单:当前 role (即"被代行目标角色") → 哪些"代行来源角色"是合法的
# 设计原则:
#   - PM 验收收口严格由人类用户 USER 授权代行，防止 Agent 私自代签验收
#   - 其他 7 角色(执行类)接受 PM 代行(典型:PM 兼任审查/测试/文档)与 USER 授权
#   - 同级互代行(DEV↔FRONTEND)被禁止(防止隐性越权——代码任务不可互换代写)
#   - USER 标识表示"人类用户授权代行",优先级最高,任何目标角色都接受
DELEGATION_ALLOW_MATRIX: Dict[str, List[str]] = {
    "PM":        ["PM", "USER"],
    "REVIEWER":  ["PM", "USER"],
    "QA":        ["PM", "USER"],
    "ARCHITECT": ["PM", "USER"],
    "DEV":       ["PM", "USER"],
    "FRONTEND":  ["PM", "USER"],
    "DOCS":      ["PM", "USER"],
    "DEVOPS":    ["PM", "USER"],
    "USER":      ["USER"],
}


def validate_delegation_authority(current_role: str, delegated_by: str) -> bool:
    """
    提权代行白名单校验:校验 "delegated_by 代行 current_role" 是否在白名单内。
    返回 True=合法代行, False=非法代行(阻断)。
    当 delegated_by 为空/None 时,直接返回 True(无代行声明,交给 validate 的常规权限矩阵处理)。
    """
    # 安全加固 (2026-08-27): OPERATOR_VIA_TOKEN 是 Web 流转 API 在主控 Token 校验通过后
    # 由服务端注入的真人操作凭据，不属于"角色代行"范畴，放行至 §2.4 人类专属门控处理。
    if str(delegated_by).strip().upper() == "OPERATOR_VIA_TOKEN":
        return True
    if not delegated_by or not str(delegated_by).strip():
        return True
    role_upper = str(current_role).upper().strip()
    by_upper = str(delegated_by).upper().strip()
    allowed = DELEGATION_ALLOW_MATRIX.get(role_upper, [])
    if by_upper in [a.upper() for a in allowed]:
        return True
    print(f"[REJECT 代行未授权] 角色 {role_upper} 不接受来自 {by_upper} 的代行授权 (白名单: {allowed})")
    return False


def validate(role: str, from_status: str, to_status: str, assignee: str, end_time: str, active_dev_count: int, task_type: str = "A", task_name: str = "", max_parallel: int = 3, remarks: str = "", special_types: List[str] = None, delegated_by: str = "", delegation_reason: str = "", pretask: str = "", adapter: Any = None, ignore_pretask: bool = False, force_verify_operator: bool = False, force_reopen: bool = False) -> bool:
    # 0. 提权代行白名单硬校验 (Fail-Closed)
    if not validate_delegation_authority(role, delegated_by):
        return False

    transition_key = f"{from_status} -> {to_status}"
    role_upper = role.upper()
    type_upper = task_type.upper()
    direct_types = [t.upper() for t in (special_types or SPECIAL_DIRECT_COMPLETE_TYPES)]

    allowed_list = list(ROLE_BASE_PERMISSIONS.get(role_upper, []))
    is_hotfix = bool(task_name and "[HOTFIX]" in task_name.upper())

    # 0. 终态不可逆流拦截与受控重开通道 (REOPEN 管理员纠偏)
    if from_status in ["已验收", "已取消"] and from_status != to_status:
        if not force_reopen:
            print(f"[REJECT 终态防篡改] 任务已处于终态【{from_status}】，禁止修改为【{to_status}】！若需管理员纠偏请使用 --force-reopen。")
            return False

        # 终态重开权限严格受控：仅限 PM 严经理、人类用户 (USER/OPERATOR_VIA_TOKEN) 或真人确认
        is_reopen_authorized = (
            role_upper in ["PM", "USER"]
            or str(delegated_by).strip().upper() in ["OPERATOR_VIA_TOKEN", "USER"]
            or force_verify_operator
        )
        if not is_reopen_authorized:
            print(f"[REJECT 重开权限拦截] 终态纠偏重开仅限 PM (严经理) 或人类用户 (USER) 授权执行！当前角色: {role}")
            return False

        # 目标状态限制：仅允许回退至【进行中】或【已完成】
        if to_status not in ["进行中", "已完成"]:
            print(f"[REJECT 重开目标非法] 终态任务仅允许纠偏回退至【进行中】或【已完成】，当前目标状态: 【{to_status}】！")
            return False

        # 强制校验 --remarks 必须写明纠偏原因
        if not remarks or not str(remarks).strip():
            print(f"[REJECT 重开原因缺失] 终态重开必须携带 --remarks 详细说明纠偏原因（约定格式：【纠偏重开】<原因>）！")
            return False

        # 关键放行补丁：动态向权限白名单追加重开流转，防止后续被 ROLE_BASE_PERMISSIONS 静态矩阵拦截
        allowed_list.extend([
            f"{from_status} -> 进行中",
            f"{from_status} -> 已完成"
        ])
        print(f"[AUDIT 纠偏重开放行] 管理员/PM 触发终态受控纠偏: 【{from_status}】 -> 【{to_status}】")

    # 1. 任务类型特权解锁
    # [HOTFIX] 紧急修复通道: 放行 DEV/FRONTEND 直接从 "进行中 -> 已完成"
    if is_hotfix and role_upper in ["DEV", "FRONTEND"]:
        allowed_list.append("进行中 -> 已完成")

    # F 类 (阶段总结): 解锁 PM 从 "进行中 -> 已完成"
    if role_upper == "PM" and type_upper == "F":
        allowed_list.append("进行中 -> 已完成")

    # 特权类任务 (默认 B 架构, C 文档, D 运维, G 环境搭建): 解锁 DEV/FRONTEND 直接推至 "已完成"
    if role_upper in ["DEV", "FRONTEND"] and type_upper in direct_types:
        allowed_list.append("进行中 -> 已完成")

    # A 类 (常规代码开发) 任务各执行角色强行推已完成判断为违规越权 (HOTFIX 豁免)
    if role_upper in ["DEV", "FRONTEND", "REVIEWER", "QA", "ARCHITECT"] and type_upper == "A" and transition_key == "进行中 -> 已完成" and not is_hotfix:
        print(f"[REJECT 越权拦截] {role_upper} 角色在 A 类 (常规代码开发) 任务中禁止直接推动至 '已完成'！必须先提交审查 (审查中 -> 测试中)！")
        return False

    # A 类 (常规代码开发) 任务 PM 强行推待开始/进行中 -> 已验收 判断为违规越权 (跳过 Review 与 QA)
    if role_upper == "PM" and type_upper == "A" and transition_key in ["待开始 -> 已验收", "进行中 -> 已验收"] and not is_hotfix:
        print(f"[REJECT 越权拦截] PM 角色在 A 类 (常规代码开发) 任务中禁止直接由 '{from_status}' 推动至 '已验收'！必须经过代码审查与测试流程！")
        return False

    if not any(transition_key.startswith(allowed) for allowed in allowed_list):
        print(f"[REJECT 越权拦截] 角色 {role_upper} (任务类型 {type_upper}) 无权推动状态转换: '{transition_key}'")
        return False

    # 2. 原子更新校验：检查 assignee 是否设置
    if not assignee:
        print(f"[REJECT 原子更新拦截] 变更状态至 '{to_status}' 时必须同步指定处理人 (Assignee)！")
        return False

    # 2.1 打回处理人定向核验：审查者/测试者打回时禁止将 Assignee 设为自身
    if to_status == "已退回":
        ROLE_SELF_NAMES = {
            "REVIEWER": ["REVIEWER", "周审查", "REVIEWER_USER"],
            "QA": ["QA", "章测试", "QA_USER"],
            "PM": ["PM", "严经理", "PM_USER"]
        }
        forbidden_names = ROLE_SELF_NAMES.get(role_upper, [role_upper])
        if assignee.strip().upper() in [f.upper() for f in forbidden_names]:
            print(f"[REJECT 打回处理人拦截] 角色 {role_upper} 执行打回操作时，禁止将处理人 (Assignee) 设置为自身 ({assignee})！必须精确退回原开发负责人！")
            return False

    # 2.2 置【已阻塞】必须携带阻断原因备注（约定格式：【阻断】<原因>），为 auto 前置验证提供数据
    if to_status == "已阻塞" and not remarks:
        print("[REJECT 阻断原因缺失] 置为【已阻塞】必须携带 --remarks 写明阻断原因（约定格式：【阻断】<原因>）！")
        return False

    # 2.3 置【已取消】必须携带取消原因备注，且经办人必须收敛至 PM (严经理)
    if to_status == "已取消":
        if not remarks:
            print("[REJECT 取消原因缺失] 置为【已取消】必须携带 --remarks 写明取消原因！")
            return False
        if not any(k in str(assignee).upper() for k in ["PM", "严经理", "经理"]):
            print(f"[REJECT 处理人拦截] 任务置为终态【已取消】时，经办人 (Assignee) 必须收敛至 PM (严经理)，当前为 '{assignee}'！")
            return False

    # 2.4 人类用户专属验收权限拦截：流转至【已验收】必须由真实人类显式授权
    # 安全加固 (2026-08-27):
    #   a) role=USER 不再是合法人类信号 —— CLI 的 --role 是纯自报参数，任何进程/Agent 都能自称 USER；
    #      USER 身份只能由 Web 看板 API 在验证主控 Token 后于服务端内部赋予；
    #   b) delegated_by=USER 不再作为人类授权凭据 —— 它是可伪造的普通字符串；
    #      真实人类授权只认两种通道：
    #      ① OPERATOR_VIA_TOKEN —— Web 流转 API 通过主控 Token 强校验后由服务端注入的内部标记；
    #      ② force_verify_operator=True —— transition_task/quick_task 入口层完成 isatty 检测与
    #         [y/N] 交互确认后注入的真人确认标记。
    if to_status == "已验收":
        is_human_authorized = (
            str(delegated_by).strip().upper() == "OPERATOR_VIA_TOKEN"
            or force_verify_operator
        )
        if not is_human_authorized:
            print(f"[REJECT 权限拦截] 状态【已验收】为人类用户专属终态，当前角色 {role} 无权代签！CLI 自报 role=USER 或 delegated_by=USER 均不再被承认。")
            print("  💡 合法验收通道：① Web 看板携带主控 Token 点击验收；② 真人终端执行 quick_task.py accept（自动 TTY 检测 + [y/N] 交互确认）")
            return False

    # 3. 终态结束时间强校验 (E 类用户自执行任务豁免 end_time 强校验)
    if to_status in ["已完成", "已验收", "已取消"] and not end_time:
        if type_upper == "E":
            print(f"[EXEMPT 豁免提示] E 类 (用户自执行/审批) 任务在推动至 '{to_status}' 时物理豁免 end_time 强校验。")
        else:
            print(f"[REJECT 结束时间缺失] 推动至终态 '{to_status}' 前，强制要求写入结束时间 (end_time)！")
            return False

    # 3.1 前置任务 (pretask) 依赖就绪门禁核验：待开始 -> 进行中
    if to_status == "进行中" and not ignore_pretask and not is_hotfix:
        if pretask and adapter:
            pre_ids = [p.strip() for p in re.split(r"[,;\s]+", str(pretask)) if p.strip()]
            for pid in pre_ids:
                prec = adapter.get_record(pid)
                if not prec:
                    print(f"[REJECT 前置依赖不存在] 前置任务 {pid} 在看板中不存在，禁止开工！可使用 --ignore-pretask 强制开工。")
                    return False
                pfields = prec.get("fields", {})
                p_status = str(pfields.get("status") or "")
                p_name = str(pfields.get("name") or pfields.get("task_name") or pid)
                if p_status not in ("已完成", "已验收"):
                    print(f"[REJECT 前置依赖未就绪] 前置任务 {pid}【{p_name}】当前处于【{p_status}】，必须推进至【已完成】或【已验收】后方可开工！如需紧急开工请加 --ignore-pretask 参数。")
                    return False

    # 4. 全角色并发上限核验 (WIP Limit)
    all_workers = ["DEV", "FRONTEND", "QA", "DOCS", "ARCHITECT", "DEVOPS"]
    if role_upper in all_workers and to_status == "进行中" and active_dev_count >= max_parallel:
        print(f"[REJECT 并发超限] 角色 {role_upper} 处于 '进行中' 任务数目前为 {active_dev_count}，超出并发上限 (≤{max_parallel})！")
        return False

    delegation_suffix = ""
    if delegated_by and str(delegated_by).strip():
        delegation_suffix = f" | 代行声明: {delegated_by} 代行 {role_upper} (理由: {delegation_reason or '未提供'})"
    print(f"[PASS 校验通过] 角色 {role_upper} (任务类型 {type_upper}) 推动 '{transition_key}' 满足所有五层防错门控。{delegation_suffix}")
    return True


def main():
    parser = argparse.ArgumentParser(description="看板状态流转预检脚本")
    parser.add_argument("--role", required=True, help="操作人角色代码 (如 DEV, REVIEWER, PM)")
    parser.add_argument("--from-status", required=True, help="原状态")
    parser.add_argument("--to-status", required=True, help="目标状态")
    parser.add_argument("--assignee", required=True, help="同步更新的处理人")
    parser.add_argument("--type", default="A", help="任务类型 (A-G)")
    parser.add_argument("--task-name", default="", help="任务名称 (包含 [HOTFIX] 可触发极简通道)")
    parser.add_argument("--end-time", default="", help="结束时间 (终态必填)")
    parser.add_argument("--remarks", default="", help="备注 (打回或补充信息)")
    parser.add_argument("--active-dev-count", type=int, default=1, help="当前开发人员进行中任务数")
    parser.add_argument("--max-parallel", type=int, default=3, help="角色允许的最大并发上限")
    parser.add_argument("--delegated-by", default="", help="提权代行来源角色 (如 PM/USER)")
    parser.add_argument("--delegation-reason", default="", help="提权代行理由")

    args = parser.parse_args()

    success = validate(
        role=args.role,
        from_status=args.from_status,
        to_status=args.to_status,
        assignee=args.assignee,
        end_time=args.end_time,
        active_dev_count=args.active_dev_count,
        task_type=args.type,
        task_name=args.task_name,
        max_parallel=args.max_parallel,
        remarks=args.remarks,
        delegated_by=args.delegated_by,
        delegation_reason=args.delegation_reason,
    )

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
