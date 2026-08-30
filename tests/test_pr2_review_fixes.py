#!/usr/bin/env python3
"""
PR #2 评审回复要求的针对性单元测试（tests/test_pr2_review_fixes.py）

覆盖维护者 YuanYii 在 PR #2 中提出的 4 处修改建议中的可测项：
- 点3：auto_scan_stack.py --json 应仅输出纯 JSON（无 [PRE-SCAN] Banner），可被 json.loads 解析
- 点2：Monorepo 多 package.json 依赖聚合识别；pyproject.toml 分支补齐 PostgreSQL/MySQL/Redis/MongoDB 存储探测
- 点1：package.json 显式 "dependencies": null 时不应抛 TypeError（or {} 防御）
- 点4：save_architecture_config(skip_export=True) 与 env YY_FLOW_SKIP_AGENT_EXPORT=1 跳过 Antigravity Subagent 导出且不生成 .agents
"""
import os
import sys
import io
import json
import tempfile
import contextlib
import importlib.util

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from _lib.discovery.stack_scanner import scan_project_stack
from scripts.save_project_architecture import save_architecture_config


def _load_script(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_auto_scan_stack_json_pure_output():
    """点3：--json 时 stdout 应为纯 JSON，不含 [PRE-SCAN] Banner，且可被 json.loads 解析。"""
    auto_scan = _load_script("auto_scan_stack_pr2_json", os.path.join(SCRIPTS_DIR, "auto_scan_stack.py"))
    with tempfile.TemporaryDirectory() as tmp:
        old_argv = sys.argv
        sys.argv = ["auto_scan_stack.py", "--json", tmp]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                auto_scan.main()
        finally:
            sys.argv = old_argv
        out = buf.getvalue()
        data = json.loads(out)  # 不得抛 JSONDecodeError
        assert isinstance(data, dict)
        assert "project_name" in data
        assert "[PRE-SCAN]" not in out  # 管道消费模式不应混入 Banner 文本


def test_auto_scan_stack_human_banner_without_json():
    """点3 反向校验：不带 --json 时应输出 [PRE-SCAN] Banner（人类可读），证明仅 --json 静默。"""
    auto_scan = _load_script("auto_scan_stack_pr2_human", os.path.join(SCRIPTS_DIR, "auto_scan_stack.py"))
    with tempfile.TemporaryDirectory() as tmp:
        old_argv = sys.argv
        sys.argv = ["auto_scan_stack.py", tmp]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                auto_scan.main()
        finally:
            sys.argv = old_argv
        assert "[PRE-SCAN]" in buf.getvalue()


def test_monorepo_package_json_aggregation_and_null_deps():
    """点2(依赖聚合) + 点1(dependencies:null 容错)：
    根壳 package.json（仅 scripts）不应遮蔽子目录 web 含 vue 的依赖；
    显式 null 的 dependencies 不应触发 TypeError，devDependencies 仍应被识别。"""
    with tempfile.TemporaryDirectory() as tmp:
        # 根壳 package.json（仅 scripts，无 deps）
        with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "root-shell", "scripts": {"dev": "echo hi"}}, f)
        # 子目录 web 含 vue/vite 依赖
        web = os.path.join(tmp, "web")
        os.makedirs(web)
        with open(os.path.join(web, "package.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "web-app",
                       "dependencies": {"vue": "^3.4.0"},
                       "devDependencies": {"vite": "^5.0.0"}}, f)

        info = scan_project_stack(tmp)
        assert "Vue.js" in info["frontend_frameworks"], f"Monorepo 聚合失败: {info['frontend_frameworks']}"
        assert "Vite" in info["build_tools"], f"build_tools 缺 Vite: {info['build_tools']}"

        # 点1：显式 null 的 dependencies，devDependencies 仍应被识别（不抛异常）
        with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "null-deps", "dependencies": None,
                       "devDependencies": {"react": "^18.2.0"}}, f)
        info2 = scan_project_stack(tmp)  # 此前会抛 TypeError
        assert "React" in info2["frontend_frameworks"], \
            f"dependencies:null 容错失败: {info2['frontend_frameworks']}"


def test_pyproject_storage_detection_aligned():
    """点2：pyproject.toml 分支应补齐 PostgreSQL/MySQL/Redis/MongoDB 探测（与 requirements.txt 分支对齐）。"""
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "pyproject.toml"), "w", encoding="utf-8") as f:
            f.write("""
[tool.poetry.dependencies]
python = "^3.12"
psycopg2-binary = "*"
redis = "*"
pymongo = "*"
""")
        info = scan_project_stack(tmp)
        for expected in ("PostgreSQL", "Redis", "MongoDB"):
            assert expected in info["storage"], f"pyproject 缺 {expected}: {info['storage']}"


def test_save_architecture_skip_export_no_agents():
    """点4：skip_export=True 时架构落盘成功，且不生成 .agents 冗余产物。"""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["YY_FLOW_PROJECT_ROOT"] = tmp
        try:
            arch = _sample_arch()
            ok = save_architecture_config(arch, skip_export=True)
            assert ok is True
            cfg = os.path.join(tmp, "user_data", "project_architecture.config.yaml")
            assert os.path.exists(cfg)
            assert not os.path.exists(os.path.join(tmp, ".agents")), "skip_export 仍生成了 .agents"
        finally:
            os.environ.pop("YY_FLOW_PROJECT_ROOT", None)


def test_save_architecture_skip_export_via_env():
    """点4：环境变量 YY_FLOW_SKIP_AGENT_EXPORT=1 等价跳过 Subagent 导出（skip_export 默认 False 也应跳过）。"""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["YY_FLOW_PROJECT_ROOT"] = tmp
        os.environ["YY_FLOW_SKIP_AGENT_EXPORT"] = "1"
        try:
            arch = _sample_arch()
            ok = save_architecture_config(arch)  # skip_export 默认 False，但 env 应使其跳过
            assert ok is True
            assert not os.path.exists(os.path.join(tmp, ".agents")), "env 跳过仍生成了 .agents"
        finally:
            os.environ.pop("YY_FLOW_PROJECT_ROOT", None)
            os.environ.pop("YY_FLOW_SKIP_AGENT_EXPORT", None)


def _sample_arch():
    return {
        "project": {"name": "sample-project", "version": "0.1.0", "app_type": "fullstack"},
        "tech_stack": {
            "languages": [{"name": "Python", "version": "latest"}],
            "backend_frameworks": ["FastAPI"],
            "frontend_frameworks": ["Vanilla JavaScript / HTML5 / CSS3"],
            "testing": {"framework": "pytest", "min_coverage_percent": 85},
            "databases_and_storage": [{"name": "SQLite (WAL)"}],
        },
        "architecture_overview": {
            "pattern": "Modular Monolith",
            "entry_points": ["src/main.py"],
            "core_directories": {"src": "Core modules"},
        },
    }
