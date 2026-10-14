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


def test_expand_capabilities_java_springboot_fullstack():
    """验证 Java 21 + Spring Boot + MyBatis-Plus + SQLite + Nuxt 3 场景下的 6 大角色画像推导。"""
    arch_data = {
        "project": {"name": "my-blog", "app_type": "fullstack"},
        "tech_stack": {
            "languages": [{"name": "Java", "version": "21"}, {"name": "TypeScript"}, {"name": "SQL"}],
            "backend_frameworks": ["Spring Boot 2.7.18", "MyBatis-Plus 3.4.3.4"],
            "frontend_frameworks": ["Nuxt 3.13.2", "Vue 3.4.38", "TailwindCSS 3.4.10"],
            "testing": {"framework": "JUnit 5", "testing_frameworks": ["JUnit 5", "Mockito", "Spring Boot Test"]},
            "databases_and_storage": [{"name": "SQLite 3 (WAL 模式)"}],
            "build_tools": ["Maven", "Vite"]
        },
        "deployment_and_ci": {"containerized": False, "ci_cd_provider": "GitHub Actions"}
    }

    caps = expand_expert_capabilities(arch_data)
    for role, role_caps in caps.items():
        assert 3 <= len(role_caps) <= 5, f"Role {role} caps count {len(role_caps)} not in [3, 5]"

    # 验证李开发: 必须是 Spring Boot + MyBatis-Plus + SQLite WAL + ControllerAdvice
    dev_str = " ".join(caps["dev"])
    assert "Java" in dev_str and "Spring Boot" in dev_str
    assert "MyBatis-Plus" in dev_str
    assert "SQLite" in dev_str and "WAL" in dev_str
    assert "ControllerAdvice" in dev_str or "异常拦截" in dev_str

    # 验证马前端: 包含 Nuxt 3 与 TailwindCSS
    fe_str = " ".join(caps["frontend"])
    assert "Nuxt 3" in fe_str
    assert "TailwindCSS" in fe_str or "Vue 3" in fe_str

    # 验证章测试: JUnit 5 与 MockMvc
    qa_str = " ".join(caps["qa"])
    assert "JUnit 5" in qa_str
    assert "MockMvc" in qa_str or "Mockito" in qa_str

    # 验证周审查: 线程安全与 SQL 注入审计
    rev_str = " ".join(caps["reviewer"])
    assert "线程安全" in rev_str or "锁竞争" in rev_str
    assert "SQL 注入" in rev_str or "MyBatis" in rev_str

    # 验证吕改特: Maven 与 Actuator
    devops_str = " ".join(caps["devops"])
    assert "Maven" in devops_str
    assert "Actuator" in devops_str


def test_polyglot_java_backend_with_python_scripts():
    """验证复合工程中包含辅助脚本 (Python) 时，主后端技术栈严格保持为 Java，不被抢占。"""
    arch_data = {
        "project": {"name": "hybrid-proj", "app_type": "fullstack"},
        "tech_stack": {
            # 模拟 my-blog 的多语言列表，包含 Python
            "languages": [
                {"name": "Java", "version": "1.8 / 21"},
                {"name": "TypeScript"},
                {"name": "JavaScript"},
                {"name": "Python", "version": ">=3.10"},
                {"name": "SQL"},
                {"name": "Shell"}
            ],
            "backend_frameworks": ["Spring Boot 2.7.18", "MyBatis-Plus"],
            "frontend_frameworks": ["Nuxt 3.13.2", "Vue 3.4.38"],
            "testing": {"framework": "JUnit 5"}
        }
    }

    caps = expand_expert_capabilities(arch_data)
    dev_str = " ".join(caps["dev"])

    # 核心断言：李开发必须绑定 Java / Spring Boot，绝不能被 Python 抢占
    assert "Java" in dev_str and "Spring Boot" in dev_str
    assert "asyncio" not in dev_str
    assert "sse-starlette" not in dev_str
    assert "Pydantic" not in dev_str

    # 章测试必须绑定 JUnit 5，绝不能分配 pytest-asyncio
    qa_str = " ".join(caps["qa"])
    assert "JUnit 5" in qa_str
    assert "pytest-asyncio" not in qa_str


def test_explicit_expert_capabilities_pass_through():
    """验证当架构师在 T0001 显式定版 expert_capabilities 时，系统直接原样直通，不被算法覆盖。"""
    custom_dev_caps = [
        "自定义领域驱动设计 (DDD) 聚合根建模",
        "自定义高性能 CQRS 读写分离管道开发",
        "自定义零内存拷贝 Netty 二进制通信协议实现"
    ]
    arch_data = {
        "project": {"name": "custom-proj"},
        "tech_stack": {
            "languages": [{"name": "Java"}],
            "expert_capabilities": {
                "dev": custom_dev_caps,
                "frontend": ["自定义微前端 qiankun 隔离沙箱"],
                "reviewer": ["自定义安全审计规则链"],
                "qa": ["自定义契约测试 Pact"],
                "architect": ["自定义异构拓扑建模"],
                "devops": ["自定义 GitOps ArgoCD 流水线"]
            }
        }
    }

    caps = expand_expert_capabilities(arch_data)
    assert caps["dev"] == custom_dev_caps
    assert caps["frontend"] == ["自定义微前端 qiankun 隔离沙箱"]
    assert caps["qa"] == ["自定义契约测试 Pact"]


def test_partial_expert_capabilities_merge():
    """验证当仅部分角色显式定制时，定制角色得到保留，其余缺失角色自动增量推导补齐。"""
    arch_data = {
        "project": {"name": "partial-custom-proj", "app_type": "fullstack"},
        "tech_stack": {
            "languages": [{"name": "Go"}],
            "backend_frameworks": ["Gin"],
            "expert_capabilities": {
                # 仅定制 dev，其余 5 个角色缺失
                "dev": ["自定义专用 Go 并发管道处理"]
            }
        }
    }

    caps = expand_expert_capabilities(arch_data)
    # dev 应保留定制内容
    assert caps["dev"] == ["自定义专用 Go 并发管道处理"]
    # 其余角色应被自动推导补齐且数量在 3~5 之间
    assert "qa" in caps and len(caps["qa"]) >= 3
    assert "frontend" in caps and len(caps["frontend"]) >= 3
    assert "architect" in caps and len(caps["architect"]) >= 3


def test_p1_java_test_framework_fallback_not_pytest():
    """P1 验证：当 Java 项目配置中遗留或错误传入 pytest 时，自动安全回退为 JUnit 5，严禁出现 Mockito 与 pytest 错配。"""
    arch_data = {
        "project": {"name": "java-service"},
        "tech_stack": {
            "languages": [{"name": "Java"}],
            "backend_frameworks": ["Spring Boot"],
            "testing": {"framework": "pytest"}  # 遗留或未命中的单测框架
        }
    }
    caps = expand_expert_capabilities(arch_data)
    dev_str = " ".join(caps["dev"])
    qa_str = " ".join(caps["qa"])

    assert "pytest" not in dev_str, f"dev capabilities should not contain pytest: {dev_str}"
    assert "JUnit 5" in dev_str
    assert "Mockito" in dev_str
    assert "pytest" not in qa_str, f"qa capabilities should not contain pytest: {qa_str}"
    assert "JUnit 5" in qa_str


def test_p2_1_non_java_capability_counts():
    """P2-1 验证：非 Java 场景 (Python, Go, Node, Rust) 下 reviewer 与 devops 必须稳定保持 5 项能力。"""
    for lang, backend, bld in [
        ("Python", ["FastAPI"], []),
        ("Go", ["Gin"], []),
        ("TypeScript", ["Express"], []),
        ("Rust", ["Axum"], ["Cargo"]),
    ]:
        arch = {
            "project": {"name": f"test-{lang.lower()}"},
            "tech_stack": {
                "languages": [{"name": lang}],
                "backend_frameworks": backend,
                "build_tools": bld,
                "testing": {"framework": "test"}
            }
        }
        caps = expand_expert_capabilities(arch)
        assert len(caps["reviewer"]) == 5, f"{lang} reviewer caps count != 5: {caps['reviewer']}"
        assert len(caps["devops"]) == 5, f"{lang} devops caps count != 5: {caps['devops']}"


def test_p2_extra_agent_tech_overlay_type_defense():
    """P2-Extra 验证：YAML 手误将 expert_capabilities[role] 写成字符串时，overlay 不做静默截断破坏字符。"""
    from scripts._lib.core.agent_tech_overlay import apply_tech_stack_to_role
    role_data = {"name": "dev", "tech_stack": {}}
    arch_data = {
        "tech_stack": {
            "languages": ["Java"],
            "backend_frameworks": ["Spring Boot"],
            "expert_capabilities": {
                "dev": "单条字符串能力描述测试"
            }
        }
    }
    updated = apply_tech_stack_to_role(role_data, arch_data, "dev")
    caps = updated["tech_stack"]["core_capabilities"]
    assert caps == ["单条字符串能力描述测试"]


def test_p2_4_find_files_depth(tmp_path):
    """P2-4 验证：find_files 支持扫描多模块 Maven/Gradle (至多 3 层深度)。"""
    from scripts._lib.discovery.stack_scanner import scan_project_stack
    # 构建 3 层目录: tmp_path / services / order / pom.xml
    sub_dir = tmp_path / "services" / "order"
    sub_dir.mkdir(parents=True)
    pom_file = sub_dir / "pom.xml"
    pom_file.write_text("<project><dependencies><dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency></dependencies></project>", encoding="utf-8")

    info = scan_project_stack(str(tmp_path))
    assert "Java" in info["languages"]
    assert "Spring Boot" in info["backend_frameworks"]
    assert "Maven" in info["build_tools"]
    assert "pytest" not in info["testing_frameworks"]
    assert "JUnit 5" in info["testing_frameworks"]


def test_expand_capabilities_all_strings_no_splitting():
    """验证当 6 大角色 expert_capabilities 全写为单条字符串时，规整为包含原句的列表，绝不被切碎为单字符。"""
    arch_data = {
        "project": {"name": "test-str-caps"},
        "tech_stack": {
            "expert_capabilities": {
                "dev": "全栈核心业务逻辑开发与单元测试",
                "frontend": "现代化前端工程与响应式交互构建",
                "reviewer": "硬编码凭据与接口权限越权专项审查",
                "qa": "全链路端到端集成测试与边界覆盖",
                "architect": "领域建模与演进式架构设计",
                "devops": "自动化持续集成与无容器轻量发布"
            }
        }
    }
    caps = expand_expert_capabilities(arch_data)
    for role, expected_str in arch_data["tech_stack"]["expert_capabilities"].items():
        assert caps[role] == [expected_str], f"Role {role} was split into characters: {caps[role]}"


def test_partial_expert_capabilities_merge_single_string():
    """验证当仅部分角色定制且写为单条字符串时，定制角色保留原字符串列表，其余角色自动推导。"""
    arch_data = {
        "project": {"name": "test-partial-str-caps"},
        "tech_stack": {
            "languages": [{"name": "Java"}],
            "backend_frameworks": ["Spring Boot"],
            "expert_capabilities": {
                "dev": "专用 Java 业务服务定制开发"
            }
        }
    }
    caps = expand_expert_capabilities(arch_data)
    assert caps["dev"] == ["专用 Java 业务服务定制开发"]
    assert len(caps["qa"]) >= 3
    assert any("JUnit 5" in c for c in caps["qa"])


def test_polyglot_scanner_purges_pytest_when_java_backend(tmp_path):
    """验证复合工程中即便包含 requirements.txt (声明 pytest)，只要主工程为 Java Spring Boot，即彻底清理错配的 pytest。"""
    from scripts._lib.discovery.stack_scanner import scan_project_stack
    # 1. 模拟根目录或子目录存在 Java Spring Boot pom.xml
    pom_file = tmp_path / "pom.xml"
    pom_file.write_text("<project><dependencies><dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency></dependencies></project>", encoding="utf-8")

    # 2. 模拟工程中同时包含 Python requirements.txt (含 pytest 与 fastapi)
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("fastapi==0.110.0\npytest==8.0.0\n", encoding="utf-8")

    info = scan_project_stack(str(tmp_path))
    assert "Java" in info["languages"]
    assert "Python" in info["languages"]
    assert "Spring Boot" in info["backend_frameworks"]
    # 关键断言：pytest 必须被清理，不能残留作为主要测试框架
    assert "pytest" not in info["testing_frameworks"]
    assert "pytest" not in info["testing_framework"].lower()
    assert "JUnit 5" in info["testing_framework"]




