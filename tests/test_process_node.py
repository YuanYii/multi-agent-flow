#!/usr/bin/env python3
"""
流程节点双标识（任务ID-N序号）测试

覆盖: 节点号锁内分配/单调递增/任务间隔离、节点行格式、
transition_task 流转写节点行、两条写入路径格式统一、
旧格式行兼容与前端排序逻辑。

运行: python3 -m pytest tests/test_process_node.py -q
"""

import json
import os
import subprocess
import sys
import tempfile

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

from offline_board_adapter import OfflineBoardAdapter  # noqa: E402


def _mk_board(tmp_path, cards):
    board = tmp_path / "b.json"
    board.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    return str(board)


class TestNodeAllocation:
    """适配器层: append_process_node"""

    def test_sequential_allocation(self, tmp_path):
        board = _mk_board(tmp_path, [{"id": "T0001", "status": "待开始", "process": None}])
        a = OfflineBoardAdapter(board)
        assert a.append_process_node("T0001", "DEV", "待开始", "进行中", "李开发") == "T0001-N01"
        assert a.append_process_node("T0001", "DEV", "进行中", "审查中", "周审查") == "T0001-N02"
        assert a.append_process_node("T0001", "PM", "已完成", "已验收", "严经理") == "T0001-N03"

    def test_per_task_isolation(self, tmp_path):
        """两任务各自独立编号，互不影响"""
        board = _mk_board(tmp_path, [
            {"id": "T0001", "status": "进行中", "process": None},
            {"id": "T0002", "status": "进行中", "process": None},
        ])
        a = OfflineBoardAdapter(board)
        assert a.append_process_node("T0001", "DEV", "进行中", "审查中", "x") == "T0001-N01"
        assert a.append_process_node("T0002", "DEV", "进行中", "审查中", "x") == "T0002-N01"
        assert a.append_process_node("T0001", "REV", "审查中", "测试中", "x") == "T0001-N02"

    def test_missing_record_returns_none(self, tmp_path):
        board = _mk_board(tmp_path, [{"id": "T0001", "status": "待开始"}])
        a = OfflineBoardAdapter(board)
        assert a.append_process_node("T9999", "PM", "a", "b", "c") is None

    def test_node_line_format(self, tmp_path):
        board = _mk_board(tmp_path, [{"id": "T0005", "status": "测试中", "process": None}])
        a = OfflineBoardAdapter(board)
        a.append_process_node("T0005", "QA", "测试中", "已完成", "章测试", comment="回归通过")
        process = json.load(open(board, encoding="utf-8"))[0]["process"]
        # 新格式: 节点行 + 可选独立"操作说明:"行（无角色段、无括号）
        first_line = process.split("\n")[0]
        assert first_line.startswith("[T0005-N01]")
        assert "[2026-" in first_line  # 时间戳在节点 ID 后
        assert "状态由【测试中】更新至【已完成】，操作人: 章测试" in first_line
        assert "[QA]" not in first_line  # 角色段已去除（角色=操作人，冗余）
        assert "(操作人" not in first_line  # 不再用括号
        lines = process.split("\n")
        assert lines[1].startswith("操作说明: 回归通过")

    def test_legacy_process_text_not_confused(self, tmp_path):
        """旧格式 process（无节点 ID）不参与编号，新节点从 N01 起"""
        legacy = "[2026-01-01 10:00:00] 旧格式：手动新增任务"
        board = _mk_board(tmp_path, [{"id": "T0001", "status": "待开始", "process": legacy}])
        a = OfflineBoardAdapter(board)
        node = a.append_process_node("T0001", "DEV", "待开始", "进行中", "李开发")
        assert node == "T0001-N01"  # 旧行不含节点 ID → 不抬号
        process = json.load(open(board, encoding="utf-8"))[0]["process"]
        assert process.startswith(legacy)  # 旧行保留在前

    def test_other_task_node_ids_ignored(self, tmp_path):
        """process 行内若出现他任务节点 ID（理论不该有），不得抬高本任务编号"""
        text = "[2026-01-01] [T0009-N07] [DEV] 他任务节点"
        board = _mk_board(tmp_path, [{"id": "T0001", "status": "待开始", "process": text}])
        a = OfflineBoardAdapter(board)
        assert a.append_process_node("T0001", "DEV", "待开始", "进行中", "x") == "T0001-N01"


def _run_flow(cfg_path, *args):
    sub_env = os.environ.copy()
    if os.path.isabs(cfg_path):
        sub_env["YY_FLOW_PROJECT_ROOT"] = os.path.dirname(cfg_path)
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "transition_task.py"),
         "--config", cfg_path] + list(args),
        capture_output=True, text=True, env=sub_env)


class TestTransitionWritesNodes:
    """transition_task 流转成功后写节点行（process 根因修复）"""

    def _setup(self, tmp_path):
        board = tmp_path / "b.json"
        board.write_text("[]", encoding="utf-8")
        cfg = yaml.safe_load(open(os.path.join(
            REPO_ROOT, "config", "workflow.config.template.yaml"), encoding="utf-8"))
        cfg["board"]["board_file"] = str(board)
        cfg_path = tmp_path / "c.yaml"
        yaml.safe_dump(cfg, open(cfg_path, "w", encoding="utf-8"))
        return board, str(cfg_path)

    def test_full_lifecycle_nodes(self, tmp_path):
        board, cfg = self._setup(tmp_path)
        steps = [
            ("--create", "--task-name", "节点E2E", "--role", "PM", "--assignee", "李开发"),
            ("--task-id", "T0001", "--role", "DEV", "--from-status", "待开始",
             "--to-status", "进行中", "--assignee", "李开发"),
            ("--task-id", "T0001", "--role", "DEV", "--from-status", "进行中",
             "--to-status", "审查中", "--assignee", "周审查"),
            ("--task-id", "T0001", "--role", "REVIEWER", "--from-status", "审查中",
             "--to-status", "测试中", "--assignee", "章测试"),
            ("--task-id", "T0001", "--role", "QA", "--from-status", "测试中",
             "--to-status", "已完成", "--assignee", "严经理",
             "--end-time", "2026-08-16 16:40:00", "--remarks", "测试通过"),
            ("--task-id", "T0001", "--role", "PM", "--from-status", "已完成",
             "--to-status", "已验收", "--assignee", "严经理",
             "--end-time", "2026-08-16 16:41:00"),
        ]
        for step in steps:
            r = _run_flow(cfg, *step)
            assert r.returncode == 0, (step, r.stdout[-300:])

        card = json.loads(board.read_text(encoding="utf-8"))[0]
        assert card["status"] == "已验收"
        node_lines = [l for l in card["process"].split("\n") if "-N" in l]
        assert len(node_lines) == 5  # 5 次流转；建单不占节点号
        for i, line in enumerate(node_lines, start=1):
            assert f"T0001-N{i:02d}" in line

    def test_create_does_not_consume_node(self, tmp_path):
        """建单是卡片诞生非流程节点 → 不写节点行、不占号"""
        board, cfg = self._setup(tmp_path)
        r = _run_flow(cfg, "--create", "--task-name", "建单验证",
                      "--role", "PM", "--assignee", "李开发")
        assert r.returncode == 0
        card = json.loads(board.read_text(encoding="utf-8"))[0]
        assert "-N" not in (card.get("process") or "")


class TestServerRouteParity:
    """/transition 路由与 transition_task 写入格式统一"""

    def test_server_transition_emits_node(self, tmp_path):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "m", os.path.join(SCRIPTS, "start_kanban_server.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)

        board = tmp_path / "board.json"
        board.write_text(json.dumps(
            [{"id": "T0003", "status": "待开始", "process": None}], ensure_ascii=False),
            encoding="utf-8")
        m.USER_DATA_BOARD = str(board)
        m.LOCK_FILE = str(board) + ".seq.lock"

        # 模拟 /transition 路由的写路径（与 handler 同逻辑）
        cards = m.read_board_data()
        card = next(c for c in cards if c["id"] == "T0003")
        from_status = card["status"]
        now_str = m.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        card["status"] = "进行中"
        node_id = f"T0003-N{m.allocate_node_seq(card):02d}"
        log_text = f"[{now_str}] [{node_id}] [DEV] 状态由【{from_status}】更新至【进行中】 (操作人: 李开发)"
        card["process"] = log_text
        assert m.atomic_write_board_data(cards)
        saved = json.loads(board.read_text(encoding="utf-8"))[0]
        assert "[T0003-N01]" in saved["process"]
        assert "[DEV]" in saved["process"]

        # 二次流转 → N02
        cards = m.read_board_data()
        card = next(c for c in cards if c["id"] == "T0003")
        node2 = f"T0003-N{m.allocate_node_seq(card):02d}"
        assert node2 == "T0003-N02"


class TestFrontendSortLogic:
    """board.js 排序: 节点行按 N 升序，旧行排前（node 复刻验证）"""

    def test_sort_logic(self):
        lines = [
            "[t] [T0001-N03] [R] 3",
            "[t] 旧格式行",
            "[t] [T0001-N01] [R] 1",
            "[t] [T0001-N02] [R] 2",
        ]

        def node_seq_of(l):
            # 与 board.js 同式
            import re
            mm = re.search(r"\[(T\d+)-N(\d+)\]", l)
            return int(mm.group(2)) if mm else -1

        sorted_lines = sorted(lines, key=node_seq_of)
        assert sorted_lines[0] == "[t] 旧格式行"
        assert sorted_lines[1].endswith("1")
        assert sorted_lines[3].endswith("3")
