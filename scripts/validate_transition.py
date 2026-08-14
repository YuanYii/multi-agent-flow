#!/usr/bin/env python3
"""
状态流转与角色门控强校验预检脚本 (Validate Transition CLI)
支持 A-G 全量 7 类任务类型 (task_type) 转换权限矩阵防越权物理硬拦截。
"""
import sys
import argparse
from typing import List, Dict

ROLE_BASE_PERMISSIONS: Dict[str, List[str]] = {
    "PM": [
        "待开始 -> 进行中",
        "待开始 -> 已验收",
        "进行中 -> 已验收",
        "已完成 -> 已验收",
        "已完成 -> 已退回",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中"
    ],
    "ARCHITECT": [
        "待开始 -> 进行中",
        "进行中 -> 已完成",
        "进行中 -> 审查中",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中"
    ],
    "DEV": [
        "待开始 -> 进行中",
        "进行中 -> 审查中",
        "已退回 -> 进行中",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中"
    ],
    "FRONTEND": [
        "待开始 -> 进行中",
        "进行中 -> 审查中",
        "已退回 -> 进行中",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中"
    ],
    "REVIEWER": [
        "审查中 -> 测试中",
        "审查中 -> 已退回",
        "审查中 -> 已阻塞",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中"
    ],
    "QA": [
        "测试中 -> 已完成",
        "测试中 -> 已退回",
        "测试中 -> 已阻塞",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中"
    ],
    "DOCS": [
        "待开始 -> 进行中",
        "进行中 -> 已完成",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中"
    ],
    "DEVOPS": [
        "待开始 -> 进行中",
        "进行中 -> 已完成",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中"
    ]
}


SPECIAL_DIRECT_COMPLETE_TYPES = ["B", "C", "D", "G"]


# 代行白名单:当前 role (即"被代行目标角色") → 哪些"代行来源角色"是合法的
# 设计原则:
#   - PM 是收口角色(验收/分配),任何角色可代行 PM(常见:任何角色代为验收)
#   - 其他 7 角色(执行类)只接受 PM 代行(典型:PM 兼任审查/测试/文档)与 USER 授权
#   - 同级互代行(DEV↔FRONTEND)被禁止(防止隐性越权——代码任务不可互换代写)
#   - USER 标识表示"人类用户授权代行",优先级最高,任何目标角色都接受
DELEGATION_ALLOW_MATRIX: Dict[str, List[str]] = {
    "PM":        ["PM", "ARCHITECT", "DEV", "FRONTEND", "REVIEWER", "QA", "DOCS", "DEVOPS", "USER"],
    "REVIEWER":  ["PM", "USER"],
    "QA":        ["PM", "USER"],
    "ARCHITECT": ["PM", "USER"],
    "DEV":       ["PM", "USER"],
    "FRONTEND":  ["PM", "USER"],
    "DOCS":      ["PM", "USER"],
    "DEVOPS":    ["PM", "USER"],
}


def validate_delegation_authority(current_role: str, delegated_by: str) -> bool:
    """
    提权代行白名单校验:校验 "delegated_by 代行 current_role" 是否在白名单内。
    返回 True=合法代行, False=非法代行(阻断)。
    当 delegated_by 为空/None 时,直接返回 True(无代行声明,交给 validate 的常规权限矩阵处理)。
    """
    if not delegated_by or not str(delegated_by).strip():
        return True
    role_upper = str(current_role).upper().strip()
    by_upper = str(delegated_by).upper().strip()
    allowed = DELEGATION_ALLOW_MATRIX.get(role_upper, [])
    if by_upper in [a.upper() for a in allowed]:
        return True
    print(f"[REJECT 代行未授权] 角色 {role_upper} 不接受来自 {by_upper} 的代行授权 (白名单: {allowed})")
    return False


def validate(role: str, from_status: str, to_status: str, assignee: str, end_time: str, active_dev_count: int, task_type: str = "A", task_name: str = "", max_parallel: int = 3, remarks: str = "", special_types: List[str] = None, delegated_by: str = "", delegation_reason: str = "") -> bool:
    # 0. 提权代行白名单硬校验 (Fail-Closed)
    if not validate_delegation_authority(role, delegated_by):
        return False

    transition_key = f"{from_status} -> {to_status}"
    role_upper = role.upper()
    type_upper = task_type.upper()
    direct_types = [t.upper() for t in (special_types or SPECIAL_DIRECT_COMPLETE_TYPES)]

    allowed_list = list(ROLE_BASE_PERMISSIONS.get(role_upper, []))
    is_hotfix = bool(task_name and "[HOTFIX]" in task_name.upper())

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

    # A 类 (常规代码开发) 任务 DEV/FRONTEND 强行推已完成判断为违规越权 (HOTFIX 豁免)
    if role_upper in ["DEV", "FRONTEND"] and type_upper == "A" and transition_key == "进行中 -> 已完成" and not is_hotfix:
        print(f"[REJECT 越权拦截] {role_upper} 角色在 A 类 (常规代码开发) 任务中禁止直接推动至 '已完成'！必须先提交审查 (审查中 -> 测试中)！")
        return False

    # A 类 (常规代码开发) 任务 PM 强行推进行中 -> 已验收 判断为违规越权 (跳过 Review 与 QA)
    if role_upper == "PM" and type_upper == "A" and transition_key == "进行中 -> 已验收":
        print(f"[REJECT 越权拦截] PM 角色在 A 类 (常规代码开发) 任务中禁止直接由 '进行中' 推动至 '已验收'！必须经过代码审查与测试流程！")
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

    # 3. 终态结束时间强校验 (E 类用户自执行任务豁免 end_time 强校验)
    if to_status in ["已完成", "已验收"] and not end_time:
        if type_upper == "E":
            print(f"[EXEMPT 豁免提示] E 类 (用户自执行/审批) 任务在推动至 '{to_status}' 时物理豁免 end_time 强校验。")
        else:
            print(f"[REJECT 结束时间缺失] 推动至终态 '{to_status}' 前，强制要求写入结束时间 (end_time)！")
            return False

    # 4. 开发人员并发上限核验
    if role_upper in ["DEV", "FRONTEND"] and to_status == "进行中" and active_dev_count >= max_parallel:
        print(f"[REJECT 并发超限] 开发人员处于 '进行中' 任务数目前为 {active_dev_count}，超出并发上限 (≤{max_parallel})！")
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
