#!/usr/bin/env python3
"""
专家技术能力拓展引擎单测 (tests/test_tech_capability_expander.py)
验证 Python/FastAPI/Agno/Milvus, Node/React, Go 以及通用 fallback 场景下
6 大角色技术能力拓展的准确性与 3~5 项弹性约束。
"""

import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(_TESTS_DIR)
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

import pytest
from scripts._lib.core.tech_capability_expander import expand_expert_capabilities


def test_expand_capabilities_python_fullstack():
    arch_data = {
        "project": {"name": "xskill", "app_type": "fullstack"},
        "tech_stack": {
            "languages": [{"name": "Python", "version": "3.11"}],
            "backend_frameworks": ["FastAPI", "Agno", "Pydantic"],
            "frontend_frameworks": ["Vanilla JavaScript / HTML5 / CSS3"],
            "testing": {"framework": "pytest-bdd", "testing_frameworks": ["pytest", "pytest-bdd", "mutmut"]},
            "databases_and_storage": [{"name": "Milvus Lite"}, {"name": "SQLite (WAL)"}, {"name": "Rank-BM25"}],
            "security_and_sandbox": [{"name": "detect-secrets"}, {"name": "dulwich"}],
        },
        "deployment_and_ci": {"containerized": False, "ci_cd_provider": "GitHub Actions"}
    }

    caps = expand_expert_capabilities(arch_data)
    assert "dev" in caps
    assert "frontend" in caps
    assert "reviewer" in caps
    assert "qa" in caps
    assert "architect" in caps
    assert "devops" in caps

    # 验证条数在 3~5 之间
    for role, role_caps in caps.items():
        assert 3 <= len(role_caps) <= 5, f"Role {role} caps count {len(role_caps)} not in [3, 5]"

    # 验证李开发专精能力
    dev_str = " ".join(caps["dev"])
    assert "FastAPI" in dev_str or "asyncio" in dev_str or "SSE" in dev_str
    assert "SQLite" in dev_str or "WAL" in dev_str
    assert "Pydantic" in dev_str or "Agno" in dev_str

    # 验证马前端专精能力（不含后端 Pydantic）
    fe_str = " ".join(caps["frontend"])
    assert "Pydantic" not in fe_str
    assert "i18n" in fe_str or "DOM" in fe_str or "CSS" in fe_str

    # 验证周审查安全能力
    rev_str = " ".join(caps["reviewer"])
    assert "detect-secrets" in rev_str or "隐私" in rev_str or "凭据" in rev_str

    # 验证章测试 BDD & 变异测试能力
    qa_str = " ".join(caps["qa"])
    assert "pytest-bdd" in qa_str or "BDD" in qa_str
    assert "mutmut" in qa_str or "变异" in qa_str


def test_expand_capabilities_go_microservice():
    arch_data = {
        "project": {"name": "go-order-service", "app_type": "microservice"},
        "tech_stack": {
            "languages": [{"name": "Go", "version": "1.22"}],
            "backend_frameworks": ["Gin"],
            "testing": {"framework": "go test"},
            "databases_and_storage": [{"name": "PostgreSQL"}, {"name": "Redis"}],
        },
        "deployment_and_ci": {"containerized": True, "ci_cd_provider": "GitHub Actions"}
    }

    caps = expand_expert_capabilities(arch_data)
    assert 3 <= len(caps["dev"]) <= 5
    dev_str = " ".join(caps["dev"])
    assert "Goroutine" in dev_str or "Channel" in dev_str or "逃逸分析" in dev_str

    qa_str = " ".join(caps["qa"])
    assert "Table-Driven" in qa_str or "Race" in qa_str

    devops_str = " ".join(caps["devops"])
    assert "Docker Sandbox" in devops_str or "容器化" in devops_str


def test_expand_capabilities_fallback():
    arch_data = {
        "project": {"name": "unknown-app"},
        "tech_stack": {"languages": [{"name": "Rust"}]}
    }
    caps = expand_expert_capabilities(arch_data)
    assert "dev" in caps
    assert len(caps["dev"]) >= 3
