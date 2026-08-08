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
