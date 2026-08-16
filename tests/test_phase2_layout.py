#!/usr/bin/env python3
"""
Phase 2 代码/数据分离集成测试

验证两条承重属性：
1. 存量 per-project 安装（数据在 skill 拷贝内）行为完全不变
2. 新安装（YY_FLOW_PROJECT_ROOT=宿主）数据全部落宿主根，skill 拷贝零写入

运行: python3 -m pytest tests/test_phase2_layout.py -q
"""

import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import paths  # noqa: E402
import yaml  # noqa: E402


def _run(args, env_extra=None, cwd=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable] + args, capture_output=True, text=True,
        env=env, cwd=cwd or REPO_ROOT)


def _make_host_config(host_dir, board_file):
    """按 test_workflow_v2.py 的 env fixture 模式生成宿主配置"""
    with open(os.path.join(REPO_ROOT, "config", "workflow.config.template.yaml"),
              encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["board"]["board_file"] = str(board_file)
    cfg_path = os.path.join(host_dir, "user_data", "workflow.config.yaml")
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)
    return cfg_path


class TestLegacyInstallUnchanged:
    """存量安装：skill 内含 user_data/board.json → 一切路径不变"""

    def test_legacy_data_root_is_skill_root(self, tmp_path):
        """本仓库即 legacy 安装；无 env 时 data_root 必须等于 skill_root"""
        assert os.path.isfile(os.path.join(paths.skill_root(), "user_data", "board.json"))
        got = paths.resolve_data_root(env={}, cwd=str(tmp_path))
        assert got == paths.skill_root()

    def test_legacy_board_write_lands_in_skill_user_data(self, tmp_path):
        """legacy 模式下建单 → board 写入 skill 拷贝内 user_data/（与旧行为一致）"""
        # 用 tmp 复制一份 skill 布局模拟 legacy 安装（避免污染真实 board）
        skill_copy = tmp_path / "skillcopy"
        (skill_copy / "scripts").mkdir(parents=True)
        (skill_copy / "user_data").mkdir()
        (skill_copy / "user_data" / "board.json").write_text("[]", encoding="utf-8")
        # 完整拷贝 scripts/（factory 依赖各 adapter 模块，逐个列举易漏）
        import shutil
        for f in os.listdir(SCRIPTS):
            if f.endswith(".py"):
                shutil.copy2(os.path.join(SCRIPTS, f), skill_copy / "scripts" / f)

        host_cfg = skill_copy / "user_data" / "workflow.config.yaml"
        with open(os.path.join(REPO_ROOT, "config", "workflow.config.template.yaml"),
                  encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        cfg["board"]["board_file"] = "user_data/board.json"  # 相对路径 → 锚定 data_root=skill_copy
        yaml.safe_dump(cfg, open(host_cfg, "w", encoding="utf-8"))

        env = {"YY_FLOW_PROJECT_ROOT": ""}  # 空 → 不生效 → legacy 判定
        r = _run([str(skill_copy / "scripts" / "quick_task.py"), "create",
                  "--config", str(host_cfg), "--name", "legacy 验证", "--role", "DEV",
                  "--assignee", "李开发"], env_extra=env, cwd=str(tmp_path))
        assert r.returncode == 0, r.stderr
        board = json.loads((skill_copy / "user_data" / "board.json").read_text(encoding="utf-8"))
        assert any(c["name"] == "legacy 验证" for c in board)


class TestNewInstallDataInHost:
    """新安装：YY_FLOW_PROJECT_ROOT=宿主 → 数据落宿主根，scripts/ 零写入"""

    def test_board_and_locks_in_host_user_data(self, tmp_path):
        host = tmp_path / "hostproj"
        host.mkdir()
        cfg_path = _make_host_config(host, str(host / "user_data" / "board.json"))

        r = _run([os.path.join(SCRIPTS, "quick_task.py"), "create",
                  "--config", str(cfg_path), "--name", "宿主隔离验证", "--role", "DEV",
                  "--assignee", "李开发"],
                 env_extra={"YY_FLOW_PROJECT_ROOT": str(host)})
        assert r.returncode == 0, r.stderr

        board = json.loads((host / "user_data" / "board.json").read_text(encoding="utf-8"))
        assert any(c["name"] == "宿主隔离验证" for c in board)

        locks = list((host / "user_data" / "locks").glob(".lock_*.lock")) if \
            (host / "user_data" / "locks").exists() else []
        assert locks, "锁文件应落宿主 user_data/locks/"

        # skill scripts/ 目录不得新增 lock（历史残留除外：比对测试前后集合）
        # 快速断言：本宿主任务的锁文件名不在 scripts/ 中
        for lk in locks:
            assert not os.path.exists(os.path.join(SCRIPTS, lk.name)), \
                f"锁 {lk.name} 不得写入 skill scripts/"

    def test_paths_resolution_env_directs_all_dirs(self, tmp_path):
        host = tmp_path / "host2"
        host.mkdir()
        got = paths.resolve_data_root(env={"YY_FLOW_PROJECT_ROOT": str(host)})
        assert got == str(host)
        assert paths.user_data_dir(env={"YY_FLOW_PROJECT_ROOT": str(host)}) == \
            str(host / "user_data")


class TestExportOverlay:
    """导出时技术栈覆盖 + agents yaml 只读"""

    def test_overlay_applies_and_template_immutable(self, tmp_path):
        host = tmp_path / "overlayhost"
        host.mkdir()
        (host / ".claude").mkdir()  # 激活 claude_code 平台
        (host / "user_data").mkdir()
        arch = {
            "project": {"name": "OverlayHost"},
            "tech_stack": {
                "languages": [{"name": "Rust"}],
                "frameworks": [{"name": "Axum"}],
                "testing": {"framework": "cargo test", "min_coverage_percent": 80},
            },
            "meta": {"initialized": True},
        }
        yaml.safe_dump(arch, open(host / "user_data" / "project_architecture.config.yaml",
                                  "w", encoding="utf-8"))

        import hashlib
        dev_yaml = os.path.join(REPO_ROOT, "agents", "03-dev.yaml")
        before = hashlib.sha256(open(dev_yaml, "rb").read()).hexdigest()

        r = _run([os.path.join(SCRIPTS, "verify_and_export_agents.py")],
                 env_extra={"YY_FLOW_PROJECT_ROOT": str(host)}, cwd=str(host))
        assert r.returncode == 0, r.stdout[-600:] + r.stderr[-300:]

        after = hashlib.sha256(open(dev_yaml, "rb").read()).hexdigest()
        assert before == after, "agents/03-dev.yaml 必须保持只读"

        out = host / ".claude" / "agents" / "flow-dev.md"
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "Rust" in content and "cargo test" in content

    def test_no_arch_config_exports_generic(self, tmp_path):
        """未初始化架构配置 → 导出与模板一致（无覆盖）"""
        host = tmp_path / "plainhost"
        host.mkdir()
        (host / ".claude").mkdir()
        r = _run([os.path.join(SCRIPTS, "verify_and_export_agents.py")],
                 env_extra={"YY_FLOW_PROJECT_ROOT": str(host)}, cwd=str(host))
        assert r.returncode == 0, r.stdout[-400:]
        content = (host / ".claude" / "agents" / "flow-dev.md").read_text(encoding="utf-8")
        assert "核心业务逻辑实现" in content  # 通用职责仍在


class TestScanReadsHost:
    """auto_scan 扫描宿主而非 skill 自身"""

    def test_scan_identifies_host_readme(self, tmp_path):
        host = tmp_path / "scanhost"
        host.mkdir()
        (host / "README.md").write_text("# My Host App\n", encoding="utf-8")

        r = _run([os.path.join(SCRIPTS, "auto_scan_stack.py")],
                 env_extra={"YY_FLOW_PROJECT_ROOT": str(host)}, cwd=str(host))
        assert r.returncode == 0
        assert "My Host App" in r.stdout
        assert "Multi-Agent Team Workflow" not in r.stdout  # 不得识别成 skill 自己


class TestReportDir:
    """报告归档目录锚定 data_root"""

    def test_report_lands_in_host_docs(self, tmp_path):
        host = tmp_path / "reporthost"
        host.mkdir()
        r = _run([os.path.join(SCRIPTS, "generate_report.py"),
                  "--type", "dev", "--task-id", "T0001", "--task-name", "验证"],
                 env_extra={"YY_FLOW_PROJECT_ROOT": str(host)}, cwd=str(host))
        assert r.returncode == 0, r.stderr
        expected = host / "docs" / "04-研发过程" / "02-报告" / "dev" / "T0001_dev_report.md"
        assert expected.exists()
