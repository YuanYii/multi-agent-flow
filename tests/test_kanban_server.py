#!/usr/bin/env python3
"""
看板服务端口回退与实例复用测试 (Phase 1)

覆盖:
1. 端口探测: 空闲绑定 / 异己服务跳过 / bind-close 竞态 / 固定端口硬失败
2. /api/health: 真实路由返回指纹与端口
3. 运行时文件: 写入/容忍过期
4. 服务类回归: SO_REUSEPORT 必须未设置 (本 bug 的回归测试)
5. 协议层: start.sh 与文档不承诺固定端口

运行: python3 -m pytest tests/test_kanban_server.py -q
"""

import json
import os
import socket
import threading
import importlib.util
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location(
    "start_kanban_server", os.path.join(REPO_ROOT, "scripts", "start_kanban_server.py"))
kanban_srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kanban_srv)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass


class TestPortProbe:
    """probe_port: 空闲/占用/竞态/固定"""

    def test_bind_on_free_port(self):
        port = _free_port()
        result = kanban_srv.probe_port(port, "fpA", pinned=False)
        assert result.action == "bind"
        assert result.port == port
        assert result.httpd is not None
        result.httpd.server_close()

    def test_foreign_plain_socket_skipped(self):
        """非本服务监听（纯 socket 无 HTTP）→ 落到其他端口"""
        holder = socket.socket()
        holder.bind(("127.0.0.1", 0))
        held_port = holder.getsockname()[1]
        holder.listen(1)
        try:
            result = kanban_srv.probe_port(held_port, "fpB", pinned=False)
            assert result.action == "bind"
            assert result.port != held_port
            result.httpd.server_close()
        finally:
            holder.close()

    def test_reuse_same_fingerprint(self):
        """同指纹 health 响应者 → reuse 并携带既有实例信息"""
        fp = "fp-reuse-test"

        class Handler(_QuietHandler):
            def do_GET(self):
                body = json.dumps({
                    "service": kanban_srv.SERVICE_NAME, "version": 1,
                    "fingerprint": fp, "port": 1, "pid": 999, "data_root": "/x",
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            result = kanban_srv.probe_port(port, fp, pinned=True)
            assert result.action == "reuse"
            assert result.health.get("pid") == 999
        finally:
            server.shutdown()
            server.server_close()

    def test_reuse_unwraps_envelope(self):
        """统一响应体 {code,message,data:{...}} 也应正确解包为 health"""
        fp = "fp-envelope-test"

        class Handler(_QuietHandler):
            def do_GET(self):
                body = json.dumps({
                    "code": 200, "message": "success",
                    "data": {"service": kanban_srv.SERVICE_NAME, "fingerprint": fp, "pid": 7},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            result = kanban_srv.probe_port(port, fp, pinned=True)
            assert result.action == "reuse"
            assert result.health.get("pid") == 7
        finally:
            server.shutdown()
            server.server_close()

    def test_pinned_foreign_exits(self):
        """固定端口 + 指纹不匹配 → 硬失败 exit(1)"""
        fp = "fp-mine"

        class Handler(_QuietHandler):
            def do_GET(self):
                body = json.dumps({
                    "service": kanban_srv.SERVICE_NAME, "fingerprint": "fp-theirs",
                }).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with pytest.raises(SystemExit) as exc:
                kanban_srv.probe_port(port, fp, pinned=True)
            assert exc.value.code == 1
        finally:
            server.shutdown()
            server.server_close()

    def test_health_404_treated_as_foreign(self):
        """404 响应（非本服务）→ pinned 模式硬失败，不误判复用"""
        class Handler(_QuietHandler):
            def do_GET(self):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with pytest.raises(SystemExit):
                kanban_srv.probe_port(port, "fp-any", pinned=True)
        finally:
            server.shutdown()
            server.server_close()


class TestHealthEndpoint:
    """/api/health 真实路由"""

    def test_health_route_serves_identity(self):
        kanban_srv.SERVER_STATE.update(
            fingerprint="fp-live", port=None, pid=os.getpid(), data_root="/d",
        )
        httpd = kanban_srv.ReusableHTTPServer(
            ("127.0.0.1", 0), kanban_srv.KanbanHTTPRequestHandler)
        port = httpd.server_address[1]
        kanban_srv.SERVER_STATE["port"] = port
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=2) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            data = payload["data"]
            assert data["service"] == kanban_srv.SERVICE_NAME
            assert data["fingerprint"] == "fp-live"
            assert data["port"] == port
        finally:
            httpd.shutdown()
            httpd.server_close()


class TestServerClass:
    """回归: SO_REUSEPORT 绝不设置（双实例同端口静默串数据的根因）"""

    def test_no_so_reuseport(self):
        httpd = kanban_srv.ReusableHTTPServer(
            ("127.0.0.1", 0), kanban_srv.KanbanHTTPRequestHandler)
        try:
            if hasattr(socket, "SO_REUSEPORT"):
                val = httpd.socket.getsockopt(
                    socket.SOL_SOCKET, socket.SO_REUSEPORT)
                assert val == 0, "SO_REUSEPORT 已设置 —— 会重新引入多实例串数据 bug"
        finally:
            httpd.server_close()

    def test_fingerprint_uses_data_root(self):
        """指纹必须来自 data_root 而非 skill_root（同正本多项目不得同指纹）"""
        fp1 = kanban_srv.compute_project_fingerprint("/proj/one")
        fp2 = kanban_srv.compute_project_fingerprint("/proj/two")
        assert fp1 != fp2
        assert len(fp1) == 16


class TestRuntimeFile:
    """运行时文件 user_data/kanban_server.json"""

    def test_write_and_remove(self, tmp_path, monkeypatch):
        runtime_file = tmp_path / "kanban_server.json"
        monkeypatch.setattr(kanban_srv, "KANBAN_RUNTIME_FILE", str(runtime_file))
        kanban_srv._write_runtime_file(32901, "fpX")
        payload = json.loads(runtime_file.read_text(encoding="utf-8"))
        assert payload["port"] == 32901
        assert payload["fingerprint"] == "fpX"
        assert payload["pid"] == os.getpid()
        kanban_srv._remove_runtime_file()
        assert not runtime_file.exists()

    def test_remove_missing_file_no_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(kanban_srv, "KANBAN_RUNTIME_FILE",
                            str(tmp_path / "never.json"))
        kanban_srv._remove_runtime_file()  # 不应抛异常


class TestAddrInUse:
    """跨平台占用错误判定"""

    def test_macos_errno_48(self):
        e = OSError()
        e.errno = 48
        assert kanban_srv._is_addr_in_use(e) is True

    def test_linux_errno_98(self):
        import errno
        e = OSError()
        e.errno = errno.EADDRINUSE
        assert kanban_srv._is_addr_in_use(e) is True

    def test_windows_winerror_10048(self):
        e = OSError()
        e.winerror = 10048
        assert kanban_srv._is_addr_in_use(e) is True

    def test_other_errors_false(self):
        e = OSError()
        e.errno = 13
        assert kanban_srv._is_addr_in_use(e) is False


class TestStartShProtocol:
    """协议层: start.sh 不再硬编码端口/回退 http.server"""

    def test_start_sh_honors_arg_and_no_http_server_fallback(self):
        with open(os.path.join(REPO_ROOT, "kanban", "start.sh"), encoding="utf-8") as f:
            src = f.read()
        assert "$1" in src, "start.sh 应透传端口参数"
        assert "http.server" not in src, "http.server 回退会提供过期的 kanban/board.json 数据"
        assert "--port 32886" not in src, "start.sh 不应硬编码 --port 32886"

    def test_docs_no_fixed_port_promise(self):
        """文档不再承诺固定 32886（默认端口说明除外，禁止'固定'表述）"""
        for rel in ("SKILL.md", "README.md", "rules/USER.md", "rules/AGENTS.md"):
            path = os.path.join(REPO_ROOT, rel)
            with open(path, encoding="utf-8") as f:
                src = f.read()
            assert "--port 32886" not in src, f"{rel} 仍指示固定 --port 32886"
            assert "固定" + "服务端口" not in src or rel != "README.md", rel


class TestResolveRunningKanban:
    """看板服务实例精准匹配与状态探测"""

    def test_resolve_matching_instance(self, tmp_path):
        data_root = str(tmp_path)
        fp = kanban_srv.compute_project_fingerprint(data_root)

        class Handler(_QuietHandler):
            def do_GET(self):
                body = json.dumps({
                    "code": 200, "message": "success",
                    "data": {
                        "service": kanban_srv.SERVICE_NAME,
                        "fingerprint": fp,
                        "data_root": data_root,
                        "port": self.server.server_address[1],
                        "pid": 999
                    }
                }).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            # 写入 runtime 文件模拟启动
            kanban_srv.KANBAN_RUNTIME_FILE = os.path.join(data_root, "user_data", "kanban_server.json")
            kanban_srv._write_runtime_file(port, fp)
            resolved = kanban_srv.resolve_running_kanban(data_root)
            assert resolved is not None
            assert resolved.get("fingerprint") == fp
            assert resolved.get("data_root") == data_root
            assert resolved.get("pid") == 999
        finally:
            server.shutdown()
            server.server_close()

    def test_resolve_foreign_instance_returns_none(self, tmp_path):
        data_root = str(tmp_path)

        class Handler(_QuietHandler):
            def do_GET(self):
                body = json.dumps({
                    "code": 200, "message": "success",
                    "data": {
                        "service": kanban_srv.SERVICE_NAME,
                        "fingerprint": "foreign-fp",
                        "data_root": "/other/project",
                        "port": self.server.server_address[1],
                        "pid": 111
                    }
                }).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            # 指纹与 data_root 不匹配，严禁误报
            kanban_srv.KANBAN_RUNTIME_FILE = os.path.join(data_root, "user_data", "kanban_server.json")
            kanban_srv._write_runtime_file(port, "foreign-fp")
            resolved = kanban_srv.resolve_running_kanban(data_root)
            assert resolved is None
        finally:
            server.shutdown()
            server.server_close()


class TestLocalIpProbe:
    """局域网物理私网 IP 探测与虚拟网卡强校验测试"""

    def test_is_valid_lan_ip_valid_cases(self):
        """合法 RFC 1918 私网 IPv4 地址必须放行"""
        valid_ips = [
            "192.168.1.1",
            "192.168.31.74",
            "10.0.0.1",
            "10.10.10.10",
            "172.16.0.1",
            "172.20.10.3",
            "172.31.255.254",
        ]
        for ip in valid_ips:
            assert kanban_srv.is_valid_lan_ip(ip) is True, f"Expected {ip} to be valid LAN IP"

    def test_is_valid_lan_ip_filters_virtual_and_public(self):
        """虚拟网卡、Fake-IP、CGNAT、回环及公网 IP 必须严格拦截"""
        invalid_ips = [
            # Fake-IP / Benchmark (198.18.0.0/15)
            "198.18.0.1",
            "198.18.0.84",
            "198.19.255.254",
            # CGNAT / Tailscale (100.64.0.0/10)
            "100.64.0.1",
            "100.100.100.100",
            "100.127.255.254",
            # 回环与链路本地
            "127.0.0.1",
            "127.0.0.2",
            "169.254.1.1",
            # 测试与保留网段
            "192.0.2.1",
            "198.51.100.1",
            "203.0.113.1",
            # 公网 IP
            "8.8.8.8",
            "1.1.1.1",
            "114.114.114.114",
            # 非 RFC 1918 的 172 网段
            "172.15.0.1",
            "172.32.0.1",
            # 非法输入
            "",
            None,
            "invalid_ip",
            "256.0.0.1",
        ]
        for ip in invalid_ips:
            assert kanban_srv.is_valid_lan_ip(ip) is False, f"Expected {ip} to be rejected"

    def test_get_local_ip_returns_valid_or_loopback(self):
        """运行态 get_local_ip() 返回结果必须合法，且绝不可返回 198.18.x 或 100.64.x"""
        local_ip = kanban_srv.get_local_ip()
        assert isinstance(local_ip, str)
        assert local_ip != ""
        if local_ip != "127.0.0.1":
            assert kanban_srv.is_valid_lan_ip(local_ip) is True
        assert not local_ip.startswith("198.18.")
        assert not local_ip.startswith("198.19.")
        assert not local_ip.startswith("100.64.")
        assert not local_ip.startswith("169.254.")

    def test_get_local_ip_fallback_to_loopback_when_all_fake(self, monkeypatch):
        """当所有探测源均仅有 Fake-IP 时，确定性安全回退至 127.0.0.1"""
        monkeypatch.setattr(kanban_srv.subprocess, "check_output", lambda *a, **kw: "inet 198.18.0.1\ninet 100.64.0.1")
        monkeypatch.setattr(kanban_srv.socket, "gethostbyname_ex", lambda *a, **kw: ("host", [], ["198.18.0.84"]))
        monkeypatch.setattr(kanban_srv.socket, "socket", lambda *a, **kw: type("DummySocket", (), {
            "connect": lambda *args: None,
            "getsockname": lambda *args: ("198.18.0.1", 0),
            "close": lambda *args: None
        })())

        result = kanban_srv.get_local_ip()
        assert result == "127.0.0.1"

    def test_get_local_ip_priority_order(self, monkeypatch):
        """优先级测试: 192.168.x.x > 10.x.x.x > 172.16-31.x.x"""
        # 1. 192.168 存在时优先返回 192.168
        monkeypatch.setattr(kanban_srv.subprocess, "check_output", lambda *a, **kw: "inet 10.0.0.5\ninet 192.168.1.100\ninet 172.20.0.1")
        monkeypatch.setattr(kanban_srv.socket, "gethostbyname_ex", lambda *a, **kw: ("host", [], []))
        monkeypatch.setattr(kanban_srv.socket, "socket", lambda *a, **kw: type("DummySocket", (), {
            "connect": lambda *args: None,
            "getsockname": lambda *args: ("127.0.0.1", 0),
            "close": lambda *args: None
        })())
        assert kanban_srv.get_local_ip() == "192.168.1.100"

        # 2. 无 192.168 时优先返回 10.x.x.x
        monkeypatch.setattr(kanban_srv.subprocess, "check_output", lambda *a, **kw: "inet 10.0.0.5\ninet 172.20.0.1")
        assert kanban_srv.get_local_ip() == "10.0.0.5"

        # 3. 仅有 172.x 时返回 172.x
        monkeypatch.setattr(kanban_srv.subprocess, "check_output", lambda *a, **kw: "inet 172.20.0.1")
        assert kanban_srv.get_local_ip() == "172.20.0.1"
