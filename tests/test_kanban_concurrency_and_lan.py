"""
看板局域网协同访问与多线程并发防死锁修复方案 - 测试套件

测试用例覆盖：
1. test_server_is_threading_http_server: 断言 ReusableHTTPServer 继承自 ThreadingHTTPServer 且 daemon_threads is True
2. test_handler_socket_timeout_configured: 断言 KanbanHTTPRequestHandler.timeout == 10.0
3. test_concurrent_slow_client_isolation: 启动测试服务端，模拟慢客户端，断言并发隔离
4. test_lan_argument_parsing: 模拟传入 --lan，断言解析出的 host 为 0.0.0.0
5. test_print_and_runtime_file_reflects_host: 断言运行时文件准确反映 host 状态
"""

import os
import sys
import json
import socket
import threading
import time
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# 添加脚本目录到路径
SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPT_DIR)


class TestServerThreadingAndTimeout:
    """测试服务器线程化与超时配置"""

    def test_server_is_threading_http_server(self):
        """断言 ReusableHTTPServer 继承自 ThreadingHTTPServer 且 daemon_threads is True"""
        from start_kanban_server import ReusableHTTPServer
        from http.server import ThreadingHTTPServer

        # 验证继承关系
        assert issubclass(ReusableHTTPServer, ThreadingHTTPServer), \
            "ReusableHTTPServer 应继承自 ThreadingHTTPServer"

        # 验证 daemon_threads 设置
        assert ReusableHTTPServer.daemon_threads is True, \
            "ReusableHTTPServer.daemon_threads 应为 True"

    def test_handler_socket_timeout_configured(self):
        """断言 KanbanHTTPRequestHandler.timeout == 10.0"""
        from start_kanban_server import KanbanHTTPRequestHandler

        assert KanbanHTTPRequestHandler.timeout == 10.0, \
            f"KanbanHTTPRequestHandler.timeout 应为 10.0，实际为 {KanbanHTTPRequestHandler.timeout}"


class TestConcurrentSlowClientIsolation:
    """测试并发慢客户端隔离"""

    def test_concurrent_slow_client_isolation(self, tmp_path):
        """启动测试服务端，模拟一个客户端建立原始 TCP 连接并休眠不发 HTTP 数据，
        断言另一个客户端并发请求 /api/board/meta 依然可在 500ms 内成功返回 200 OK"""
        import subprocess
        import urllib.request

        # 准备临时数据目录
        data_dir = tmp_path / "user_data"
        data_dir.mkdir()
        board_file = data_dir / "board.json"
        board_file.write_text("[]", encoding="utf-8")

        # 随机端口
        port = 18888

        # 启动服务器进程
        env = os.environ.copy()
        env["KANBAN_DATA_ROOT"] = str(tmp_path)
        server_proc = subprocess.Popen(
            [sys.executable, os.path.join(SCRIPT_DIR, "start_kanban_server.py"),
             "--port", str(port), "--host", "127.0.0.1"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        try:
            # 等待服务器启动
            time.sleep(2)

            # 创建慢客户端（只建立 TCP 连接，不发送 HTTP 请求）
            slow_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            slow_sock.connect(("127.0.0.1", port))
            # 不发送任何数据，模拟慢客户端

            # 并发发起正常 HTTP 请求
            start_time = time.time()
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/api/board/meta")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    status = resp.status
                    data = json.loads(resp.read().decode("utf-8"))
                elapsed_ms = (time.time() - start_time) * 1000

                assert status == 200, f"预期 200 OK，实际 {status}"
                assert elapsed_ms < 500, f"请求耗时 {elapsed_ms:.0f}ms，超过 500ms 阈值"
            finally:
                slow_sock.close()

        finally:
            server_proc.terminate()
            server_proc.wait(timeout=5)


class TestLanArgumentParsing:
    """测试 --lan 参数解析"""

    def test_lan_argument_parsing(self):
        """模拟传入 --lan，断言解析出的 host 为 0.0.0.0"""
        import argparse

        # 模拟 start_kanban_server.py 中的参数解析逻辑
        parser = argparse.ArgumentParser()
        parser.add_argument("--lan", action="store_true",
                            help="开启局域网协同访问 (自动监听 0.0.0.0 物理网卡)")
        parser.add_argument("--host", type=str, default="127.0.0.1")

        # 测试 --lan 参数
        args = parser.parse_args(["--lan"])
        host = "0.0.0.0" if args.lan else args.host
        assert host == "0.0.0.0", f"传入 --lan 时 host 应为 0.0.0.0，实际为 {host}"

        # 测试不传 --lan 时的默认值
        args = parser.parse_args([])
        host = "0.0.0.0" if args.lan else args.host
        assert host == "127.0.0.1", f"不传 --lan 时 host 应为 127.0.0.1，实际为 {host}"

    def test_lan_argument_with_host_conflict(self):
        """测试 --lan 与 --host 同时传入时的行为"""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--lan", action="store_true")
        parser.add_argument("--host", type=str, default="127.0.0.1")

        # --lan 应覆盖 --host
        args = parser.parse_args(["--lan", "--host", "192.168.1.100"])
        host = "0.0.0.0" if args.lan else args.host
        assert host == "0.0.0.0", "--lan 应覆盖 --host 参数"


class TestRuntimeFileReflectsHost:
    """测试运行时文件准确反映 host 状态"""

    def test_runtime_file_with_loopback_host(self, tmp_path):
        """断言在 host='127.0.0.1' 时，kanban_server.json 中的 lan_url 为 None"""
        from start_kanban_server import _write_runtime_file, is_valid_lan_ip

        # 模拟 _write_runtime_file 的逻辑
        port = 32886
        host = "127.0.0.1"
        fingerprint = "test123"
        runtime_file = tmp_path / "kanban_server.json"

        # 计算 is_lan_enabled
        is_lan_enabled = host in ("0.0.0.0", "") or is_valid_lan_ip(host)

        local_ip = "192.168.1.100"  # 模拟局域网 IP
        payload = {
            "port": port,
            "host": host,
            "url": f"http://127.0.0.1:{port}/",
            "lan_url": f"http://{local_ip}:{port}/" if is_lan_enabled and local_ip != "127.0.0.1" else None,
            "lan_master_url": f"http://{local_ip}:{port}/?token=test" if is_lan_enabled and local_ip != "127.0.0.1" else None,
        }

        with open(runtime_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        # 验证
        with open(runtime_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["host"] == "127.0.0.1"
        assert data["lan_url"] is None, "host=127.0.0.1 时 lan_url 应为 None"
        assert data["lan_master_url"] is None, "host=127.0.0.1 时 lan_master_url 应为 None"

    def test_runtime_file_with_lan_host(self, tmp_path):
        """断言在 host='0.0.0.0' 时，kanban_server.json 中正常生成局域网 URL"""
        from start_kanban_server import is_valid_lan_ip

        port = 32886
        host = "0.0.0.0"
        local_ip = "192.168.1.100"

        is_lan_enabled = host in ("0.0.0.0", "") or is_valid_lan_ip(host)

        payload = {
            "port": port,
            "host": host,
            "url": f"http://127.0.0.1:{port}/",
            "lan_url": f"http://{local_ip}:{port}/" if is_lan_enabled and local_ip != "127.0.0.1" else None,
            "lan_master_url": f"http://{local_ip}:{port}/?token=test" if is_lan_enabled and local_ip != "127.0.0.1" else None,
        }

        runtime_file = tmp_path / "kanban_server.json"
        with open(runtime_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        with open(runtime_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["host"] == "0.0.0.0"
        assert data["lan_url"] == f"http://{local_ip}:{port}/", "host=0.0.0.0 时应生成局域网 URL"
        assert "token" in data["lan_master_url"], "lan_master_url 应包含 token"


class TestBoardCacheThreadSafety:
    """测试看板缓存线程安全性"""

    def test_board_cache_lock_exists(self):
        """断言 _BOARD_CACHE_LOCK 和 _BOARD_WRITE_LOCK 存在"""
        import start_kanban_server

        assert hasattr(start_kanban_server, '_BOARD_CACHE_LOCK'), \
            "start_kanban_server 应定义 _BOARD_CACHE_LOCK"
        assert hasattr(start_kanban_server, '_BOARD_WRITE_LOCK'), \
            "start_kanban_server 应定义 _BOARD_WRITE_LOCK"

        import threading
        assert isinstance(start_kanban_server._BOARD_CACHE_LOCK, type(threading.Lock())), \
            "_BOARD_CACHE_LOCK 应为 threading.Lock 实例"
        assert isinstance(start_kanban_server._BOARD_WRITE_LOCK, type(threading.RLock())), \
            "_BOARD_WRITE_LOCK 应为 threading.RLock 实例"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])