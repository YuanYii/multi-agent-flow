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


def test_pm_cannot_directly_accept_a_type_task():
    """测试 PM 角色禁止将 A 类 (常规代码开发) 任务直接从进行中拉升至已验收"""
    res = validate(
        role="PM",
        from_status="进行中",
        to_status="已验收",
        assignee="严经理",
        end_time="2026-08-11 12:00",
        active_dev_count=1,
        task_type="A"
    )
    assert res is False


def test_reviewer_cannot_reject_to_self_assignee():
    """测试 REVIEWER / QA 打回时禁止将 Assignee 设为自身"""
    res = validate(
        role="REVIEWER",
        from_status="审查中",
        to_status="已退回",
        assignee="周审查",
        end_time="",
        active_dev_count=1,
        task_type="A"
    )
    assert res is False

    res_ok = validate(
        role="REVIEWER",
        from_status="审查中",
        to_status="已退回",
        assignee="李开发",
        end_time="",
        active_dev_count=1,
        task_type="A"
    )
    assert res_ok is True


def test_iso8601_timezone_calc_minutes():
    """测试 ISO 8601 带时区戳计算分钟差值"""
    from offline_board_adapter import OfflineBoardAdapter
    res = OfflineBoardAdapter._calc_minutes("2026-08-11T23:00:00+08:00", "2026-08-11T23:15:00+08:00")
    assert res == 15


def test_validate_delegation_direct_call():
    """测试直调 validate() 函数时，代行白名单硬拦截生效"""
    # 非法代行 (DEV 尝试代行 FRONTEND) 应该被拒绝
    res_illegal = validate(
        role="FRONTEND",
        from_status="待开始",
        to_status="进行中",
        assignee="前端开发",
        end_time="",
        active_dev_count=1,
        task_type="A",
        delegated_by="DEV",
        delegation_reason="代行前端编码"
    )
    assert res_illegal is False

    # 合法代行 (USER 授权代行 PM 验收) 应该通过
    res_legal = validate(
        role="PM",
        from_status="已完成",
        to_status="已验收",
        assignee="严经理",
        end_time="2026-08-14 12:00",
        active_dev_count=1,
        task_type="A",
        delegated_by="USER",
        delegation_reason="用户明确授权"
    )
    assert res_legal is True

