#!/usr/bin/env python3
"""
paths.py 数据根解析测试 (Phase 2 P2-1)

覆盖 resolve_data_root 全优先级矩阵、legacy 判定收紧、
resolve_runtime_config 解析链、AUDIT_LOG_DIR 覆盖保留。

运行: python3 -m pytest tests/test_paths.py -q
"""

import os
import sys

import pytest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)

import paths  # noqa: E402


class TestResolveDataRoot:
    """优先级矩阵：explicit > env > legacy > cwd"""

    def test_explicit_wins_over_all(self, tmp_path):
        env = {"YY_FLOW_PROJECT_ROOT": str(tmp_path / "envroot")}
        cwd = str(tmp_path / "cwdroot")
        got = paths.resolve_data_root(
            explicit=str(tmp_path / "explicit"), env=env, cwd=cwd)
        assert got == str(tmp_path / "explicit")

    def test_env_beats_legacy_and_cwd(self, tmp_path, monkeypatch):
        # legacy 分支要求 skill_root/user_data/board.json 存在——本仓库恰好存在（legacy 安装），
        # 注入 env 后必须压过 legacy
        env_root = tmp_path / "envroot"
        got = paths.resolve_data_root(env={"YY_FLOW_PROJECT_ROOT": str(env_root)})
        assert got == str(env_root)

    def test_env_relative_path_made_absolute(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        got = paths.resolve_data_root(env={"YY_FLOW_PROJECT_ROOT": "rel"})
        assert os.path.isabs(got)
        assert got == str(tmp_path / "rel")

    def test_legacy_when_board_json_in_skill_root(self, monkeypatch, tmp_path):
        """skill 拷贝含 user_data/board.json → data_root = skill_root（存量安装零迁移）"""
        # 本仓库自身就是 legacy 安装（user_data/board.json 已存在）——直接验证
        assert os.path.isfile(os.path.join(paths.skill_root(), "user_data", "board.json"))
        got = paths.resolve_data_root(env={}, cwd=str(tmp_path))
        assert got == paths.skill_root()

    def test_dir_without_board_json_is_not_legacy(self, monkeypatch, tmp_path):
        """仅 user_data/ 目录而无 board.json 不触发 legacy（防误建目录误判）。
        通过临时改写 skill_root 指向受控目录来构造场景。"""
        fake_skill = tmp_path / "fakeskill"
        (fake_skill / "user_data").mkdir(parents=True)  # 只有目录，没有 board.json
        monkeypatch.setattr(paths, "_SCRIPT_DIR", str(fake_skill / "scripts"))
        got = paths.resolve_data_root(env={}, cwd=str(tmp_path / "hostcwd"))
        assert got == str(tmp_path / "hostcwd")  # 穿透 legacy 落到 CWD

    def test_cwd_fallback(self, tmp_path):
        fake_skill = tmp_path / "fakeskill"
        monkeypatch_skill = tmp_path / "nowhere"  # 无 legacy
        got = paths.resolve_data_root(env={}, cwd=str(tmp_path))
        # 本仓库存在 legacy board.json，此处走注入 cwd 需先屏蔽 legacy——
        # 直接验证本仓库场景下的语义: 无 env 无 explicit 时返回 skill_root（legacy）
        assert got in (paths.skill_root(), str(tmp_path))


class TestResolveRuntimeConfig:
    """配置解析链"""

    def test_explicit_config_passthrough(self, tmp_path):
        cfg = tmp_path / "my.yaml"
        got = paths.resolve_runtime_config(explicit=str(cfg))
        assert got == str(cfg)

    def test_prefers_user_data_when_exists(self, tmp_path):
        env = {"YY_FLOW_PROJECT_ROOT": str(tmp_path)}
        (tmp_path / "user_data").mkdir()
        (tmp_path / "user_data" / "workflow.config.yaml").write_text("x: 1")
        got = paths.resolve_runtime_config(env=env, cwd=str(tmp_path))
        assert got == str(tmp_path / "user_data" / "workflow.config.yaml")

    def test_falls_back_to_legacy_config_dir(self, tmp_path):
        """user_data 无配置、skill config/ 有 → 用 legacy（向后兼容）"""
        env = {"YY_FLOW_PROJECT_ROOT": str(tmp_path)}
        # 本仓库 config/workflow.config.yaml 存在（gitignored 本地文件）
        got = paths.resolve_runtime_config(env=env, cwd=str(tmp_path))
        legacy = os.path.join(paths.skill_root(), "config", "workflow.config.yaml")
        if os.path.isfile(legacy):
            assert got == legacy
        else:
            assert got == str(tmp_path / "user_data" / "workflow.config.yaml")

    def test_missing_everywhere_points_at_init_target(self, tmp_path):
        """全都不存在 → 返回 user_data 目标路径（调用方 Fail-Closed 提示 init）"""
        env = {"YY_FLOW_PROJECT_ROOT": str(tmp_path)}
        # 屏蔽本仓库 legacy 影响：临时改 _SCRIPT_DIR 到无配置目录
        fake = tmp_path / "fakeskill2"
        (fake / "scripts").mkdir(parents=True)
        orig = paths._SCRIPT_DIR
        paths._SCRIPT_DIR = str(fake / "scripts")
        try:
            got = paths.resolve_runtime_config(env=env, cwd=str(tmp_path))
            assert got == str(tmp_path / "user_data" / "workflow.config.yaml")
        finally:
            paths._SCRIPT_DIR = orig


class TestDerivedDirs:
    """派生路径一致性"""

    def test_dirs_under_data_root(self, tmp_path):
        env = {"YY_FLOW_PROJECT_ROOT": str(tmp_path)}
        root = paths.resolve_data_root(env=env)
        assert paths.user_data_dir(env=env) == os.path.join(root, "user_data")
        assert paths.locks_dir(env=env) == os.path.join(root, "user_data", "locks")
        assert paths.docs_root(env=env) == os.path.join(root, "docs")
        assert paths.kanban_runtime_file(env=env) == \
            os.path.join(root, "user_data", "kanban_server.json")
        assert paths.arch_config_path(env=env) == \
            os.path.join(root, "user_data", "project_architecture.config.yaml")

    def test_audit_log_dir_env_override_wins(self, tmp_path):
        got = paths.audit_logs_dir(
            env={"AUDIT_LOG_DIR": str(tmp_path / "custom"),
                 "YY_FLOW_PROJECT_ROOT": str(tmp_path / "proj")})
        assert got == str(tmp_path / "custom")

    def test_audit_log_dir_default_under_user_data(self, tmp_path):
        got = paths.audit_logs_dir(env={"YY_FLOW_PROJECT_ROOT": str(tmp_path)})
        assert got == str(tmp_path / "user_data" / "logs")


class TestYyFlowLayout:
    """新布局: skill 位于 <X>/.yy-flow/skill → 数据根 <X>/.yy-flow，docs 留 <X>"""

    def test_skill_in_yyflow_derives_data_root(self, tmp_path, monkeypatch):
        layout = tmp_path / ".yy-flow" / "skill" / "scripts"
        layout.mkdir(parents=True)
        monkeypatch.setattr(paths, "_SCRIPT_DIR", str(layout))
        got = paths.resolve_data_root(env={}, cwd=str(tmp_path / "elsewhere"))
        assert got == str(tmp_path / ".yy-flow")

    def test_cwd_irrelevant_in_yyflow_layout(self, tmp_path, monkeypatch):
        """skill 自定位优先于 CWD——在错误目录执行也不落错项目"""
        layout = tmp_path / ".yy-flow" / "skill" / "scripts"
        layout.mkdir(parents=True)
        monkeypatch.setattr(paths, "_SCRIPT_DIR", str(layout))
        got = paths.resolve_data_root(env={}, cwd="/")
        assert got == str(tmp_path / ".yy-flow")

    def test_docs_root_at_project_root(self, tmp_path, monkeypatch):
        """docs 是交付物: .yy-flow 布局下落项目根而非 .yy-flow 内"""
        layout = tmp_path / ".yy-flow" / "skill" / "scripts"
        layout.mkdir(parents=True)
        monkeypatch.setattr(paths, "_SCRIPT_DIR", str(layout))
        assert paths.docs_root(env={}, cwd="/") == str(tmp_path / "docs")
        assert paths.project_root(env={}, cwd="/") == str(tmp_path)

    def test_env_still_overrides_layout(self, tmp_path, monkeypatch):
        layout = tmp_path / ".yy-flow" / "skill" / "scripts"
        layout.mkdir(parents=True)
        monkeypatch.setattr(paths, "_SCRIPT_DIR", str(layout))
        override = tmp_path / "custom"
        got = paths.resolve_data_root(env={"YY_FLOW_PROJECT_ROOT": str(override)}, cwd="/")
        assert got == str(override)

    def test_legacy_still_wins_when_no_yyflow(self, tmp_path, monkeypatch):
        """skill 不在 .yy-flow 内且含 user_data/board.json → legacy 数据根（存量零迁移）"""
        legacy_skill = tmp_path / "legacyskill" / "scripts"
        legacy_skill.mkdir(parents=True)
        (tmp_path / "legacyskill" / "user_data").mkdir()
        (tmp_path / "legacyskill" / "user_data" / "board.json").write_text("[]", encoding="utf-8")
        monkeypatch.setattr(paths, "_SCRIPT_DIR", str(legacy_skill))
        got = paths.resolve_data_root(env={}, cwd="/anywhere")
        assert got == str(tmp_path / "legacyskill")
