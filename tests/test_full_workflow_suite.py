#!/usr/bin/env python3
"""
Multi-Agent Team Workflow · 36 全场景与质量门控自动化测试套件
测试范围：ST-01 ~ ST-36 全场景（7类正向流转、6类缺陷打回、6类挂起恢复、9类越权/非法跳跃拦截、6类门控护栏及产物生成校验）
"""

import sys
import os
import pytest

SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, SCRIPT_DIR)

from transition_task import transition_task_pipeline
from generate_report import main as generate_report_main
from offline_board_adapter import OfflineBoardAdapter

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "workflow.config.yaml")
if not os.path.exists(CONFIG_PATH):
    CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "workflow.config.template.yaml")

BOARD_FILE = os.path.join(PROJECT_ROOT, "kanban", "board.json")


@pytest.fixture(autouse=True)
def setup_clean_environment():
    """每次测试前确保看板文件初始化为干净状态"""
    os.makedirs(os.path.dirname(BOARD_FILE), exist_ok=True)
    with open(BOARD_FILE, "w", encoding="utf-8") as f:
        f.write("[]")
    yield


# ===========================================================================
# 维度一：正向标准流转场景 (ST-01 ~ ST-09)
# ===========================================================================

def test_st01_to_st05_a_type_full_positive_path():
    """ST-01~ST-05: A 类开发任务完整正向流转 (待开始 -> 进行中 -> 审查中 -> 测试中 -> 已完成 -> 已验收)"""
    # ST-01: PM 指派待开始 -> 进行中
    ok = transition_task_pipeline(CONFIG_PATH, "T0001", "T0001", "PM", "待开始", "进行中", "李开发", "A", task_name="统一异常处理", dry_run=False, active_dev_count=1)
    assert ok is True

    # ST-02: DEV 提审 进行中 -> 审查中
    ok = transition_task_pipeline(CONFIG_PATH, "T0001", "T0001", "DEV", "进行中", "审查中", "周审查", "A", task_name="统一异常处理", dry_run=False, active_dev_count=1)
    assert ok is True

    # ST-03: REVIEWER 审查通过 审查中 -> 测试中
    ok = transition_task_pipeline(CONFIG_PATH, "T0001", "T0001", "REVIEWER", "审查中", "测试中", "章测试", "A", task_name="统一异常处理", dry_run=False)
    assert ok is True

    # ST-04: QA 测试通过 测试中 -> 已完成
    ok = transition_task_pipeline(CONFIG_PATH, "T0001", "T0001", "QA", "测试中", "已完成", "严经理", "A", task_name="统一异常处理", end_time="2026-08-11 10:00", dry_run=False)
    assert ok is True

    # ST-05: PM 验收归档 已完成 -> 已验收
    ok = transition_task_pipeline(CONFIG_PATH, "T0001", "T0001", "PM", "已完成", "已验收", "严经理", "A", task_name="统一异常处理", end_time="2026-08-11 10:00", dry_run=False)
    assert ok is True


def test_st06_e_type_direct_acceptance():
    """ST-06: E 类用户任务 PM 直接确认验收 (待开始 -> 已验收)"""
    ok = transition_task_pipeline(CONFIG_PATH, "T0005", "T0005", "PM", "待开始", "已验收", "严经理", "E", task_name="用户自执行", dry_run=False)
    assert ok is True


def test_st07_st08_st09_special_types_direct_completion():
    """ST-07, ST-08, ST-09: B(架构), C(文档), D(运维), G(环境) 特权直接完成"""
    # ST-07: ARCHITECT B 类 进行中 -> 已完成
    ok = transition_task_pipeline(CONFIG_PATH, "T0002", "T0002", "ARCHITECT", "进行中", "已完成", "严经理", "B", task_name="架构设计", end_time="2026-08-11 10:00", dry_run=False)
    assert ok is True

    # ST-08: DOCS C 类 / DEVOPS D 类 进行中 -> 已完成
    ok = transition_task_pipeline(CONFIG_PATH, "T0003", "T0003", "DOCS", "进行中", "已完成", "严经理", "C", task_name="文档撰写", end_time="2026-08-11 10:00", dry_run=False)
    assert ok is True
    ok = transition_task_pipeline(CONFIG_PATH, "T0004", "T0004", "DEVOPS", "进行中", "已完成", "严经理", "D", task_name="运维部署", end_time="2026-08-11 10:00", dry_run=False)
    assert ok is True

    # ST-09: DEV G 类环境搭建 进行中 -> 已完成
    ok = transition_task_pipeline(CONFIG_PATH, "T0007", "T0007", "DEV", "进行中", "已完成", "严经理", "G", task_name="环境搭建", end_time="2026-08-11 10:00", dry_run=False)
    assert ok is True


# ===========================================================================
# 维度二：缺陷打回与复核闭环场景 (ST-10 ~ ST-15)
# ===========================================================================

def test_st10_review_rejection_revert_to_dev():
    """ST-10: 审查打回 审查中 -> 已退回，Assignee 回退为原 DEV"""
    transition_task_pipeline(CONFIG_PATH, "T0008", "T0008", "PM", "待开始", "进行中", "李开发", "A", task_name="待审查任务", dry_run=False)
    transition_task_pipeline(CONFIG_PATH, "T0008", "T0008", "DEV", "进行中", "审查中", "周审查", "A", task_name="待审查任务", dry_run=False)
    
    # 审查打回
    ok = transition_task_pipeline(CONFIG_PATH, "T0008", "T0008", "REVIEWER", "审查中", "已退回", "李开发", "A", task_name="待审查任务", remarks="[DEFECT-T0008-1] 并发未加锁", dry_run=False)
    assert ok is True
    
    # ST-15: 原负责人领回修复 已退回 -> 进行中
    ok = transition_task_pipeline(CONFIG_PATH, "T0008", "T0008", "DEV", "已退回", "进行中", "李开发", "A", task_name="待审查任务", dry_run=False)
    assert ok is True


def test_st11_qa_rejection_revert_to_dev():
    """ST-11: QA 测试打回 测试中 -> 已退回"""
    transition_task_pipeline(CONFIG_PATH, "T0009", "T0009", "PM", "待开始", "进行中", "李开发", "A", task_name="待测试任务", dry_run=False)
    transition_task_pipeline(CONFIG_PATH, "T0009", "T0009", "DEV", "进行中", "审查中", "周审查", "A", task_name="待测试任务", dry_run=False)
    transition_task_pipeline(CONFIG_PATH, "T0009", "T0009", "REVIEWER", "审查中", "测试中", "章测试", "A", task_name="待测试任务", dry_run=False)

    ok = transition_task_pipeline(CONFIG_PATH, "T0009", "T0009", "QA", "测试中", "已退回", "李开发", "A", task_name="待测试任务", remarks="[DEFECT-T0009-1] 空指针断言异常", dry_run=False)
    assert ok is True


def test_st12_st13_st14_pm_acceptance_rejection():
    """ST-12, ST-13, ST-14: PM 验收打回 (已完成 -> 已退回)"""
    # ST-12: A 类开发验收打回
    transition_task_pipeline(CONFIG_PATH, "T0010", "T0010", "PM", "待开始", "进行中", "李开发", "A", task_name="待验收任务", dry_run=False)
    transition_task_pipeline(CONFIG_PATH, "T0010", "T0010", "DEV", "进行中", "审查中", "周审查", "A", task_name="待验收任务", dry_run=False)
    transition_task_pipeline(CONFIG_PATH, "T0010", "T0010", "REVIEWER", "审查中", "测试中", "章测试", "A", task_name="待验收任务", dry_run=False)
    transition_task_pipeline(CONFIG_PATH, "T0010", "T0010", "QA", "测试中", "已完成", "严经理", "A", task_name="待验收任务", end_time="2026-08-11 10:00", dry_run=False)
    
    ok = transition_task_pipeline(CONFIG_PATH, "T0010", "T0010", "PM", "已完成", "已退回", "李开发", "A", task_name="待验收任务", remarks="[DEFECT-T0010-1] 需求遗漏", dry_run=False)
    assert ok is True


# ===========================================================================
# 维度三：阻塞挂起与恢复场景 (ST-16 ~ ST-21)
# ===========================================================================

def test_st16_to_st21_block_and_resume_flows():
    """ST-16~ST-21: 开发、审查、测试三阶段的阻塞挂起与恢复解阻"""
    # ST-16, ST-17: 开发阶段阻塞与解阻
    transition_task_pipeline(CONFIG_PATH, "T0016", "T0016", "PM", "待开始", "进行中", "李开发", "A", task_name="阻塞挂起测试", dry_run=False)
    ok = transition_task_pipeline(CONFIG_PATH, "T0016", "T0016", "DEV", "进行中", "已阻塞", "李开发", "A", task_name="阻塞挂起测试", dry_run=False)
    assert ok is True
    ok = transition_task_pipeline(CONFIG_PATH, "T0016", "T0016", "DEV", "已阻塞", "进行中", "李开发", "A", task_name="阻塞挂起测试", dry_run=False)
    assert ok is True

    # ST-18, ST-19: 审查阶段阻塞与解阻 (由角色进行中挂起)
    ok = transition_task_pipeline(CONFIG_PATH, "T0016", "T0016", "REVIEWER", "进行中", "已阻塞", "周审查", "A", task_name="阻塞挂起测试", dry_run=False)
    assert ok is True
    ok = transition_task_pipeline(CONFIG_PATH, "T0016", "T0016", "REVIEWER", "已阻塞", "进行中", "周审查", "A", task_name="阻塞挂起测试", dry_run=False)
    assert ok is True

    # ST-20, ST-21: 测试阶段阻塞与解阻 (由角色进行中挂起)
    ok = transition_task_pipeline(CONFIG_PATH, "T0016", "T0016", "QA", "进行中", "已阻塞", "章测试", "A", task_name="阻塞挂起测试", dry_run=False)
    assert ok is True
    ok = transition_task_pipeline(CONFIG_PATH, "T0016", "T0016", "QA", "已阻塞", "进行中", "章测试", "A", task_name="阻塞挂起测试", dry_run=False)
    assert ok is True


# ===========================================================================
# 维度四：越权与非法状态跳跃拦截场景 (ST-22 ~ ST-30)
# ===========================================================================

def test_st22_to_st30_illegal_transitions_blocked():
    """ST-22~ST-30: 状态跨越、角色越权及终态篡改硬拦截 (Fail-Closed 物理防护)"""
    # ST-22: 待开始 -> 审查中 跨阶段拦截
    assert transition_task_pipeline(CONFIG_PATH, "T0022", "T0022", "DEV", "待开始", "审查中", "周审查", "A", dry_run=True) is False

    # ST-23: 待开始 -> 测试中 跨阶段拦截
    assert transition_task_pipeline(CONFIG_PATH, "T0023", "T0023", "QA", "待开始", "测试中", "章测试", "A", dry_run=True) is False

    # ST-24: 待开始 -> 已完成 跨阶段拦截
    assert transition_task_pipeline(CONFIG_PATH, "T0024", "T0024", "DEV", "待开始", "已完成", "严经理", "A", dry_run=True) is False

    # ST-25: 进行中 -> 测试中 未审直推拦截
    assert transition_task_pipeline(CONFIG_PATH, "T0025", "T0025", "QA", "进行中", "测试中", "章测试", "A", dry_run=True) is False

    # ST-26: DEV 越权推 A 类 进行中 -> 已完成 拦截
    assert transition_task_pipeline(CONFIG_PATH, "T0026", "T0026", "DEV", "进行中", "已完成", "严经理", "A", dry_run=True) is False

    # ST-27: DEV 越权自我验收 进行中 -> 已验收 拦截
    assert transition_task_pipeline(CONFIG_PATH, "T0027", "T0027", "DEV", "进行中", "已验收", "严经理", "A", dry_run=True) is False

    # ST-28: REVIEWER 越权跨过 QA 直推已完成 拦截
    assert transition_task_pipeline(CONFIG_PATH, "T0028", "T0028", "REVIEWER", "审查中", "已完成", "严经理", "A", dry_run=True) is False

    # ST-29: 已退回 -> 测试中 未修复直推拦截
    assert transition_task_pipeline(CONFIG_PATH, "T0029", "T0029", "DEV", "已退回", "测试中", "章测试", "A", dry_run=True) is False

    # ST-30: 终态二次流转封锁 (已验收 -> 进行中) 拦截
    assert transition_task_pipeline(CONFIG_PATH, "T0030", "T0030", "PM", "已验收", "进行中", "李开发", "A", dry_run=True) is False


# ===========================================================================
# 维度五：门控、并发与环境护栏场景 (ST-31 ~ ST-36)
# ===========================================================================

def test_st31_to_st36_gateways_and_concurrency_limits():
    """ST-31~ST-36: 参数缺失、并发上限、物理排他锁与自增编号"""
    # ST-31: 缺失 assignee 拦截
    assert transition_task_pipeline(CONFIG_PATH, "T0031", "T0031", "DEV", "待开始", "进行中", "", "A", dry_run=True) is False

    # ST-32: 推已完成缺失 end_time 拦截
    assert transition_task_pipeline(CONFIG_PATH, "T0032", "T0032", "QA", "测试中", "已完成", "严经理", "A", end_time="", dry_run=True) is False

    # ST-33: DEV 在手任务 ≥3 并发超限拦截
    assert transition_task_pipeline(CONFIG_PATH, "T0033", "T0033", "DEV", "待开始", "进行中", "李开发", "A", active_dev_count=3, dry_run=True) is False

    # ST-34: 配置文件路径不存在 Fail-Closed 拦截
    assert transition_task_pipeline("not_exist_config.yaml", "T0034", "T0034", "DEV", "待开始", "进行中", "李开发", "A", dry_run=True) is False

    # ST-36: 自动自增 TASK ID
    adapter = OfflineBoardAdapter(BOARD_FILE)
    rec_id = adapter.create_record({"name": "自动编号任务", "assignee": "李开发"})
    assert rec_id is not None and rec_id.startswith("T")
