#!/usr/bin/env python3
"""
跨平台排他文件锁抽象 (Cross-Platform File Lock Abstraction)

统一 fcntl (Unix/macOS/Linux) 与 msvcrt (Windows) 两种文件锁实现，
供并发门控锁与看板 seq 锁复用，业务代码零平台分支。

设计要点：
1. acquire_lock(): 加锁（阻塞/非阻塞），加锁成功后写入持有者元数据 (pid + ts)；
2. release_lock(): 解锁并关闭句柄；【不删除锁文件】——删除必须走 remove_lock_file_if_free；
3. remove_lock_file_if_free(): 先非阻塞试锁，确认无持有者后【持锁状态下 unlink】——
   并发进程在 unlink 后只能创建新 inode 文件，互斥性不因删除被破坏；
4. 绝不删除正在被持有的锁文件（删除持锁文件会让两个进程各持一把锁，破坏排他）。
"""
import os
import sys
import time


class LockBusyError(Exception):
    """锁已被其他进程持有（非阻塞获取失败或阻塞超时）"""


def _ensure_nonempty(f):
    """Windows msvcrt 字节区间锁要求文件至少 1 字节；Unix flock 无此要求但保持行为一致。"""
    f.seek(0, os.SEEK_END)
    if f.tell() == 0:
        f.write(b"\x00")
        f.flush()
    f.seek(0)


def _lock_nonblocking(f):
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _lock_blocking(f):
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)


def _unlock(f):
    try:
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass


def _write_meta(f):
    """在锁内写入持有者元数据 (pid + 时间戳)，便于排查僵尸锁。"""
    try:
        f.seek(0)
        f.truncate()
        f.write(f"pid={os.getpid()} ts={int(time.time())}\n".encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    except Exception:
        pass


class LockHandle:
    """锁句柄：path = 锁文件路径, file = 底层文件对象"""

    __slots__ = ("path", "file")

    def __init__(self, path, f):
        self.path = path
        self.file = f


def acquire_lock(lock_path, blocking=False, timeout=0.0, write_meta=True):
    """获取排他锁。

    :param lock_path: 锁文件路径
    :param blocking: True=阻塞等待; False=非阻塞（拿不到立即抛 LockBusyError）
    :param timeout: blocking=True 时的最大等待秒数（0=无限等待）
    :param write_meta: 加锁成功后是否写入 pid/ts 元数据
    :return: LockHandle
    :raises LockBusyError: 非阻塞获取失败或阻塞超时
    """
    lock_path = os.path.abspath(lock_path)
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    deadline = (time.time() + timeout) if (blocking and timeout > 0) else None
    while True:
        f = open(lock_path, "a+b")
        try:
            _ensure_nonempty(f)
            try:
                if blocking:
                    _lock_blocking(f)
                else:
                    _lock_nonblocking(f)
            except OSError:
                f.close()
                if not blocking:
                    raise LockBusyError(lock_path)
                if deadline is not None and time.time() >= deadline:
                    raise LockBusyError(lock_path)
                time.sleep(0.05)
                continue
            if write_meta:
                _write_meta(f)
            return LockHandle(lock_path, f)
        except Exception:
            try:
                f.close()
            except Exception:
                pass
            raise


def release_lock(handle):
    """释放锁并关闭句柄。注意：不删除锁文件；删除请使用 remove_lock_file_if_free。"""
    if handle is None:
        return
    f = getattr(handle, "file", None)
    if f is not None:
        _unlock(f)
        try:
            f.close()
        except Exception:
            pass
    handle.file = None


def remove_lock_file_if_free(lock_path):
    """仅当锁文件当前无持有者时才删除。

    实现：非阻塞试锁成功 → 【持锁状态下 os.remove】 → 释放。
    持锁 unlink 保证：unlink 后其他进程打开该路径只会得到新 inode，
    已持旧 inode 锁的进程与新锁进程不会同时互斥失效。
    返回 True=已删除, False=有持有者或删除失败。
    """
    lock_path = os.path.abspath(lock_path)
    if not os.path.exists(lock_path):
        return False
    handle = None
    try:
        handle = acquire_lock(lock_path, blocking=False, write_meta=False)
    except LockBusyError:
        return False
    except Exception:
        return False
    try:
        os.remove(lock_path)
        return True
    except Exception:
        return False
    finally:
        release_lock(handle)


def read_lock_meta(lock_path):
    """读取锁文件元数据 {pid, ts}；文件不存在或不可读时返回空 dict。"""
    try:
        with open(lock_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(256)
        meta = {}
        for part in content.split():
            if part.startswith("pid="):
                try:
                    meta["pid"] = int(part.split("=", 1)[1])
                except ValueError:
                    pass
            elif part.startswith("ts="):
                try:
                    meta["ts"] = int(part.split("=", 1)[1])
                except ValueError:
                    pass
        return meta
    except Exception:
        return {}
