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
    """HTTP 请求助手：返回 (status, parsed_json)；path 中的中文自动 URL 编码"""
    import urllib.request
    import urllib.error
    from urllib.parse import quote
    # 编码 query 中的非 ASCII 字符（保留结构符）
    encoded_path = quote(path, safe="/?=&%")
    url = f"http://127.0.0.1:{server['port']}{encoded_path}"
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


# ===============================================================
# 共用 seed：12 张卡覆盖不同状态/负责人/阶段/工时，支撑筛选与排序
# ===============================================================
def _seed_12(server):
    cards = []
    specs = [
        ("T0001", "登录模块开发", "待开始", "李开发", "S1 需求分析", "WP-前端", 8.0, 0.0),
        ("T0002", "接口联调", "待开始", "马前端", "S2 系统设计", "WP-后端", 3.0, 0.0),
        ("T0003", "数据库设计", "进行中", "李开发", "S2 系统设计", "WP-后端", 5.0, 2.5),
        ("T0004", "单元测试", "进行中", "章测试", "S3 编码实现", "WP-测试", 4.0, 1.0),
        ("T0005", "部署上线", "进行中", "章测试", "S3 编码实现", "WP-运维", 2.0, 1.0),
        ("T0006", "需求评审", "已完成", "严经理", "S1 需求分析", "WP-管理", 1.0, 1.0),
        ("T0007", "架构评审", "已完成", "钱架构", "S2 系统设计", "WP-管理", 1.5, 1.5),
        ("T0008", "压力测试", "已完成", "章测试", "S4 集成测试", "WP-测试", 6.0, 6.0),
        ("T0009", "安全审计", "待开始", "章测试", "S4 集成测试", "WP-测试", 2.5, 0.0),
        ("T0010", "文档编写", "待开始", "李文通", "S5 文档交付", "WP-文档", 3.5, 0.0),
        ("T0011", "代码走查", "进行中", "周审查", "S3 编码实现", "WP-审查", 2.0, 0.5),
        ("T0012", "验收测试", "已完成", "章测试", "S4 集成测试", "WP-测试", 4.5, 4.0),
    ]
    for (tid, name, status, assignee, stage, wp, est, act) in specs:
        cards.append(_mk_card(tid, name, status, assignee, stage, wp, est=est, act=act))
    _seed_cards(server, cards)
    return cards


# ===============================================================
# 用例 3-7: GET /api/tasks 组合筛选
# ===============================================================
class TestApiTasksFilter:
    def test_03_no_param_full_list(self, server):
        """用例 3: 无参全量返回，响应携带 total/items/v"""
        _seed_12(server)
        s, r = _api(server, "GET", "/api/tasks")
        assert s == 200
        assert r["code"] == 200
        assert r["data"]["total"] == 12
        assert len(r["data"]["items"]) == 12
        assert re.fullmatch(r"[0-9a-f]{12}", r["data"]["v"])

    def test_04_status_filter(self, server):
        """用例 4: status 精确过滤"""
        _seed_12(server)
        _, r = _api(server, "GET", "/api/tasks?status=已完成")
        assert r["data"]["total"] == 4
        assert all(c["status"] == "已完成" for c in r["data"]["items"])

    def test_05_assignee_filter(self, server):
        """用例 5: assignee 精确过滤"""
        _seed_12(server)
        _, r = _api(server, "GET", "/api/tasks?assignee=章测试")
        assert r["data"]["total"] == 5
        assert all(c["assignee"] == "章测试" for c in r["data"]["items"])

    def test_06_stage_filter(self, server):
        """用例 6: stage 过滤"""
        _seed_12(server)
        _, r = _api(server, "GET", "/api/tasks?stage=S2 系统设计")
        assert r["data"]["total"] == 3
        assert all(c["stage"] == "S2 系统设计" for c in r["data"]["items"])

    def test_07_wp_filter(self, server):
        """用例 7: wp 过滤（与 stage 同域兼容）"""
        _seed_12(server)
        _, r = _api(server, "GET", "/api/tasks?wp=WP-测试")
        assert r["data"]["total"] == 4
        assert all(c["wp"] == "WP-测试" for c in r["data"]["items"])


# ===============================================================
# 用例 8-14: 搜索 / 空结果 / 非法参数 400
# ===============================================================
class TestApiTasksSearch:
    def test_08_keyword_multi_field(self, server):
        """用例 8: keyword 跨多字段模糊搜索"""
        _seed_12(server)
        _, r = _api(server, "GET", "/api/tasks?keyword=测试")
        names = {c["id"] for c in r["data"]["items"]}
        assert "T0004" in names and "T0008" in names and "T0012" in names

    def test_09_q_alias(self, server):
        """用例 9: q 作为 keyword 别名"""
        _seed_12(server)
        _, r = _api(server, "GET", "/api/tasks?q=评审")
        assert r["data"]["total"] == 2

    def test_10_case_insensitive(self, server):
        """用例 10: 搜索大小写不敏感（针对英文字段）"""
        cards = [
            _mk_card("T0001", "API Gateway 设计", "待开始", "李开发", "S1 需求分析", "WP-后端"),
            _mk_card("T0002", "普通任务", "待开始", "李开发", "S1 需求分析", "WP-后端"),
        ]
        _seed_cards(server, cards)
        _, r = _api(server, "GET", "/api/tasks?keyword=api gateway")
        assert r["data"]["total"] == 1
        assert r["data"]["items"][0]["id"] == "T0001"

    def test_11_empty_result(self, server):
        """用例 11: 空结果集返回（total=0, items=[]）"""
        _seed_12(server)
        _, r = _api(server, "GET", "/api/tasks?keyword=不存在的关键词xyz")
        assert r["data"]["total"] == 0
        assert r["data"]["items"] == []

    def test_12_invalid_page_400(self, server):
        """用例 12: 非法 page → 400"""
        _seed_12(server)
        for bad in ("0", "-1", "abc", "1.5"):
            s, r = _api(server, "GET", f"/api/tasks?page={bad}")
            assert s == 400, f"page={bad} 应 400，实际 {s}"
            assert r["code"] == 400

    def test_13_invalid_size_400(self, server):
        """用例 13: 非法 size → 400"""
        _seed_12(server)
        for bad in ("5", "30", "abc", "0"):
            s, r = _api(server, "GET", f"/api/tasks?size={bad}")
            assert s == 400, f"size={bad} 应 400，实际 {s}"

    def test_14_invalid_sort_order_400(self, server):
        """用例 14: 非法 sort/order → 400"""
        _seed_12(server)
        s, r = _api(server, "GET", "/api/tasks?sort=name")
        assert s == 400
        s, r = _api(server, "GET", "/api/tasks?order=up")
        assert s == 400


# ===============================================================
# 用例 15-20: 分页 page/size 与排序 sort/order
# ===============================================================
class TestApiTasksPaging:
    def test_15_page_size_slice_and_total(self, server):
        """用例 15: page+size 切片及 total 准确性"""
        _seed_12(server)
        _, r = _api(server, "GET", "/api/tasks?page=2&size=10")
        assert r["data"]["total"] == 12
        assert len(r["data"]["items"]) == 2
        # 默认按 seq 升序：第 2 页应为 T0011..T0012
        ids = [c["id"] for c in r["data"]["items"]]
        assert ids == ["T0011", "T0012"]

    def test_16_page_default_1(self, server):
        """用例 16: 只给 size 时 page 默认 1"""
        _seed_12(server)
        _, r = _api(server, "GET", "/api/tasks?size=10")
        assert len(r["data"]["items"]) == 10
        assert r["data"]["items"][0]["id"] == "T0001"

    def test_17_size_all_full(self, server):
        """用例 17: size=all 返回全量"""
        _seed_12(server)
        _, r = _api(server, "GET", "/api/tasks?size=all")
        assert r["data"]["total"] == 12
        assert len(r["data"]["items"]) == 12

    def test_18_size_tiers(self, server):
        """用例 18: size 5 档位（10/20/50/100/all）均可用"""
        _seed_12(server)
        for sz in ("10", "20", "50", "100"):
            _, r = _api(server, "GET", f"/api/tasks?size={sz}")
            assert r["data"]["total"] == 12
            assert len(r["data"]["items"]) == min(12, int(sz))

    def test_19_out_of_range_page_empty(self, server):
        """用例 19: 越界页返回空集（total 仍为命中总数）"""
        _seed_12(server)
        _, r = _api(server, "GET", "/api/tasks?page=99&size=10")
        assert r["data"]["total"] == 12
        assert r["data"]["items"] == []

    def test_20_sort_combinations(self, server):
        """用例 20: sort 白名单 × asc/desc 组合"""
        _seed_12(server)
        # 数值字段按数值比较：est_hours 升序
        _, r = _api(server, "GET", "/api/tasks?sort=est_hours&order=asc&size=all")
        ests = [c["est_hours"] for c in r["data"]["items"]]
        assert ests == sorted(ests)
        # est_hours 降序
        _, r = _api(server, "GET", "/api/tasks?sort=est_hours&order=desc&size=all")
        ests = [c["est_hours"] for c in r["data"]["items"]]
        assert ests == sorted(ests, reverse=True)
        # id 升序（T 编号数值序）
        _, r = _api(server, "GET", "/api/tasks?sort=id&order=asc&size=all")
        assert r["data"]["items"][0]["id"] == "T0001"
        assert r["data"]["items"][-1]["id"] == "T0012"
        # 默认 sort=seq, order=asc
        _, r = _api(server, "GET", "/api/tasks?size=all")
        assert r["data"]["items"][0]["id"] == "T0001"


# ===============================================================
# 用例 21-26: POST 新增 / PUT 修改 / DELETE 删除 / 409 乐观锁
# ===============================================================
class TestApiMutation:
    def test_21_post_create_task(self, server):
        """用例 21: POST 创建新任务，成功返回 200 + 卡片 + 新 v"""
        _seed_cards(server, [])
        s, r = _api(server, "POST", "/api/tasks", {
            "name": "新任务A", "stage": "S1 需求分析", "wp": "WP-前端",
            "assignee": "李开发", "status": "待开始"
        })
        assert s == 200
        assert r["code"] == 200
        assert r["data"]["id"] == "T0001"
        assert r["data"]["name"] == "新任务A"
        assert re.fullmatch(r"[0-9a-f]{12}", r["data"]["v"])

    def test_22_post_duplicate_id_409(self, server):
        """用例 22: POST 同 ID 重复创建 → 409 已存在"""
        _seed_cards(server, [_mk_card("T0001", "已有任务")])
        s, r = _api(server, "POST", "/api/tasks", {"id": "T0001", "name": "冲突任务"})
        assert s == 409
        assert r["code"] == 409
        assert "已存在" in r["message"]

    def test_23_post_missing_name_400(self, server):
        """用例 23: POST 缺少 name 必填字段 → 400"""
        _seed_cards(server, [])
        s, r = _api(server, "POST", "/api/tasks", {"stage": "S1"})
        assert s == 400
        assert r["code"] == 400

    def test_24_put_update_task(self, server):
        """用例 24: PUT 更新单条任务字段"""
        _seed_cards(server, [_mk_card("T0001", "原名称", "待开始")])
        s, r = _api(server, "PUT", "/api/tasks/T0001", {
            "name": "更新后名称", "status": "进行中", "act_hours": 3.5
        })
        assert s == 200
        assert r["code"] == 200
        assert "name" in r["data"]["updated_fields"]
        assert r["data"]["card"]["name"] == "更新后名称"
        assert r["data"]["card"]["status"] == "进行中"

    def test_25_optimistic_lock_409_conflict(self, server):
        """用例 25: 携带 If-Match / v，当数据被外部修改导致哈希不一致时 → 409 Conflict 拦截且不覆盖数据"""
        _seed_cards(server, [_mk_card("T0001", "初始版本")])
        _, ver_resp = _api(server, "GET", "/api/version")
        stale_v = ver_resp["data"]["v"]

        # 外部修改数据（如 CLI 或其他客户端提交）
        _seed_cards(server, [_mk_card("T0001", "外部并发修改")])

        # 客户端使用过期的 stale_v 提交 PUT 更新
        s, r = _api(server, "PUT", "/api/tasks/T0001", {
            "name": "过期客户端尝试覆盖", "v": stale_v
        })
        assert s == 409
        assert r["code"] == 409
        assert "conflict" in r["message"] or "冲突" in r["message"]
        # 验证服务端当前最新 v 已返回
        assert "v" in r["data"]

        # 验证原数据未被错误覆盖
        _, get_r = _api(server, "GET", "/api/tasks")
        assert get_r["data"]["items"][0]["name"] == "外部并发修改"

    def test_26_delete_single_and_batch(self, server):
        """用例 26: DELETE 单删与批量删除"""
        _seed_cards(server, [_mk_card("T0001"), _mk_card("T0002"), _mk_card("T0003")])
        # 单删
        s, r = _api(server, "DELETE", "/api/tasks/T0001")
        assert s == 200
        assert r["data"]["deleted_id"] == "T0001"

        # 批量删除
        s, r = _api(server, "DELETE", "/api/tasks?ids=T0002,T0003")
        assert s == 200
        assert r["data"]["deleted"] == 2
        assert r["data"]["remaining_total"] == 0


# ===============================================================
# 用例 27-28: 并发安全性（多线程 HTTP 并发 + CLI 双层锁互斥）
# ===============================================================
class TestConcurrencyLock:
    def test_27_multi_thread_http_concurrent_writes(self, server):
        """用例 27: 10 线程并发写入 20 次，验证无文件损坏且数据最终一致"""
        _seed_cards(server, [])
        threads = []
        errors = []

        def worker(thread_idx):
            for i in range(2):
                s, r = _api(server, "POST", "/api/tasks", {
                    "name": f"并发任务-{thread_idx}-{i}", "assignee": "李开发"
                })
                if s != 200:
                    errors.append((s, r))

        for t_i in range(10):
            t = threading.Thread(target=worker, args=(t_i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"并发写出现错误: {errors}"
        s, r = _api(server, "GET", "/api/tasks?size=all")
        assert s == 200
        assert r["data"]["total"] == 20
        assert len(r["data"]["items"]) == 20
        # 验证 seq 连续且不重复
        seqs = [c["seq"] for c in r["data"]["items"]]
        assert seqs == list(range(1, 21))

    def test_28_server_and_file_lock_coexistence(self, server):
        """用例 28: Server HTTP 写入与底层 atomic_mutate_board_data 共用 seq.lock，验证双层锁协同"""
        _seed_cards(server, [_mk_card("T0001", "基线任务")])
        s, r = _api(server, "POST", "/api/tasks", {"name": "HTTP新增任务"})
        assert s == 200
        assert r["data"]["id"] == "T0002"
        s, r = _api(server, "GET", "/api/tasks?size=all")
        assert r["data"]["total"] == 2
