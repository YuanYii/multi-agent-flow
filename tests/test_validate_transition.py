import pytest
import sys
import os

SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPT_DIR)

from validate_transition import validate


def test_dev_a_type_cannot_directly_complete():
    """测试 A 类 (常规代码开发) 任务中，DEV 直接推向已完成将被绝对硬拦截"""
    res = validate(
        role="DEV",
        from_status="进行中",
        to_status="已完成",
        assignee="DEV",
        end_time="2026-08-08 12:00",
        active_dev_count=1,
        task_type="A"
    )
    assert res is False


def test_dev_g_type_can_directly_complete():
    """测试 G 类 (环境搭建) 任务中，DEV 允许直接推向已完成"""
    res = validate(
        role="DEV",
        from_status="进行中",
        to_status="已完成",
        assignee="DEV",
        end_time="2026-08-08 12:00",
        active_dev_count=1,
        task_type="G"
    )
    assert res is True


def test_dev_concurrent_limit_exceeded():
    """测试 DEV 角色在进行中任务数 >= 3 时，自领取被硬拦截"""
    res = validate(
        role="DEV",
        from_status="待开始",
        to_status="进行中",
        assignee="DEV",
        end_time="",
        active_dev_count=3,
        task_type="A"
    )
    assert res is False


def test_end_time_required_for_completion():
    """测试推动至终态已完成时，缺少 end_time 必须被硬拦截"""
    res = validate(
        role="QA",
        from_status="测试中",
        to_status="已完成",
        assignee="PM",
        end_time="",
        active_dev_count=1,
        task_type="A"
    )
    assert res is False


def test_e_type_exempt_end_time():
    """测试 E 类 (用户自执行) 任务推送至已验收时，豁免 end_time 强校验"""
    res = validate(
        role="PM",
        from_status="待开始",
        to_status="已验收",
        assignee="PM",
        end_time="",
        active_dev_count=1,
        task_type="E"
    )
    assert res is True


def test_f_type_pm_complete():
    """测试 F 类 (阶段总结) 任务，允许 PM 从进行中推至已完成"""
    res = validate(
        role="PM",
        from_status="进行中",
        to_status="已完成",
        assignee="PM",
        end_time="2026-08-08 12:00",
        active_dev_count=1,
        task_type="F"
    )
    assert res is True


def test_assignee_required_for_transition():
    """测试未指定 Assignee 时触发原子更新拦截"""
    res = validate(
        role="DEV",
        from_status="待开始",
        to_status="进行中",
        assignee="",
        end_time="",
        active_dev_count=1,
        task_type="A"
    )
    assert res is False
