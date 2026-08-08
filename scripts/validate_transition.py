#!/usr/bin/env python3
"""
状态流转与角色门控强校验预检脚本 (Validate Transition CLI)
支持 A-G 任务类型 (task_type) 转换权限矩阵防越权物理硬拦截。
"""
import sys
import argparse
from typing import List, Dict

# 定义基础权限矩阵 (区分通用流转)
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
        # 注意: 进行中 -> 已完成 属于特权，仅允许在 G/B/C/D 类任务中解锁！
    ],
    "REVIEWER": [
        "审查中 -> 测试中",
        "审查中 -> 已退回",
        "进行中 -> 已阻塞",
        "已阻塞 -> 进行中"
    ],
    "QA": [
        "测试中 -> 已完成",
        "测试中 -> 已退回",
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


def validate(role: str, from_status: str, to_status: str, assignee: str, end_time: str, active_dev_count: int, task_type: str = "A") -> bool:
    transition_key = f"{from_status} -> {to_status}"
    role_upper = role.upper()
    type_upper = task_type.upper()

    # 1. 越权校验 (基于 task_type 分级判定)
    allowed_list = list(ROLE_BASE_PERMISSIONS.get(role_upper, []))

    # 特殊规则解锁：仅当为 B(架构), C(文档), D(运维), G(环境搭建) 类任务时，DEV 允许直接推至已完成
    if role_upper == "DEV" and type_upper in ["B", "C", "D", "G"]:
        allowed_list.append("进行中 -> 已完成")

    # A 类 (常规开发任务) DEV 强行推已完成判断为违规越权
    if role_upper == "DEV" and type_upper == "A" and transition_key == "进行中 -> 已完成":
        print(f"[REJECT 越权拦截] DEV 角色在 A 类 (常规代码开发) 任务中禁止直接推动至 '已完成'！必须先提交审查 (审查中 ➔ 测试中)！")
        return False

    if not any(transition_key.startswith(allowed) for allowed in allowed_list):
        print(f"[REJECT 越权拦截] 角色 {role_upper} (任务类型 {type_upper}) 无权推动状态转换: '{transition_key}'")
        return False

    # 2. 原子更新校验：检查 assignee 是否设置
    if not assignee:
        print(f"[REJECT 原子更新拦截] 变更状态至 '{to_status}' 时必须同步指定处理人 (Assignee)！")
        return False

    # 3. 终态结束时间强校验
    if to_status in ["已完成", "已验收"] and not end_time:
        print(f"[REJECT 结束时间缺失] 推动至终态 '{to_status}' 前，强制要求写入结束时间 (end_time)！")
        return False

    # 4. 开发人员并发上限核验
    if role_upper == "DEV" and to_status == "进行中" and active_dev_count >= 3:
        print(f"[REJECT 并发超限] 开发人员处于 '进行中' 任务数目前为 {active_dev_count}，超出并发上限 (≤3)！")
        return False

    print(f"[PASS 校验通过] 角色 {role_upper} (任务类型 {type_upper}) 推动 '{transition_key}' 满足所有四层防错门控。")
    return True


def main():
    parser = argparse.ArgumentParser(description="看板状态流转预检脚本")
    parser.add_argument("--role", required=True, help="操作人角色代码 (如 DEV, REVIEWER, PM)")
    parser.add_argument("--from-status", required=True, help="原状态")
    parser.add_argument("--to-status", required=True, help="目标状态")
    parser.add_argument("--assignee", required=True, help="同步更新的处理人")
    parser.add_argument("--type", default="A", help="任务类型 (A-G)")
    parser.add_argument("--end-time", default="", help="结束时间 (终态必填)")
    parser.add_argument("--active-dev-count", type=int, default=1, help="当前开发人员进行中任务数")

    args = parser.parse_args()

    success = validate(
        role=args.role,
        from_status=args.from_status,
        to_status=args.to_status,
        assignee=args.assignee,
        end_time=args.end_time,
        active_dev_count=args.active_dev_count,
        task_type=args.type
    )

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
