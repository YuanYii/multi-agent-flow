import os
import pytest
from scripts.check_static_consistency import StaticConsistencyChecker, REPO_ROOT


def test_gate1_static_consistency_all_pass():
    """验证 Gate 1 静态 Schema 与双轨一致性门禁检查项全部通过。"""
    checker = StaticConsistencyChecker(REPO_ROOT)
    result = checker.run_all()
    assert result["passed"] is True, f"发现静态一致性违规项: {result['violations']}"
    assert result["violations_count"] == 0
    assert result["total_items_checked"] > 20
