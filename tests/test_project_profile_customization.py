"""
项目路径自定义 (docs_dir) 与技术栈全自动静默采纳 (策略 B) 单元测试
"""
import os
import sys
import tempfile
import pytest
import yaml

SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPT_DIR)

import paths
from _lib.core.agent_tech_overlay import interpolate_custom_paths, apply_tech_stack_to_role
from update_project_profile import merge_detected_tech_stack, update_docs_directory


def test_docs_root_default():
    """测试默认文档路径为 project_root/docs"""
    d_root = paths.docs_root()
    assert d_root.endswith("docs")
    assert paths.custom_docs_name() == "docs"


def test_docs_root_custom_kwargs():
    """测试传参自定义 docs_dir 优先级"""
    custom = paths.docs_root(docs_dir="project_wiki")
    assert custom.endswith("project_wiki")
    assert paths.custom_docs_name(docs_dir="project_wiki") == "project_wiki"


def test_interpolate_custom_paths():
    """测试覆盖层路径动态插值渲染"""
    # 1. 默认 docs: 保持原样不替换
    sample = {
        "responsibilities": ["查验 docs/D03-业务模块/ 契约"],
        "orchestration_rules": ["归档到 docs/草稿箱/", "无相关 docs 目录的文本"]
    }
    unchanged = interpolate_custom_paths(sample, "docs")
    assert unchanged["responsibilities"][0] == "查验 docs/D03-业务模块/ 契约"

    # 2. 自定义路径 documentation: 动态替换
    replaced = interpolate_custom_paths(sample, "documentation")
    assert replaced["responsibilities"][0] == "查验 documentation/D03-业务模块/ 契约"
    assert replaced["orchestration_rules"][0] == "归档到 documentation/草稿箱/"
    assert replaced["orchestration_rules"][1] == "无相关 docs 目录的文本"


def test_strategy_b_incremental_merge():
    """测试策略 B：执行态新识别技术栈的增量静默合并 (Merge Patch)"""
    arch_data = {
        "project": {"name": "TestApp", "version": "1.0.0"},
        "tech_stack": {
            "languages": [{"name": "Python"}],
            "backend_frameworks": ["FastAPI"],
            "frontend_frameworks": [],
            "databases_and_storage": ["SQLite"]
        }
    }

    detected = {
        "project_name": "TestApp",
        "languages": ["Python", "Go"],
        "backend_frameworks": ["FastAPI", "Gin"],
        "frontend_frameworks": ["Vue.js"],
        "storage": ["SQLite", "PostgreSQL", "Redis"],
        "testing_framework": "pytest"
    }

    added = merge_detected_tech_stack(arch_data, detected, silent=True)

    # 验证新探测到的项已增量合入，未覆盖旧项
    tech = arch_data["tech_stack"]
    assert "Go" in added
    assert "Gin" in added
    assert "Vue.js" in added
    assert "PostgreSQL" in added
    assert "Redis" in added

    # 验证最终技术列表包含既有与新增项
    lang_names = [l if isinstance(l, str) else l.get("name") for l in tech["languages"]]
    assert "Python" in lang_names
    assert "Go" in lang_names

    assert "FastAPI" in tech["backend_frameworks"]
    assert "Gin" in tech["backend_frameworks"]

    assert "Vue.js" in tech["frontend_frameworks"]

    db_names = [d if isinstance(d, str) else d.get("name") for d in tech["databases_and_storage"]]
    assert "SQLite" in db_names
    assert "PostgreSQL" in db_names
    assert "Redis" in db_names
