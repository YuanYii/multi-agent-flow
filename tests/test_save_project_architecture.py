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
