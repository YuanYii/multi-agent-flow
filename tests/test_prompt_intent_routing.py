import os
import re
import json
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(REPO_ROOT, "tests/data/intent_prompt_suite.json")


def classify_user_intent(prompt: str) -> dict:
    """
    依照 SKILL.md 与 references/01-gateway/01-task_classification.md 规范实现的
    网关意图分流与分级三问决策器。
    """
    p = prompt.strip()

    # 1. 分支 A: 控制台快捷指令
    if p.startswith("/yy-flow"):
        cmd_map = {
            "/yy-flow help": "scripts/show_help.py",
            "/yy-flow status": "scripts/heartbeat.py",
            "/yy-flow kanban": "scripts/start_kanban_server.py",
            "/yy-flow sync-pr": "scripts/sync_pr_status.py",
            "/yy-flow trace": "scripts/generate_trace_html.py",
            "/yy-flow start": "scripts/init_skill.sh",
        }
        for prefix, script in cmd_map.items():
            if p.startswith(prefix):
                return {
                    "branch": "A",
                    "level": None,
                    "target": script,
                    "reason": "控制台运维与状态直通指令",
                }
        return {
            "branch": "A",
            "level": None,
            "target": "scripts/show_help.py",
            "reason": "通用控制台帮助回退",
        }

    # 2. 分支 B: 业务交互与研发需求
    # 分级三问 1: 会留下代码/文档/配置等仓库文件修改吗？
    pure_qa_prefixes = ("解释", "分析", "看看", "什么是", "查询", "为什么", "怎么理解", "帮我看看")
    imperative_mod_phrases = ["请实现", "去实现", "帮我实现", "实现一个", "去开发", "请修复", "请修改", "请重构"]

    is_pure_qa = p.startswith(pure_qa_prefixes) and not any(phrase in p for phrase in imperative_mod_phrases)

    mod_keywords = [
        "修复", "修改", "增加", "追加", "补全", "重构", "实现", "开发",
        "优化", "重写", "修正", "引入", "设计并实现"
    ]
    has_mod = any(k in p for k in mod_keywords)

    if is_pure_qa or not has_mod:
        return {
            "branch": "B",
            "level": "L0",
            "target": "direct_answer",
            "reason": "无仓库文件落盘需求，判定为 L0 即时问答",
        }

    # 分级三问 3: 需要多角色协作、修改核心业务代码或变更公共基础库吗？
    complex_l2_keywords = [
        "微服务", "彻底重构", "设计并实现", "双向实时", "CI/CD", "流水线",
        "端到端加密", "深度重构", "架构", "重写"
    ]
    is_l2 = any(k in p for k in complex_l2_keywords)

    if is_l2:
        return {
            "branch": "B",
            "level": "L2",
            "target": "scripts/auto_task.py",
            "reason": "涉及多角色协同、跨正交领域或重大架构变更，判定为 L2 标准研发任务",
        }

    return {
        "branch": "B",
        "level": "L1",
        "target": "scripts/quick_task.py",
        "reason": "单一原子改动或局部优化，判定为 L1 短链轻量任务",
    }


def test_intent_prompt_suite_accuracy():
    """验证 24 条黄金 Prompt 基准测试集的分类准确率 >= 95%"""
    assert os.path.exists(DATA_PATH), f"基准数据集不存在: {DATA_PATH}"
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        suite = json.load(f)

    assert len(suite) >= 20, f"数据集用例不足 20 条: {len(suite)}"

    passed = 0
    failures = []

    for item in suite:
        res = classify_user_intent(item["prompt"])
        branch_ok = res["branch"] == item["expected_branch"]
        level_ok = res["level"] == item["expected_level"]
        target_ok = res["target"] == item["expected_target"]

        if branch_ok and level_ok and target_ok:
            passed += 1
        else:
            failures.append({
                "id": item["id"],
                "prompt": item["prompt"],
                "expected": (item["expected_branch"], item["expected_level"], item["expected_target"]),
                "actual": (res["branch"], res["level"], res["target"]),
                "reason": res["reason"],
            })

    accuracy = passed / len(suite)
    assert accuracy >= 0.95, f"意图分类准确率未达标 ({accuracy:.2%}): {failures}"
