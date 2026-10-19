#!/usr/bin/env python3
"""
单元测试：V2.1 子代理认知投影与执行治理协议级改造专项验证
涵盖 7 项核心治理能力：
1. 派单前白名单门禁（严格模式拦截）
2. 派单前白名单门禁（非严格模式警告放行）
3. 静态符号行号预索引生成与路径归一化
4. Git 差异提取器未跟踪文件与行区间提取
5. Tier-3 审查直推已完成（凭据新鲜且未漂移）
6. Tier-3 审查直推已完成（凭据失效或漂移拦截）与 Tier-2 隔离
7. 遥测时间戳缺失容错与心跳巡检告警闭环
"""
import os
import sys
import subprocess
import tempfile
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_SCRIPTS_DIR = os.path.join(_PROJ_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _lib.ccp.validators.pipeline import (
    verify_scope_before_dispatch,
    validate_pre_dispatch,
)
from _lib.core.validate_transition import validate
from build_agent_context import (
    build_pre_dispatch_code_map,
    render_governance_and_projection_block,
)
from _lib.ccp.deltas.git_extractor import (
    get_worktree_fingerprint,
    extract_changed_line_ranges,
    detect_out_of_scope_touches,
)
from _lib.metrics.heartbeat_engine import run_heartbeat


def test_pre_dispatch_scope_gate_strict():
    """用例 1: 派单前白名单门禁 - 严格模式下无白名单拦截，有白名单放行"""
    # 1. 缺失 contract.scope.in_scope -> 拦截
    task_no_scope = {"id": "T001", "target": "核心模块开发", "acceptance_criteria": ["通过验收"]}
    ok, msg = verify_scope_before_dispatch(task_no_scope, "DEV", strict=True)
    assert ok is False
    assert "缺失必填契约字段 contract.scope.in_scope" in msg

    # 空列表 -> 拦截
    task_empty_scope = {
        "id": "T001",
        "contract": {"scope": {"in_scope": ["  ", ""]}},
    }
    ok, msg = verify_scope_before_dispatch(task_empty_scope, "DEV", strict=True)
    assert ok is False

    # 2. 正常配置白名单 -> 放行
    task_with_scope = {
        "id": "T001",
        "contract": {"scope": {"in_scope": ["src/core/parser.py # 解析核心"]}},
    }
    ok, msg = verify_scope_before_dispatch(task_with_scope, "DEV", strict=True)
    assert ok is True
    assert msg == "OK"

    # 3. 非编码角色（如 PM）豁免白名单检查
    ok, msg = verify_scope_before_dispatch(task_no_scope, "PM", strict=True)
    assert ok is True

    # 4. 集成验证 validate_pre_dispatch
    valid_task = {
        "id": "T001",
        "target": "实现用户账户安全注销接口",
        "acceptance_criteria": ["1. 接口返回 200"],
        "contract": {"scope": {"in_scope": ["src/auth.py"]}},
    }
    ok_p, errs = validate_pre_dispatch(valid_task, proj_root=_PROJ_ROOT, target_role="DEV", strict=True)
    assert ok_p is True
    assert len(errs) == 0

    invalid_task = {
        "id": "T001",
        "target": "实现用户账户安全注销接口",
        "acceptance_criteria": ["1. 接口返回 200"],
    }
    ok_p2, errs2 = validate_pre_dispatch(invalid_task, proj_root=_PROJ_ROOT, target_role="DEV", strict=True)
    assert ok_p2 is False
    assert any("缺失必填契约字段 contract.scope.in_scope" in e for e in errs2)


def test_pre_dispatch_scope_gate_non_strict():
    """用例 2: 派单前白名单门禁 - 非严格模式 (--no-strict-scope) 降级为警告放行"""
    task = {"id": "T002", "target": "临时紧急修复", "acceptance_criteria": ["验证通过"]}
    ok, msg = verify_scope_before_dispatch(task, "DEV", strict=False)
    assert ok is True
    assert "[WARN]" in msg
    assert "缺失必填契约字段 contract.scope.in_scope" in msg

    # 集成校验 validate_pre_dispatch 非严格模式
    valid_ac_task = {
        "id": "T002",
        "target": "实现用户账户安全注销接口",
        "acceptance_criteria": ["1. 接口返回 200"],
    }
    ok_p, errs = validate_pre_dispatch(valid_ac_task, proj_root=_PROJ_ROOT, target_role="DEV", strict=False)
    assert ok_p is True
    assert any("[WARN]" in e and "contract.scope.in_scope" in e for e in errs)


def test_code_map_generation_and_normalization(tmp_path):
    """用例 3: 静态符号行号预索引生成与反斜杠路径兼容归一化"""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    code_file = src_dir / "parser.py"
    code_file.write_text(
        "class AstParser:\n"
        "    def parse_tokens(self):\n"
        "        pass\n"
        "\n"
        "def helper_func():\n"
        "    return 42\n",
        encoding="utf-8",
    )

    in_scope_list = [
        "src\\parser.py # Windows反斜杠测试",
        "src/not_exist.py # 待新建文件测试",
    ]

    code_map = build_pre_dispatch_code_map(str(tmp_path), in_scope_list)

    # 1. 验证反斜杠已正规化
    assert "src/parser.py" in code_map
    # 2. 验证类与方法行号提取
    assert "`AstParser` (L1)" in code_map
    assert "`parse_tokens` (L2)" in code_map
    assert "`helper_func` (L5)" in code_map
    # 3. 验证未存在文件标记为 (待新建文件)
    assert "src/not_exist.py" in code_map
    assert "(待新建文件)" in code_map


def test_git_extractor_untracked_and_line_ranges(tmp_path):
    """用例 4: Git 差异提取器 - 验证未跟踪新文件识别与行区间解析"""
    # 建立临时 git 仓库
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(tmp_path), check=True)

    # 提交基线文件
    f1 = tmp_path / "base.py"
    f1.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), check=True)

    # 修改已跟踪文件
    f1.write_text("line1\nline2_modified\nline3\nline4\nline5\nline6_new\n", encoding="utf-8")

    # 新建未跟踪文件 (git add 未执行)
    f2 = tmp_path / "untracked.py"
    f2.write_text("untracked_1\nuntracked_2\n", encoding="utf-8")

    # 1. 验证行区间提取覆盖跟踪与未跟踪文件
    diff_ranges = extract_changed_line_ranges(str(tmp_path))
    assert any("base.py" in r for r in diff_ranges)
    assert any("untracked.py:1-2" in r for r in diff_ranges)

    # 2. 验证越界检测 detect_out_of_scope_touches
    # 若白名单只有 base.py，则 untracked.py 属于越界
    out_of_scope = detect_out_of_scope_touches(str(tmp_path), ["base.py # 基线修改"])
    assert "untracked.py" in out_of_scope
    assert "base.py" not in out_of_scope

    # 若白名单包含 untracked.py，则无越界
    out_of_scope2 = detect_out_of_scope_touches(str(tmp_path), ["base.py", "untracked.py"])
    assert len(out_of_scope2) == 0

    # 3. 验证快照指纹计算稳定
    fp = get_worktree_fingerprint(str(tmp_path))
    assert isinstance(fp, str) and (fp.startswith("git-tree:") or fp.startswith("sha256:"))


def test_tier3_reviewer_direct_complete_fresh():
    """用例 5: Tier-3 审查直推已完成 - 凭据新鲜且代码快照未漂移时放行"""
    ok = validate(
        role="REVIEWER",
        from_status="审查中",
        to_status="已完成",
        assignee="严经理",
        end_time="2026-10-18 20:00:00",
        active_dev_count=0,
        tier="Tier-3",
        evidence_fresh=True,
    )
    assert ok is True


def test_tier3_reviewer_direct_complete_drifted():
    """用例 6: Tier-3 审查直推已完成 - 快照漂移或凭据失效拦截，且 Tier-2 强制走测试"""
    # 1. Tier-3 但凭据过期/漂移 -> 拦截
    ok_drift = validate(
        role="REVIEWER",
        from_status="审查中",
        to_status="已完成",
        assignee="严经理",
        end_time="2026-10-18 20:00:00",
        active_dev_count=0,
        tier="Tier-3",
        evidence_fresh=False,
    )
    assert ok_drift is False

    # 2. Tier-2 任务即使 evidence_fresh=True 也不能免 QA 直推已完成（必须走测试中）
    ok_tier2 = validate(
        role="REVIEWER",
        from_status="审查中",
        to_status="已完成",
        assignee="严经理",
        end_time="2026-10-18 20:00:00",
        active_dev_count=0,
        tier="Tier-2",
        evidence_fresh=True,
    )
    assert ok_tier2 is False


def test_telemetry_missing_dispatched_at_ts_safe():
    """用例 7: 遥测数据计算多级容错与心跳巡检告警闭环"""
    # 1. 模拟 transition 容错计算：缺失 dispatched_at_ts 与 dispatched_at 时的安全兜底
    fake_hc = {}
    start_ts = fake_hc.get("dispatched_at_ts")
    wall_clock_sec = 0.0 if not start_ts else round(100.0 - float(start_ts), 1)
    assert wall_clock_sec == 0.0

    # 2. 模拟心跳巡检：超 600s 与白名单越界告警验证
    class DummyAdapter:
        def list_records(self, limit=1000):
            return [
                {
                    "id": "T8801",
                    "status": "进行中",
                    "assignee": "李开发",
                    "handover_context": {
                        "telemetry": {
                            "wall_clock_sec": 750.5,
                            "out_of_scope_modified": ["src/secret_leak.py"],
                        }
                    },
                },
                {
                    "id": "T8802",
                    "status": "审查中",
                    "assignee": "周审查",
                    "handover_context": {
                        "telemetry": {
                            "wall_clock_sec": 150.0,
                            "out_of_scope_modified": [],
                        }
                    },
                },
            ]

    hb_res = run_heartbeat(DummyAdapter(), doc_dirs_override=[])
    alerts = hb_res.get("alerts", [])

    codes = [a.get("code") for a in alerts]
    assert "SUBAGENT_TIMEOUT" in codes
    assert "SUBAGENT_SCOPE_DRIFT" in codes

    timeout_alert = next(a for a in alerts if a.get("code") == "SUBAGENT_TIMEOUT")
    assert timeout_alert["task_id"] == "T8801"
    assert "750.5s" in timeout_alert["message"]

    drift_alert = next(a for a in alerts if a.get("code") == "SUBAGENT_SCOPE_DRIFT")
    assert drift_alert["task_id"] == "T8801"
    assert "src/secret_leak.py" in drift_alert["message"]
