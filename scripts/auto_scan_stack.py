#!/usr/bin/env python3
"""
项目架构技术栈与 README 自动物理预扫描工具 (Auto Scan Stack CLI)
作为 CLI 快速预检 / 无 Agent 降级分析工具：
1. 深度解析 pyproject.toml / package.json / go.mod / Cargo.toml / Dockerfile 与 README.md；
2. 提取语言、后端框架、前端框架、数据库/向量、单测构建工具；
3. 输出结构化项目特征摘要供钱架构/CLI 使用。
"""

import os
import sys
import json
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import paths as _paths


def scan_project_stack(target_dir: str = None) -> dict:
    """扫描目标项目技术栈（支持深度 2 层子目录探测）"""
    if target_dir is None:
        target_dir = _paths.project_root()
    info = {
        "project_name": "未知应用",
        "languages": [],
        "backend_frameworks": [],
        "frontend_frameworks": [],
        "frameworks": [],
        "testing_framework": "pytest",
        "testing_frameworks": ["pytest"],
        "storage": [],
        "security": [],
        "build_tools": [],
        "readme_title": None
    }

    default_name = os.path.basename(os.path.abspath(target_dir))
    if default_name and default_name not in [".", "/", ""]:
        info["project_name"] = default_name

    # 收集根目录及 1~2 层子目录候选文件
    def find_files(fname):
        found = []
        p = os.path.join(target_dir, fname)
        if os.path.exists(p):
            found.append(p)
        try:
            for item in os.listdir(target_dir):
                sub = os.path.join(target_dir, item)
                if os.path.isdir(sub) and not item.startswith(".") and item not in ["node_modules", ".venv", "venv", "dist", "build", "user_data"]:
                    p_sub = os.path.join(sub, fname)
                    if os.path.exists(p_sub):
                        found.append(p_sub)
        except Exception:
            pass
        return found

    # 1. 解析 README.md 中的物理项目名称
    readme_candidates = [
        os.path.join(target_dir, "README.md"),
        os.path.join(target_dir, "README.zh-CN.md"),
        os.path.join(target_dir, default_name, "README.md"),
        os.path.join(target_dir, "docs", "README.md"),
    ]
    for r_path in readme_candidates:
        if os.path.exists(r_path):
            try:
                with open(r_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line_str = line.strip()
                        if line_str.startswith("# "):
                            clean_title = line_str.replace("# ", "").split("\n")[0].split("\r")[0].strip()
                            info["readme_title"] = clean_title
                            info["project_name"] = clean_title
                            break
                if info["readme_title"]:
                    break
            except Exception:
                pass

    # 2. 深度解析 Python (pyproject.toml / requirements.txt / setup.py)
    pyproject_files = find_files("pyproject.toml")
    req_files = find_files("requirements.txt")
    if pyproject_files or req_files:
        if "Python" not in info["languages"]:
            info["languages"].append("Python")
        info["testing_framework"] = "pytest"

        all_content = ""
        for pf in pyproject_files + req_files:
            try:
                with open(pf, "r", encoding="utf-8", errors="ignore") as f:
                    all_content += "\n" + f.read().lower()
            except Exception:
                pass

        if "fastapi" in all_content:
            info["backend_frameworks"].append("FastAPI")
        if "agno" in all_content or "phidata" in all_content:
            info["backend_frameworks"].append("Agno")
        if "django" in all_content:
            info["backend_frameworks"].append("Django")
        if "flask" in all_content:
            info["backend_frameworks"].append("Flask")
        if "pydantic" in all_content:
            info["backend_frameworks"].append("Pydantic")

        if "milvus" in all_content or "pymilvus" in all_content:
            info["storage"].append("Milvus Lite")
        if "sqlite" in all_content:
            info["storage"].append("SQLite (WAL)")
        if "rank-bm25" in all_content or "bm25" in all_content:
            info["storage"].append("Rank-BM25")

        if "detect-secrets" in all_content:
            info["security"].append("detect-secrets")
        if "dulwich" in all_content:
            info["security"].append("dulwich")

        if "pytest-bdd" in all_content:
            info["testing_frameworks"].append("pytest-bdd")
        if "mutmut" in all_content:
            info["testing_frameworks"].append("mutmut")
        if "pytest-asyncio" in all_content:
            info["testing_frameworks"].append("pytest-asyncio")

    # 3. 深度解析 Node.js / Web 前端 (package.json / index.html)
    pkg_files = find_files("package.json")
    for pf in pkg_files:
        if "TypeScript/JavaScript" not in info["languages"]:
            info["languages"].append("TypeScript/JavaScript")
        try:
            with open(pf, "r", encoding="utf-8") as f:
                pkg_data = json.load(f)
                info["project_name"] = pkg_data.get("name", info["project_name"])
                deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
                scripts = pkg_data.get("scripts", {})
                scripts_str = json.dumps(scripts).lower()

                if "next" in deps: info["frontend_frameworks"].append("Next.js")
                if "react" in deps: info["frontend_frameworks"].append("React")
                if "vue" in deps: info["frontend_frameworks"].append("Vue.js")

                if "vitest" in deps or "vitest" in scripts_str:
                    info["testing_framework"] = "vitest"
                    info["testing_frameworks"] = ["vitest"]
                elif "jest" in deps or "jest" in scripts_str:
                    info["testing_framework"] = "jest"
                    info["testing_frameworks"] = ["jest"]
        except Exception:
            pass

    # 4. 静态 Web 站点 / Wiki 探测
    html_files = find_files("index.html") + find_files("wiki.html")
    if html_files and not info["frontend_frameworks"]:
        info["frontend_frameworks"].append("Vanilla JavaScript / HTML5 / CSS3")

    # 5. 解析 Go (go.mod)
    go_files = find_files("go.mod")
    if go_files:
        if "Go" not in info["languages"]:
            info["languages"].append("Go")
        info["testing_framework"] = "go test"
        info["testing_frameworks"] = ["go test"]

    # 6. 解析 Docker
    docker_files = find_files("Dockerfile")
    if docker_files:
        info["build_tools"].append("Docker")

    # 汇总扁平 frameworks (兼容老展示)
    info["frameworks"] = list(dict.fromkeys(info["backend_frameworks"] + info["frontend_frameworks"]))
    if not info["frameworks"]:
        info["frameworks"] = ["现代化业务框架"]

    return info


def sync_stack_to_config(info: dict, target_project_dir: str = None) -> bool:
    """委托 save_project_architecture 进行标准 Schema 落盘（保证单一写入源）"""
    from save_project_architecture import save_architecture_config
    
    arch_dict = {
        "meta": {"initialized": True},
        "project": {
            "name": info.get("project_name") or "未知应用",
            "version": "0.1.0",
            "app_type": "fullstack" if info.get("frontend_frameworks") else "backend",
        },
        "tech_stack": {
            "languages": [{"name": l, "version": "latest"} for l in (info.get("languages") or ["Python"])],
            "backend_frameworks": info.get("backend_frameworks") or ["FastAPI / 核心业务框架"],
            "frontend_frameworks": info.get("frontend_frameworks") or ["Vanilla JavaScript / HTML5 / CSS3"],
            "testing": {
                "framework": info.get("testing_framework") or "pytest",
                "min_coverage_percent": 80,
                "testing_frameworks": info.get("testing_frameworks") or ["pytest"],
            },
            "databases_and_storage": [{"name": s} for s in (info.get("storage") or ["SQLite"])],
            "security_and_sandbox": [{"name": s} for s in (info.get("security") or [])],
        },
        "architecture_overview": {
            "pattern": "Modular Monolith",
            "entry_points": [],
            "core_directories": {},
        },
        "deployment_and_ci": {
            "containerized": "Docker" in (info.get("build_tools") or []),
            "ci_cd_provider": "GitHub Actions",
        }
    }
    return save_architecture_config(arch_dict)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="自动物理扫描项目依赖与预检分析工具")
    parser.add_argument("--write", action="store_true", help="委托 save_project_architecture 安全落盘（降级通道）")
    parser.add_argument("--project-root", default=None, help="显式数据根（默认: 解析链）")
    args = parser.parse_args()
    if args.project_root:
        import os as _os
        _os.environ.setdefault("YY_FLOW_PROJECT_ROOT", args.project_root)

    print("[SCAN]  [auto_scan_stack] 正在物理代码扫描工程依赖与 README.md...")
    info = scan_project_stack()

    title = info["readme_title"] or info["project_name"]
    print("==============================================================================")
    print(f"[PM]  【已预检识别 {title} 项目】")
    print(f"  - 编程语言: {', '.join(info['languages']) or 'Python'}")
    print(f"  - 后端框架: {', '.join(info['backend_frameworks']) or '未显式指定'}")
    print(f"  - 前端框架: {', '.join(info['frontend_frameworks']) or '未显式指定'}")
    print(f"  - 单测工具: {', '.join(info['testing_frameworks'])}")
    if info['storage']:
        print(f"  - 存储技术: {', '.join(info['storage'])}")
    if info['security']:
        print(f"  - 安全机制: {', '.join(info['security'])}")
    print("==============================================================================")

    if args.write:
        sync_stack_to_config(info)


if __name__ == "__main__":
    main()
