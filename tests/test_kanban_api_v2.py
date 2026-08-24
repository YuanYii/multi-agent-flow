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


def _api(server, method: str, path: str, body=None, headers=None, auth: bool = True) -> tuple:
    """HTTP 请求助手：返回 (status, parsed_json)；path 中的中文自动 URL 编码"""
    import urllib.request
    import urllib.error
    from urllib.parse import quote
    # 编码 query 中的非 ASCII 字符（保留结构符）
    encoded_path = quote(path, safe="/?=&%")
    url = f"http://127.0.0.1:{server['port']}{encoded_path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    h = dict(headers or {})
    if auth and "X-Master-Token" not in h and "Authorization" not in h:
        h["X-Master-Token"] = kanban_srv.ACTIVE_MASTER_TOKEN
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=h)
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

    def test_07b_date_range_filters(self, server):
        """用例 7b: start_from/start_to/end_from/end_to 日期范围过滤"""
        cards = [
            _mk_card("T0001", start="2026-08-01", end="2026-08-05"),
            _mk_card("T0002", start="2026-08-10", end="2026-08-15"),
            _mk_card("T0003", start="2026-08-20", end="2026-08-25"),
            _mk_card("T0004", start="", end=""),  # 空日期卡片
        ]
        _seed_cards(server, cards)

        # 1. start_from 过滤
        _, r1 = _api(server, "GET", "/api/tasks?start_from=2026-08-10")
        assert [c["id"] for c in r1["data"]["items"]] == ["T0002", "T0003"]

        # 2. start_to 过滤 (空日期必须被排除)
        _, r2 = _api(server, "GET", "/api/tasks?start_to=2026-08-10")
        assert [c["id"] for c in r2["data"]["items"]] == ["T0001", "T0002"]

        # 3. 闭区间范围过滤
        _, r3 = _api(server, "GET", "/api/tasks?start_from=2026-08-05&start_to=2026-08-15")
        assert [c["id"] for c in r3["data"]["items"]] == ["T0002"]

        # 4. end_from & end_to 过滤
        _, r4 = _api(server, "GET", "/api/tasks?end_from=2026-08-15&end_to=2026-08-30")
        assert [c["id"] for c in r4["data"]["items"]] == ["T0002", "T0003"]


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


# ===============================================================
# 用例 29-35: 状态流转、重排序、偏好元数据与高级写接口
# ===============================================================
class TestAdvancedEndpoints:
    def test_29_transition_lifecycle(self, server):
        """用例 29: POST /api/tasks/{id}/transition 状态流转与节点追加"""
        _seed_cards(server, [_mk_card("T0001", "待开发任务", "待开始", "李开发")])
        s, r = _api(server, "POST", "/api/tasks/T0001/transition", {
            "target_status": "进行中", "operator_name": "李开发", "comment": "开始编码"
        })
        assert s == 200
        assert r["data"]["to_status"] == "进行中"
        assert "进行中" in r["data"]["history_entry"]

        # 再次获取验证
        _, get_r = _api(server, "GET", "/api/tasks")
        card = get_r["data"]["items"][0]
        assert card["status"] == "进行中"
        assert "开始编码" in card["process"]

    def test_30_transition_optimistic_lock(self, server):
        """用例 30: 状态流转携带过期 If-Match / v 时触发 409 拦截"""
        _seed_cards(server, [_mk_card("T0001", "流转锁测试", "待开始")])
        _, ver_resp = _api(server, "GET", "/api/version")
        stale_v = ver_resp["data"]["v"]

        # 模拟外部变更
        _seed_cards(server, [_mk_card("T0001", "流转锁测试-已外部变更", "进行中")])

        s, r = _api(server, "POST", "/api/tasks/T0001/transition", {
            "target_status": "已完成", "v": stale_v
        })
        assert s == 409

    def test_31_reorder_tasks(self, server):
        """用例 31: PUT /api/tasks/reorder 拖拽重排"""
        _seed_cards(server, [_mk_card("T0001"), _mk_card("T0002"), _mk_card("T0003")])
        s, r = _api(server, "PUT", "/api/tasks/reorder", {
            "ordered_task_ids": ["T0003", "T0001", "T0002"]
        })
        assert s == 200
        assert r["data"]["reordered"] == 3

        _, get_r = _api(server, "GET", "/api/tasks?size=all")
        ids = [c["id"] for c in get_r["data"]["items"]]
        assert ids == ["T0003", "T0001", "T0002"]

    def test_32_board_meta_preferences(self, server):
        """用例 32: GET /api/board/meta 与 PUT /api/board/meta"""
        s, r = _api(server, "GET", "/api/board/meta")
        assert s == 200
        assert "title" in r["data"]

        s, r = _api(server, "PUT", "/api/board/meta", {
            "title": "定制敏捷看板", "theme": "dark"
        })
        assert s == 200
        assert r["data"]["title"] == "定制敏捷看板"
        assert r["data"]["theme"] == "dark"

    def test_33_legacy_bulk_save_post(self, server):
        """用例 33: 向后兼容 POST /board.json 全量覆盖"""
        cards = [_mk_card("T0001", "兼容全量A"), _mk_card("T0002", "兼容全量B")]
        s, r = _api(server, "POST", "/board.json", cards)
        assert s == 200
        assert r["data"]["count"] == 2

    def test_34_batch_delete_route(self, server):
        """用例 34: POST /api/tasks/batch-delete 批量删除"""
        _seed_cards(server, [_mk_card("T0001"), _mk_card("T0002"), _mk_card("T0003")])
        s, r = _api(server, "POST", "/api/tasks/batch-delete", {"task_ids": ["T0001", "T0003"]})
        assert s == 200
        assert r["data"]["deleted_count"] == 2
        assert r["data"]["remaining_total"] == 1

    def test_35_alias_routes_cards(self, server):
        """用例 35: /api/cards 路由别名与 /api/tasks 完全对齐"""
        _seed_cards(server, [_mk_card("T0001")])
        s, r = _api(server, "GET", "/api/cards")
        assert s == 200
        assert r["data"]["total"] == 1


# ===============================================================
# 用例 36-50: 复杂多维组合筛选、边界条件与排序完整矩阵
# ===============================================================
class TestMatrixAndEdgeCases:
    def test_36_filter_and_page_combined(self, server):
        """用例 36: 筛选 + 分页组合（size 在 10/20/50/100 白名单内）"""
        _seed_12(server)
        s, r = _api(server, "GET", "/api/tasks?status=已完成&page=1&size=10")
        assert s == 200
        assert r["data"]["total"] == 4
        assert len(r["data"]["items"]) == 4

    def test_37_filter_page_and_sort_combined(self, server):
        """用例 37: 筛选 + 分页 + 排序组合"""
        _seed_12(server)
        s, r = _api(server, "GET", "/api/tasks?assignee=章测试&sort=act_hours&order=desc&page=1&size=10")
        assert s == 200
        assert r["data"]["total"] == 5
        assert len(r["data"]["items"]) == 5
        # 验证排序按 act_hours 降序排列
        acts = [c["act_hours"] for c in r["data"]["items"]]
        assert acts == sorted(acts, reverse=True)

    def test_38_empty_board_query(self, server):
        """用例 38: 空看板（0张卡）时所有查询均优雅返回"""
        _seed_cards(server, [])
        s, r = _api(server, "GET", "/api/tasks?page=1&size=20")
        assert s == 200
        assert r["data"]["total"] == 0
        assert r["data"]["items"] == []

    def test_39_special_characters_in_search(self, server):
        """用例 39: 搜索特殊符号（空格、下划线、中文标点）"""
        _seed_cards(server, [
            _mk_card("T0001", "【重构】auth_v2 & jwt 鉴权"),
            _mk_card("T0002", "普通任务")
        ])
        s, r = _api(server, "GET", "/api/tasks?keyword=auth_v2")
        assert s == 200
        assert r["data"]["total"] == 1
        assert r["data"]["items"][0]["id"] == "T0001"

    def test_40_nonexistent_task_update_404(self, server):
        """用例 40: PUT 不存在的任务 ID → 404"""
        _seed_cards(server, [])
        s, r = _api(server, "PUT", "/api/tasks/T9999", {"name": "ghost"})
        assert s == 404

    def test_41_nonexistent_task_delete_404(self, server):
        """用例 41: DELETE 不存在的任务 ID → 404"""
        _seed_cards(server, [])
        s, r = _api(server, "DELETE", "/api/tasks/T9999")
        assert s == 404

    def test_42_nonexistent_task_transition_404(self, server):
        """用例 42: POST transition 不存在的任务 ID → 404"""
        _seed_cards(server, [])
        s, r = _api(server, "POST", "/api/tasks/T9999/transition", {"target_status": "已完成"})
        assert s == 404

    def test_43_sort_by_start_date(self, server):
        """用例 43: 按 start_date 排序"""
        cards = [
            _mk_card("T0001", start="2026-08-03"),
            _mk_card("T0002", start="2026-08-01"),
            _mk_card("T0003", start="2026-08-02"),
        ]
        _seed_cards(server, cards)
        _, r = _api(server, "GET", "/api/tasks?sort=start_date&order=asc&size=all")
        starts = [c["start_date"] for c in r["data"]["items"]]
        assert starts == ["2026-08-01", "2026-08-02", "2026-08-03"]

    def test_44_sort_by_act_hours_numeric(self, server):
        """用例 44: act_hours 数值排序与 NULLS LAST 机制（已完成任务数值排序，未完成任务沉底）"""
        cards = [
            _mk_card("T0001", status="已完成", act=2.0),
            _mk_card("T0002", status="已完成", act=10.0),
            _mk_card("T0003", status="已完成", act=1.5),
            _mk_card("T0004", status="待开始", act=0.0),
        ]
        _seed_cards(server, cards)
        # 升序: 1.5 -> 2.0 -> 10.0 -> T0004 (未完成/无耗时沉底)
        _, r = _api(server, "GET", "/api/tasks?sort=act_hours&order=asc&size=all")
        items = r["data"]["items"]
        assert [c["id"] for c in items] == ["T0003", "T0001", "T0002", "T0004"]
        assert [c["act_hours"] for c in items[:3]] == [1.5, 2.0, 10.0]

        # 降序: 10.0 -> 2.0 -> 1.5 -> T0004 (未完成/无耗时沉底)
        _, r_desc = _api(server, "GET", "/api/tasks?sort=act_hours&order=desc&size=all")
        items_desc = r_desc["data"]["items"]
        assert [c["id"] for c in items_desc] == ["T0002", "T0001", "T0003", "T0004"]

    def test_45_role_name_normalization_in_create(self, server):
        """用例 45: 创建任务时传入角色代号 (如 'dev') 自动归一化为中文名 '李开发'"""
        _seed_cards(server, [])
        s, r = _api(server, "POST", "/api/tasks", {"name": "自动归一化测试", "assignee": "dev"})
        assert s == 200
        assert r["data"]["assignee"] == "李开发"

    def test_46_first_node_created_on_task_create(self, server):
        """用例 46: 创建任务自动生成 N01 建单节点且格式规范"""
        _seed_cards(server, [])
        s, r = _api(server, "POST", "/api/tasks", {"name": "首节点测试", "assignee": "李开发", "remarks": "初始说明"})
        assert s == 200
        assert "T0001-N01" in r["data"]["process"]
        assert "初始说明" in r["data"]["process"]

    def test_47_reorder_empty_payload_400(self, server):
        """用例 47: PUT reorder 缺少 ordered_task_ids → 400"""
        s, r = _api(server, "PUT", "/api/tasks/reorder", {})
        assert s == 400

    def test_48_batch_delete_empty_payload_400(self, server):
        """用例 48: POST batch-delete 缺少 task_ids → 400"""
        s, r = _api(server, "POST", "/api/tasks/batch-delete", {})
        assert s == 400

    def test_49_delete_via_query_ids(self, server):
        """用例 49: DELETE /api/tasks?ids=T0001,T0002 批量删除"""
        _seed_cards(server, [_mk_card("T0001"), _mk_card("T0002"), _mk_card("T0003")])
        s, r = _api(server, "DELETE", "/api/tasks?ids=T0001,T0002")
        assert s == 200
        assert r["data"]["deleted"] == 2
        assert r["data"]["remaining_total"] == 1

    def test_50_static_html_and_version_probe(self, server):
        """用例 50: 根路径重定向与 /api/version 版本端点协同"""
        s, r = _api(server, "GET", "/api/version")
        assert s == 200
        assert "v" in r["data"]


# ===============================================================
# 用例 51-52: 5000 卡大数据压测与现场清理还原
# ===============================================================
class TestBigDataAndTeardown:
    def test_51_5000_cards_stress_and_paging_performance(self, server):
        """用例 51: 5000 张任务大数据卡片批量注入性能与分页响应测试 (< 50ms)"""
        import time
        big_cards = [
            _mk_card(f"T{i:04d}", f"大数据性能压测任务-{i}", "进行中", "李开发", "S3 编码实现", "WP-后端", est=2.0, act=1.0)
            for i in range(1, 5001)
        ]
        _seed_cards(server, big_cards)

        # 1. 验证版本哈希计算正常
        s, r = _api(server, "GET", "/api/version")
        assert s == 200
        assert re.fullmatch(r"[0-9a-f]{12}", r["data"]["v"])

        # 2. 分页查询第 50 页（size=20），耗时统计
        t0 = time.perf_counter()
        s, r = _api(server, "GET", "/api/tasks?page=50&size=20")
        t1 = time.perf_counter()
        query_time_ms = (t1 - t0) * 1000

        assert s == 200
        assert r["data"]["total"] == 5000
        assert len(r["data"]["items"]) == 20
        assert r["data"]["items"][0]["id"] == "T0981"
        assert r["data"]["items"][-1]["id"] == "T1000"
        # 响应时间应极快（通常 < 50ms）
        assert query_time_ms < 500, f"5000卡分页查询耗时过长: {query_time_ms:.2f}ms"

        # 3. 关键字搜索压测
        t0 = time.perf_counter()
        s, r = _api(server, "GET", "/api/tasks?keyword=4999&size=10")
        t1 = time.perf_counter()
        search_time_ms = (t1 - t0) * 1000

        assert s == 200
        assert r["data"]["total"] == 1
        assert r["data"]["items"][0]["id"] == "T4999"
        assert search_time_ms < 500, f"5000卡搜索耗时过长: {search_time_ms:.2f}ms"

    def test_52_restore_clean_state(self, server):
        """用例 52: 测后恢复空数据基线，确保测试环境纯净"""
        _seed_cards(server, [])
        s, r = _api(server, "GET", "/api/tasks")
        assert s == 200
        assert r["data"]["total"] == 0
        assert r["data"]["items"] == []


# ===============================================================
# 用例 53-62: 局域网主控权限与并发锁安全防护测试 (Phase 3)
# ===============================================================
class TestMasterTokenAndSecurity:
    def test_53_unauthenticated_post_task_returns_403(self, server):
        """无 Token 发起 POST /api/tasks 创建任务必须被 403 拦截"""
        _seed_cards(server, [])
        s, r = _api(server, "POST", "/api/tasks", {"name": "越权任务"}, auth=False)
        assert s == 403
        assert r["code"] == 403
        assert "主控权限" in r["message"]

    def test_54_unauthenticated_delete_task_returns_403(self, server):
        """无 Token 发起 DELETE /api/tasks/T0001 必须被 403 拦截"""
        _seed_cards(server, [_mk_card("T0001")])
        s, r = _api(server, "DELETE", "/api/tasks/T0001", auth=False)
        assert s == 403
        assert r["code"] == 403

    def test_55_unauthenticated_batch_delete_returns_403(self, server):
        """无 Token 发起 POST /api/tasks/batch-delete 必须被 403 拦截"""
        _seed_cards(server, [_mk_card("T0001")])
        s, r = _api(server, "POST", "/api/tasks/batch-delete", {"task_ids": ["T0001"]}, auth=False)
        assert s == 403
        assert r["code"] == 403

    def test_56_unauthenticated_reorder_returns_403(self, server):
        """无 Token 发起 PUT /api/tasks/reorder 必须被 403 拦截"""
        _seed_cards(server, [_mk_card("T0001"), _mk_card("T0002")])
        s, r = _api(server, "PUT", "/api/tasks/reorder", {"ordered_task_ids": ["T0002", "T0001"]}, auth=False)
        assert s == 403
        assert r["code"] == 403

    def test_57_unauthenticated_board_meta_returns_403(self, server):
        """无 Token 发起 PUT /api/board/meta 必须被 403 拦截"""
        s, r = _api(server, "PUT", "/api/board/meta", {"title": "越权修改标题"}, auth=False)
        assert s == 403
        assert r["code"] == 403

    def test_58_unauthenticated_legacy_bulk_save_returns_403(self, server):
        """无 Token 发起 POST /board.json 批量覆写必须被 403 拦截"""
        s, r = _api(server, "POST", "/board.json", [], auth=False)
        assert s == 403
        assert r["code"] == 403

    def test_59_non_master_terminal_transition_returns_403(self, server):
        """非主控尝试流转至【已验收】或【已取消】必须被 403 阻断"""
        _seed_cards(server, [_mk_card("T0001", status="已完成")])
        # 1. 尝试流转到 已验收 (无 Token)
        s, r = _api(server, "POST", "/api/tasks/T0001/transition", {"target_status": "已验收"}, auth=False)
        assert s == 403
        assert "终态需主控权限" in r["message"]

        # 2. 尝试流转到 已取消 (无 Token)
        s, r = _api(server, "POST", "/api/tasks/T0001/transition", {"target_status": "已取消"}, auth=False)
        assert s == 403
        assert "终态需主控权限" in r["message"]

        # 3. 流转至非终态（如 进行中 → 测试中）允许非主控协作者操作
        s, r = _api(server, "POST", "/api/tasks/T0001/transition", {"target_status": "进行中"}, auth=False)
        assert s == 200

    def test_60_non_master_put_protected_fields_diff_returns_403(self, server):
        """非主控尝试通过 PUT /api/tasks/T0001 修改任务名称/负责人/阶段必须被 403 拦截"""
        _seed_cards(server, [_mk_card("T0001", name="原始任务名", act=1.0)])
        # 尝试篡改任务名称
        s, r = _api(server, "PUT", "/api/tasks/T0001", {"name": "篡改名称"}, auth=False)
        assert s == 403
        assert "无权修改核心字段" in r["message"]

        # 尝试篡改负责人
        s, r = _api(server, "PUT", "/api/tasks/T0001", {"assignee": "严经理"}, auth=False)
        assert s == 403

        # 修改允许的工时与备注允许通过
        s, r = _api(server, "PUT", "/api/tasks/T0001", {"act_hours": 3.5, "remarks": "协作者更新实际工时"}, auth=False)
        assert s == 200
        assert r["data"]["updated_fields"] == ["act_hours", "remarks"]

    def test_61_cors_preflight_and_options_headers(self, server):
        """OPTIONS 预检请求必须允许 X-Master-Token 与 X-Device-Name 请求头"""
        s, r = _api(server, "OPTIONS", "/api/tasks", auth=False)
        assert s == 200

    def test_62_handshake_returns_is_master_status(self, server):
        """GET /api/version 与 /api/health 正确返回 is_master 握手状态与终端解析"""
        # 带 Master Token
        s, r = _api(server, "GET", "/api/version", auth=True)
        assert s == 200
        assert r["data"]["is_master"] is True
        assert "主控" in r["data"]["client_device"]

        # 不带 Token
        s, r = _api(server, "GET", "/api/version", auth=False)
        assert s == 200
        assert r["data"]["is_master"] is False
