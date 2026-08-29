#!/usr/bin/env python3
"""
Multi-Agent Team Workflow (YY-Flow) - 全景指令帮助与使用手册 CLI (show_help.py)
用于在控制台或 Agent 对话中输出全量 /yy-flow 快捷指令矩阵、专家角色与流转规范。
"""
import sys
import json
import argparse


HELP_MANUAL = {
    "name": "Multi-Agent Team Workflow (YY-Flow)",
    "version": "1.0.0",
    "description": "适用于 AI 多 Agent 与人类团队协同研发的多角色状态流转、质量审计、防错闭环与看板自动化工作流技能包。",
    "slash_commands": [
        {
            "command": "/yy-flow help",
            "aliases": ["/yy-flow --help", "/yy-flow -h", "yy-flow help"],
            "title": "全景帮助手册",
            "description": "输出工作流全量快捷指令矩阵、8 大专家职责定义与协同流转说明。",
            "script": "scripts/show_help.py",
            "typical_usage": "/yy-flow help"
        },
        {
            "command": "/yy-flow start",
            "aliases": ["/yy-flow", "/yy-flow init"],
            "title": "一键激活工作流",
            "description": "自动执行初始化 7 步 SOP：凭据安全扫描、架构指纹探测、数据资产初始化、文档骨架建立、专家技术栈同步与基线工单派发。",
            "script": "scripts/init_skill.sh",
            "typical_usage": "/yy-flow start"
        },
        {
            "command": "/yy-flow status",
            "aliases": ["/yy-flow heartbeat"],
            "title": "看板全局大盘与健康巡检",
            "description": "一键输出项目完成进度、交付周期 Lead Time、专家负荷与风险阻断告警。",
            "script": "scripts/heartbeat.py",
            "typical_usage": "/yy-flow status"
        },
        {
            "command": "/yy-flow kanban",
            "aliases": ["/yy-flow board", "/yy-flow server"],
            "title": "启动 Web 可视化看板",
            "description": "启动内置可视化看板 HTTP 服务（默认 32886 端口），输出本地直达链接、局域网协作链接与 Master Token。",
            "script": "scripts/start_kanban_server.py",
            "typical_usage": "/yy-flow kanban"
        },
        {
            "command": "/yy-flow sync-pr",
            "aliases": ["/yy-flow unblock"],
            "title": "PR 状态监听与合流自动解阻",
            "description": "扫描【已阻塞】任务卡，检测 GitHub PR Merged 状态自动推进至【已完成】并提请 PM 严经理验收。",
            "script": "scripts/sync_pr_status.py",
            "typical_usage": "/yy-flow sync-pr"
        },
        {
            "command": "/yy-flow auto <需求>",
            "aliases": ["/yy-flow auto --task <需求>"],
            "title": "全自动多专家研发流水线",
            "description": "由主 Agent 串行调度多专家子代理（DEV ➔ REVIEWER ➔ QA ➔ PM）进行实体代码开发、审查与测试，在【已完成】主动停机交付。",
            "script": "scripts/auto_task.py --task \"<需求>\"",
            "typical_usage": "/yy-flow auto \"实现用户登录与鉴权接口\""
        },
    ],
    "experts": [
        {"role": "PM", "name": "严经理", "title": "项目经理", "duties": "WBS 维护、任务分级（L0/L1/L2）、并发控制、阶段结项与终态验收"},
        {"role": "ARCHITECT", "name": "钱架构", "title": "系统架构师", "duties": "系统总体架构设计、ADR 决策记录、模块边界划分与接口契约制定"},
        {"role": "DEV", "name": "李开发", "title": "开发工程师", "duties": "后端/全栈业务编码、单元测试覆盖（≥80%）、开发报告撰写与环境治理"},
        {"role": "FRONTEND", "name": "马前端", "title": "前端开发工程师", "duties": "现代 Web/UI 组件与交互开发、响应式布局、前端性能与体验优化"},
        {"role": "REVIEWER", "name": "周审查", "title": "代码审查专家", "duties": "代码规范 (Clean Code)、安全漏洞扫描、越权风险审计与结构化打回"},
        {"role": "QA", "name": "章测试", "title": "测试工程师", "duties": "端到端集成测试、边界与极限场景覆盖、缺陷复现与质量准出"},
        {"role": "DOCS", "name": "李文通", "title": "文档工程师", "duties": "工程文档架构治理、操作手册、API 文档维护与历史文档隔离归档"},
        {"role": "DEVOPS", "name": "吕改特", "title": "运维管理员", "duties": "分支模型管理、Git Pre-flight 自检、SemVer Tag 打标与发布合流治理"}
    ],
    "task_tiers": [
        {"tier": "L0 即时问答", "scope": "纯文本咨询、逻辑解释、无文件修改", "flow": "无卡直答，0 延迟响应，草稿入草稿箱"},
        {"tier": "L1 轻量任务", "scope": "单角色独立闭环（架构B/文档C/运维D/总结F/环境G）", "flow": "待开始 ➔ 进行中 ➔ 已完成 ➔ 已验收"},
        {"tier": "L2 标准研发", "scope": "业务代码变更、核心库修改、多角色协作", "flow": "待开始 ➔ 进行中 ➔ 审查中 ➔ 测试中 ➔ 已完成 ➔ 已验收"}
    ]
}


def format_text_output() -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("🚀 Multi-Agent Team Workflow (YY-Flow) · 全景指令帮助手册")
    lines.append("=" * 80)
    lines.append(f"描述: {HELP_MANUAL['description']}")
    lines.append("")
    lines.append("⚡ 【快捷唤醒指令矩阵 (Slash Commands)】")
    lines.append("-" * 80)
    for cmd in HELP_MANUAL["slash_commands"]:
        lines.append(f"• {cmd['command']:<26} | {cmd['title']}")
        lines.append(f"  说明: {cmd['description']}")
        lines.append(f"  底层: {cmd['script']}")
        lines.append("")

    lines.append("👥 【8 大专家角色协同矩阵】")
    lines.append("-" * 80)
    for exp in HELP_MANUAL["experts"]:
        lines.append(f"• @flow-{exp['role'].lower():<12} 【{exp['name']}】({exp['title']})")
        lines.append(f"  核心职责: {exp['duties']}")
    lines.append("")

    lines.append("🎯 【业务需求分级三问决策流】")
    lines.append("-" * 80)
    for t in HELP_MANUAL["task_tiers"]:
        lines.append(f"• 【{t['tier']}】: {t['scope']}")
        lines.append(f"  流转路径: {t['flow']}")
    lines.append("")

    lines.append("🛡️ 【核心协同铁律与安全防线】")
    lines.append("-" * 80)
    lines.append("1. 无工单不 Git: 任何代码/文档提交或 PR 发起内部必须有处于【进行中】的工单承载；")
    lines.append("2. 外部纯净化: Git Commit Message 与 PR 标题严禁包含内部任务编号与虚拟角色人名；")
    lines.append("3. 提 PR 挂起闭环: 创建 GitHub PR 后立即将工单推至【已阻塞】并回填 URL，接入自动解阻；")
    lines.append("4. 人类专属终态验收: 状态【已验收】严格由真实人类用户在 Web 看板或交互终端确认，严禁 Agent 私自代签。")
    lines.append("=" * 80)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Flow 全景帮助手册")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出全量元数据")
    args = parser.parse_args()

    if args.json:
        print(json.dumps(HELP_MANUAL, ensure_ascii=False, indent=2))
    else:
        print(format_text_output())


if __name__ == "__main__":
    main()
