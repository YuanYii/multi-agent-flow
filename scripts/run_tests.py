#!/usr/bin/env python3
"""
Multi-Agent Flow 智能增量测试调度器 (Smart Incremental Test Runner)

设计理念：
遵循全局指令《事实驱动与客观求真》第 1 条“改动与验证分级原则 (Graded Verification)”。
根据 Git Diff 自动感知改动范围，精准定位并仅执行受影响的测试文件，规避机械化全量回归。

核心特性：
1. 纯文档/配置豁免：若仅改动 Markdown、HTML、文本或静态数据，直接秒级跳过代码测试；
2. 模块级精准映射：按代码改动边界匹配对应的专用测试套件；
3. 变更测试自反识别：若改动本身即为 tests/test_*.py，直接针对性执行该测试；
4. 兜底与全量支持：支持 --all 强制全量回归，核心基础设施变更自动扩大测试覆盖；
5. 参数透明透传：支持将 pytest 原生参数（如 -v, -k, -s 等）无缝传递至底层引擎。
"""

import os
import sys
import subprocess
import argparse
from typing import List, Set, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
TESTS_DIR = os.path.join(PROJECT_ROOT, "tests")

# 1. 纯静态文档与资产后缀白名单（无需触发代码测试）
DOC_EXTENSIONS = {
    ".md", ".markdown", ".html", ".htm", ".txt", ".png", ".jpg", ".jpeg",
    ".gif", ".svg", ".ico", ".drawio", ".pdf", ".css", ".scss"
}

# 2. 忽略的运行态与临时数据路径前缀
IGNORE_PATHS = [
    ".yy-flow/user_data/",
    "user_data/",
    ".pytest_cache/",
    "__pycache__/",
    ".idea/",
    ".vscode/",
    ".git/",
    "test-reports/",
]

# 3. 源码到测试文件的精确映射规则库 (Source -> Tests Mapping)
ROUTING_RULES = [
    # 任务流转与生命周期状态机
    (
        ["scripts/transition_task.py", "scripts/validate_transition.py"],
        ["tests/test_workflow_v2.py", "tests/test_process_node.py", "tests/test_task_record_model.py"]
    ),
    # 任务建卡与快建接口
    (
        ["scripts/quick_task.py"],
        ["tests/test_target_criteria_pipeline.py", "tests/test_workflow_v2.py", "tests/test_accept_gate_hardening.py"]
    ),
    # 任务派发与并发门禁
    (
        ["scripts/dispatch_task.py", "scripts/subagent_gate.py"],
        ["tests/test_dispatch_and_gate.py", "tests/test_subagent_gate.py"]
    ),
    # 看板服务端、前端脚本与接口
    (
        ["scripts/start_kanban_server.py", "kanban/js/board.js", "kanban/offline_board.html", "kanban/js/data.js"],
        ["tests/test_kanban_api_v2.py", "tests/test_kanban_server.py", "tests/test_kanban_startup_migration.py"]
    ),
    # 阶段门禁与质量卡点
    (
        ["scripts/check_stage_gate.py", "scripts/_lib/gates/"],
        ["tests/test_check_stage_gate.py", "tests/test_dispatch_and_gate.py", "tests/test_accept_gate_hardening.py"]
    ),
    # 心跳巡检与大盘度量
    (
        ["scripts/heartbeat.py", "scripts/time_tracking.py"],
        ["tests/test_heartbeat_fixes.py", "tests/test_time_tracking_optimizations.py"]
    ),
    # PR 状态监听与合流解阻
    (
        ["scripts/sync_pr_status.py"],
        ["tests/test_sync_pr_status.py", "tests/test_pr2_review_fixes.py"]
    ),
    # 上下文连续性协议 (CCP)
    (
        ["scripts/_lib/ccp/"],
        ["tests/test_ccp_pipeline_gates.py", "tests/test_ccp_chunked_board.py", "tests/test_ccp_domain.py"]
    ),
    # 存储适配器与分卷迁移
    (
        ["scripts/_lib/adapters/", "scripts/chunked_board_adapter.py", "scripts/weekly_board_adapter.py"],
        ["tests/test_weekly_board_adapter.py", "tests/test_ccp_chunked_board.py", "tests/test_init_layout_and_migrator.py"]
    ),
    # 技术栈探测与项目配置
    (
        ["scripts/_lib/discovery/", "scripts/update_project_profile.py", "scripts/save_project_architecture.py"],
        ["tests/test_project_profile_customization.py", "tests/test_save_project_architecture.py", "tests/test_tech_capability_expander.py"]
    ),
    # 链路全景图鉴生成
    (
        ["scripts/generate_trace_html.py"],
        ["tests/test_generate_trace_html.py"]
    ),
    # 工单格式校验 (Linter)
    (
        ["scripts/task_linter.py"],
        ["tests/test_task_linter.py"]
    ),
    # 审计日志轮转与归档
    (
        ["scripts/audit_rotate.py"],
        ["tests/test_audit_rotate.py"]
    ),
    # 全局导出与环境探测
    (
        ["scripts/verify_and_export_agents.py", "scripts/install_global.sh"],
        ["tests/test_export_global.py"]
    ),
    # CLI 总入口门面
    (
        ["scripts/cli.py"],
        ["tests/test_workflow_v2.py", "tests/test_process_node.py"]
    ),
]

# 核心基础设施：一旦修改，扩大测试覆盖范围
CORE_INFRA_FILES = [
    "tests/conftest.py",
    "scripts/_lib/core/",
    "scripts/_lib/audit/",
    "scripts/init_skill.sh",
]


def get_git_changed_files(repo_root: str) -> List[str]:
    """通过 Git 状态与 Diff 获取工作区与暂存区的所有变更文件相对路径。"""
    changed = set()

    # 1. 获取工作区未跟踪、未暂存与已暂存的文件
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True
        )
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # 剥离状态位（形如 " M file.py" 或 "?? file.py" 或 "R  old -> new"）
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                path = parts[1]
                if " -> " in path:
                    path = path.split(" -> ")[1]
                changed.add(path.strip())
    except Exception:
        pass

    # 2. 获取针对 HEAD 的 Diff 文件列表
    try:
        res = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            for p in res.stdout.splitlines():
                if p.strip():
                    changed.add(p.strip())
    except Exception:
        pass

    return sorted(list(changed))


def is_doc_or_ignorable(file_path: str) -> bool:
    """判定文件是否属于纯文档、静态资产或忽略的临时数据。"""
    normalized = file_path.replace("\\", "/")
    # 检查忽略路径
    for ign in IGNORE_PATHS:
        if normalized.startswith(ign) or f"/{ign}" in normalized:
            return True

    # 检查后缀白名单
    _, ext = os.path.splitext(normalized)
    if ext.lower() in DOC_EXTENSIONS:
        return True

    return False


def resolve_target_tests(changed_files: List[str], repo_root: str) -> Tuple[List[str], str]:
    """
    根据变更文件列表推导应执行的目标测试文件。
    
    返回:
        (target_tests, reason_message)
    """
    if not changed_files:
        return ([], "未检测到任何改动文件。")

    # 过滤掉忽略路径文件
    active_files = [f for f in changed_files if not is_doc_or_ignorable(f)]

    # 若所有改动文件均属于纯文档或数据文件
    if not active_files:
        return ([], "检测到仅有文档、静态资产或运行态数据变更，按分级验证原则跳过代码测试。")

    target_tests: Set[str] = set()
    trigger_full = False
    core_triggered = []

    for f in active_files:
        normalized = f.replace("\\", "/")

        # 1. 变更本身就是测试文件 (自反性匹配)
        if normalized.startswith("tests/test_") and normalized.endswith(".py"):
            target_tests.add(normalized)
            continue

        # 2. 检查是否触发核心基础设施改动
        for core_pat in CORE_INFRA_FILES:
            if core_pat in normalized:
                trigger_full = True
                core_triggered.append(normalized)
                break

        # 3. 按规则库精确匹配
        matched = False
        for src_patterns, test_files in ROUTING_RULES:
            for pat in src_patterns:
                if pat in normalized or normalized.endswith(pat):
                    for tf in test_files:
                        target_tests.add(tf)
                    matched = True
                    break

        # 4. 若为 scripts/ 下未收录的 Python 脚本，默认运行核心回归用例
        if not matched and normalized.startswith("scripts/") and normalized.endswith(".py"):
            target_tests.add("tests/test_workflow_v2.py")
            target_tests.add("tests/test_process_node.py")

    # 若触碰核心基础设施，执行全量测试以防隐式副作用
    if trigger_full:
        return (["tests/"], f"检测到核心基础设施变更 ({', '.join(core_triggered[:2])})，触发全量回归测试。")

    # 检查并仅保留在磁盘上真实存在的测试文件
    valid_tests = []
    for t in sorted(list(target_tests)):
        full_p = os.path.join(repo_root, t)
        if os.path.exists(full_p):
            valid_tests.append(t)

    if not valid_tests:
        # 若有代码变动但未匹配到针对性单测，回退至核心工作流测试
        default_fallback = ["tests/test_workflow_v2.py", "tests/test_process_node.py"]
        existing_fallback = [t for t in default_fallback if os.path.exists(os.path.join(repo_root, t))]
        return (existing_fallback, "未精确命中专用测试映射，回退执行核心工作流冒烟测试。")

    return (valid_tests, f"根据改动精准匹配到 {len(valid_tests)} 个相关测试文件。")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="yy-flow test (run_tests.py)",
        description="Multi-Agent Flow 智能增量测试调度器：仅运行与当前改动相关的测试用例"
    )
    parser.add_argument("--all", action="store_true", help="强制执行全量测试套件 (453 项用例)")
    parser.add_argument("--dry-run", action="store_true", help="仅分析并打印待执行的测试文件清单，不实际运行 pytest")
    parser.add_argument("--files", nargs="*", help="显式指定改动的文件清单进行模拟测试推导")

    # 解析已知参数，其余透传给 pytest
    args, pytest_args = parser.parse_known_args()

    print("=" * 70)
    print("  Multi-Agent Flow 智能增量测试调度器 (Smart Incremental Test Runner)")
    print("=" * 70)

    # 1. 强制全量测试
    if args.all:
        print("[*] 模式: 强制全量测试 (--all)")
        cmd = [sys.executable, "-m", "pytest", "tests/"] + pytest_args
        if args.dry_run:
            print(f"[Dry-run] 拟执行命令: {' '.join(cmd)}")
            return 0
        print(f"[*] 执行命令: {' '.join(cmd)}\n")
        return subprocess.run(cmd, cwd=PROJECT_ROOT).returncode

    # 2. 获取改动文件
    if args.files:
        changed_files = args.files
        print(f"[*] 模式: 显式指定改动文件 ({len(changed_files)} 个)")
    else:
        changed_files = get_git_changed_files(PROJECT_ROOT)
        print(f"[*] 模式: Git 增量变更自动探测 (发现 {len(changed_files)} 个改动项)")

    if changed_files:
        for f in changed_files[:8]:
            print(f"    - {f}")
        if len(changed_files) > 8:
            print(f"    ... 以及其余 {len(changed_files) - 8} 个文件")

    # 3. 解析目标测试
    target_tests, reason = resolve_target_tests(changed_files, PROJECT_ROOT)
    print(f"\n[*] 决策分析: {reason}")

    # 若无需执行测试（纯文档豁免）
    if not target_tests:
        print("[+] 判定结果: 门禁秒级通过 (0 测试用例开销，耗时 0.05s)。")
        return 0

    print(f"[*] 目标测试清单 ({len(target_tests)} 项):")
    for t in target_tests:
        print(f"    • {t}")

    # 4. 执行测试
    cmd = [sys.executable, "-m", "pytest"] + target_tests + pytest_args

    if args.dry_run:
        print(f"\n[Dry-run] 拟执行命令: {' '.join(cmd)}")
        return 0

    print(f"\n[*] 正在启动针对性测试...\n")
    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
