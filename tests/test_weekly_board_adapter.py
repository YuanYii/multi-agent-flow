#!/usr/bin/env python3
"""
单元测试：周口径看板适配器 WeeklyBoardAdapter
覆盖并发发号、冷封剪枝、索引损坏自愈、原位就地更新、僵尸锁破锁自愈、定向原位写回等关键场景。
"""
import os
import sys
import tempfile
import shutil
import threading
import time
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_SCRIPTS_DIR = os.path.join(_PROJ_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _lib.boards.weekly_board_adapter import WeeklyBoardAdapter


@pytest.fixture
def temp_weekly_env():
    td = tempfile.mkdtemp(prefix="test_weekly_board_")
    tasks_dir = os.path.join(td, "docs", "D04-研发过程", "D01-任务")
    os.makedirs(tasks_dir, exist_ok=True)
    locks_dir = os.path.join(td, "user_data", "locks")
    os.makedirs(locks_dir, exist_ok=True)
    index_file = os.path.join(td, "user_data", ".tasks_index.json")

    adapter = WeeklyBoardAdapter(
        tasks_dir=tasks_dir,
        index_file=index_file,
        locks_dir=locks_dir
    )
    yield adapter, td
    shutil.rmtree(td, ignore_errors=True)


def test_concurrent_id_allocation(temp_weekly_env):
    """场景1：多线程并发建卡，发号锁保障 ID 严格递增且零重复"""
    adapter, _ = temp_weekly_env
    allocated_ids = []
    list_lock = threading.Lock()

    def _worker(idx):
        tid = adapter._next_task_id()
        with list_lock:
            allocated_ids.append(tid)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert len(allocated_ids) == 8
    assert len(set(allocated_ids)) == 8
    assert sorted(allocated_ids) == [f"T{i:04d}" for i in range(1, 9)]


def test_target_and_criteria_persistence(temp_weekly_env):
    """场景2：目标与验收标准清洗与持久化"""
    adapter, _ = temp_weekly_env
    tid = adapter.create_record({
        "name": "多专家协同治理",
        "target": "实现跨平台任务卡轻量流转",
        "acceptance_criteria": ["1. 存储至自然周YAML; 2. 索引倒排查询", "3. 单元测试全覆盖"],
        "assignee": "李开发",
        "status": "待开始"
    }, week="2026-W36")

    assert tid == "T0001"
    rec = adapter.get_record("T0001")
    assert rec is not None
    fields = rec["fields"]
    assert fields["target"] == "实现跨平台任务卡轻量流转"
    assert len(fields["acceptance_criteria"]) == 3
    assert "3. 单元测试全覆盖" in fields["acceptance_criteria"]
    assert fields["_source_file"].endswith("2026-W36.yaml")


def test_in_place_update_immutability(temp_weekly_env):
    """场景3：跨周状态流转，原位就地更新绝不物理漂移"""
    adapter, _ = temp_weekly_env
    # 模拟在 W35 创建任务
    tid = adapter.create_record({
        "name": "历史跨周任务",
        "target": "验证原位就地更新",
        "assignee": "李开发",
        "status": "待开始"
    }, week="2026-W35")
    assert tid == "T0001"

    # 在 W36 周期进行更新流转
    ok = adapter.update_record("T0001", {"status": "进行中", "handler": "李开发"})
    assert ok is True

    rec = adapter.get_record("T0001")
    assert rec["fields"]["status"] == "进行中"
    # 断言依然在 2026-W35.yaml 内
    assert rec["fields"]["_source_file"].endswith("2026-W35.yaml")
    # 检查 W36 没有该任务卡
    w36_path = os.path.join(adapter.tasks_dir, "2026-W36.yaml")
    if os.path.exists(w36_path):
        w36_data = adapter._read_yaml_file(w36_path)
        assert not any(t.get("id") == "T0001" for t in w36_data.get("tasks", []))


def test_cold_week_sealing_and_pruning(temp_weekly_env):
    """场景4：周冷封自动标记与查询剪枝"""
    adapter, _ = temp_weekly_env
    tid = adapter.create_record({
        "name": "待终态卡片",
        "status": "待开始"
    }, week="2026-W30")

    # 未完成时未冷封
    w30_file = os.path.join(adapter.tasks_dir, "2026-W30.yaml")
    d1 = adapter._read_yaml_file(w30_file)
    assert d1["metadata"].get("is_sealed") is False

    # 更新为终态【已验收】
    ok = adapter.update_record(tid, {"status": "已验收"})
    assert ok is True

    d2 = adapter._read_yaml_file(w30_file)
    assert d2["metadata"].get("is_sealed") is True
    assert d2["metadata"].get("active_task_count") == 0


def test_index_corruption_rebuild(temp_weekly_env):
    """场景5：索引文件被误删或损坏后极速自愈重建"""
    adapter, _ = temp_weekly_env
    adapter.create_record({"name": "任务一"}, week="2026-W35")
    adapter.create_record({"name": "任务二"}, week="2026-W36")

    # 模拟删除索引文件
    if os.path.exists(adapter.index_file):
        os.remove(adapter.index_file)

    # 重新读取，自动重建并正确命中
    rec = adapter.get_record("T0002")
    assert rec is not None
    assert rec["record_id"] == "T0002"
    assert os.path.exists(adapter.index_file)


def test_zombie_lock_auto_recovery(temp_weekly_env):
    """场景6：僵尸锁（进程被 kill -9）超时自愈破锁"""
    adapter, _ = temp_weekly_env
    # 模拟一个死亡 PID 且时间戳在过去 100s 前的僵尸锁文件
    with open(adapter.seq_lock_file, "w", encoding="utf-8") as f:
        f.write("pid=99999999 ts=1000000000")
    past_mtime = time.time() - 70.0
    os.utime(adapter.seq_lock_file, (past_mtime, past_mtime))

    # 执行发号，触发破锁自愈
    tid = adapter._next_task_id()
    assert tid.startswith("T")
    # 断言成功生成了新锁并获取
    assert os.path.exists(adapter.seq_lock_file)


def test_delete_record_and_index_sync(temp_weekly_env):
    """场景7：物理删除记录与索引联动，自动更新冷封与统计"""
    adapter, _ = temp_weekly_env
    tid1 = adapter.create_record({"name": "任务A", "status": "待开始"}, week="2026-W36")
    tid2 = adapter.create_record({"name": "任务B", "status": "已验收"}, week="2026-W36")

    # 验证删除前两张卡都在
    assert adapter.get_record(tid1) is not None
    assert adapter.get_record(tid2) is not None

    # 删除 tid1 (唯一的活跃任务)
    ok = adapter.delete_record(tid1)
    assert ok is True
    assert adapter.get_record(tid1) is None

    # 索引中已清理 tid1
    index = adapter._load_index()
    assert tid1 not in index["tasks"]
    assert tid2 in index["tasks"]

    # 周元数据中变为全部已验收 -> 自动转冷封
    w36_data = adapter._read_yaml_file(os.path.join(adapter.tasks_dir, "2026-W36.yaml"))
    assert w36_data["metadata"]["active_task_count"] == 0
    assert w36_data["metadata"]["total_task_count"] == 1
    assert w36_data["metadata"]["is_sealed"] is True


def test_list_records_filter(temp_weekly_env):
    """场景8：list_records 多条件过滤"""
    adapter, _ = temp_weekly_env
    adapter.create_record({"name": "前台开发", "assignee": "马前端", "status": "进行中"}, week="2026-W36")
    adapter.create_record({"name": "后端接口", "assignee": "李开发", "status": "开发中"}, week="2026-W36")
    adapter.create_record({"name": "测试任务", "assignee": "章测试", "status": "待测试"}, week="2026-W36")

    # 按处理人 is
    res1 = adapter.list_records(filter_json={"conditions": [{"field_name": "assignee", "operator": "is", "value": ["马前端"]}]})
    assert len(res1) == 1
    assert res1[0]["fields"]["name"] == "前台开发"

    # 按名称 contains
    res2 = adapter.list_records(filter_json={"conditions": [{"field_name": "task_name", "operator": "contains", "value": ["接口"]}]})
    assert len(res2) == 1
    assert res2[0]["fields"]["name"] == "后端接口"


def test_tamper_prevention_on_terminal_status(temp_weekly_env):
    """场景9：终态防篡改拦截"""
    adapter, _ = temp_weekly_env
    tid = adapter.create_record({"name": "已完成验收", "status": "已验收"}, week="2026-W36")
    
    # 未传 force_reopen 禁止修改状态
    ok = adapter.update_record(tid, {"status": "进行中"})
    assert ok is False
    rec = adapter.get_record(tid)
    assert rec["fields"]["status"] == "已验收"

    # force_reopen 允许管理员纠偏
    ok2 = adapter.update_record(tid, {"status": "进行中"}, force_reopen=True)
    assert ok2 is True
    rec2 = adapter.get_record(tid)
    assert rec2["fields"]["status"] == "进行中"


def test_append_remarks(temp_weekly_env):
    """场景10：追加备注拼接"""
    adapter, _ = temp_weekly_env
    tid = adapter.create_record({"name": "带备注任务", "remarks": "初始说明"}, week="2026-W36")
    ok = adapter.append_remarks(tid, "打回修改意见")
    assert ok is True
    rec = adapter.get_record(tid)
    assert "初始说明 | 打回修改意见" in rec["fields"]["remarks"]


def test_server_weekly_mutate_persistence(temp_weekly_env, monkeypatch):
    """场景11：看板服务端 atomic_mutate_board_data 在 weekly 模式下的创建/更新/删除持久化闭环"""
    adapter, td = temp_weekly_env
    import start_kanban_server as srv
    import _lib.boards.board_adapter_factory as b_factory

    # 将工厂适配器重定向为测试沙箱 adapter
    monkeypatch.setattr(srv, "_is_weekly_storage_mode", lambda: True)
    monkeypatch.setattr(b_factory, "get_board_adapter", lambda: adapter)

    # 1. 模拟 POST /api/tasks 创建任务（res_data 含有 id, name, target, acceptance_criteria）
    def _mutate_create_sim(cards):
        new_card = {
            "id": "T0099",
            "name": "通过服务端创建的任务",
            "status": "待开始",
            "assignee": "李开发",
            "target": "验证服务端原子落盘",
            "acceptance_criteria": ["标一", "标二"]
        }
        cards.append(new_card)
        return True, 200, "成功创建", new_card

    code, msg, res = srv.atomic_mutate_board_data(_mutate_create_sim)
    assert code == 200
    # 验证物理持久化至周 YAML
    rec = adapter.get_record("T0099")
    assert rec is not None
    assert rec["fields"]["name"] == "通过服务端创建的任务"
    assert rec["fields"]["target"] == "验证服务端原子落盘"
    assert rec["fields"]["acceptance_criteria"] == ["标一", "标二"]

    # 2. 模拟 PUT /api/tasks/T0099 更新任务（res_data 含有 "card" 包装）
    def _mutate_put_sim(cards):
        c = next(x for x in cards if x["id"] == "T0099")
        c["status"] = "进行中"
        c["target"] = "更新后的目标"
        return True, 200, "更新成功", {"id": "T0099", "card": c}

    code, msg, res = srv.atomic_mutate_board_data(_mutate_put_sim)
    assert code == 200
    rec = adapter.get_record("T0099")
    assert rec["fields"]["status"] == "进行中"
    assert rec["fields"]["target"] == "更新后的目标"


def test_server_weekly_mutate_error_bubbling(temp_weekly_env, monkeypatch):
    """场景12：验证底层适配器落盘失败时，atomic_mutate_board_data 拒绝返回虚假 200，严密向上冒泡 500"""
    adapter, td = temp_weekly_env
    import start_kanban_server as srv
    import _lib.boards.board_adapter_factory as b_factory

    monkeypatch.setattr(srv, "_is_weekly_storage_mode", lambda: True)
    monkeypatch.setattr(b_factory, "get_board_adapter", lambda: adapter)

    # 1. 先建一张终态任务卡【已验收】
    tid = adapter.create_record({"name": "终态不可篡改任务", "status": "已验收"}, week="2026-W36")

    # 2. 模拟未经授权尝试修改该已验收卡片为【进行中】
    def _tamper_mutate(cards):
        c = next(x for x in cards if x["id"] == tid)
        c["status"] = "进行中"
        return True, 200, "尝试篡改", {"id": tid, "card": c}

    code, msg, res = srv.atomic_mutate_board_data(_tamper_mutate)
    # 断言：必须被冒泡拦截并返回 500 磁盘写入失败，绝不虚报 200！
    assert code == 500
    assert "周口径数据持久化至磁盘失败" in msg
    assert res is None

    # 磁盘数据未被污染
    rec = adapter.get_record(tid)
    assert rec["fields"]["status"] == "已验收"


def test_seq_id_recovery_on_external_yaml_injection(temp_weekly_env):
    """场景13：外部 Git Pull 拉取包含更大 Task ID 的周文件时，发号器轻量探活并自愈"""
    adapter, td = temp_weekly_env
    # 本地先建两张单
    adapter.create_record({"name": "本地单1"}, week="2026-W35")
    adapter.create_record({"name": "本地单2"}, week="2026-W35")
    assert adapter._load_index()["max_seq"] == 2

    # 模拟外部通过 Git 同步拉入一个包含 T0050 的全新周文件 2026-W34.yaml
    ext_file = os.path.join(adapter.tasks_dir, "2026-W34.yaml")
    ext_data = {
        "metadata": {"week_cycle": "2026-W34", "is_sealed": True},
        "tasks": [
            {"id": "T0050", "name": "外部协作者提交的高编号卡片", "status": "已验收"}
        ]
    }
    adapter._atomic_yaml_write(ext_file, ext_data)

    # 调用发号器建单，验证自愈感知到外部 T0050，分配 T0051 而不是 T0003
    new_tid = adapter._next_task_id()
    assert new_tid == "T0051"
    assert adapter._load_index()["max_seq"] == 51


def test_none_fields_defense_and_process_purification(temp_weekly_env, monkeypatch):
    """场景14：验证显式传入 None 参数时，create_record 防御生效且流程节点 process 绝无 None 字符串污染"""
    adapter, td = temp_weekly_env
    import start_kanban_server as srv
    import _lib.boards.board_adapter_factory as b_factory

    monkeypatch.setattr(srv, "_is_weekly_storage_mode", lambda: True)
    monkeypatch.setattr(b_factory, "get_board_adapter", lambda: adapter)

    # 1. 模拟上游传入显式 None 的字段集（如 transition_task.py 的 create_fields）
    tid = adapter.create_record({
        "name": "防None污染测试任务",
        "stage": None,
        "wp": None,
        "wbs": None,
        "pretask": None,
        "process": None,
        "remarks": None,
        "target": None,
        "status": "待开始"
    }, week="2026-W36")

    rec = adapter.get_record(tid)
    fields = rec["fields"]
    assert fields["stage"] == "开发阶段"
    assert fields["wp"] == "WP-默认"
    assert fields["pretask"] == ""
    # 核心断言：process 开头绝对不能是 "None"，必须是合法的建卡节点
    assert fields["process"].startswith(f"[{tid}-N01]")
    assert "None" not in fields["process"]

    # 2. 模拟通过服务端进行状态流转，再次断言流转后的 process 节点干净无污染
    def _mutate_trans_sim(cards):
        c = next(x for x in cards if x["id"] == tid)
        c["status"] = "进行中"
        # 即使历史或者上游某种异常将 process 变成了字符串 "None"
        c["process"] = "None"
        return True, 200, "流转成功", {"id": tid, "card": c}

    code, msg, res = srv.atomic_mutate_board_data(_mutate_trans_sim)
    assert code == 200

    rec_updated = adapter.get_record(tid)
    assert rec_updated["fields"]["status"] == "进行中"


def test_four_roles_model_defaults_and_explicit(temp_weekly_env):
    """场景15：四元人机协同身份模型（创建人、创建角色、负责角色、操作人）默认与显式设置"""
    adapter, _ = temp_weekly_env
    # 1. 默认建卡：creator 取 OS 用户，creator_role 默认 严经理，assignee 默认 李开发，operator 默认 creator
    tid1 = adapter.create_record({"name": "默认四元任务"}, week="2026-W36")
    rec1 = adapter.get_record(tid1)
    f1 = rec1["fields"]
    assert f1["creator_role"] == "严经理"
    assert f1["assignee"] == "李开发"
    assert f1["creator"] != ""
    assert f1["operator"] == f1["creator"]
    assert "创建角色: 严经理" in f1["process"]

    # 2. 显式指定四元：真实自然人“yuanyi”，创建角色“钱架构”，负责角色“马前端”，操作人“张三”
    tid2 = adapter.create_record({
        "name": "显式四元任务",
        "creator": "yuanyi",
        "creator_role": "钱架构",
        "assignee": "马前端",
        "operator": "张三"
    }, week="2026-W36")
    rec2 = adapter.get_record(tid2)
    f2 = rec2["fields"]
    assert f2["creator"] == "yuanyi"
    assert f2["creator_role"] == "钱架构"
    assert f2["assignee"] == "马前端"
    assert f2["operator"] == "张三"
    assert "创建人: yuanyi (创建角色: 钱架构) | 负责角色: 马前端" in f2["process"]


def test_operator_updates_on_transition(temp_weekly_env):
    """场景16：多次流转时根属性 operator 实时更新为最新操作人"""
    adapter, _ = temp_weekly_env
    tid = adapter.create_record({
        "name": "流转操作人测试",
        "creator": "yuanyi",
        "creator_role": "严经理",
        "assignee": "李开发"
    }, week="2026-W36")

    # 初始状态
    assert adapter.get_record(tid)["fields"]["operator"] == "yuanyi"

    # 第一次流转由“李四”推进至“进行中”
    ok1 = adapter.update_record(tid, {"status": "进行中", "operator": "李四"})
    assert ok1 is True
    assert adapter.get_record(tid)["fields"]["operator"] == "李四"

    # 第二次流转由“王五”推进至“审查中”
    ok2 = adapter.update_record(tid, {"status": "审查中", "operator": "王五"})
    assert ok2 is True
    assert adapter.get_record(tid)["fields"]["operator"] == "王五"


def test_legacy_yaml_fallback_creator_role_and_operator(temp_weekly_env):
    """场景17：存量缺少 creator_role 与 operator 的旧周 YAML 优雅降级兼容"""
    adapter, td = temp_weekly_env
    import yaml
    legacy_file = os.path.join(adapter.tasks_dir, "2026-W30.yaml")
    legacy_data = {
        "metadata": {"week_cycle": "2026-W30", "is_sealed": False},
        "tasks": [
            {
                "id": "T0001",
                "seq": 1,
                "name": "存量任务卡",
                "status": "待开始",
                "creator": "old_user",
                "assignee": "李开发"
                # 无 creator_role 与 operator
            }
        ]
    }
    with open(legacy_file, "w", encoding="utf-8") as f:
        yaml.dump(legacy_data, f)

    # get_record 读取存量卡
    rec = adapter.get_record("T0001")
    assert rec is not None
    assert rec["fields"]["creator_role"] == "严经理"
    assert rec["fields"]["operator"] == "old_user"

    # list_records 读取存量卡
    all_recs = adapter.list_records(include_sealed=True)
    t1 = next(r for r in all_recs if r["record_id"] == "T0001")
    assert t1["fields"]["creator_role"] == "严经理"
    assert t1["fields"]["operator"] == "old_user"
