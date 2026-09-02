"""
基于 user_data/context/state_{task_id}.json 的原子持久化仓储
严格使用 paths.data_root() 解析物理路径，使用 file_lock 保障并发安全。
"""
import os
import re
import json
import time
from typing import Optional
import paths
from _lib.core.file_lock import acquire_lock, release_lock
from ..interfaces import IContextStateStore
from ..models import ContextState


def sanitize_task_id(task_id: str) -> str:
    """对 task_id 进行安全过滤，防止非法字符破坏文件路径与锁"""
    if not task_id:
        return "DEFAULT"
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', str(task_id).strip())


class JsonFileContextStore(IContextStateStore):
    def __init__(self):
        self.data_root = paths.data_root()
        self.context_dir = os.path.join(self.data_root, "user_data", "context")
        self.snapshot_dir = os.path.join(self.context_dir, "snapshots")
        os.makedirs(self.snapshot_dir, exist_ok=True)

    def _get_file_path(self, task_id: str) -> str:
        safe_id = sanitize_task_id(task_id)
        return os.path.join(self.context_dir, f"state_{safe_id}.json")

    def load(self, task_id: str) -> Optional[ContextState]:
        file_path = self._get_file_path(task_id)
        if not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ContextState.from_dict(data)
        except Exception:
            return None

    def save_with_cas(self, task_id: str, state: ContextState, expected_version: int) -> bool:
        safe_id = sanitize_task_id(task_id)
        file_path = self._get_file_path(task_id)
        locks_dir = paths.locks_dir()
        os.makedirs(locks_dir, exist_ok=True)
        lock_path = os.path.join(locks_dir, f"ccp_store_{safe_id}.lock")
        lock_handle = acquire_lock(lock_path, blocking=True, timeout=10.0)
        try:
            current = self.load(task_id)
            curr_ver = current.version if current else 0
            if curr_ver != expected_version:
                return False  # 版本冲突 (CAS 拦截)

            state.task_id = task_id
            state.version = expected_version + 1
            state.last_updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            
            # 写入临时文件后原子替换
            temp_path = file_path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
            os.replace(temp_path, file_path)
            return True
        finally:
            release_lock(lock_handle)

    def create_snapshot(self, task_id: str) -> str:
        safe_id = sanitize_task_id(task_id)
        state = self.load(task_id)
        if not state:
            raise ValueError(f"Task {task_id} ContextState 不存在，无法创建快照")
        snapshot_id = f"CTX-SNAP-{safe_id}-v{state.version}-{int(time.time())}"
        snap_path = os.path.join(self.snapshot_dir, f"{snapshot_id}.json")
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
        return snapshot_id
