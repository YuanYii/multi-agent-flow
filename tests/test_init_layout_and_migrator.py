#!/usr/bin/env python3
"""
测试工程初始化布局收敛与文档迁移防护：
1. 校验 scan_and_migrate_legacy_docs 排除 .yy-flow 及目标文档目录自身
2. 校验在包含已存在文档目录（如 项目文档）的项目中，docs_root 正确探测
3. 校验 init_skill.sh 执行后：
   - 数据根位于 <proj>/.yy-flow
   - .gitignore 包含 .yy-flow/
   - 宿主项目根无残留 user_data/
   - 历史文档直接落到已存在的文档目录（如 项目文档/），不生成多余 docs/
"""

import os
import subprocess
import pytest
import paths
from _lib.discovery.legacy_migrator import scan_and_migrate_legacy_docs, EXCLUDE_DIRS


def test_exclude_dirs_contains_yyflow():
    assert ".yy-flow" in EXCLUDE_DIRS
    assert ".yy-flow-shared" in EXCLUDE_DIRS


def test_migrator_does_not_scan_custom_docs_or_yyflow(tmp_path, monkeypatch):
    """验证扫描迁移历史文档时，绝不重复扫描目标文档目录或 .yy-flow 目录"""
    proj = tmp_path / "my_proj"
    proj.mkdir()
    
    # 模拟项目文档目录
    docs = proj / "项目文档"
    docs.mkdir()
    (docs / "existing_doc.md").write_text("# Existing Doc", encoding="utf-8")
    
    # 模拟 .yy-flow 目录
    yyflow = proj / ".yy-flow"
    (yyflow / "user_data").mkdir(parents=True)
    (yyflow / "user_data" / "some_internal.md").write_text("internal", encoding="utf-8")
    
    # 模拟项目根散落历史文档
    (proj / "scattered_arch.md").write_text("# System Architecture Design", encoding="utf-8")

    fake_skill = tmp_path / "fakeskill"
    (fake_skill / "scripts").mkdir(parents=True)
    monkeypatch.setattr(paths, "_SCRIPT_DIR", str(fake_skill / "scripts"))
    monkeypatch.setenv("YY_FLOW_PROJECT_ROOT", str(yyflow))
    
    migrated = scan_and_migrate_legacy_docs(project_root=str(proj))
    
    migrated_srcs = [m[0] for m in migrated]
    # 必须迁移项目根的散落文档
    assert any("scattered_arch.md" in s for s in migrated_srcs)
    # 绝不能迁移目标项目文档或 .yy-flow 内的文件
    assert not any("existing_doc.md" in s for s in migrated_srcs)
    assert not any("some_internal.md" in s for s in migrated_srcs)


def test_init_skill_sh_execution(tmp_path):
    """测试 init_skill.sh 在目标宿主项目中的执行行为"""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    init_script = os.path.join(repo_root, "scripts", "init_skill.sh")
    
    proj = tmp_path / "test_host_proj"
    proj.mkdir()
    
    # 创建模拟 git 仓库
    (proj / ".git").mkdir()
    (proj / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    
    # 创建已有文档目录及文档
    (proj / "项目文档").mkdir()
    (proj / "项目文档" / "spec.md").write_text("# Product Spec", encoding="utf-8")
    
    # 模拟旧逻辑误建的残留 user_data/
    (proj / "user_data").mkdir()
    (proj / "user_data" / "stray.txt").write_text("stray data", encoding="utf-8")

    # 清理环境变量中的 YY_FLOW_PROJECT_ROOT
    clean_env = {k: v for k, v in os.environ.items() if k != "YY_FLOW_PROJECT_ROOT"}

    # 在该项目根下执行 init_skill.sh
    res = subprocess.run(
        ["bash", init_script],
        cwd=str(proj),
        capture_output=True,
        text=True,
        env=clean_env
    )
    assert res.returncode == 0, f"init_skill.sh failed:\nSTDERR: {res.stderr}\nSTDOUT: {res.stdout}"

    # 1. 验证 .yy-flow/ 被写入 .gitignore
    gitignore_content = (proj / ".gitignore").read_text(encoding="utf-8")
    assert ".yy-flow/" in gitignore_content

    # 2. 验证宿主项目根无残留 user_data/
    assert not (proj / "user_data").exists()

    # 3. 验证数据已收敛至 <proj>/.yy-flow/user_data
    assert (proj / ".yy-flow" / "user_data").is_dir()
    assert (proj / ".yy-flow" / "user_data" / "board.json").is_file()
    assert (proj / ".yy-flow" / "user_data" / "workflow.config.yaml").is_file()
    assert (proj / ".yy-flow" / "user_data" / "stray.txt").is_file()

    # 4. 验证任务分卷收敛至 .yy-flow/user_data/tasks，且由于宿主已有文档目录规范，未强行注入 D01~D06
    assert not (proj / "docs").exists()
    assert (proj / ".yy-flow" / "user_data" / "tasks").is_dir()
    assert (proj / ".yy-flow" / "user_data" / "tasks" / "tasks_0001_0050.yaml").is_file()
    assert not (proj / "项目文档" / "D01-项目管理").exists()
    assert not (proj / "项目文档" / "D04-研发过程").exists()


def test_init_skill_sh_on_fresh_project_creates_docs_skeleton(tmp_path):
    """测试在完全无既有文档的空白项目中，init_skill.sh 建立默认推荐文档骨架"""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    init_script = os.path.join(repo_root, "scripts", "init_skill.sh")

    proj = tmp_path / "fresh_proj"
    proj.mkdir()
    (proj / ".git").mkdir()

    clean_env = {k: v for k, v in os.environ.items() if k != "YY_FLOW_PROJECT_ROOT"}
    res = subprocess.run(
        ["bash", init_script],
        cwd=str(proj),
        capture_output=True,
        text=True,
        env=clean_env
    )
    assert res.returncode == 0

    # 空白项目建立 docs/ 默认推荐骨架
    assert (proj / "docs" / "D01-项目管理" / "D01-需求").is_dir()
    # 任务分卷依然干净落入 .yy-flow/user_data/tasks
    assert (proj / ".yy-flow" / "user_data" / "tasks" / "tasks_0001_0050.yaml").is_file()


def test_migration_from_legacy_docs_tasks_to_user_data_tasks(tmp_path, monkeypatch):
    """验证从旧路径 docs/D04-研发过程/D01-任务 存量分卷自动平滑迁移至 user_data/tasks/"""
    from migrate_to_chunked_storage import migrate_to_chunked_storage
    proj = tmp_path / "legacy_proj"
    proj.mkdir()

    # 模拟旧版存量文档路径与任务分卷
    old_tasks_dir = proj / "docs" / "D04-研发过程" / "D01-任务"
    old_tasks_dir.mkdir(parents=True)
    legacy_chunk = {
        "metadata": {"chunk_id": "tasks_0001_0050", "start_seq": 1, "end_seq": 50},
        "tasks": [
            {"id": "T0001", "name": "历史任务1", "status": "已完成", "seq": 1},
            {"id": "T0002", "name": "历史任务2", "status": "待开始", "seq": 2}
        ]
    }
    import yaml
    with open(old_tasks_dir / "tasks_0001_0050.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(legacy_chunk, f)

    fake_skill = tmp_path / "fakeskill"
    (fake_skill / "scripts").mkdir(parents=True)
    monkeypatch.setattr(paths, "_SCRIPT_DIR", str(fake_skill / "scripts"))
    monkeypatch.setenv("YY_FLOW_PROJECT_ROOT", str(proj / ".yy-flow"))
    monkeypatch.chdir(proj)

    ok = migrate_to_chunked_storage(project_root=str(proj))
    assert ok

    # 验证任务已合并归集至新版 .yy-flow/user_data/tasks/
    new_chunk = proj / ".yy-flow" / "user_data" / "tasks" / "tasks_0001_0050.yaml"
    assert new_chunk.is_file()
    with open(new_chunk, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    tids = [t["id"] for t in data.get("tasks", [])]
    assert "T0001" in tids
    assert "T0002" in tids
