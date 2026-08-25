#!/usr/bin/env python3
"""
看板文件 IO 共享内核 (Board File IO Kernel)

供 start_kanban_server.py（Web 服务自研 IO）与 _lib/boards/offline_board_adapter.py（离线适配器）
共同使用的"物理文件层"原语，消除双轨原子写/锁实现漂移。

职责边界（只做物理文件层，不掺业务语义）：
  - load_cards      : 读取 JSON 数组文件（容错 {"cards": [...]}），文件缺失/损坏返回空列表
  - board_lock      : 跨进程排他锁上下文管理器（基于 _lib/core/file_lock.py）
  - atomic_write    : 临时文件 + os.replace 原子替换写入（失败自动清理临时文件）

业务语义（由调用方各自负责，不得下沉到本模块）：
  - 字段结构/翻译、seq 分配或规范化、append-only 完整性断言
  - 内存缓存、HTTP 409 版本乐观锁
"""
import os
import sys
import json
import tempfile
from contextlib import contextmanager
from typing import Any, Dict, List

from _lib.core import file_lock


def load_cards(board_file: str) -> List[Dict[str, Any]]:
    """读取看板卡片（JSON 数组，兼容 {"cards": [...]} 包装）。文件缺失或解析失败返回 []。"""
    if not os.path.exists(board_file):
        return []
    try:
        with open(board_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("cards"), list):
            return data["cards"]
    except Exception:
        return []
    return []


@contextmanager
def board_lock(lock_file: str, timeout: float = 5.0):
    """跨进程排他锁上下文管理器；超时未获取到锁抛出异常（Fail-Closed）。"""
    handle = None
    try:
        handle = file_lock.acquire_lock(lock_file, blocking=True, timeout=timeout)
        yield
    finally:
        if handle:
            file_lock.release_lock(handle)


def atomic_write(board_file: str, cards: List[Dict[str, Any]]) -> bool:
    """tmp 临时文件 + os.replace 原子替换写入；任何异常返回 False 并清理临时文件。"""
    target_dir = os.path.dirname(os.path.abspath(board_file))
    os.makedirs(target_dir, exist_ok=True)
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".board_tmp_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cards, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, board_file)
        return True
    except Exception as e:
        sys.stderr.write(f"[ERROR] board_io.atomic_write failed: {e}\n")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False
