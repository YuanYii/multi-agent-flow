"""核心全量导入接口的身份完整性测试。"""

import start_kanban_server as server


def test_bulk_payload_rejects_duplicate_ids():
    error = server.validate_bulk_cards_payload([
        {"id": "T0001", "name": "A"},
        {"id": "T0001", "name": "B"},
    ])
    assert error and "重复" in error


def test_bulk_payload_rejects_missing_ids():
    error = server.validate_bulk_cards_payload([{"name": "没有编号"}])
    assert error and "缺少任务 ID" in error


def test_bulk_payload_accepts_unique_cards():
    assert server.validate_bulk_cards_payload([
        {"id": "T0001", "name": "A"},
        {"id": "T0002", "name": "B"},
    ]) is None
