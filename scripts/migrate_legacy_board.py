#!/usr/bin/env python3
"""
存量看板数据平滑迁移工具（向后兼容转发入口）

说明:
该存量数据迁移工具已归档至 scripts/migrations/migrate_legacy_board.py。
本文件保留用于兼容历史脚本调用。
"""
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MIGRATIONS_DIR = os.path.join(_SCRIPT_DIR, "migrations")
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
if _MIGRATIONS_DIR not in sys.path:
    sys.path.insert(0, _MIGRATIONS_DIR)

from migrations.migrate_legacy_board import (
    migrate_board_data,
    resolve_week_cycle,
    get_current_week_info,
    atomic_write_yaml,
)

if __name__ == "__main__":
    ok = migrate_board_data()
    sys.exit(0 if ok else 1)
