#!/usr/bin/env python3
"""
架构配置安全定版与 Fail-Closed 断言测试 (tests/test_save_project_architecture.py)
"""

import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(_TESTS_DIR)
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

import yaml
import pytest
from scripts.save_project_architecture import save_architecture_config, validate_schema


def test_validate_schema_valid():
    valid_data = {
        "project": {"name": "test-app", "version": "1.0.0", "app_type": "fullstack"},
        "tech_stack": {
            "languages": [{"name": "Python", "version": "3.12"}],
            "backend_frameworks": ["FastAPI"],
            "frontend_frameworks": ["Vue.js"],
            "testing": {"framework": "pytest", "min_coverage_percent": 80}
        },
        "architecture_overview": {
            "pattern": "Modular Monolith",
            "entry_points": ["main.py"],
            "core_directories": {"src": "source code"}
        }
    }
    assert validate_schema(valid_data) is True


def test_validate_schema_missing_required():
    invalid_data = {
        "project": {"name": "test-app"},
    }
    assert validate_schema(invalid_data) is False


def test_save_architecture_config_and_assertions(tmp_path, monkeypatch):
    test_user_data = tmp_path / "user_data"
    test_user_data.mkdir()
    
    # 模拟 paths
    monkeypatch.setenv("YY_FLOW_PROJECT_ROOT", str(tmp_path))
    
    arch_data = {
        "project": {"name": "sample-project", "version": "0.1.0", "app_type": "fullstack"},
        "tech_stack": {
            "languages": [{"name": "Python", "version": "latest"}],
            "backend_frameworks": ["FastAPI", "Agno"],
            "frontend_frameworks": ["Vanilla JavaScript / HTML5 / CSS3"],
            "testing": {"framework": "pytest", "min_coverage_percent": 85},
            "databases_and_storage": [{"name": "SQLite (WAL)"}]
        },
        "architecture_overview": {
            "pattern": "Modular Monolith",
            "entry_points": ["src/main.py"],
            "core_directories": {"src": "Core modules"}
        }
    }
    
    success = save_architecture_config(arch_data)
    assert success is True
    
    # 验证文件物理生成且 meta.initialized == True
    config_file = test_user_data / "project_architecture.config.yaml"
    assert config_file.exists()
    
    with open(config_file, "r", encoding="utf-8") as f:
        saved = yaml.safe_load(f)
    assert saved["meta"]["initialized"] is True
    assert "expert_capabilities" in saved["tech_stack"]
    assert "dev" in saved["tech_stack"]["expert_capabilities"]


def test_save_architecture_config_force_recalc(tmp_path, monkeypatch):
    """P2-2 验证：force_recalc=True 强制丢弃旧 expert_capabilities 并重新推导计算。"""
    test_user_data = tmp_path / "user_data"
    test_user_data.mkdir()
    monkeypatch.setenv("YY_FLOW_PROJECT_ROOT", str(tmp_path))

    old_stale_caps = {
        "dev": ["陈旧的历史能力1", "陈旧的历史能力2", "陈旧的历史能力3"],
        "frontend": ["旧前端1", "旧前端2", "旧前端3"],
        "reviewer": ["旧审查1", "旧审查2", "旧审查3"],
        "qa": ["旧测试1", "旧测试2", "旧测试3"],
        "architect": ["旧架构1", "旧架构2", "旧架构3"],
        "devops": ["旧运维1", "旧运维2", "旧运维3"]
    }
    arch_data = {
        "project": {"name": "recalc-project", "version": "1.0.0", "app_type": "fullstack"},
        "tech_stack": {
            "languages": [{"name": "Java"}],
            "backend_frameworks": ["Spring Boot"],
            "testing": {"framework": "JUnit 5"},
            "expert_capabilities": old_stale_caps
        },
        "architecture_overview": {
            "pattern": "Modular Monolith",
            "entry_points": ["Application.java"],
            "core_directories": {"src": "source code"}
        }
    }

    # 1. 默认不加 force_recalc 时，直通保留 old_stale_caps
    save_architecture_config(arch_data, skip_export=True, force_recalc=False)
    config_file = test_user_data / "project_architecture.config.yaml"
    with open(config_file, "r", encoding="utf-8") as f:
        saved1 = yaml.safe_load(f)
    assert saved1["tech_stack"]["expert_capabilities"]["dev"] == ["陈旧的历史能力1", "陈旧的历史能力2", "陈旧的历史能力3"]

    # 2. 携带 force_recalc=True 时，强制丢弃并根据当前 Java + Spring Boot 重算
    save_architecture_config(arch_data, skip_export=True, force_recalc=True)
    with open(config_file, "r", encoding="utf-8") as f:
        saved2 = yaml.safe_load(f)
    dev_caps = saved2["tech_stack"]["expert_capabilities"]["dev"]
    assert "陈旧的历史能力1" not in dev_caps
    assert any("Spring Boot" in c for c in dev_caps)

