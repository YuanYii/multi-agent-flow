"""
Domain Packages 结构与 Facade 门面一致性正交测试 (tests/test_domain_packages.py)
验证 7 大领域子包与对应 CLI 门面的符号导出一致性、API 契约与 Fail-Closed 防护。
"""
import os
import sys
import pytest

# 1. 质量门控域 (_lib/gates)
from _lib.gates.stage_gate_checker import (
    CheckResult,
    StageGateReport,
    StageContext,
    run_stage_gate_check,
    format_terminal_report,
)
from _lib.gates.git_gate_verifier import verify_git_gate
from _lib.gates.secrets_checker import SECRET_PATTERNS, scan_file, run_secrets_scan
from _lib.gates.hooks_installer import install_hooks

# 2. 效能度量域 (_lib/metrics)
from _lib.metrics.metrics_calculator import parse_datetime, MetricsCalculator, TerminalRenderer
from _lib.metrics.heartbeat_engine import DEFAULT_THRESHOLDS, run_heartbeat, format_progress_bar

# 3. 架构嗅探域 (_lib/discovery)
from _lib.discovery.stack_scanner import scan_project_stack
from _lib.discovery.arch_persister import clean_list, validate_schema, save_architecture_config
from _lib.discovery.field_mapper import discover_feishu_fields

# 4. 文档治理域 (_lib/docs)
from _lib.docs.legacy_migrator import EXCLUDE_DIRS, CATEGORY_KEYWORDS, classify_document, scan_and_migrate_legacy_docs

# 5. 打包导出域 (_lib/export)
from _lib.export.qwen_packager import validate_icon, validate_manifest, package_plugin

# 门面 CLI 模块
import check_stage_gate
import verify_git_gate as cli_verify_git_gate
import check_secrets
import heartbeat
import metrics_analyzer
import auto_scan_stack
import save_project_architecture
import migrate_legacy_docs
import package_qwen_plugin
import install_git_hooks


class TestDomainPackagesIntegrity:
    """验证子包与顶层门面之间的符号一致性与契约兼容"""

    def test_gates_facade_reexport_integrity(self):
        """验证 gates 域的门面脚本完整重导出了核心检查器与流水线函数"""
        assert check_stage_gate.run_stage_gate_check is run_stage_gate_check
        assert check_stage_gate.CheckResult is CheckResult
        assert check_stage_gate.StageGateReport is StageGateReport
        assert check_stage_gate.format_terminal_report is format_terminal_report
        assert cli_verify_git_gate.verify_git_gate is verify_git_gate
        assert check_secrets.scan_file is scan_file
        assert check_secrets.SECRET_PATTERNS is SECRET_PATTERNS
        assert install_git_hooks.install_hooks is install_hooks

    def test_metrics_facade_reexport_integrity(self):
        """验证 metrics 域的门面脚本完整重导出了计算器与大盘巡检函数"""
        assert metrics_analyzer.MetricsCalculator is MetricsCalculator
        assert metrics_analyzer.parse_datetime is parse_datetime
        assert metrics_analyzer.TerminalRenderer is TerminalRenderer
        assert heartbeat.run_heartbeat is run_heartbeat
        assert heartbeat.format_progress_bar is format_progress_bar
        assert heartbeat.DEFAULT_THRESHOLDS == DEFAULT_THRESHOLDS

    def test_discovery_facade_reexport_integrity(self):
        """验证 discovery 域的门面脚本完整重导出了架构探测与持久化函数"""
        assert auto_scan_stack.scan_project_stack is scan_project_stack
        assert save_project_architecture.save_architecture_config is save_architecture_config
        assert save_project_architecture.validate_schema is validate_schema
        assert save_project_architecture.clean_list is clean_list

    def test_docs_and_export_facade_reexport_integrity(self):
        """验证 docs 与 export 域的门面脚本完整重导出了迁移与打包函数"""
        assert migrate_legacy_docs.classify_document is classify_document
        assert migrate_legacy_docs.scan_and_migrate_legacy_docs is scan_and_migrate_legacy_docs
        assert package_qwen_plugin.validate_icon is validate_icon
        assert package_qwen_plugin.validate_manifest is validate_manifest
        assert package_qwen_plugin.package_plugin is package_plugin


class TestDomainLogicUnits:
    """针对新子包内核心算法与业务逻辑的轻量单测"""

    def test_clean_list_parsing(self):
        """验证 clean_list 对不同输入的清洗与规范化"""
        assert clean_list("Python, FastAPI， Vue.js") == ["Python", "FastAPI", "Vue.js"]
        assert clean_list([{"name": "SQLite"}, "FastAPI", ""]) == ["SQLite", "FastAPI"]
        assert clean_list(None) == []

    def test_legacy_docs_classification(self, tmp_path):
        """验证历史文档基于路径与文件名的智能分类权重"""
        pm_doc = tmp_path / "my_project_charter.md"
        pm_doc.write_text("# 项目章程\n需求规格说明书", encoding="utf-8")
        assert classify_document(str(pm_doc)) == "D01-项目管理"

        arch_doc = tmp_path / "system_architecture_design.md"
        arch_doc.write_text("# 架构设计方案", encoding="utf-8")
        assert classify_document(str(arch_doc)) == "D02-架构设计"

    def test_secrets_pattern_detection(self):
        """验证敏感凭据扫描正则能够有效捕获常见 Token"""
        fake_feishu_token = "cli_a1b2c3d4e5f6g7h8"
        findings = []
        for pattern, desc in SECRET_PATTERNS:
            if pattern.search(fake_feishu_token):
                findings.append(desc)
        assert "飞书 App ID / Token" in findings

    def test_resolve_default_stage_wp_wbs_spec(self):
        """验证用户未指定阶段/工作包/WBS编号时，自动继承最新阶段并生成三段式标准编号"""
        from _lib.core.task_spec import resolve_default_stage_wp_wbs

        # 1. 空看板时：默认使用 S1 阶段与 1.1.1 编号
        stg, wp, wbs = resolve_default_stage_wp_wbs([])
        assert "S1" in stg
        assert wp == "WP-S1-01 常规研发工作包"
        assert wbs == "1.1.1"

        # 2. 已有 S1 和 S2 任务时：自动继承最新阶段 S2，并自增 WBS 编号
        cards = [
            {"id": "T0001", "stage": "S1 需求分析", "wp": "WP-1.1", "wbs": "1.1.1"},
            {"id": "T0002", "stage": "S2 核心研发", "wp": "WP-S2-01", "wbs": "2.1.1"},
        ]
        stg, wp, wbs = resolve_default_stage_wp_wbs(cards)
        assert "S2" in stg
        assert wp == "WP-S2-01 常规研发工作包"
        assert wbs == "2.1.2"

        # 3. 用户显式指定部分字段时：仅对缺省字段进行推导
        stg, wp, wbs = resolve_default_stage_wp_wbs(cards, stage="S3 系统测试")
        assert stg == "S3 系统测试"
        assert wp == "WP-S3-01 常规研发工作包"
        assert wbs == "3.1.1"

