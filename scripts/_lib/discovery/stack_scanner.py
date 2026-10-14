"""
项目技术栈与依赖深度预扫描核心模块
"""
import os
import sys
import json
import re
from typing import Optional, Dict, Any

import paths as _paths


def scan_project_stack(target_dir: Optional[str] = None) -> Dict[str, Any]:
    """扫描目标项目技术栈（支持深度 2 层子目录探测）"""
    if target_dir is None:
        target_dir = _paths.project_root()
    info = {
        "project_name": "未知应用",
        "languages": [],
        "backend_frameworks": [],
        "frontend_frameworks": [],
        "frameworks": [],
        "testing_framework": "",
        "testing_frameworks": [],
        "storage": [],
        "security": [],
        "build_tools": [],
        "readme_title": None
    }

    default_name = os.path.basename(os.path.abspath(target_dir))
    if default_name and default_name not in [".", "/", ""]:
        info["project_name"] = default_name

    def find_files(fname: str, max_depth: int = 3):
        """
        探测指定目录及至多 max_depth 层子目录中匹配目标文件名的路径列表。
        自动忽略 node_modules、.venv、dist 等构建与依赖目录。
        """
        found = []
        ignore_dirs = {
            "node_modules", ".venv", "venv", "dist", "build", "user_data",
            ".git", ".idea", ".agents", "target", ".gradle", ".mvn", "bin", "out"
        }
        target_abs = os.path.abspath(target_dir)

        p = os.path.join(target_abs, fname)
        if os.path.exists(p):
            found.append(p)

        try:
            for root, dirs, files in os.walk(target_abs):
                # 过滤黑名单目录
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ignore_dirs]
                rel = os.path.relpath(root, target_abs)
                depth = 0 if rel == "." else len(rel.split(os.sep))
                if depth > max_depth:
                    dirs[:] = []
                    continue
                if rel != "." and fname in files:
                    found.append(os.path.join(root, fname))
        except Exception:
            pass

        # 保序去重
        return list(dict.fromkeys(found))

    # 1. 解析 README.md 中的物理项目名称
    readme_candidates = find_files("README.md")
    if readme_candidates:
        try:
            with open(readme_candidates[0], "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str.startswith("# ") and len(line_str) > 2:
                        raw_title = line_str[2:].strip()
                        cleaned_title = re.sub(r"[^\w\s\-\u4e00-\u9fa5]", "", raw_title).strip()
                        if cleaned_title:
                            info["readme_title"] = cleaned_title
                            if info["project_name"] in ["未知应用", "src", "app", "workspace", "multi-agent-flow"]:
                                info["project_name"] = cleaned_title
                        break
        except Exception:
            pass

    # 2. 探测 pyproject.toml
    pyproject_files = find_files("pyproject.toml")
    if pyproject_files:
        if "Python" not in info["languages"]:
            info["languages"].append("Python")
        try:
            with open(pyproject_files[0], "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                if m and m.group(1):
                    info["project_name"] = m.group(1).strip()
                if "fastapi" in content.lower() and "FastAPI" not in info["backend_frameworks"]:
                    info["backend_frameworks"].append("FastAPI")
                if "django" in content.lower() and "Django" not in info["backend_frameworks"]:
                    info["backend_frameworks"].append("Django")
                if "flask" in content.lower() and "Flask" not in info["backend_frameworks"]:
                    info["backend_frameworks"].append("Flask")
                if "pytest" in content.lower():
                    info["testing_framework"] = "pytest"
                    if "pytest" not in info["testing_frameworks"]:
                        info["testing_frameworks"].append("pytest")
                if "agno" in content.lower():
                    info["backend_frameworks"].append("Agno")
                if "langchain" in content.lower():
                    info["backend_frameworks"].append("LangChain")
                if "sqlite" in content.lower():
                    info["storage"].append("SQLite")
                if "sqlalchemy" in content.lower() or "sqlmodel" in content.lower():
                    info["storage"].append("SQLAlchemy / SQLModel")
                # 与 requirements.txt 分支对齐：补齐 PostgreSQL/MySQL/Redis/MongoDB 探测
                if ("psycopg" in content.lower() or "asyncpg" in content.lower()
                        or "postgresql" in content.lower()) and "PostgreSQL" not in info["storage"]:
                    info["storage"].append("PostgreSQL")
                if ("pymysql" in content.lower() or "mysql" in content.lower()) and "MySQL" not in info["storage"]:
                    info["storage"].append("MySQL")
                if "redis" in content.lower() and "Redis" not in info["storage"]:
                    info["storage"].append("Redis")
                if ("pymongo" in content.lower() or "mongodb" in content.lower()) and "MongoDB" not in info["storage"]:
                    info["storage"].append("MongoDB")
        except Exception:
            pass

    # 3. 探测 requirements.txt
    req_files = find_files("requirements.txt")
    if req_files:
        if "Python" not in info["languages"]:
            info["languages"].append("Python")
        try:
            with open(req_files[0], "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().lower()
                if "fastapi" in content and "FastAPI" not in info["backend_frameworks"]:
                    info["backend_frameworks"].append("FastAPI")
                if "pytest" in content and "pytest" not in info["testing_frameworks"]:
                    info["testing_frameworks"].append("pytest")
                if "uvicorn" in content and "Uvicorn" not in info["backend_frameworks"]:
                    info["backend_frameworks"].append("Uvicorn")
                # 存储/数据库识别（requirements.txt 分支此前缺失，导致仅含 SQLAlchemy 等项目 storage 为空）
                if ("sqlalchemy" in content or "sqlmodel" in content) and "SQLAlchemy / SQLModel" not in info["storage"]:
                    info["storage"].append("SQLAlchemy / SQLModel")
                if "sqlite" in content and "SQLite" not in info["storage"]:
                    info["storage"].append("SQLite")
                if ("psycopg" in content or "asyncpg" in content or "postgresql" in content) and "PostgreSQL" not in info["storage"]:
                    info["storage"].append("PostgreSQL")
                if ("pymysql" in content or "mysql" in content) and "MySQL" not in info["storage"]:
                    info["storage"].append("MySQL")
                if "redis" in content and "Redis" not in info["storage"]:
                    info["storage"].append("Redis")
                if ("pymongo" in content or "mongodb" in content) and "MongoDB" not in info["storage"]:
                    info["storage"].append("MongoDB")
        except Exception:
            pass

    # 4. 探测 package.json (Node/前端技术栈)
    #    聚合根与子目录全部命中文件，避免 monorepo 根壳 package.json（仅含 scripts）优先命中
    #    而遗漏 frontend/ / web/ 下含框架依赖的 package.json，导致误判 Vanilla HTML5
    pkg_files = find_files("package.json")
    if pkg_files:
        if "JavaScript / TypeScript" not in info["languages"]:
            info["languages"].append("JavaScript / TypeScript")
        deps = {}
        picked_name = None
        for pf in pkg_files:
            try:
                with open(pf, "r", encoding="utf-8", errors="ignore") as f:
                    pkg_data = json.load(f)
                if pkg_data.get("name") and picked_name is None:
                    picked_name = pkg_data.get("name")
                deps.update(pkg_data.get("dependencies") or {})
                deps.update(pkg_data.get("devDependencies") or {})
            except Exception:
                continue
        if picked_name and info["project_name"] in ["未知应用", "src", "app", "workspace"]:
            info["project_name"] = picked_name
        deps_keys = " ".join(deps.keys()).lower()

        if "vue" in deps_keys and "Vue.js" not in info["frontend_frameworks"]:
            info["frontend_frameworks"].append("Vue.js")
        if "react" in deps_keys and "React" not in info["frontend_frameworks"]:
            info["frontend_frameworks"].append("React")
        if "next" in deps_keys and "Next.js" not in info["frontend_frameworks"]:
            info["frontend_frameworks"].append("Next.js")
        if "vite" in deps_keys and "Vite" not in info["build_tools"]:
            info["build_tools"].append("Vite")
        if "tailwindcss" in deps_keys and "TailwindCSS" not in info["frontend_frameworks"]:
            info["frontend_frameworks"].append("TailwindCSS")
        if "jest" in deps_keys and "Jest" not in info["testing_frameworks"]:
            info["testing_frameworks"].append("Jest")
        if "vitest" in deps_keys and "Vitest" not in info["testing_frameworks"]:
            info["testing_frameworks"].append("Vitest")

    # 5. 探测 go.mod
    go_files = find_files("go.mod")
    if go_files:
        if "Go" not in info["languages"]:
            info["languages"].append("Go")
        try:
            with open(go_files[0], "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                m = re.search(r"module\s+([^\s\n]+)", content)
                if m and m.group(1) and info["project_name"] in ["未知应用", "src", "app"]:
                    info["project_name"] = os.path.basename(m.group(1))
                if "gin-gonic/gin" in content:
                    info["backend_frameworks"].append("Gin")
                if "gorm.io/gorm" in content:
                    info["storage"].append("GORM")
        except Exception:
            pass

    # 6. 探测 Java (pom.xml / build.gradle)
    pom_files = find_files("pom.xml")
    gradle_files = find_files("build.gradle") + find_files("build.gradle.kts")
    if pom_files or gradle_files:
        if "Java" not in info["languages"]:
            info["languages"].append("Java")
        java_contents = []
        for jf in (pom_files + gradle_files):
            try:
                with open(jf, "r", encoding="utf-8", errors="ignore") as f:
                    java_contents.append(f.read().lower())
            except Exception:
                continue
        combined_java = " ".join(java_contents)
        if "spring-boot" in combined_java or "org.springframework.boot" in combined_java:
            if "Spring Boot" not in info["backend_frameworks"]:
                info["backend_frameworks"].append("Spring Boot")
        if "mybatis" in combined_java:
            fw_title = "MyBatis-Plus" if "mybatis-plus" in combined_java else "MyBatis"
            if fw_title not in info["backend_frameworks"]:
                info["backend_frameworks"].append(fw_title)
        if "sqlite" in combined_java and "SQLite" not in info["storage"]:
            info["storage"].append("SQLite")
        if "mysql" in combined_java and "MySQL" not in info["storage"]:
            info["storage"].append("MySQL")
        if ("postgresql" in combined_java or "r2dbc-postgresql" in combined_java) and "PostgreSQL" not in info["storage"]:
            info["storage"].append("PostgreSQL")
        if "redis" in combined_java and "Redis" not in info["storage"]:
            info["storage"].append("Redis")
        if "junit" in combined_java or "spring-boot-starter-test" in combined_java:
            info["testing_framework"] = "JUnit 5 / Spring Boot Test"
            if "JUnit 5" not in info["testing_frameworks"]:
                info["testing_frameworks"].append("JUnit 5")
        if pom_files and "Maven" not in info["build_tools"]:
            info["build_tools"].append("Maven")
        if gradle_files and "Gradle" not in info["build_tools"]:
            info["build_tools"].append("Gradle")

    # 7. 探测 Rust (Cargo.toml)
    cargo_files = find_files("Cargo.toml")
    if cargo_files:
        if "Rust" not in info["languages"]:
            info["languages"].append("Rust")
        try:
            with open(cargo_files[0], "r", encoding="utf-8", errors="ignore") as f:
                c_content = f.read().lower()
                if "axum" in c_content and "Axum" not in info["backend_frameworks"]:
                    info["backend_frameworks"].append("Axum")
                if "actix-web" in c_content and "Actix-web" not in info["backend_frameworks"]:
                    info["backend_frameworks"].append("Actix-web")
                if "tokio" in c_content and "Tokio" not in info["backend_frameworks"]:
                    info["backend_frameworks"].append("Tokio")
                if "cargo" not in [b.lower() for b in info["build_tools"]]:
                    info["build_tools"].append("Cargo")
        except Exception:
            pass

    # 8. 探测 Dockerfile / docker-compose
    docker_files = find_files("Dockerfile") + find_files("docker-compose.yml") + find_files("docker-compose.yaml")
    if docker_files:
        if "Docker / Container" not in info["build_tools"]:
            info["build_tools"].append("Docker / Container")

    # 9. 纯前端 / 原生静态资源兜底探测 (HTML / CSS / JS)
    if not info["frontend_frameworks"]:
        html_files = find_files("index.html")
        if html_files:
            info["frontend_frameworks"].append("Vanilla HTML5 / Modern CSS / ES6")
            if "JavaScript" not in " ".join(info["languages"]):
                info["languages"].append("JavaScript")

    # 10. 测试框架语言自适应兜底与多语言互斥清理
    langs_lower = [str(l).lower() for l in info["languages"]]
    backend_lower = [str(b).lower() for b in info["backend_frameworks"]]
    build_lower = [str(b).lower() for b in info["build_tools"]]
    has_java_backend = (
        any("spring" in b or "mybatis" in b for b in backend_lower)
        or ("java" in langs_lower and any(b in ["maven", "gradle"] for b in build_lower))
    )

    # 若为主 Java 后端工程（即使包含辅助 Python 脚本），或仅有 Java 无 Python，清理可能残留的 pytest
    if has_java_backend or (any("java" in l for l in langs_lower) and not any("python" in l for l in langs_lower)):
        info["testing_frameworks"] = [tf for tf in info["testing_frameworks"] if "pytest" not in tf.lower()]
        if info["testing_framework"] and "pytest" in info["testing_framework"].lower():
            info["testing_framework"] = ""

    if not info["testing_framework"]:
        if any("java" in l for l in langs_lower):
            info["testing_framework"] = "JUnit 5 / Spring Boot Test" if any("spring" in b.lower() for b in info["backend_frameworks"]) else "JUnit 5"
            if "JUnit 5" not in info["testing_frameworks"]:
                info["testing_frameworks"].append("JUnit 5")
        elif any("go" in l for l in langs_lower):
            info["testing_framework"] = "go test"
            if "go test" not in info["testing_frameworks"]:
                info["testing_frameworks"].append("go test")
        elif any("rust" in l for l in langs_lower):
            info["testing_framework"] = "cargo test"
            if "cargo test" not in info["testing_frameworks"]:
                info["testing_frameworks"].append("cargo test")
        elif any("python" in l for l in langs_lower):
            info["testing_framework"] = "pytest"
            if "pytest" not in info["testing_frameworks"]:
                info["testing_frameworks"].append("pytest")
        elif any(k in l for l in langs_lower for k in ["javascript", "typescript", "node"]):
            info["testing_framework"] = info["testing_frameworks"][0] if info["testing_frameworks"] else "Jest / Vitest"
            if not info["testing_frameworks"]:
                info["testing_frameworks"].append("Jest / Vitest")
        else:
            info["testing_framework"] = "pytest"
            if "pytest" not in info["testing_frameworks"]:
                info["testing_frameworks"].append("pytest")
    elif not info["testing_frameworks"]:
        info["testing_frameworks"].append(info["testing_framework"])

    # 合并 frameworks 列表
    info["frameworks"] = list(set(info["backend_frameworks"] + info["frontend_frameworks"]))
    return info
