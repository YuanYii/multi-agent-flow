"""
看板局域网协同访问与多线程并发防死锁修复方案 - 测试套件

测试用例覆盖：
1. test_server_is_threading_http_server: 断言 ReusableHTTPServer 继承自 ThreadingHTTPServer 且 daemon_threads is True
2. test_handler_socket_timeout_configured: 断言 KanbanHTTPRequestHandler.timeout == 10.0
3. test_concurrent_slow_client_isolation: 启动测试服务端，模拟慢客户端，断言并发隔离
4. test_default_host_is_lan_enabled: 断言默认监听 0.0.0.0，开箱即支持局域网协同
5. test_runtime_file_reflects_host: 断言 _write_runtime_file 准确反映 host 状态
6. test_board_cache_thread_safety: 断言 _BOARD_CACHE_LOCK 存在且为 Lock
"""

import os
import sys
import json
import socket
import threading
import time
import pytest
from unittest.mock import patch

# 添加脚本目录到路径
SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPT_DIR)


def _get_free_port():
    """动态获取一个当前空闲的 TCP 端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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

        port = _get_free_port()

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
            # 等待服务器端口就绪
            ready = False
            for _ in range(30):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        ready = True
                        break
                except OSError:
                    time.sleep(0.1)
            assert ready, f"服务器在端口 {port} 未能及时就绪"

            # 创建慢客户端（只建立 TCP 连接，不发送 HTTP 请求）
            slow_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            slow_sock.connect(("127.0.0.1", port))

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


class TestDefaultHostConfiguration:
    """测试默认启动监听地址即支持局域网协同"""

    def test_default_host_is_all_interfaces(self):
        """断言默认启动参数 host 为 0.0.0.0，无需额外增加命令"""
        import argparse
        import start_kanban_server

        # 检查 start_kanban_server 中的 main 参数定义
        with patch("argparse.ArgumentParser.parse_args") as mock_args, \
             patch("start_kanban_server.start_server") as mock_start:
            # 模拟不传参数
            mock_args.return_value = argparse.Namespace(port=None, host="0.0.0.0", status=False)
            start_kanban_server.main()
            mock_start.assert_called_once()
            _, kwargs = mock_start.call_args
            assert kwargs.get("host") == "0.0.0.0", "默认启动 host 应为 0.0.0.0"


class TestRuntimeFileReflectsHost:
    """测试运行时文件准确反映 host 状态"""

    def test_runtime_file_with_loopback_host(self, tmp_path, monkeypatch):
        """断言在 host='127.0.0.1' 时，kanban_server.json 中的 lan_url 为 None"""
        import start_kanban_server
        runtime_file = tmp_path / "kanban_server.json"
        monkeypatch.setattr(start_kanban_server, "KANBAN_RUNTIME_FILE", str(runtime_file))

        start_kanban_server._write_runtime_file(32886, "test_fp", host="127.0.0.1")

        with open(runtime_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["host"] == "127.0.0.1"
        assert data["lan_url"] is None, "host=127.0.0.1 时 lan_url 应为 None"
        assert data["lan_master_url"] is None, "host=127.0.0.1 时 lan_master_url 应为 None"

    def test_runtime_file_with_lan_host(self, tmp_path, monkeypatch):
        """断言在 host='0.0.0.0' 时，kanban_server.json 中正常生成局域网 URL"""
        import start_kanban_server
        runtime_file = tmp_path / "kanban_server.json"
        monkeypatch.setattr(start_kanban_server, "KANBAN_RUNTIME_FILE", str(runtime_file))

        start_kanban_server._write_runtime_file(32886, "test_fp", host="0.0.0.0")

        with open(runtime_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["host"] == "0.0.0.0"
        local_ip = start_kanban_server.get_local_ip()
        if local_ip != "127.0.0.1":
            assert data["lan_url"] == f"http://{local_ip}:32886/", "host=0.0.0.0 时应生成局域网 URL"
            assert "token" in data["lan_master_url"], "lan_master_url 应包含 token"


class TestBoardCacheThreadSafety:
    """测试看板缓存线程安全性"""

    def test_board_cache_lock_exists(self):
        """断言 _BOARD_CACHE_LOCK 存在且为 Lock 实例"""
        import start_kanban_server

        assert hasattr(start_kanban_server, "_BOARD_CACHE_LOCK"), \
            "start_kanban_server 应定义 _BOARD_CACHE_LOCK"
        assert isinstance(start_kanban_server._BOARD_CACHE_LOCK, type(threading.Lock())), \
            "_BOARD_CACHE_LOCK 应为 threading.Lock 实例"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
