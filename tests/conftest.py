import os
import sys
import tempfile
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


@pytest.fixture(autouse=True)
def global_test_sandbox(tmp_path, monkeypatch):
    """
    全量单测沙箱隔离 Fixture (100% 保护生产 user_data 资产)
    每个测试用例均运行在独立的临时目录中，彻底杜绝单测污染或清空生产数据。
    """
    sandbox_dir = tmp_path / "sandbox_user_data"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = sandbox_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # 1. 临时看板文件
    sandbox_board = sandbox_dir / "board.json"
    sandbox_board.write_text("[]", encoding="utf-8")

    # 2. 隔离环境变量
    monkeypatch.setenv("AUDIT_LOG_DIR", str(logs_dir))
    monkeypatch.setenv("BOARD_STORAGE_PATH", str(sandbox_board))

    yield sandbox_dir
