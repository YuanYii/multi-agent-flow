"""看板损坏文件保护、锁超时和 Web 持久化完整性的回归测试。"""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from _lib.boards.offline_board_adapter import OfflineBoardAdapter
from _lib.core import file_lock


@pytest.mark.parametrize("damaged", ['[{"id":"T0001"},', '{"wrong": "shape"}'])
def test_write_does_not_replace_damaged_board(tmp_path, damaged):
    board = tmp_path / "board.json"
    board.write_text(damaged, encoding="utf-8")
    adapter = OfflineBoardAdapter(str(board))
    with pytest.raises((ValueError, json.JSONDecodeError)):
        adapter.create_record({"name": "新任务"})
    assert board.read_text(encoding="utf-8") == damaged


def test_contended_lock_honors_timeout(tmp_path):
    lock_file = str(tmp_path / "busy.lock")
    scripts = str(Path(__file__).resolve().parents[1] / "scripts")
    child_code = """
import sys, time
sys.path.insert(0, sys.argv[1])
from _lib.core import file_lock
with file_lock.acquire_lock(sys.argv[2]):
    print('ready', flush=True)
    time.sleep(3)
"""
    child = subprocess.Popen([sys.executable, "-c", child_code, scripts, lock_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        started = time.monotonic()
        with pytest.raises(file_lock.LockBusyError):
            file_lock.acquire_lock(lock_file, blocking=True, timeout=0.15)
        assert time.monotonic() - started < 1.0
    finally:
        child.terminate()
        child.communicate(timeout=5)


def test_web_mutation_preserves_damaged_json(tmp_path, monkeypatch):
    import start_kanban_server as server
    board = tmp_path / "board.json"
    original = '[{"id":"T0001"},'
    board.write_text(original, encoding="utf-8")
    monkeypatch.setattr(server, "USER_DATA_BOARD", str(board))
    monkeypatch.setattr(server, "LOCK_FILE", str(tmp_path / "board.lock"))
    monkeypatch.setattr(server, "_is_weekly_storage_mode", lambda: False)
    called = []
    def mutate(cards):
        called.append(True)
        cards.append({"id": "T0002", "name": "新任务"})
        return True, 200, "ok", {}
    code, _, _ = server.atomic_mutate_board_data(mutate)
    assert code == 500
    assert not called
    assert board.read_text(encoding="utf-8") == original
