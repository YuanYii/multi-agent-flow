import os
import sys
import json
import yaml
import shutil
import tempfile
import pytest

_SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from start_kanban_server import _check_and_auto_migrate_to_chunked
from _lib.boards.chunked_board_adapter import ChunkedBoardAdapter


@pytest.fixture
def sandbox_env():
    """建立隔离测试沙箱"""
    tmp_dir = tempfile.mkdtemp(prefix="kanban_test_")
    user_data_dir = os.path.join(tmp_dir, "user_data")
    os.makedirs(user_data_dir, exist_ok=True)
    tasks_dir = os.path.join(user_data_dir, "tasks")
    os.makedirs(tasks_dir, exist_ok=True)
    legacy_tasks_dir = os.path.join(tmp_dir, "docs", "D04-研发过程", "D01-任务")
    os.makedirs(legacy_tasks_dir, exist_ok=True)
    cfg_path = os.path.join(user_data_dir, "workflow.config.yaml")

    yield {
        "root": tmp_dir,
        "user_data": user_data_dir,
        "tasks_dir": tasks_dir,
        "legacy_tasks_dir": legacy_tasks_dir,
        "config_path": cfg_path,
    }

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_startup_migration_from_single_board_json(sandbox_env, monkeypatch):
    """测试当存在存量 board.json 且为 single 模式时，看板启动自动完成迁移与配置升级"""
    root = sandbox_env["root"]
    user_data = sandbox_env["user_data"]
    tasks_dir = sandbox_env["tasks_dir"]
    cfg_path = sandbox_env["config_path"]

    # 1. 初始化存量配置与 board.json
    cfg = {
        "board": {
            "provider": "local",
            "storage_mode": "single",
            "board_file": "user_data/board.json",
        }
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)

    legacy_tasks = [
        {"id": "T0001", "name": "历史单体任务1", "status": "待开始", "type": "A"},
        {"id": "T0002", "name": "历史单体任务2", "status": "进行中", "type": "B"},
    ]
    board_json = os.path.join(user_data, "board.json")
    with open(board_json, "w", encoding="utf-8") as f:
        json.dump(legacy_tasks, f)

    # 拦截 paths
    import paths
    monkeypatch.setattr(paths, "resolve_data_root", lambda **kw: root)
    monkeypatch.setattr(paths, "project_root", lambda **kw: root)
    monkeypatch.setattr(paths, "tasks_dir", lambda **kw: tasks_dir)
    monkeypatch.setattr(paths, "resolve_runtime_config", lambda **kw: cfg_path)

    # 2. 执行启动自愈检查
    ok = _check_and_auto_migrate_to_chunked(data_root=root)
    assert ok is True

    # 3. 验证分卷生成
    chunk_file = os.path.join(tasks_dir, "tasks_0001_0050.yaml")
    assert os.path.exists(chunk_file)
    with open(chunk_file, "r", encoding="utf-8") as f:
        cdata = yaml.safe_load(f)
    assert len(cdata["tasks"]) == 2
    assert cdata["tasks"][0]["id"] == "T0001"
    assert cdata["tasks"][0]["tier"] == "Tier-1"
    assert cdata["tasks"][1]["id"] == "T0002"
    assert cdata["tasks"][1]["tier"] == "Tier-2"

    # 4. 验证配置被自动升级为 chunked
    with open(cfg_path, "r", encoding="utf-8") as f:
        up_cfg = yaml.safe_load(f)
    assert up_cfg["board"]["storage_mode"] == "chunked"

    # 5. 验证原 board.json 被安全移走/重命名备份
    assert not os.path.exists(board_json)
    bak_files = [f for f in os.listdir(user_data) if f.startswith("board.json.bak.")]
    assert len(bak_files) == 1


def test_startup_migration_from_weekly_yaml_and_archive(sandbox_env, monkeypatch):
    """测试当存在存量自然周 YYYY-Www.yaml 时，看板启动自动合并至分卷并将周文件归档至 archive_weekly"""
    root = sandbox_env["root"]
    user_data = sandbox_env["user_data"]
    tasks_dir = sandbox_env["tasks_dir"]
    cfg_path = sandbox_env["config_path"]

    cfg = {
        "board": {
            "provider": "local",
            "storage_mode": "weekly",
        }
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)

    weekly_file = os.path.join(tasks_dir, "2026-W36.yaml")
    w_tasks = [
        {"id": "T0001", "name": "周维度任务1", "status": "待开始", "type": "A"},
        {"id": "T0002", "name": "周维度任务2", "status": "已完成", "type": "C"},
    ]
    with open(weekly_file, "w", encoding="utf-8") as f:
        yaml.safe_dump({"tasks": w_tasks}, f)

    import paths
    monkeypatch.setattr(paths, "resolve_data_root", lambda **kw: root)
    monkeypatch.setattr(paths, "project_root", lambda **kw: root)
    monkeypatch.setattr(paths, "tasks_dir", lambda **kw: tasks_dir)
    monkeypatch.setattr(paths, "resolve_runtime_config", lambda **kw: cfg_path)

    ok = _check_and_auto_migrate_to_chunked(data_root=root)
    assert ok is True

    # 验证新分卷已生成
    chunk_file = os.path.join(tasks_dir, "tasks_0001_0050.yaml")
    assert os.path.exists(chunk_file)

    # 验证原周文件被移入 archive_weekly
    assert not os.path.exists(weekly_file)
    archived_file = os.path.join(tasks_dir, "archive_weekly", "2026-W36.yaml")
    assert os.path.exists(archived_file)

    # 验证 ChunkedBoardAdapter 检索不会出现重复任务
    adapter = ChunkedBoardAdapter(tasks_dir=tasks_dir)
    recs = adapter.list_records()
    assert len(recs) == 2


def test_startup_migration_short_circuit_when_already_chunked(sandbox_env, monkeypatch):
    """测试已升级至 chunked 模式后，启动检查瞬间短路返回，零开销"""
    root = sandbox_env["root"]
    cfg_path = sandbox_env["config_path"]

    cfg = {
        "board": {
            "provider": "local",
            "storage_mode": "chunked",
        }
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)

    import paths
    monkeypatch.setattr(paths, "resolve_data_root", lambda **kw: root)
    monkeypatch.setattr(paths, "resolve_runtime_config", lambda **kw: cfg_path)

    # 短路返回 True
    ok = _check_and_auto_migrate_to_chunked(data_root=root)
    assert ok is True


def test_startup_migration_skips_remote_provider(sandbox_env, monkeypatch):
    """测试远程看板模式（如 feishu_base）绝不触发本地分卷迁移"""
    root = sandbox_env["root"]
    user_data = sandbox_env["user_data"]
    tasks_dir = sandbox_env["tasks_dir"]
    cfg_path = sandbox_env["config_path"]

    cfg = {
        "board": {
            "provider": "feishu_base",
            "base_token": "token123",
            "table_id": "tbl123",
        }
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)

    # 即使残留了 board.json
    board_json = os.path.join(user_data, "board.json")
    with open(board_json, "w", encoding="utf-8") as f:
        json.dump([{"id": "T0001", "name": "残留数据"}], f)

    import paths
    monkeypatch.setattr(paths, "resolve_data_root", lambda **kw: root)
    monkeypatch.setattr(paths, "resolve_runtime_config", lambda **kw: cfg_path)
    monkeypatch.setattr(paths, "tasks_dir", lambda **kw: tasks_dir)

    ok = _check_and_auto_migrate_to_chunked(data_root=root)
    assert ok is True

    # 验证原 board.json 完全未被触碰，未生成 chunked 分卷
    assert os.path.exists(board_json)
    chunk_file = os.path.join(tasks_dir, "tasks_0001_0050.yaml")
    assert not os.path.exists(chunk_file)
