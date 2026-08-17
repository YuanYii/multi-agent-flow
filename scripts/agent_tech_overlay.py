#!/usr/bin/env python3
"""
技术栈覆盖层 (Agent Tech Overlay)
从 <data_root>/user_data/project_architecture.config.yaml 读取项目技术栈，
在【导出时】覆盖到内存中的角色定义上——agents/*.yaml 模板保持只读不可变。

背景：旧版 update_agent_tech_stacks.py 直接改写 skill 拷贝内的 agents/*.yaml，
共享安装下多项目互相覆盖；本模块把同样的合并逻辑做成纯函数，供导出器调用。
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import paths as _paths


def load_arch_data():
    """加载运行态架构配置；未初始化（不存在/占位）返回 None（导出走模板原样）"""
    import yaml
    config_path = _paths.arch_config_path()
    if not os.path.isfile(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            arch = yaml.safe_load(f) or {}
    except Exception:
        return None
    meta = arch.get("meta") or {}
    project_name = (arch.get("project") or {}).get("name", "")
    if not meta.get("initialized") and project_name in ("", "project_name"):
        return None  # 模板占位：不覆盖
    return arch


def _lang_str(arch_data):
    tech = arch_data.get("tech_stack", {})
    langs = [l.get("name") for l in tech.get("languages", []) if isinstance(l, dict)]
    return "/".join(langs) if langs else "通用语言"


def _fw_str(arch_data):
    tech = arch_data.get("tech_stack", {})
    fws = [fw.get("name") for fw in tech.get("frameworks", []) if isinstance(fw, dict)]
    return "/".join(fws) if fws else "通用框架"


def _test_framework(arch_data):
    return (arch_data.get("tech_stack", {}).get("testing", {}) or {}).get("framework", "pytest/unittest")


def apply_tech_stack_to_role(role_data: dict, arch_data: dict, role_key: str) -> dict:
    """把项目技术栈合并进角色定义（内存中；不落盘）。无 arch_data 时原样返回。"""
    if not arch_data or not isinstance(role_data, dict):
        return role_data

    lang_str = _lang_str(arch_data)
    fw_str = _fw_str(arch_data)
    test_framework = _test_framework(arch_data)

    if role_key == "architect":
        role_data["tech_stack"] = {
            "architecture_pattern": arch_data.get("project_type", "Monolith / Microservices"),
            "primary_languages": lang_str,
            "frameworks": fw_str,
        }
        role_data["responsibilities"] = [
            f"基于 {lang_str} 与 {fw_str} 进行系统总体架构设计与 ADR 编写",
            "模块边界划分、API 契约定义与高可用方案审查",
            "指导关键技术攻关与性能瓶颈建模",
        ]
    elif role_key == "dev":
        role_data["tech_stack"] = {
            "languages": lang_str,
            "frameworks": fw_str,
            "testing_framework": test_framework,
        }
        role_data["responsibilities"] = [
            f"{lang_str} 与 {fw_str} 核心业务逻辑实现",
            f"单元测试撰写与覆盖率达标 ({test_framework})",
            "开发任务报告撰写与工作包归档",
            "依赖治理与本地运行环境维护",
        ]
    elif role_key == "reviewer":
        role_data["tech_stack"] = {
            "target_languages": lang_str,
            "code_style": f"{lang_str} 最佳实践与规范检查",
        }
        role_data["responsibilities"] = [
            f"{lang_str} 代码规范与编码风格审查",
            "安全漏洞、越权风险与性能瓶颈核验",
            "架构契约与设计模式合规性审查",
        ]
    elif role_key == "qa":
        testing = arch_data.get("tech_stack", {}).get("testing", {}) or {}
        min_cov = testing.get("min_coverage_percent", 80)
        role_data["tech_stack"] = {
            "testing_framework": test_framework,
            "min_coverage_percent": f"{min_cov}%",
        }
        role_data["responsibilities"] = [
            f"基于 {test_framework} 的集成与端到端测试覆盖",
            f"测试用例执行与单测覆盖率校验 (≥{min_cov}%)",
            "缺陷回写与复测结论追加",
        ]
    elif role_key == "devops":
        deploy = arch_data.get("deployment_and_ci", {}) or {}
        is_docker = deploy.get("containerized", False)
        ci_provider = deploy.get("ci_cd_provider", "GitHub Actions")
        role_data["tech_stack"] = {
            "containerized": is_docker,
            "ci_cd_provider": ci_provider,
        }
        role_data["responsibilities"] = [
            "分支管理与 Git 工作流治理 (SemVer Tag)",
            f"CI/CD 自动化流水线维护 ({ci_provider})",
            f"环境镜像与容器化支持 (Docker: {is_docker})",
        ]
    elif role_key == "frontend":
        tech = arch_data.get("tech_stack", {})
        frameworks = [fw.get("name") for fw in tech.get("frameworks", []) if isinstance(fw, dict)]
        fe_fw = [fw for fw in frameworks
                 if any(k in fw.lower() for k in ["react", "vue", "next", "nuxt", "svelte", "html", "css", "ts", "js"])]
        fw_out = "/".join(fe_fw) if fe_fw else "/".join(frameworks) if frameworks else "HTML/JavaScript/CSS"
        role_data["tech_stack"] = {
            "web_frameworks": fw_out,
            "styling": "Vanilla CSS / CSS Modules",
            "ui_principles": "Vanilla JS, Responsive, Function-Driven Design",
        }
        role_data["responsibilities"] = [
            f"基于 {fw_out} 实现高质量现代 Web 用户界面与微交互",
            "响应式布局、UI 交互体验与前端性能优化",
            "前端组件模块化开发与界面质量自测",
        ]
    # pm / docs：无技术栈绑定，保持模板原样

    return role_data
