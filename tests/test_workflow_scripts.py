import pytest
import sys
import os
import tempfile
from pathlib import Path

SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPT_DIR)

from build_agent_context import build_context
from generate_report import main as generate_report_main
from audit_logger import record_audit_event
from check_secrets import scan_file


def test_build_agent_context_dev_boundaries():
    """测试 build_agent_context 能准确从 boundaries 读取 max_parallel_tasks 和 can_self_claim"""
    context = build_context(role="DEV", action="claim")
    assert "- **并发上限**: 3" in context
    assert "- **允许自领取**: True" in context


def test_generate_report_main_dev():
    """测试 generate_report 脚本成功在临时目录产出 dev 任务报告"""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = os.path.join(tmpdir, "T0001_dev_report.md")
        exit_code = generate_report_main([
            "--type", "dev",
            "--task-id", "T0001",
            "--task-name", "单元测试功能",
            "--assignee", "DEV",
            "--output", output_file
        ])
        assert exit_code == 0
        assert os.path.exists(output_file)
        content = Path(output_file).read_text(encoding="utf-8")
        assert "T0001" in content


def test_audit_logger_record():
    """测试 audit_logger 记录事件不抛出异常"""
    record_audit_event("T_TEST", "DEV", "待开始", "进行中", "DEV_USER", True, "测试事件")
    log_file = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "logs", "audit_trail.log"))
    assert os.path.exists(log_file)


def test_check_secrets_clean_file():
    """测试 check_secrets 对安全代码不报错"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write("print('Hello World')\n")
        f.flush()
        findings = scan_file(f.name)
    os.unlink(f.name)
    assert len(findings) == 0


# ---------------------------------------------------------------------------
# 回归防护：generate_report.py 退出码 / 7 模板可达性 / 元数据占位符
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "workflow.config.yaml")


def _report_out(tmpdir, rtype, task_id="T0001", assignee="李开发"):
    output_file = os.path.join(tmpdir, f"{task_id}_{rtype}_report.md")
    exit_code = generate_report_main([
        "--type", rtype,
        "--task-id", task_id,
        "--task-name", "回归测试任务",
        "--assignee", assignee,
        "--output", output_file,
    ])
    return exit_code, output_file


def test_generate_report_unsupported_type_returns_nonzero():
    """不支持的 --type 必须返回非零退出码 (Fail-Closed)，不能静默成功"""
    with tempfile.TemporaryDirectory() as tmpdir:
        exit_code, _ = _report_out(tmpdir, "not_a_type")
        assert exit_code == 1


def test_generate_report_review_alias_maps_to_reviewer():
    """--type review 兼容别名应映射到 reviewer 模板并成功"""
    with tempfile.TemporaryDirectory() as tmpdir:
        exit_code, output_file = _report_out(tmpdir, "review")
        assert exit_code == 0
        assert os.path.exists(output_file)
        content = open(output_file, encoding="utf-8").read()
        assert "T0001" in content
        assert "李开发" in content


def test_generate_report_all_7_types_accessible():
    """7 大专家模板 (pm/arch/dev/reviewer/qa/docs/devops) CLI 全部可达"""
    with tempfile.TemporaryDirectory() as tmpdir:
        for rtype in ["pm", "arch", "dev", "reviewer", "qa", "docs", "devops"]:
            exit_code, output_file = _report_out(tmpdir, rtype)
            assert exit_code == 0, f"type={rtype} 应成功生成报告"
            assert os.path.exists(output_file), f"type={rtype} 报告文件应存在"


def test_generate_report_no_meta_placeholder_leftover():
    """生成的报告不应残留元数据类 ${...} 占位符"""
    with tempfile.TemporaryDirectory() as tmpdir:
        for rtype in ["dev", "qa", "docs", "reviewer"]:
            exit_code, output_file = _report_out(tmpdir, rtype)
            assert exit_code == 0
            content = open(output_file, encoding="utf-8").read()
            for ph in ["${STAGE_NAME}", "${WORKPACKAGE_NAME}", "${START_DATE}",
                       "${END_DATE}", "${QA_NAME}", "${SCENARIO_1}", "${TASK_ID}"]:
                assert ph not in content, f"type={rtype} 仍残留占位符 {ph}"


# ---------------------------------------------------------------------------
# 回归防护：transition_task.py 管道层并发上限透传
# ---------------------------------------------------------------------------

def test_transition_pipeline_concurrency_limit_reject():
    """管道层应透传 active_dev_count，DEV 并发超限时物理拦截 (不再硬编码放行)"""
    from transition_task import transition_task_pipeline
    ok = transition_task_pipeline(
        config_path=CONFIG_PATH,
        task_id="T_CONC",
        record_id="rec_concurrency_test",
        current_role="DEV",
        from_status="待开始",
        to_status="进行中",
        assignee="Dev_User_1",
        task_type="A",
        dry_run=True,
        active_dev_count=3
    )
    assert ok is False


def test_transition_pipeline_concurrency_under_limit_passes():
    """并发未超限时管道层正常放行"""
    from transition_task import transition_task_pipeline
    ok = transition_task_pipeline(
        config_path=CONFIG_PATH,
        task_id="T_CONC_OK",
        record_id="rec_concurrency_ok",
        current_role="DEV",
        from_status="待开始",
        to_status="进行中",
        assignee="Dev_User_1",
        task_type="A",
        dry_run=True,
        active_dev_count=2
    )
    assert ok is True
