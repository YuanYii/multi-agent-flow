#!/usr/bin/env python3
"""
自动将 project_architecture.config.yaml 中的技术栈同步更新至 agents/*.yaml
"""
import os
import sys
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(SCRIPT_DIR, "..", "config")
AGENTS_DIR = os.path.join(SCRIPT_DIR, "..", "agents")

class IndentedDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow=False, indentless=False)

def dump_yaml(data, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=IndentedDumper, allow_unicode=True, sort_keys=False)

def load_architecture_config():
    target_config = os.path.join(CONFIG_DIR, "project_architecture.config.yaml")
    template_config = os.path.join(CONFIG_DIR, "project_architecture.template.yaml")
    
    config_path = target_config if os.path.exists(target_config) else template_config
    if not os.path.exists(config_path):
        print(f"[ERROR] 未找到技术架构配置文件: {config_path}")
        sys.exit(1)
        
    with open(config_path, "r", encoding="utf-8") as f:
        arch_data = yaml.safe_load(f)

    # 物理 Schema 强校验
    schema_path = os.path.join(CONFIG_DIR, "project_architecture.schema.json")
    if os.path.exists(schema_path):
        try:
            import jsonschema
            with open(schema_path, "r", encoding="utf-8") as sf:
                s_data = json.load(sf)
            jsonschema.validate(instance=arch_data, schema=s_data)
        except ImportError:
            pass
        except Exception as e:
            print(f"[WARNING] 架构配置文件违反 project_architecture.schema.json 规范: {e}")
            
    return arch_data

def update_dev_role(arch_data):
    dev_path = os.path.join(AGENTS_DIR, "03-dev.yaml")
    if not os.path.exists(dev_path):
        return

    with open(dev_path, "r", encoding="utf-8") as f:
        dev_data = yaml.safe_load(f)

    tech = arch_data.get("tech_stack", {})
    langs = [l.get("name") for l in tech.get("languages", []) if isinstance(l, dict)]
    frameworks = [fw.get("name") for fw in tech.get("frameworks", []) if isinstance(fw, dict)]
    testing = tech.get("testing", {})
    
    lang_str = "/".join(langs) if langs else "通用语言"
    fw_str = "/".join(frameworks) if frameworks else "通用框架"
    test_framework = testing.get("framework", "pytest/unittest")

    dev_data["tech_stack"] = {
        "languages": lang_str,
        "frameworks": fw_str,
        "testing_framework": test_framework
    }

    dev_data["responsibilities"] = [
        f"{lang_str} 与 {fw_str} 核心业务逻辑实现",
        f"单元测试撰写与覆盖率达标 ({test_framework})",
        "开发任务报告撰写与工作包归档",
        "依赖治理与本地运行环境维护"
    ]

    dump_yaml(dev_data, dev_path)
    print(f"[SUCCESS] 已更新开发专家配置: {dev_path}")

def update_reviewer_role(arch_data):
    reviewer_path = os.path.join(AGENTS_DIR, "04-reviewer.yaml")
    if not os.path.exists(reviewer_path):
        return

    with open(reviewer_path, "r", encoding="utf-8") as f:
        reviewer_data = yaml.safe_load(f)

    tech = arch_data.get("tech_stack", {})
    langs = [l.get("name") for l in tech.get("languages", []) if isinstance(l, dict)]
    lang_str = "/".join(langs) if langs else "通用"

    reviewer_data["tech_stack"] = {
        "target_languages": lang_str,
        "code_style": f"{lang_str} 最佳实践与规范检查"
    }

    reviewer_data["responsibilities"] = [
        f"{lang_str} 代码规范与编码风格审查",
        "安全漏洞、越权风险与性能瓶颈核验",
        "架构契约与设计模式合规性审查"
    ]

    dump_yaml(reviewer_data, reviewer_path)
    print(f"[SUCCESS] 已更新代码审查专家配置: {reviewer_path}")

def update_qa_role(arch_data):
    qa_path = os.path.join(AGENTS_DIR, "05-qa.yaml")
    if not os.path.exists(qa_path):
        return

    with open(qa_path, "r", encoding="utf-8") as f:
        qa_data = yaml.safe_load(f)

    tech = arch_data.get("tech_stack", {})
    testing = tech.get("testing", {})
    test_framework = testing.get("framework", "pytest")
    min_cov = testing.get("min_coverage_percent", 80)

    qa_data["tech_stack"] = {
        "testing_framework": test_framework,
        "min_coverage_percent": f"{min_cov}%"
    }

    qa_data["responsibilities"] = [
        f"基于 {test_framework} 的集成与端到端测试覆盖",
        f"测试用例执行与单测覆盖率校验 (≥{min_cov}%)",
        "缺陷回写与复测结论追加"
    ]

    dump_yaml(qa_data, qa_path)
    print(f"[SUCCESS] 已更新测试专家配置: {qa_path}")

def update_devops_role(arch_data):
    devops_path = os.path.join(AGENTS_DIR, "07-devops.yaml")
    if not os.path.exists(devops_path):
        return

    with open(devops_path, "r", encoding="utf-8") as f:
        devops_data = yaml.safe_load(f)

    deploy = arch_data.get("deployment_and_ci", {})
    is_docker = deploy.get("containerized", False)
    ci_provider = deploy.get("ci_cd_provider", "GitHub Actions")

    devops_data["tech_stack"] = {
        "containerized": is_docker,
        "ci_cd_provider": ci_provider
    }

    devops_data["responsibilities"] = [
        "分支管理与 Git 工作流治理 (SemVer Tag)",
        f"CI/CD 自动化流水线维护 ({ci_provider})",
        f"环境镜像与容器化支持 (Docker: {is_docker})"
    ]

    dump_yaml(devops_data, devops_path)
    print(f"[SUCCESS] 已更新 DevOps 专家配置: {devops_path}")

def main():
    arch_data = load_architecture_config()
    update_dev_role(arch_data)
    update_reviewer_role(arch_data)
    update_qa_role(arch_data)
    update_devops_role(arch_data)
    print("✨ 所有专家 Agent 的技术栈已成功同步！")

if __name__ == "__main__":
    main()
