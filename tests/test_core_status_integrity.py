"""核心状态字段的 API 完整性回归测试。"""

import importlib.util
import json
import os
import socket
import threading
from http.server import HTTPServer
from urllib import request


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PATH = os.path.join(REPO_ROOT, "scripts", "start_kanban_server.py")
spec = importlib.util.spec_from_file_location("status_integrity_server", SERVER_PATH)
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


def _free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _request(base_url, method, path, body=None):
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    req = request.Request(
        f"{base_url}{path}",
        data=payload,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Master-Token": server_module.ACTIVE_MASTER_TOKEN,
        },
    )
    try:
        with request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_api_rejects_unknown_status_before_persistence(tmp_path, monkeypatch):
    board = tmp_path / "user_data" / "board.json"
    board.parent.mkdir(parents=True)
    board.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(server_module, "USER_DATA_BOARD", str(board))
    monkeypatch.setattr(server_module, "LOCK_FILE", str(board) + ".lock")
    monkeypatch.setattr(server_module, "AUDIT_LOG_FILE", str(tmp_path / "audit.log"))

    httpd = HTTPServer(("127.0.0.1", _free_port()), server_module.KanbanHTTPRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{httpd.server_port}"
    try:
        status, payload = _request(base_url, "POST", "/api/tasks", {
            "name": "不应写入的非法状态任务",
            "status": "进行中<script>",
        })
        assert status == 400
        assert payload["data"]["error_type"] == "INVALID_TASK_STATUS"
        assert json.loads(board.read_text(encoding="utf-8")) == []
    finally:
        httpd.shutdown()
        httpd.server_close()
