#!/usr/bin/env python3
"""
代码化任务派发引擎 (Dispatch Task CLI)
负责：
1. 校验前置依赖 (pretask 是否就绪)
2. 校验角色并发容量 (max_parallel_tasks <= 3)
3. 自动将任务从【待开始】推进至【进行中】(状态原子绑定)
4. 自动装配结构化 Payload v2.0 与物理文件锚点
5. 输出 invoke_subagent 兼容的参数载荷 (JSON / Prompt)
"""
import os
import sys
import json
import argparse
import glob
from typing import Dict, Any, Optional, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import paths
from enums import TaskStatus, normalize_role
from _lib.boards import board_adapter_factory
from transition_task import transition_task_pipeline

# 角色到 Antigravity Subagent TypeName 与官方名称映射
ROLE_SUBAGENT_MAP = {
    "DEV": {
        "type_name": "flow-dev",
        "role_desc": "李开发 (开发工程师)",
        "next_status": "审查中",
        "exit_role": "DEV"
    },
    "FRONTEND": {
        "type_name": "flow-frontend",
        "role_desc": "马前端 (前端开发工程师)",
        "next_status": "审查中",
        "exit_role": "FRONTEND"
    },
    "ARCHITECT": {
        "type_name": "flow-architect",
        "role_desc": "钱架构 (系统架构师)",
        "next_status": "已完成",
        "exit_role": "ARCHITECT"
    },
    "REVIEWER": {
        "type_name": "flow-reviewer",
        "role_desc": "周审查 (代码审查专家)",
        "next_status": "测试中",
        "exit_role": "REVIEWER"
    },
    "QA": {
        "type_name": "flow-qa",
        "role_desc": "章测试 (测试工程师)",
        "next_status": "已完成",
        "exit_role": "QA"
    },
    "DOCS": {
        "type_name": "flow-docs",
        "role_desc": "李文通 (文档工程师)",
        "next_status": "已完成",
        "exit_role": "DOCS"
    },
    "DEVOPS": {
        "type_name": "flow-devops",
        "role_desc": "吕改特 (运维管理员)",
        "next_status": "已完成",
        "exit_role": "DEVOPS"
    },
    "PM": {
        "type_name": "flow-pm",
        "role_desc": "严经理 (项目经理)",
        "next_status": "已完成",
        "exit_role": "PM"
    }
}


def find_related_docs(task: Dict[str, Any], project_root: str) -> List[str]:
    """智能查找与当前任务关联的架构设计或需求文档"""
    docs = []
    # 1. 扫描 docs/ 目录下的设计方案
    doc_patterns = [
        os.path.join(project_root, "docs", "**", "*.md"),
        os.path.join(project_root, "docs", "D02-架构设计", "*.md"),
        os.path.join(project_root, "docs", "1-方案设计", "*.md"),
    ]
    for pat in doc_patterns:
        for f in glob.glob(pat, recursive=True):
            rel = os.path.relpath(f, project_root)
            if rel not in docs:
                docs.append(rel)
    return docs[:5]


def dispatch_task(
    task_id: str,
    target_role: Optional[str] = None,
    config_path: Optional[str] = None,
    output_format: str = "json",
    dry_run: bool = False,
    max_parallel: int = 3
) -> Dict[str, Any]:
    # 1. 加载看板适配器并检索任务卡
    adapter = board_adapter_factory.get_board_adapter(config_path)
    if hasattr(adapter, "get_record"):
        raw_task = adapter.get_record(task_id)
    elif hasattr(adapter, "get_task"):
        raw_task = adapter.get_task(task_id)
    else:
        raw_task = None
    if not raw_task:
        raise ValueError(f"[FAIL-CLOSED] 任务卡不存在: {task_id}")

    task = raw_task.get("fields", raw_task) if isinstance(raw_task, dict) else raw_task

    current_status = task.get("status", "")
    assignee = task.get("assignee", "")
    task_name = task.get("name", "")
    target = task.get("target", "") or task_name
    criteria = task.get("acceptance_criteria") or task.get("criteria", [])
    if isinstance(criteria, str):
        criteria = [criteria]
    pretask = task.get("pretask", "无") or "无"

    # 确定目标角色
    role_code = (target_role or normalize_role(assignee) or "DEV").upper()
    subagent_info = ROLE_SUBAGENT_MAP.get(role_code, ROLE_SUBAGENT_MAP["DEV"])

    # 2. 门禁一：前置依赖门禁 (Dependency Gate)
    if pretask and pretask != "无":
        pre_ids = [p.strip() for p in pretask.replace("，", ",").split(",") if p.strip()]
        for pid in pre_ids:
            if hasattr(adapter, "get_record"):
                raw_pt = adapter.get_record(pid)
            elif hasattr(adapter, "get_task"):
                raw_pt = adapter.get_task(pid)
            else:
                raw_pt = None
            if not raw_pt:
                raise RuntimeError(f"[REJECT 依赖不存在] 前置任务 {pid} 在看板中未找到！")
            pt = raw_pt.get("fields", raw_pt) if isinstance(raw_pt, dict) else raw_pt
            p_status = pt.get("status", "")
            if p_status not in ["已完成", "已验收", "已取消"]:
                raise RuntimeError(
                    f"[REJECT 依赖未就绪] 前置任务 {pid} 当前状态为【{p_status}】，"
                    f"尚未处于【已完成】或【已验收】终态，禁止派单！"
                )

    # 3. 门禁二：并发容量感知门禁 (Concurrency Gate)
    if hasattr(adapter, "list_records"):
        raw_all_tasks = adapter.list_records(limit=1000)
    elif hasattr(adapter, "list_tasks"):
        raw_all_tasks = adapter.list_tasks()
    else:
        raw_all_tasks = []
    all_tasks = [t.get("fields", t) if isinstance(t, dict) else t for t in raw_all_tasks]
    in_progress_count = sum(
        1 for t in all_tasks
        if t.get("status") == "进行中" and normalize_role(t.get("assignee", "")).upper() == role_code
        and t.get("id") != task_id
    )
    if in_progress_count >= max_parallel:
        raise RuntimeError(
            f"[REJECT 并发超载] 角色 {role_code} ({subagent_info['role_desc']}) "
            f"当前已有 {in_progress_count} 项任务处于【进行中】（上限: {max_parallel}），禁止继续派单！"
        )

    # 4. 状态流转推进：待开始 -> 进行中
    if current_status == "待开始" and not dry_run:
        ok = transition_task_pipeline(
            config_path=config_path,
            current_role="PM",
            assignee=assignee,
            task_id=task_id,
            from_status="待开始",
            to_status="进行中",
            remarks=f"【代码化派单】PM 严经理派发任务至 {subagent_info['role_desc']}"
        )
        if not ok:
            raise RuntimeError(f"[REJECT 流转失败] 自动推进任务 {task_id} 从【待开始】到【进行中】未通过门禁！")

    # 5. 上下文与 Payload 装配
    proj_root = paths.project_root()
    related_docs = find_related_docs(task, proj_root)

    next_status = subagent_info["next_status"]
    exit_role = subagent_info["exit_role"]
    exit_cli = (
        f"python3 scripts/transition_task.py --task-id {task_id} "
        f"--role {exit_role} --from-status 进行中 --to-status {next_status} "
        f"--remarks '完成工单交付与自测通过'"
    )

    criteria_str = "\n".join([f"  - {c}" for c in criteria]) if criteria else "  - 按设计契约与单测用例准出"

    payload_json = {
        "protocol_version": "2.0",
        "task_id": task_id,
        "task_name": task_name,
        "role": role_code,
        "subagent": subagent_info["type_name"],
        "target": target,
        "acceptance_criteria": criteria,
        "context_files": related_docs,
        "exit_contract": {
            "target_status": next_status,
            "required_cli": exit_cli
        }
    }

    subagent_prompt = f"""【YY-Flow 专家工单派发指令】

你已被指派承接研发工单: [{task_id}] {task_name}
你的专家角色: {subagent_info['role_desc']} (Type: {subagent_info['type_name']})

【核心交付目标 (Target)】:
{target}

【条目化验收标准 (Acceptance Criteria)】:
{criteria_str}

【参考设计文档与上下文】:
{chr(10).join(['- ' + d for d in related_docs]) if related_docs else '- 遵循工作区既有架构与规范'}

【硬性退出契约与防错铁律】:
1. 必须在独立会话中编写实体源码并执行针对性单元测试（保持单测全部通过）；
2. 完工前必须物理执行以下 CLI 推进状态至【{next_status}】:
   `{exit_cli}`
3. 严禁在会话中仅进行口头承诺而不调用流转命令；流转成功后输出结构化成果汇报。
"""

    dispatch_result = {
        "task_id": task_id,
        "task_name": task_name,
        "role": role_code,
        "subagent_type": subagent_info["type_name"],
        "subagent_role": subagent_info["role_desc"],
        "tool_name": "invoke_subagent",
        "parameters": {
            "Subagents": [
                {
                    "TypeName": subagent_info["type_name"],
                    "Role": subagent_info["role_desc"],
                    "Model": "inherit",
                    "Workspace": "inherit",
                    "Prompt": subagent_prompt.strip()
                }
            ]
        },
        "payload": payload_json
    }

    return dispatch_result


def main():
    parser = argparse.ArgumentParser(
        prog="dispatch_task",
        description="Multi-Agent Flow 代码化任务派单引擎"
    )
    parser.add_argument("--task-id", required=True, help="待派发的任务卡编号 (如 T0001)")
    parser.add_argument("--role", default=None, help="目标执行专家角色 (DEV|FRONTEND|ARCHITECT|QA 等，缺省按卡片处理人)")
    parser.add_argument("--config", default=None, help="工作流配置文件路径")
    parser.add_argument("--format", choices=["json", "prompt", "summary"], default="json", help="输出格式")
    parser.add_argument("--dry-run", action="store_true", help="演练模式，不实际触发看板状态跃迁")
    parser.add_argument("--max-parallel", type=int, default=3, help="角色最大并行在手任务数限制")

    args = parser.parse_args()

    try:
        res = dispatch_task(
            task_id=args.task_id,
            target_role=args.role,
            config_path=args.config,
            output_format=args.format,
            dry_run=args.dry_run,
            max_parallel=args.max_parallel
        )
        if args.format == "json":
            print(json.dumps(res, ensure_ascii=False, indent=2))
        elif args.format == "prompt":
            print(res["parameters"]["Subagents"][0]["Prompt"])
        else:
            print(f"[SUCCESS] 任务 {res['task_id']} 派单载荷组装成功！")
            print(f"目标子代理: {res['subagent_role']} ({res['subagent_type']})")
            print(f"退出指令: {res['payload']['exit_contract']['required_cli']}")
    except Exception as e:
        print(f"[ERROR] 派单失败: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
