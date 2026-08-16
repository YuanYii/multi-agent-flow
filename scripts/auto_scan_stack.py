#!/usr/bin/env python3
"""
项目架构技术栈与 README 自动物理扫描解析工具 (Auto Scan Stack CLI)
代替纯 Echo 占位，真正代码解析 package.json/pyproject.toml/go.mod/Dockerfile 与 README.md，
提取真实的框架语言、单测构建工具，并物理格式化打出【已识别 xxxx 项目】标志。
"""

import os
import sys
import json
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import paths as _paths


def scan_project_stack(target_dir: str = None) -> dict:
    """扫描目标项目技术栈；默认目标为解析后的 data_root（宿主项目），而非 skill 拷贝自身"""
    if target_dir is None:
        target_dir = _paths.resolve_data_root()
    info = {
        "project_name": "未知应用",
        "languages": [],
        "frameworks": [],
        "testing_framework": "pytest / jest / go test",
        "build_tools": [],
        "readme_title": None
    }

    # 1. 解析 README.md 中的物理项目名称
    readme_path = os.path.join(target_dir, "README.md")
    if os.path.exists(readme_path):
        try:
            with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str.startswith("# "):
                        clean_title = line_str.replace("# ", "").split("\n")[0].split("\r")[0].strip()
                        info["readme_title"] = clean_title
                        info["project_name"] = clean_title
                        break
        except Exception:
            pass

    # 2. 解析 Python (pyproject.toml / setup.py / requirements.txt)
    pyproject_path = os.path.join(target_dir, "pyproject.toml")
    req_path = os.path.join(target_dir, "requirements.txt")
    if os.path.exists(pyproject_path) or os.path.exists(req_path):
        info["languages"].append("Python")
        info["testing_framework"] = "pytest"
        if os.path.exists(pyproject_path):
            try:
                with open(pyproject_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if "pytest" in content:
                        info["testing_framework"] = "pytest"
                    elif "unittest" in content:
                        info["testing_framework"] = "unittest"
            except Exception:
                pass

    # 3. 解析 Node.js (package.json)
    pkg_path = os.path.join(target_dir, "package.json")
    if os.path.exists(pkg_path):
        info["languages"].append("TypeScript/JavaScript")
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg_data = json.load(f)
                info["project_name"] = pkg_data.get("name", info["project_name"])
                deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
                scripts = pkg_data.get("scripts", {})
                scripts_str = json.dumps(scripts).lower()

                if "next" in deps: info["frameworks"].append("Next.js")
                if "react" in deps: info["frameworks"].append("React")
                if "vue" in deps: info["frameworks"].append("Vue.js")

                if "vitest" in deps or "vitest" in scripts_str:
                    info["testing_framework"] = "vitest"
                elif "jest" in deps or "jest" in scripts_str:
                    info["testing_framework"] = "jest"
        except Exception:
            pass

    # 4. 解析 Go (go.mod)
    if os.path.exists(os.path.join(target_dir, "go.mod")):
        info["languages"].append("Go")
        info["testing_framework"] = "go test"

    # 5. 解析 Docker (Dockerfile)
    if os.path.exists(os.path.join(target_dir, "Dockerfile")):
        info["build_tools"].append("Docker")

    return info


def sync_stack_to_config(info: dict, target_project_dir: str = None) -> bool:
    """将扫描到的语言、框架、单测映射写回 <data_root>/user_data/project_architecture.config.yaml"""
    import yaml
    import shutil
    import subprocess

    if target_project_dir is None:
        target_project_dir = _paths.resolve_data_root()
    # 配置落宿主 user_data/（与 init step 4 生成位置一致）；模板恒取 skill 拷贝
    config_path = os.path.join(target_project_dir, "user_data", "project_architecture.config.yaml")
    template_path = os.path.join(_paths.skill_root(), "config", "project_architecture.template.yaml")

    if not os.path.exists(config_path):
        if os.path.exists(template_path):
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            shutil.copy2(template_path, config_path)
        else:
            print(f"[WARN]  未找到架构配置文件: {config_path}")
            return False

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        if "tech_stack" not in cfg:
            cfg["tech_stack"] = {}

        langs = info.get("languages") or ["Python"]
        fws = info.get("frameworks") or ["Pydantic / Web Framework"]
        test_fw = info.get("testing_framework") or "pytest"

        cfg["tech_stack"]["languages"] = [{"name": l, "version": "latest"} for l in langs]
        cfg["tech_stack"]["frameworks"] = [{"name": fw, "type": "backend/frontend"} for fw in fws]
        cfg["tech_stack"]["testing"] = {"framework": test_fw, "min_coverage_percent": 80}

        # 填充真实扫描值后置初始化完成标志：SKILL.md 依此判断是否需要重扫
        if "meta" not in cfg:
            cfg["meta"] = {}
        cfg["meta"]["initialized"] = True

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)
        print(f" [配置同步] 已成功将识别出的技术栈写回 {config_path}")

        # 联动触发 update_agent_tech_stacks.py 同步更新 agents/*.yaml
        update_script = os.path.join(SCRIPT_DIR, "update_agent_tech_stacks.py")
        if os.path.exists(update_script):
            res = subprocess.run([sys.executable, update_script], capture_output=True, text=True)
            if res.returncode == 0:
                print(" [闭环同步完成] 已自动触发 update_agent_tech_stacks.py 完成全量 agents/*.yaml 同步！")
            else:
                print(f"[WARN]  [警告] 触发 agents/*.yaml 同步失败: {res.stderr}")
        return True
    except Exception as e:
        print(f"[FAILED]  [写回失败] 同步技术栈配置抛出异常: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="自动物理扫描项目依赖与 README 工具")
    parser.add_argument("--write", action="store_true", help="自动将扫描到的技术栈同步落盘至 user_data 配置")
    parser.add_argument("--project-root", default=None, help="显式数据根（默认: 解析链）")
    args = parser.parse_args()
    if args.project_root:
        import os as _os
        _os.environ.setdefault("YY_FLOW_PROJECT_ROOT", args.project_root)

    print("[SCAN]  [auto_scan_stack] 正在物理代码扫描工程依赖与 README.md...")
    info = scan_project_stack()

    title = info["readme_title"] or info["project_name"]
    print("==============================================================================")
    print(f"[PM]  【已识别 {title} 项目】")
    print(f"  - 识别编程语言: {', '.join(info['languages']) or 'Python'}")
    print(f"  - 识别核心框架: {', '.join(info['frameworks']) or 'Pydantic / Web Framework'}")
    print(f"  - 识别单测工具: {info['testing_framework']}")
    print("==============================================================================")

    if args.write:
        sync_stack_to_config(info)


if __name__ == "__main__":
    main()
