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


from _lib.core.tech_capability_expander import expand_expert_capabilities


def _clean_str(s: str) -> str:
    """清理字符串中的脏占位斜杠字符"""
    if not s:
        return ""
    # 若包含 pytest / jest / go test 等多语言未清洗占位，默认取主项
    if "pytest / jest / go test" in s or "pytest/unittest" in s:
        return "pytest"
    return s.strip()


def _lang_str(arch_data):
    tech = arch_data.get("tech_stack", {}) or {}
    langs = [l.get("name") if isinstance(l, dict) else str(l) for l in tech.get("languages", [])]
    return "/".join([_clean_str(l) for l in langs if l]) if langs else "Python"


def _backend_fw_str(arch_data):
    tech = arch_data.get("tech_stack", {}) or {}
    if "backend_frameworks" in tech and isinstance(tech["backend_frameworks"], list):
        fws = [str(f) for f in tech["backend_frameworks"] if f]
        if fws:
            return "/".join(fws)
    # 兼容老版本 frameworks
    fws = []
    for fw in tech.get("frameworks", []):
        fw_name = fw.get("name") if isinstance(fw, dict) else str(fw)
        if fw_name and not any(k in fw_name.lower() for k in ["react", "vue", "next", "nuxt", "svelte", "html", "css", "ts", "js", "wiki"]):
            fws.append(fw_name)
    return "/".join(fws) if fws else "FastAPI / 现代化核心业务框架"


def _frontend_fw_str(arch_data):
    tech = arch_data.get("tech_stack", {}) or {}
    if "frontend_frameworks" in tech and isinstance(tech["frontend_frameworks"], list):
        fws = [str(f) for f in tech["frontend_frameworks"] if f]
        if fws:
            return "/".join(fws)
    # 兼容老版本 frameworks 提取前端
    fws = []
    for fw in tech.get("frameworks", []):
        fw_name = fw.get("name") if isinstance(fw, dict) else str(fw)
        if fw_name and any(k in fw_name.lower() for k in ["react", "vue", "next", "nuxt", "svelte", "html", "css", "ts", "js", "wiki"]):
            fws.append(fw_name)
    return "/".join(fws) if fws else "Vanilla JavaScript / HTML5 / CSS3 (含 i18n 国际化)"


def _test_framework(arch_data):
    raw = (arch_data.get("tech_stack", {}).get("testing", {}) or {}).get("framework", "pytest")
    return _clean_str(raw) or "pytest"


def apply_tech_stack_to_role(role_data: dict, arch_data: dict, role_key: str) -> dict:
    """把项目技术栈与 3~5 项专属技术能力合并进角色定义（内存中；不落盘）。无 arch_data 时原样返回。"""
    if not arch_data or not isinstance(role_data, dict):
        return role_data

    lang_str = _lang_str(arch_data)
    backend_fw = _backend_fw_str(arch_data)
    frontend_fw = _frontend_fw_str(arch_data)
    test_framework = _test_framework(arch_data)

    # 动态推导各专家 3~5 项高匹配能力
    all_caps = expand_expert_capabilities(arch_data)
    role_caps = all_caps.get(role_key, [])

    if role_key == "architect":
        role_data["tech_stack"] = {
            "architecture_pattern": arch_data.get("project_type", "Modular Monolith / Microservices"),
            "primary_languages": lang_str,
            "frameworks": f"{backend_fw} & {frontend_fw}",
            "core_capabilities": role_caps,
        }
        role_data["responsibilities"] = role_caps if role_caps else [
            f"基于 {lang_str} 与 {backend_fw} 进行系统总体架构设计与 ADR 编写",
            "模块边界划分、API 契约定义与高可用方案审查",
            "指导关键技术攻关与性能瓶颈建模",
        ]
    elif role_key == "dev":
        role_data["tech_stack"] = {
            "languages": lang_str,
            "frameworks": backend_fw,
            "testing_framework": test_framework,
            "core_capabilities": role_caps,
        }
        role_data["responsibilities"] = role_caps if role_caps else [
            f"{lang_str} 与 {backend_fw} 核心业务逻辑实现",
            f"单元测试撰写与覆盖率达标 ({test_framework})",
            "开发任务报告撰写与工作包归档",
            "依赖治理与本地运行环境维护",
        ]
    elif role_key == "reviewer":
        role_data["tech_stack"] = {
            "target_languages": lang_str,
            "code_style": f"{lang_str} 最佳实践与规范检查",
            "core_capabilities": role_caps,
        }
        role_data["responsibilities"] = role_caps if role_caps else [
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
            "core_capabilities": role_caps,
        }
        role_data["responsibilities"] = role_caps if role_caps else [
            f"基于 {test_framework} 的集成与端到端测试覆盖",
            f"测试用例执行与单测覆盖率校验 (≥{min_cov}%)",
            "缺陷回写与复测结论追加",
        ]
    elif role_key == "devops":
        deploy = arch_data.get("deployment_and_ci", {}) or {}
        is_docker = bool(deploy.get("containerized", False))
        ci_provider = deploy.get("ci_cd_provider", "GitHub Actions")
        role_data["tech_stack"] = {
            "containerized": is_docker,
            "ci_cd_provider": ci_provider,
            "core_capabilities": role_caps,
        }
        role_data["responsibilities"] = role_caps if role_caps else [
            "分支管理与 Git 工作流治理 (SemVer Tag)",
            f"CI/CD 自动化流水线维护 ({ci_provider})",
            f"环境镜像与容器化支持 (Docker: {is_docker})",
        ]
    elif role_key == "frontend":
        role_data["tech_stack"] = {
            "web_frameworks": frontend_fw,
            "styling": "Vanilla CSS / CSS Modules",
            "ui_principles": "Vanilla JS, Responsive, Function-Driven Design",
            "core_capabilities": role_caps,
        }
        role_data["responsibilities"] = role_caps if role_caps else [
            f"基于 {frontend_fw} 实现高质量现代 Web 用户界面与微交互",
            "响应式布局、UI 交互体验与前端性能优化",
            "前端组件模块化开发与界面质量自测",
        ]
    # pm / docs：无技术栈绑定，保持模板原样

    return role_data
