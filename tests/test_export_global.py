#!/usr/bin/env python3
"""
Phase 3 全局共享安装测试

覆盖: --global 挂载各宿主用户级目录、用户级 Subagent 导出、
项目级路径不受影响、共享标记否决 legacy 误判、安装器守卫逻辑。

运行: python3 -m pytest tests/test_export_global.py -q
"""

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

# 与运行环境解耦：本机 python 的 user site-packages 在 HOME 下，改 HOME 会丢依赖
try:
    import site
    _USER_SITE = site.getusersitepackages()
    if os.path.isdir(_USER_SITE):
        _PYTHONPATH = _USER_SITE + os.pathsep + os.environ.get("PYTHONPATH", "")
    else:
        _PYTHONPATH = os.environ.get("PYTHONPATH", "")
except Exception:
    _PYTHONPATH = os.environ.get("PYTHONPATH", "")


def _run(args, env_extra=None, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = _PYTHONPATH
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable] + args, capture_output=True, text=True,
        env=env, cwd=cwd or REPO_ROOT)


class TestGlobalExport:
    """--global: 用户级挂载与导出"""

    def test_global_mounts_claude_skills_dir(self, tmp_path):
        fake_home = tmp_path / "home"
        (fake_home / ".claude").mkdir(parents=True)
        r = _run([os.path.join(SCRIPTS, "verify_and_export_agents.py"), "--global"],
                 env_extra={"HOME": str(fake_home)})
        assert r.returncode == 0, r.stdout[-500:] + r.stderr[-300:]

        link = fake_home / ".claude" / "skills" / "yy-flow"
        assert link.is_symlink()
        assert os.path.realpath(str(link)) == os.path.realpath(REPO_ROOT)

        # 用户级 subagent 导出（Claude Code 支持 user_pattern）
        agents_dir = fake_home / ".claude" / "agents"
        exported = list(agents_dir.glob("flow-*.md"))
        assert len(exported) == 8
        dev = (agents_dir / "flow-dev.md").read_text(encoding="utf-8")
        assert "核心业务逻辑实现" in dev

    def test_global_subagents_are_generic(self, tmp_path):
        """全局模式不合并项目技术栈（本仓库 legacy 架构配置存在也不得泄漏）"""
        fake_home = tmp_path / "home2"
        (fake_home / ".claude").mkdir(parents=True)
        r = _run([os.path.join(SCRIPTS, "verify_and_export_agents.py"), "--global"],
                 env_extra={"HOME": str(fake_home), "YY_FLOW_PROJECT_ROOT": str(REPO_ROOT)})
        assert r.returncode == 0, r.stdout[-400:]
        dev = (fake_home / ".claude" / "agents" / "flow-dev.md").read_text(encoding="utf-8")
        assert "Rust" not in dev
        assert "通用语言" in dev  # 模板基线

    def test_project_mode_unaffected_by_global_flag(self, tmp_path):
        """同一台机器上项目级导出照常（.claude 目录存在 → 项目级激活）"""
        host = tmp_path / "projhost"
        (host / ".claude").mkdir(parents=True)
        r = _run([os.path.join(SCRIPTS, "verify_and_export_agents.py")],
                 env_extra={"YY_FLOW_PROJECT_ROOT": str(host)}, cwd=str(host))
        assert r.returncode == 0, r.stdout[-400:]
        assert (host / ".claude" / "skills" / "yy-flow").exists()
        assert (host / ".claude" / "agents" / "flow-pm.md").exists()

    def test_global_no_platform_detected_fails_closed(self, tmp_path):
        """无任何已安装宿主（fake HOME 空）→ 全局模式 Fail-Closed"""
        empty_home = tmp_path / "emptyhome"
        empty_home.mkdir()
        r = _run([os.path.join(SCRIPTS, "verify_and_export_agents.py"), "--global"],
                 env_extra={"HOME": str(empty_home)})
        assert r.returncode == 1
        assert "FAILED" in r.stdout


class TestSharedMarker:
    """.yy-flow-shared 标记否决 legacy 判定"""

    def test_marker_vetoes_legacy(self, tmp_path, monkeypatch):
        import paths
        fake_skill = tmp_path / "sharedskill"
        (fake_skill / "scripts").mkdir(parents=True)
        (fake_skill / "user_data").mkdir()
        (fake_skill / "user_data" / "board.json").write_text("[]", encoding="utf-8")
        (fake_skill / ".yy-flow-shared").write_text("", encoding="utf-8")  # 共享标记

        monkeypatch.setattr(paths, "_SCRIPT_DIR", str(fake_skill / "scripts"))
        got = paths.resolve_data_root(env={}, cwd=str(tmp_path / "someproject"))
        assert got == str(tmp_path / "someproject"), "共享正本含 board.json 也不得当数据根"

    def test_no_marker_legacy_still_works(self, tmp_path, monkeypatch):
        import paths
        fake_skill = tmp_path / "legacyskill"
        (fake_skill / "scripts").mkdir(parents=True)
        (fake_skill / "user_data").mkdir()
        (fake_skill / "user_data" / "board.json").write_text("[]", encoding="utf-8")
        # 无标记 → legacy 生效
        monkeypatch.setattr(paths, "_SCRIPT_DIR", str(fake_skill / "scripts"))
        got = paths.resolve_data_root(env={}, cwd=str(tmp_path / "elsewhere"))
        assert got == str(fake_skill)


class TestInstallerGuards:
    """install_global 守卫逻辑（source-grep，不实际联网安装）"""

    def test_installer_refuses_polluted_canonical(self):
        with open(os.path.join(REPO_ROOT, "scripts", "install_global.sh"), encoding="utf-8") as f:
            src = f.read()
        assert "user_data/board.json" in src, "安装器必须含正本污染守卫"
        assert ".yy-flow-shared" in src, "安装器必须写入共享标记"
        assert "degit" in src and "tar.gz" in src, "degit + tarball 双通道"

    def test_installer_ps1_same_guards(self):
        with open(os.path.join(REPO_ROOT, "scripts", "install_global.ps1"), encoding="utf-8") as f:
            src = f.read()
        assert "user_data\\board.json" in src
        assert ".yy-flow-shared" in src
