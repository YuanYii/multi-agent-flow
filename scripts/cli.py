#!/usr/bin/env python3
"""
Multi-Agent Flow 统一现代 CLI 总入口 (Unified CLI Gateway)
支持子命令透明转发与分发：task, dispatch, kanban, status, ccp, help
采用微内核门面设计模式，通过方法内部延迟加载（Lazy Import）确保毫秒级冷启动与环境故障隔离。
"""
import sys
import os
import argparse

# 将脚本当前所在目录加入 sys.path，保证无论从哪个工作目录调用均能正确检索同级模块
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


def print_usage():
    """
    打印 yy-flow 统一命令行工具的全景使用说明与典型示例。
    
    展示所支持的 6 大核心子命令（task, dispatch, kanban, status, help, ccp）
    以及常见研发场景下的标准调用示例。
    """
    print("""usage: yy-flow [-h] {task,dispatch,kanban,status,help,ccp} ...

Multi-Agent Team Workflow (YY-Flow) 统一命令行工具

subcommands:
  task      任务管理与流转 (透明转发至 quick_task / transition_task)
  dispatch  代码化任务派发 (透明转发至 dispatch_task，生成 Subagent 载荷)
  kanban    启动 Web 可视化看板 (透明转发至 start_kanban_server)
  status    大盘全局健康度巡检 (透明转发至 heartbeat)
  help      输出全景指令帮助手册 (透明转发至 show_help)
  ccp       上下文连续性协议门禁操作

示例:
  yy-flow task create --name "实现新接口" --type A --assignee 李开发
  yy-flow dispatch --task-id T0001
  yy-flow task accept --task-id T0001
  yy-flow kanban --port 32886
  yy-flow status --json
  yy-flow ccp --task-id T0001 --stage 审查中
""")


def cmd_task(extra_args):
    """
    处理 task 子命令：负责任务卡创建、状态推进、人类终态验收等操作。
    
    参数:
        extra_args (list[str]): 透传给 quick_task 的后续命令行参数列表（如 create, accept 等）。
    """
    # 核心设计：方法内部延迟加载 (Lazy Import)
    # 避免在运行其他非任务相关子命令（如 help、status）时提前加载重量级的状态机与存储适配器
    from quick_task import main as quick_main

    # 核心机制：动态改写 sys.argv，剥离外层命令动词 'task'
    # 将参数透传组装为形如 [sys.argv[0], 'create', ...]，模拟底层 quick_task.py 的独立调用上下文
    sys.argv = [sys.argv[0]] + extra_args

    # 调用底层任务管理主入口执行具体的建卡或状态转移逻辑
    quick_main()


def cmd_dispatch(extra_args):
    """
    处理 dispatch 子命令：执行代码化派单，校验依赖与并发限制，生成标准 Subagent 载荷。
    
    参数:
        extra_args (list[str]): 透传给 dispatch_task 的后续参数列表（如 --task-id 等）。
    """
    # 延迟导入任务派发引擎，避免全局冷启动开销
    from dispatch_task import main as dispatch_main

    # 动态重写命令行参数，透传 task-id 等派发参数
    sys.argv = [sys.argv[0]] + extra_args

    # 触发派发校验：推至【进行中】状态，并打印标准 invoke_subagent JSON 契约
    dispatch_main()


def cmd_kanban(extra_args):
    """
    处理 kanban 子命令：启动本地/局域网 Web 可视化看板 HTTP 服务。
    
    参数:
        extra_args (list[str]): 透传给 start_kanban_server 的参数列表（如 --port 等）。
    """
    # 延迟导入看板服务端模块
    # 关键隔离：避免在其他命令执行时触发看板模块顶层的动态高熵 Master Token 生成逻辑
    from start_kanban_server import main as kanban_main

    # 动态重写参数列表，透传服务配置
    sys.argv = [sys.argv[0]] + extra_args

    # 启动轻量 RESTful 看板服务并监听指定端口
    kanban_main()


def cmd_status(extra_args):
    """
    处理 status 子命令：触发全局健康度巡检，输出进度、阻塞卡片与效能度量。
    
    参数:
        extra_args (list[str]): 透传给 heartbeat 巡检引擎的参数列表（如 --json 等）。
    """
    # 延迟导入心跳与大盘巡检引擎
    from heartbeat import main as heartbeat_main

    # 动态重写参数列表
    sys.argv = [sys.argv[0]] + extra_args

    # 执行全局大盘扫描并输出诊断结果
    heartbeat_main()


def cmd_help(extra_args):
    """
    处理 help 子命令：展示系统全景指令速查、8 专家职责矩阵与协同规约。
    
    参数:
        extra_args (list[str]): 透传给 show_help 的参数列表。
    """
    # 延迟导入帮助文档输出模块
    from show_help import main as help_main

    # 动态重写参数列表
    sys.argv = [sys.argv[0]] + extra_args

    # 输出格式化帮助手册
    help_main()


def cmd_ccp(extra_args):
    """
    处理 ccp 子命令：执行上下文连续性协议 (CCP) 阶段门禁验证。
    
    参数:
        extra_args (list[str]): 包含 --task-id 与可选 --stage 的参数列表。
    """
    # 延迟导入连续性验证责任链管道，隔离实验性协议插件环境
    from _lib.ccp.validators.pipeline import check_continuity_gate

    # 构建专属的局部参数解析器，严格校验任务编号与目标阶段
    parser = argparse.ArgumentParser(prog="yy-flow ccp", description="上下文连续性协议门禁操作")
    parser.add_argument("--task-id", required=True, help="任务卡 ID (如 T0001)")
    parser.add_argument("--stage", default="审查中", help="目标流转阶段 (缺省为审查中)")
    args = parser.parse_args(extra_args)

    task_id = args.task_id
    stage = args.stage
    print(f"[*] 正在为任务 {task_id} 执行连续性门禁校验 (目标阶段: {stage})...")

    # 调用责任链执行阶段必填字段与未知项 (Unknowns) 的物理存在性断言
    report = check_continuity_gate(task_id, stage)
    print(f"[+] 门禁校验结果状态: {report.status}")

    # 若存在缺失必填字段，输出具体字段列表供排查
    if report.missing_fields:
        print(f"[-] 缺失必填字段: {report.missing_fields}")

    # 若存在阻断性未知项，输出警告阻断流转
    if report.blocking_unknowns:
        print(f"[!] 存在阻断未知项: {report.blocking_unknowns}")


def main():
    """
    CLI 统一门面主调度入口函数。
    
    负责解析一级子命令参数，路由分发至对应的专用处理函数，并处理帮助与异常退出。
    """
    # 当未传递任何参数时，展示全景使用说明并以成功状态退出
    if len(sys.argv) == 1:
        print_usage()
        sys.exit(0)

    # 提取目标子命令名称 (subcommand) 与后续透传参数 (extra_args)
    subcommand = sys.argv[1]
    extra_args = sys.argv[2:]

    # 拦截全局帮助标志 (-h, --help)，统一输出顶层帮助手册
    if subcommand in ["-h", "--help"]:
        print_usage()
        sys.exit(0)

    # 子命令分发路由表：通过字典映射消解多重 if-else 分支，提升分发扩展性
    handlers = {
        "task": cmd_task,
        "dispatch": cmd_dispatch,
        "kanban": cmd_kanban,
        "status": cmd_status,
        "help": cmd_help,
        "ccp": cmd_ccp,
    }

    # 根据子命令命中情况分发调用；若遇到未知子命令，提示错误并按 Unix 规范返回退出码 2
    if subcommand in handlers:
        handlers[subcommand](extra_args)
    else:
        print(f"未知子命令: {subcommand}\n")
        print_usage()
        sys.exit(2)


if __name__ == "__main__":
    main()
