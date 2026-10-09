"""真实 HTTP 与本地适配器回归：全量保存、核心字段权限、主控终态纠偏。"""
import importlib.util
import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "kanban_persistence_permissions", REPO_ROOT / "scripts" / "start_kanban_server.py"
)
kanban_srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kanban_srv)


@pytest.fixture(params=["single", "weekly", "chunked"])
def server(request, tmp_path, monkeypatch):
    mode = request.param
    user_data = tmp_path / "user_data"
    user_data.mkdir()
    config = {
        "project": {"name": "隔离回归测试", "version": "1", "root_dir": str(tmp_path)},
        "board": {
            "provider": "local", "storage_mode": mode,
            "fields": {"task_id": "id", "status": "status", "assignee": "assignee", "owner": "owner"},
        },
        "roles": {},
        "paths": {"docs_root": "docs", "dev_reports_dir": "docs/dev",
                  "review_reports_dir": "docs/review", "qa_reports_dir": "docs/qa"},
    }
    (user_data / "workflow.config.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True), encoding="utf-8"
    )
    monkeypatch.setenv("YY_FLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(kanban_srv, "_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(kanban_srv, "USER_DATA_BOARD", str(user_data / "board.json"))
    monkeypatch.setattr(kanban_srv, "USER_DATA_PREFERENCES", str(user_data / "preferences.json"))
    monkeypatch.setattr(kanban_srv, "AUDIT_LOG_FILE", str(user_data / "logs" / "audit_trail.log"))
    monkeypatch.setattr(kanban_srv, "LOCK_FILE", str(user_data / "board.json.seq.lock"))
    monkeypatch.setattr(kanban_srv, "_BOARD_MEMORY_CACHE", {"mtime": 0, "size": -1, "cards": []})
    # 服务对 /tmp 下数据刻意走单体测试兼容模式；本组测试显式覆盖真实多文件持久化路径。
    monkeypatch.setattr(kanban_srv, "_is_weekly_storage_mode", lambda: mode != "single")
    monkeypatch.setattr(kanban_srv, "get_local_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(kanban_srv, "get_default_operator", lambda: "测试用户")
    monkeypatch.setattr(kanban_srv.KanbanHTTPRequestHandler, "log_message", lambda *args: None)
    from _lib.boards.board_adapter_factory import get_board_adapter
    adapter = get_board_adapter()
    assert adapter.create_record({
        "id": "T0001", "name": "测试任务", "status": "已验收", "assignee": "李开发",
        "process": "[T0001-N01] 原始审计记录", "target": "原始目标",
        "acceptance_criteria": ["原始验收标准"],
    }) == "T0001"
    httpd = kanban_srv.ReusableHTTPServer(("127.0.0.1", 0), kanban_srv.KanbanHTTPRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    opener = build_opener(ProxyHandler({}))

    def api(method, path, body=None, master=False):
        headers = {"Content-Type": "application/json"}
        if master:
            headers["X-Master-Token"] = kanban_srv.ACTIVE_MASTER_TOKEN
        req = Request(f"http://127.0.0.1:{httpd.server_port}{path}", method=method,
                      data=None if body is None else json.dumps(body).encode("utf-8"), headers=headers)
        try:
            response = opener.open(req, timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    yield {"api": api, "adapter": adapter, "mode": mode, "user_data": user_data}
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)


@pytest.mark.parametrize("path", ["/board.json", "/user_data/board.json", "/api/save_board"])
def test_bulk_replace_never_reports_unsaved_success(server, path):
    before = server["adapter"].get_record("T0001")["fields"]
    status, payload = server["api"]("POST", path, [{"id": "T0002", "name": "导入任务"}], master=True)
    if server["mode"] == "single":
        assert status == 200
        assert server["adapter"].get_record("T0002") is not None
    else:
        assert status == 501
        assert payload["data"]["error_type"] == "BULK_REPLACE_UNSUPPORTED"
        assert server["adapter"].get_record("T0002") is None
        assert server["adapter"].get_record("T0001")["fields"] == before


@pytest.mark.parametrize("field,value", [
    ("process", ""), ("target", "被修改的目标"), ("acceptance_criteria", []),
])
def test_collaborator_cannot_overwrite_history_or_contract(server, field, value):
    before = server["adapter"].get_record("T0001")["fields"][field]
    status, payload = server["api"]("PUT", "/api/tasks/T0001", {field: value})
    assert status == 403
    assert payload["data"]["field"] == field
    assert server["adapter"].get_record("T0001")["fields"][field] == before


def test_master_can_edit_contract_fields(server):
    status, payload = server["api"]("PUT", "/api/tasks/T0001", {
        "target": "经主控调整的目标", "acceptance_criteria": ["新验收标准"],
    }, master=True)
    assert status == 200
    stored = server["adapter"].get_record("T0001")["fields"]
    assert stored["target"] == "经主控调整的目标"
    assert stored["acceptance_criteria"] == ["新验收标准"]


def test_collaborator_can_still_update_work_notes(server):
    status, payload = server["api"]("PUT", "/api/tasks/T0001", {"remarks": "补充工作记录"})
    assert status == 200
    assert server["adapter"].get_record("T0001")["fields"]["remarks"] == "补充工作记录"


def test_only_master_can_reopen_terminal_card(server):
    body = {"target_status": "进行中", "reopen": True, "force_reopen": True}
    status, payload = server["api"]("POST", "/api/tasks/T0001/transition", body)
    assert status == 403
    assert server["adapter"].get_record("T0001")["fields"]["status"] == "已验收"
    status, payload = server["api"]("POST", "/api/tasks/T0001/transition", body, master=True)
    assert status == 200
    assert payload["data"]["reopen"] is True
    stored = server["adapter"].get_record("T0001")["fields"]
    assert stored["status"] == "进行中"
    assert "REOPEN 管理员纠偏" in stored["process"]
    assert stored["end_date"] == ""


def test_internal_reopen_marker_does_not_grant_adapter_override(server):
    if server["mode"] == "single":
        pytest.skip("单体适配器没有独立 REOPEN 保护；覆盖分卷/周适配器的可信授权参数")

    def mutate(cards):
        cards[0]["status"] = "进行中"
        return True, 200, "updated", {"card": cards[0], "reopen": True}

    code, message, data = kanban_srv.atomic_mutate_board_data(mutate)
    assert code == 500
    assert server["adapter"].get_record("T0001")["fields"]["status"] == "已验收"
