#!/usr/bin/env python3
"""
文件锁超时语义回归测试 (File Lock Timeout Regression Tests)

覆盖 _lib/core/file_lock.py 的核心契约：
  1. blocking + timeout：锁被占用时必须在约 timeout 秒后抛 LockBusyError，
     而不是无限挂起（回归：_lock_blocking 曾用纯阻塞式 flock/LK_LOCK 实现，
     timeout 参数为死代码，调用方误以为 fail-closed 实则永久阻塞）
  2. blocking + timeout=0：无限等待语义保持，持有者释放后能拿到锁
  3. 非阻塞模式：锁被占用时立即抛 LockBusyError
  4. 基本加锁/释放往返与 with 上下文管理

注意：用线程模拟“另一持有者”（两次 open() 得到独立的文件描述符，
flock 跨线程互斥生效）。若实现退化为纯阻塞式，第 1 个用例将永远挂起。
"""
import os
import sys
import threading
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from _lib.core import file_lock
from _lib.core.file_lock import LockBusyError, acquire_lock, release_lock


@pytest.fixture
def lock_path(tmp_path):
    return str(tmp_path / "test.lock")


def _hold_lock_in_thread(lock_path, hold_seconds, ready):
    """在子线程中持有锁 hold_seconds 秒，用于模拟锁竞争。"""
    handle = acquire_lock(lock_path, blocking=False)
    ready.set()
    try:
        time.sleep(hold_seconds)
    finally:
        release_lock(handle)


def test_blocking_timeout_raises_lockbusy(lock_path):
    """锁被占用时，blocking + timeout 必须约 timeout 后抛 LockBusyError。"""
    ready = threading.Event()
    t = threading.Thread(
        target=_hold_lock_in_thread, args=(lock_path, 5.0, ready), daemon=True
    )
    t.start()
    assert ready.wait(timeout=5), "持有者线程未能及时拿到锁"

    start = time.time()
    with pytest.raises(LockBusyError):
        acquire_lock(lock_path, blocking=True, timeout=1.0)
    elapsed = time.time() - start

    assert elapsed < 3.0, f"timeout=1.0 却耗时 {elapsed:.2f}s，疑似退化为无限阻塞"
    t.join(timeout=6)


def test_blocking_no_timeout_waits_until_released(lock_path):
    """timeout=0（无限等待）语义保持：持有者释放后能拿到锁。"""
    ready = threading.Event()
    t = threading.Thread(
        target=_hold_lock_in_thread, args=(lock_path, 1.0, ready), daemon=True
    )
    t.start()
    assert ready.wait(timeout=5)

    start = time.time()
    handle = acquire_lock(lock_path, blocking=True, timeout=0)
    elapsed = time.time() - start
    try:
        assert elapsed < 5.0, "持有者已释放但无限等待未返回"
    finally:
        release_lock(handle)
    t.join(timeout=6)


def test_nonblocking_raises_immediately(lock_path):
    """非阻塞模式下锁被占用时立即抛 LockBusyError。"""
    ready = threading.Event()
    t = threading.Thread(
        target=_hold_lock_in_thread, args=(lock_path, 2.0, ready), daemon=True
    )
    t.start()
    assert ready.wait(timeout=5)

    start = time.time()
    with pytest.raises(LockBusyError):
        acquire_lock(lock_path, blocking=False)
    assert time.time() - start < 1.0, "非阻塞获取不应等待"
    t.join(timeout=5)


def test_acquire_release_roundtrip(lock_path):
    """基本加锁/释放往返：释放后可重新获取；with 上下文自动释放。"""
    handle = acquire_lock(lock_path)
    release_lock(handle)

    with acquire_lock(lock_path) as h2:
        assert h2 is not None
        assert os.path.exists(lock_path)
    # with 退出后锁已释放，能再次非阻塞拿到
    h3 = acquire_lock(lock_path, blocking=False)
    release_lock(h3)
