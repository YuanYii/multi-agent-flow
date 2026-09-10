#!/usr/bin/env python3
"""
单元测试：CCP V2.0 确定性门禁责任链 (Pre-Dispatch Gate & Pre-Review Gate)
覆盖派单准入门禁（前置断言探测、目标与AC健全性、Tier分级）及提审准出门禁（Git差异白名单、结案回执四件套、P5-1自测凭据与AC逐条映射）。
"""
import os
import sys
import tempfile
import shutil
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_SCRIPTS_DIR = os.path.join(_PROJ_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _lib.ccp.validators.pipeline import (
    validate_pre_dispatch,
    validate_pre_review,
    ContinuityValidationPipeline,
    check_continuity_gate
)
from _lib.ccp.models import HandoffContext


@pytest.fixture
def temp_project_env():
    td = tempfile.mkdtemp(prefix="test_ccp_gates_")
    # 创建模拟源码目录
    os.makedirs(os.path.join(td, "app", "api", "v1"), exist_ok=True)
    os.makedirs(os.path.join(td, "app", "models"), exist_ok=True)
    os.makedirs(os.path.join(td, "docs", "D04-研发过程", "D02-报告", "dev"), exist_ok=True)

    # 写入测试基础文件
    user_model = os.path.join(td, "app", "models", "user.py")
    with open(user_model, "w", encoding="utf-8") as f:
        f.write("class User:\n    id = 1\n    is_active = True\n")

    yield td
    shutil.rmtree(td, ignore_errors=True)


def test_pre_dispatch_target_and_criteria_validation(temp_project_env):
    """场景1：派单准入门禁 - target 长度与验收标准必填拦截"""
    root = temp_project_env

    # target 过短 (<5 字符)
    task_short_target = {
        "target": "修复",
        "acceptance_criteria": ["1. 修复已知缺陷"]
    }
    ok, errors = validate_pre_dispatch(task_short_target, proj_root=root)
    assert ok is False
    assert any("目标描述过短" in e for e in errors)

    # acceptance_criteria 为空
    task_no_ac = {
        "target": "实现用户账户安全注销接口",
        "acceptance_criteria": []
    }
    ok2, errors2 = validate_pre_dispatch(task_no_ac, proj_root=root)
    assert ok2 is False
    assert any("缺少验收标准" in e for e in errors2)

    # 合格基础字段
    task_valid = {
        "target": "实现用户账户安全注销接口",
        "acceptance_criteria": ["1. 调用注销返回200", "2. 单元测试全部通过"]
    }
    ok3, errors3 = validate_pre_dispatch(task_valid, proj_root=root)
    assert ok3 is True
    assert len(errors3) == 0


def test_pre_dispatch_preconditions_probe(temp_project_env):
    """场景2：派单准入门禁 - 前置断言 (Preconditions) 静态扫描"""
    root = temp_project_env

    # 1. 前置断言依赖文件真实存在，字段也存在 -> 通过
    task_ok = {
        "target": "实现注销逻辑并软删除用户",
        "acceptance_criteria": ["1. 状态置为 false"],
        "contract": {
            "preconditions": [
                "app/models/user.py 已存在 is_active 字段",
            ],
            "scope": {"in_scope": ["app/api/v1/user.py"]}
        }
    }
    ok, errors = validate_pre_dispatch(task_ok, proj_root=root)
    assert ok is True

    # 2. 声明了不存在的文件 -> 拦截
    task_bad_file = {
        "target": "实现注销逻辑并软删除用户",
        "acceptance_criteria": ["1. 状态置为 false"],
        "contract": {
            "preconditions": [
                "app/models/non_existent.py 已存在 is_active 字段",
            ],
            "scope": {"in_scope": ["app/api/v1/user.py"]}
        }
    }
    ok_bf, errors_bf = validate_pre_dispatch(task_bad_file, proj_root=root)
    assert ok_bf is False
    assert any("未检索到物理文件" in e for e in errors_bf)

    # 3. 文件存在但声明的字段不存在 -> 拦截
    task_bad_field = {
        "target": "实现注销逻辑并软删除用户",
        "acceptance_criteria": ["1. 状态置为 false"],
        "contract": {
            "preconditions": [
                "app/models/user.py 已存在 non_existent_column 字段",
            ],
            "scope": {"in_scope": ["app/api/v1/user.py"]}
        }
    }
    ok_field, errors_field = validate_pre_dispatch(task_bad_field, proj_root=root)
    assert ok_field is False
    assert any("未检索到该定义" in e for e in errors_field)


def test_pre_review_tier3_fast_path(temp_project_env):
    """场景3：提审准出门禁 - Tier-3 轻量任务走快速放行通道"""
    root = temp_project_env
    task_t3 = {
        "tier": "Tier-3",
        "target": "修复 README 文字错别字",
        "acceptance_criteria": ["1. 错别字订正"]
    }
    ok, errors = validate_pre_review(task_t3, proj_root=root)
    assert ok is True
    assert len(errors) == 0


def test_pre_review_return_contract_and_p5_1_validation(temp_project_env):
    """场景4：提审准出门禁 - 结案回执四件套与 P5-1 自测凭据校验"""
    root = temp_project_env
    report_rel_path = "docs/D04-研发过程/D02-报告/dev/DEV_T0001_Report.md"
    abs_report = os.path.join(root, report_rel_path)

    # 1. 报告文件缺失 -> 拦截
    task_missing_report = {
        "tier": "Tier-1",
        "target": "核心模块研发",
        "return_contract": {"report_path": report_rel_path}
    }
    ok1, errors1 = validate_pre_review(task_missing_report, proj_root=root)
    assert ok1 is False
    assert any("未找到物理文件" in e for e in errors1)

    # 2. 报告存在但缺少四件套标头 -> 拦截
    with open(abs_report, "w", encoding="utf-8") as f:
        f.write("# 简易汇报\n我完成了所有的任务，代码写好了。\n")

    ok2, errors2 = validate_pre_review(task_missing_report, proj_root=root)
    assert ok2 is False
    assert any("缺少以下标准四件套小节" in e for e in errors2)

    # 3. 报告包含四件套标头但缺少 P5-1 测试凭据 (口头交卷) -> 拦截
    with open(abs_report, "w", encoding="utf-8") as f:
        f.write("""# 任务交付回执报告 [T0001]
## 一、 变更文件清单与 Diff 摘要
- app/api/v1/user.py

## 二、 自动化测试结果凭据
单测写好了，感觉没问题。

## 三、 与契约的偏离点及原因说明
无偏离

## 四、 遗留问题与决策项
无
""")

    ok3, errors3 = validate_pre_review(task_missing_report, proj_root=root)
    assert ok3 is False
    assert any("P5-1 自测凭据缺失" in e for e in errors3)

    # 4. 报告包含完整四件套、P5-1 用例数/通过数凭据与 AC 映射 -> 通过
    with open(abs_report, "w", encoding="utf-8") as f:
        f.write("""# 任务交付回执报告 [T0001]
## 一、 变更文件清单与 Diff 摘要
- `app/api/v1/user.py`: 新增 endpoint

## 二、 自动化测试结果凭据
- 验收项逐条映射:
  * [x] AC-1: 调用注销成功
  * [x] AC-2: Redis 会话清理
- 新增用例数: 3
- 通过用例数: 3
- 回归结论: Exit Code: 0, 396 passed

## 三、 与契约的偏离点及原因说明
无偏离

## 四、 遗留问题与决策项
无阻断项
""")

    ok4, errors4 = validate_pre_review(task_missing_report, proj_root=root)
    assert ok4 is True
    assert len(errors4) == 0


def test_continuity_validation_pipeline_backward_compat():
    """场景5：CCP V1.0 管道与 check_continuity_gate 向后兼容性"""
    pipeline = ContinuityValidationPipeline()
    handoff = HandoffContext(
        handoff_id="H-01",
        task_id="T0001",
        parent_agent="PM",
        child_agent="DEV",
        snapshot_id="S-01",
        base_version=1,
        payload={"task_id": "T0001", "name": "Task 1"},
        must_know=["task_id", "name"]
    )
    report = pipeline.validate(handoff)
    assert report.status == "READY"
    assert report.test_results["task_id"] == "PASS"

    gate_rep = check_continuity_gate("T0001", "进行中")
    assert gate_rep.status == "READY"


def test_pre_dispatch_dict_preconditions(temp_project_env):
    """场景6：派单准入门禁 - 结构化字典型 preconditions (files_required & fields_required)"""
    root = temp_project_env

    # 1. 字典形式且依赖文件与字段均存在 -> 通过
    task_dict_ok = {
        "target": "实现注销功能逻辑并测试",
        "acceptance_criteria": ["1. 注销成功"],
        "contract": {
            "scope": {"in_scope": ["app/api/v1/user.py"]},
            "preconditions": {
                "files_required": ["app/models/user.py"],
                "fields_required": ["is_active"]
            }
        }
    }
    ok1, errs1 = validate_pre_dispatch(task_dict_ok, proj_root=root)
    assert ok1 is True
    assert len(errs1) == 0

    # 2. 依赖字段不存在 -> 拦截
    task_dict_bad_field = {
        "target": "实现注销功能逻辑并测试",
        "acceptance_criteria": ["1. 注销成功"],
        "contract": {
            "scope": {"in_scope": ["app/api/v1/user.py"]},
            "preconditions": {
                "files_required": ["app/models/user.py"],
                "fields_required": ["non_existent_column_xyz"]
            }
        }
    }
    ok2, errs2 = validate_pre_dispatch(task_dict_bad_field, proj_root=root)
    assert ok2 is False
    assert any("未检索到" in e for e in errs2)


def test_pre_review_out_of_scope_redline(temp_project_env):
    """场景7：提审准出门禁 - 触犯 scope.out_of_scope 禁区硬拦截"""
    root = temp_project_env
    task_scope = {
        "tier": "Tier-1",
        "target": "核心模块研发",
        "contract": {
            "scope": {
                "in_scope": ["app/api/v1/user.py"],
                "out_of_scope": ["app/models/user.py (核心模型不可改)"]
            }
        },
        "return_contract": {
            "report_path": "docs/D04-研发过程/D02-报告/dev/DEV_T0001_Report.md"
        }
    }

    # 模拟报告存在且合规
    rep_path = os.path.join(root, "docs", "D04-研发过程", "D02-报告", "dev", "DEV_T0001_Report.md")
    with open(rep_path, "w", encoding="utf-8") as f:
        f.write("""# 任务交付回执报告 [T0001]
## 一、 变更文件清单与 Diff 摘要
- app/api/v1/user.py
## 二、 自动化测试结果凭据
- 验收项逐条映射:
  * [x] AC-1: 通过
- 新增用例数: 1, 通过用例数: 1, Exit Code: 0
## 三、 与契约的偏离点及原因说明
无
## 四、 遗留问题与决策项
无
""")

    # 正常无 Git diff 越界场景通过
    ok, errs = validate_pre_review(task_scope, proj_root=root)
    assert ok is True


def test_pre_review_structured_inline_pass_without_physical_report(temp_project_env):
    """场景8：提审准出门禁 - 免物理 Markdown 报告，仅凭工单结构化自测凭据通过"""
    root = temp_project_env
    task_no_file_but_has_summary = {
        "tier": "Tier-1",
        "target": "重构订单状态计算服务",
        "return_contract": {
            "test_summary": {
                "exit_code": 0,
                "total": 5,
                "passed": 5
            }
        },
        "remarks": "单测全部通过 (Exit Code 0)，用例覆盖边界条件"
    }

    ok, errs = validate_pre_review(task_no_file_but_has_summary, proj_root=root)
    assert ok is True
    assert len(errs) == 0


def test_pre_review_tier2_elastic_gate(temp_project_env):
    """场景9：提审准出门禁 - Tier-2 局部优化任务免物理报告直接放行"""
    root = temp_project_env
    task_t2 = {
        "tier": "Tier-2",
        "target": "优化缓存并发读取性能",
        "contract": {
            "scope": {
                "in_scope": ["app/api/v1/user.py"]
            }
        },
        "remarks": "单测通过 (Exit Code 0)"
    }

    ok, errs = validate_pre_review(task_t2, proj_root=root)
    assert ok is True
    assert len(errs) == 0

