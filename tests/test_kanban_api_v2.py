#!/usr/bin/env python3
"""
看板 v3.2 优化 API 测试套件（方案测试矩阵 1-28）

覆盖:
- 用例 1-2:  GET /api/version 版本端点（哈希稳定性 / 数据变更实时变动）
- 用例 3-7:  GET /api/tasks 组合筛选（status/assignee/stage/wp）
- 用例 8-14: keyword/q 模糊搜索、大小写不敏感、空结果、非法参数 400
- 用例 15-20: 分页 page/size（5 档位 + all + 越界 + 非法 400）与 sort/order 排序
- 用例 21-26: POST 新增 / PUT 修改 / 字段缺失 400 / 批量删除 / 409 乐观锁拦截
- 用例 27-28: 双层锁跨进程并发写 100 次无数据丢失

运行: python3 -m pytest tests/test_kanban_api_v2.py -q
"""

import json
import os
import re
import socket
import subprocess
import sys
import threading
import importlib.util
from http.server import HTTPServer

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

_spec = importlib.util.spec_from_file_location(
    "start_kanban_server_v2", os.path.join(SCRIPTS_DIR, "start_kanban_server.py"))
kanban_srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kanban_srv)


# ---------------------------------------------------------------
# 测试服务夹具：真实启动一个服务实例（随机端口，隔离数据目录）
# ---------------------------------------------------------------
@pytest.fixture(scope="module")
def server():
    """启动独立看板服务实例，模块级复用；结束时恢复现场"""
    orig_board_path = kanban_srv.USER_DATA_BOARD
    orig_data_root = kanban_srv._DATA_ROOT

    # 隔离数据目录：避免污染真实 user_data
    import tempfile
    tmp_root = tempfile.mkdtemp(prefix="kanban_api_test_")
    board_path = os.path.join(tmp_root, "user_data", "board.json")
    os.makedirs(os.path.dirname(board_path), exist_ok=True)
    with open(board_path, "w", encoding="utf-8") as f:
        json.dump([], f)

    kanban_srv._DATA_ROOT = tmp_root
    kanban_srv.USER_DATA_BOARD = board_path
    kanban_srv.USER_DATA_PREFERENCES = os.path.join(tmp_root, "user_data", "preferences.json")
    kanban_srv.AUDIT_LOG_FILE = os.path.join(tmp_root, "user_data", "logs", "audit_trail.log")
    kanban_srv.LOCK_FILE = board_path + ".seq.lock"
    kanban_srv.KANBAN_RUNTIME_FILE = os.path.join(tmp_root, "user_data", "kanban_server.json")

    port = _free_port()
    httpd = HTTPServer(("127.0.0.1", port), kanban_srv.KanbanHTTPRequestHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield {"port": port, "httpd": httpd, "board_path": board_path, "tmp_root": tmp_root}

    httpd.shutdown()
    httpd.server_close()
    kanban_srv._DATA_ROOT = orig_data_root
    kanban_srv.USER_DATA_BOARD = orig_board_path
    kanban_srv.USER_DATA_PREFERENCES = os.path.join(orig_data_root, "user_data", "preferences.json")
    kanban_srv.AUDIT_LOG_FILE = os.path.join(orig_data_root, "user_data", "logs", "audit_trail.log")
    kanban_srv.LOCK_FILE = orig_board_path + ".seq.lock"
    kanban_srv.KANBAN_RUNTIME_FILE = os.path.join(orig_data_root, "user_data", "kanban_server.json")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _api(server, method: str, path: str, body=None, headers=None) -> dict:
    """HTTP 请求助手：返回 (status, parsed_json)"""
    import urllib.request
    import urllib.error
    url = f"http://127.0.0.1:{server['port']}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers or {})
    if data is not None and "Content-Type" not in req.headers:
        req.add_header("Content-Type", "application/json")
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw}


def _seed_cards(server, cards: list):
    """直接落盘 seed 数据（绕过 HTTP，模拟 CLI 直写）"""
    with open(server["board_path"], "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)


def _mk_card(tid, name="任务", status="待开始", assignee="李开发", stage="S6 工作流集成测试",
             wp="WP-自定义", est=0.0, act=0.0, start="2026-08-01", end=""):
    return {
        "id": tid, "seq": int(tid[1:]), "name": name, "stage": stage, "wp": wp,
        "wbs": "", "assignee": assignee, "status": status, "handler": assignee,
        "est_hours": est, "act_hours": act, "start_date": start, "end_date": end,
        "remarks": "", "process": "",
    }


# ===============================================================
# 用例 1-2: GET /api/version
# ===============================================================
class TestApiVersion:
    def test_01_version_hash_stable(self, server):
        """用例 1: 版本哈希对同一数据保持稳定"""
        _seed_cards(server, [_mk_card("T0001"), _mk_card("T0002")])
        s1, r1 = _api(server, "GET", "/api/version")
        s2, r2 = _api(server, "GET", "/api/version")
        assert s1 == 200 and s2 == 200
        assert r1["code"] == 200 and r1["message"] == "success"
        assert re.fullmatch(r"[0-9a-f]{12}", r1["data"]["v"])
        assert r1["data"]["v"] == r2["data"]["v"]
        assert "timestamp" in r1

    def test_02_version_hash_changes_on_data_change(self, server):
        """用例 2: board.json 变更后哈希实时变化"""
        _seed_cards(server, [_mk_card("T0001")])
        _, r1 = _api(server, "GET", "/api/version")
        v1 = r1["data"]["v"]
        _seed_cards(server, [_mk_card("T0001"), _mk_card("T0002")])
        _, r2 = _api(server, "GET", "/api/version")
        v2 = r2["data"]["v"]
        assert v1 != v2
        # 恢复后回到原哈希（确定性）
        _seed_cards(server, [_mk_card("T0001")])
        _, r3 = _api(server, "GET", "/api/version")
        assert r3["data"]["v"] == v1
