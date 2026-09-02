"""
CCP 领域核心模型、JSON 存储与门禁管道专项单元测试 (tests/test_ccp_domain.py)
"""
import pytest
import os
import json
from _lib.ccp.models import (
    ContextState,
    RequirementsSlice,
    HandoffContext,
    ValidationReport,
)
from _lib.ccp.stores.json_store import JsonFileContextStore, sanitize_task_id
from _lib.ccp.validators.pipeline import ContinuityValidationPipeline, check_continuity_gate
from _lib.ccp.deltas.git_extractor import GitWorkspaceDeltaExtractor
from _lib.ccp.telemetry.profiler import CcpTelemetryProfiler


class TestCcpModels:
    def test_context_state_serialization(self):
        """测试 ContextState 序列化与反序列化对称性"""
        state = ContextState(task_id="TASK-1024", version=3)
        state.requirements.functional.append({"id": "REQ-01", "desc": "创建订单"})
        state.invariants.rules.append({"rule": "订单状态单调递增", "severity": "critical"})
        
        data = state.to_dict()
        assert data["task_id"] == "TASK-1024"
        assert data["version"] == 3
        assert len(data["requirements"]["functional"]) == 1
        assert len(data["invariants"]["rules"]) == 1

        restored = ContextState.from_dict(data)
        assert restored.task_id == "TASK-1024"
        assert restored.requirements.functional[0]["id"] == "REQ-01"
        assert restored.invariants.rules[0]["severity"] == "critical"


class TestCcpJsonStore:
    def test_sanitize_task_id(self):
        """测试 Task ID 安全过滤，防止非法字符"""
        assert sanitize_task_id("T001/sub_01") == "T001_sub_01"
        assert sanitize_task_id("T-1024:dev") == "T-1024_dev"
        assert sanitize_task_id("") == "DEFAULT"

    def test_cas_version_control(self, tmp_path, monkeypatch):
        """测试 JsonFileContextStore 基于版本号的 CAS 乐观锁防覆写"""
        monkeypatch.setattr("paths.data_root", lambda: str(tmp_path))
        store = JsonFileContextStore()

        state = ContextState(task_id="T001", version=1)
        # 初始保存 expected_version = 0 -> 写入后版本应为 1
        assert store.save_with_cas("T001", state, expected_version=0) is True
        
        loaded = store.load("T001")
        assert loaded is not None
        assert loaded.version == 1

        # 并发冲突测试：使用过期的 expected_version=0 写入 -> 必须返回 False
        state.requirements.functional.append({"desc": "并发修改"})
        assert store.save_with_cas("T001", state, expected_version=0) is False

        # 正确版本 expected_version=1 -> 必须成功并递增至 2
        assert store.save_with_cas("T001", state, expected_version=1) is True
        assert store.load("T001").version == 2

    def test_snapshot_creation(self, tmp_path, monkeypatch):
        """测试快照归档生成"""
        monkeypatch.setattr("paths.data_root", lambda: str(tmp_path))
        store = JsonFileContextStore()

        state = ContextState(task_id="T002", version=1)
        store.save_with_cas("T002", state, expected_version=0)

        snapshot_id = store.create_snapshot("T002")
        assert "CTX-SNAP-T002-v1" in snapshot_id
        
        snap_file = os.path.join(str(tmp_path), "user_data", "context", "snapshots", f"{snapshot_id}.json")
        assert os.path.isfile(snap_file)


class TestContinuityPipeline:
    def test_pipeline_validation_statuses(self):
        """测试连续性门禁的 READY / INCOMPLETE / AMBIGUOUS 状态判定"""
        pipeline = ContinuityValidationPipeline()
        
        # 缺少必填字段 -> INCOMPLETE
        handoff_incomplete = HandoffContext(
            handoff_id="H01", task_id="T001", parent_agent="PM", child_agent="DEV",
            snapshot_id="SNAP1", base_version=1,
            payload={"objective": "实现订单"},
            must_know=["objective", "scope"]  # 缺少 scope
        )
        report = pipeline.validate(handoff_incomplete)
        assert report.status == "INCOMPLETE"
        assert "scope" in report.missing_fields

        # 存在阻塞性 Unknown -> AMBIGUOUS
        handoff_ambiguous = HandoffContext(
            handoff_id="H02", task_id="T001", parent_agent="PM", child_agent="DEV",
            snapshot_id="SNAP1", base_version=1,
            payload={
                "objective": "实现订单",
                "scope": ["OrderService"],
                "unknowns": [{"question": "超时策略尚未确定", "blocking": True}]
            },
            must_know=["objective", "scope"]
        )
        report_ambiguous = pipeline.validate(handoff_ambiguous)
        assert report_ambiguous.status == "AMBIGUOUS"
        assert len(report_ambiguous.blocking_unknowns) == 1

        # 完整无阻塞 -> READY
        handoff_ready = HandoffContext(
            handoff_id="H03", task_id="T001", parent_agent="PM", child_agent="DEV",
            snapshot_id="SNAP1", base_version=1,
            payload={"objective": "实现订单", "scope": ["OrderService"]},
            must_know=["objective", "scope"]
        )
        assert pipeline.validate(handoff_ready).status == "READY"

    def test_check_continuity_gate_helper(self):
        """测试快速状态机预检辅助函数"""
        report = check_continuity_gate("T100", "审查中")
        assert report.status == "READY"


class TestGitExtractor:
    def test_non_git_dir_graceful_fallback(self, tmp_path):
        """测试非 Git 目录下优雅降级，不抛出崩溃异常"""
        extractor = GitWorkspaceDeltaExtractor()
        res = extractor.extract_physical(str(tmp_path))
        assert res["files_modified"] == []
        assert res["lines_added"] == 0
        assert res["lines_deleted"] == 0


class TestTelemetryProfiler:
    def test_profiler_output(self):
        """测试审计分析器报告生成"""
        profiler = CcpTelemetryProfiler(trace_id="TR-001", task_id="T1024")
        entry = profiler.generate_audit_entry(
            parent_snapshot_id="SNAP-1",
            result_snapshot_id="SNAP-2",
            verification_status="READY",
            projected_tokens=1200
        )
        assert entry["trace_id"] == "TR-001"
        assert entry["verification_status"] == "READY"
        assert entry["projected_tokens"] == 1200
        assert "duration_sec" in entry
