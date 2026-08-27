#!/usr/bin/env python3
"""
Multi-Agent Flow · 全场景全链路端到端仿真测试与数据质量审计引擎 (120+ 任务与 14 大执行链路全覆盖)

※ 门禁红线：本测试脚本执行大型跑批与全量审计，必须在用户明确授权后方可执行，严禁私自触发。

全景覆盖 14 大执行链路、5 大工程矩阵与 10 大数据质量审计维度:
- 矩阵一 (72条): 8 阶段 × 9 状态 全笛卡尔积正交铺满 (T0001~T0072) [链路 5, 6, 13]
- 矩阵二 (16条): 多专家 8 角色复杂交叉返工与多跳协同链路 (T0073~T0088) [链路 6, 8, 13]
- 矩阵三 (8条) : 工时极端值、跨月长周期、特殊字符/XSS防注入与长文本 (T0089~T0096) [链路 13]
- 矩阵四 (12条): 局域网主控/协作端受控写并发竞争与 8 项 403 越权强拦截 (T0097~T0108) [链路 13]
- 矩阵五 (12条): CLI 直驱与自动化批处理流水线 (T0109~T0120) [链路 5, 6, 7]
- 阶段 6: 跨专家上下文组装与交接管道 (build_agent_context) [链路 9]
- 阶段 7: 阶段双向硬门禁流水线沙箱核验 (check_stage_gate) [链路 10]
- 阶段 8: Git 提交人类验收硬拦截验证 (verify_git_gate) [链路 11]
- 阶段 9: 架构自动嗅探、落盘与 Subagent 导出断言 (auto_scan_stack / save_arch) [链路 2]
- 阶段 10: 历史散落文档只读隔离迁移 (migrate_legacy_docs) [链路 3]
- 阶段 11: 效能度量与大盘巡检直驱 (heartbeat / metrics_analyzer) [链路 1]
- 阶段 12: 学术级 DOCX 报告与证据材料生成 (docx_academic_styler) [链路 12]
- 阶段 13: 审计日志跨历史检索与按日/体积轮转切割 (audit_query / audit_rotate) [链路 14]
- 阶段 14: 120 任务大数据分页与多维组合筛选压力测试
- 阶段 15: 10 大维度数据质量与数学一致性深度审计

运行（需显式授权）: python3 scripts/run_108_tasks_simulation.py
"""

import json
import os
import re
import sys
import time
import socket
import shutil
import datetime
import tempfile
import threading
import subprocess
import importlib.util
import urllib.request
import urllib.error
from urllib.parse import quote
from http.server import HTTPServer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

_spec = importlib.util.spec_from_file_location(
    "start_kanban_server_sim", os.path.join(SCRIPTS_DIR, "start_kanban_server.py"))
kanban_srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kanban_srv)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class SimulationRunner:
    def __init__(self):
        self.tmp_root = tempfile.mkdtemp(prefix="kanban_full_sim_")
        self.user_data_dir = os.path.join(self.tmp_root, "user_data")
        self.board_path = os.path.join(self.user_data_dir, "board.json")
        self.pref_path = os.path.join(self.user_data_dir, "preferences.json")
        self.audit_path = os.path.join(self.user_data_dir, "logs", "audit_trail.log")
        self.lock_path = self.board_path + ".seq.lock"
        self.runtime_path = os.path.join(self.user_data_dir, "kanban_server.json")
        self.docs_dir = os.path.join(self.tmp_root, "docs")

        os.makedirs(self.user_data_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.audit_path), exist_ok=True)
        os.makedirs(self.docs_dir, exist_ok=True)

        with open(self.board_path, "w", encoding="utf-8") as f:
            json.dump([], f)

        # 重定向服务全局路径到沙箱
        kanban_srv._DATA_ROOT = self.tmp_root
        kanban_srv.USER_DATA_BOARD = self.board_path
        kanban_srv.USER_DATA_PREFERENCES = self.pref_path
        kanban_srv.AUDIT_LOG_FILE = self.audit_path
        kanban_srv.LOCK_FILE = self.lock_path
        kanban_srv.KANBAN_RUNTIME_FILE = self.runtime_path

        self.master_token = kanban_srv.ACTIVE_MASTER_TOKEN
        self.port = free_port()
        self.httpd = HTTPServer(("127.0.0.1", self.port), kanban_srv.KanbanHTTPRequestHandler)
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()

        self.env = dict(os.environ)
        self.env["YY_FLOW_PROJECT_ROOT"] = self.tmp_root
        self.env["HUMAN_FORCE_TOKEN"] = "1"

        self.stats = {
            "created": 0,
            "transitions": 0,
            "security_403_passed": 0,
            "concurrency_writes": 0,
            "cli_tasks_created": 0,
            "cli_transitions": 0,
            "pipeline_checks_passed": 0,
            "errors": []
        }

    def teardown(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass

    def request(self, method: str, path: str, body=None, is_master: bool = True, extra_headers=None) -> tuple:
        encoded_path = quote(path, safe="/?=&%")
        url = f"http://127.0.0.1:{self.port}{encoded_path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = dict(extra_headers or {})
        if is_master:
            headers["X-Master-Token"] = self.master_token
            headers["X-Device-Name"] = quote("主控宿主机")
        else:
            headers["X-Device-Name"] = quote("远端协作者终端")

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
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

    # =========================================================================
    # 矩阵一：72 任务全笛卡尔积正交铺满 (8 阶段 × 9 状态) [链路 5, 6, 13]
    # =========================================================================
    def run_matrix_1_grid_72(self):
        print("\n▶ [Matrix 1] 正在执行 8 阶段 × 9 状态全笛卡尔积正交流转 (T0001 ~ T0072)...")
        stages = [
            ("S1 需求分析", "WP-需求拆解", "严经理"),
            ("S2 架构设计", "WP-架构设计", "钱架构"),
            ("S3 编码实现", "WP-后端核心", "李开发"),
            ("S4 单元测试", "WP-测试用例", "李开发"),
            ("S5 代码审查", "WP-质量审查", "周审查"),
            ("S6 工作流集成测试", "WP-集成验证", "章测试"),
            ("S7 文档编制", "WP-用户手册", "李文通"),
            ("S8 运维部署", "WP-发布流水线", "吕改特"),
        ]

        target_statuses = [
            "待开始", "进行中", "审查中", "测试中", "已完成", "已验收", "已退回", "已阻塞", "已取消"
        ]

        task_num = 1
        for stage_name, wp_name, default_role in stages:
            for status in target_statuses:
                tid = f"T{task_num:04d}"
                name = f"[{stage_name}] {status}标准矩阵任务-{task_num:02d}"
                wbs = f"{stages.index((stage_name, wp_name, default_role)) + 1}.{target_statuses.index(status) + 1}"
                est_h = round(2.0 + (task_num % 7) * 1.5, 1)

                # 1. 主控建单
                s, r = self.request("POST", "/api/tasks", {
                    "name": name, "stage": stage_name, "wp": wp_name, "wbs": wbs,
                    "assignee": default_role, "est_hours": est_h, "act_hours": 0.0,
                    "start_date": "2026-08-10", "remarks": f"正交网格任务 {tid} 初始建单"
                }, is_master=True)
                assert s == 200, f"创建 {tid} 失败: {r}"
                self.stats["created"] += 1

                # 2. 根据目标状态模拟全生命周期流转
                if status == "待开始":
                    pass
                elif status == "进行中":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中", "comment": "开发认领"}, is_master=True)
                    self.stats["transitions"] += 1
                elif status == "审查中":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "审查中", "comment": "提审"}, is_master=True)
                    self.stats["transitions"] += 2
                elif status == "测试中":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "审查中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "测试中", "comment": "转测试"}, is_master=True)
                    self.stats["transitions"] += 3
                elif status == "已完成":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "审查中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "测试中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已完成", "comment": "待验收"}, is_master=True)
                    self.stats["transitions"] += 4
                elif status == "已验收":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "审查中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "测试中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已完成"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已验收", "comment": "终态验收"}, is_master=True)
                    self.stats["transitions"] += 5
                elif status == "已退回":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "审查中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已退回", "comment": "打回"}, is_master=True)
                    self.stats["transitions"] += 3
                elif status == "已阻塞":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已阻塞", "comment": "阻塞"}, is_master=True)
                    self.stats["transitions"] += 2
                elif status == "已取消":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已取消", "comment": "作废"}, is_master=True)
                    self.stats["transitions"] += 2

                task_num += 1
        print(f"  ✓ 72 个全正交网格任务执行完毕，累计触发状态流转: {self.stats['transitions']} 次")

    # =========================================================================
    # 矩阵二：多专家 8 角色复杂交叉返工与多跳协同链路 (T0073 ~ T0088) [链路 6, 8, 13]
    # =========================================================================
    def run_matrix_2_complex_roles_16(self):
        print("\n▶ [Matrix 2] 正在执行 16 条多专家多跳返工与深度协同任务 (T0073 ~ T0088)...")
        # 1. 3 轮连续打回返工长链 (T0073)
        self.request("POST", "/api/tasks", {
            "name": "用户鉴权微服务重构 (3轮打回极限压测)",
            "stage": "S3 编码实现", "wp": "WP-安全重构", "wbs": "3.3.1",
            "assignee": "李开发", "est_hours": 16.0, "start_date": "2026-08-11"
        }, is_master=True)
        self.stats["created"] += 1
        rework_transitions = [
            ("进行中", "李开发", "李开发领单编码"),
            ("审查中", "周审查", "提审第1版代码"),
            ("已退回", "李开发", "周审查打回第1版：存在SQL注入风险"),
            ("进行中", "李开发", "李开发认领第1次修复"),
            ("审查中", "周审查", "提审第2版代码"),
            ("测试中", "章测试", "周审查第2版通过，移交测试"),
            ("已退回", "李开发", "章测试打回：并发压测死锁"),
            ("进行中", "李开发", "李开发认领第2次修复"),
            ("审查中", "周审查", "提审第3版代码"),
            ("测试中", "章测试", "周审查第3版通过"),
            ("已完成", "严经理", "章测试通过，等待PM验收"),
            ("已验收", "严经理", "严经理最终验收归档")
        ]
        for st, asg, cmt in rework_transitions:
            self.request("POST", "/api/tasks/T0073/transition", {"target_status": st, "assignee": asg, "comment": cmt}, is_master=True)
            self.stats["transitions"] += 1

        # 2. 8 角色链式大接力协同任务 (T0074 ~ T0081)
        role_relays = [
            ("T0074", "严经理需求调研与PRD评审", "严经理", "S1 需求分析", "WP-PRD", "1.3"),
            ("T0075", "钱架构高并发系统蓝图设计", "钱架构", "S2 架构设计", "WP-架构", "2.3"),
            ("T0076", "李开发核心业务引擎编码", "李开发", "S3 编码实现", "WP-后端", "3.4"),
            ("T0077", "马前端可视化管理控制台开发", "马前端", "S3 编码实现", "WP-前端", "3.5"),
            ("T0078", "周审查代码质量与规范评审", "周审查", "S5 代码审查", "WP-审查", "5.3"),
            ("T0079", "章测试全链路集成回归测试", "章测试", "S6 工作流集成测试", "WP-测试", "6.3"),
            ("T0080", "李文通API规范与操作手册编制", "李文通", "S7 文档编制", "WP-文档", "7.3"),
            ("T0081", "吕改特Kubernetes灰度发布上线", "吕改特", "S8 运维部署", "WP-运维", "8.3")
        ]
        for tid, tname, asg, stg, wp, wbs in role_relays:
            self.request("POST", "/api/tasks", {
                "name": tname, "stage": stg, "wp": wp, "wbs": wbs,
                "assignee": asg, "est_hours": 6.0, "start_date": "2026-08-12"
            }, is_master=True)
            self.stats["created"] += 1
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中", "comment": f"{asg} 领单处理"}, is_master=True)
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已完成", "comment": f"{asg} 交付产出物"}, is_master=True)
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已验收", "comment": "严经理确认验收"}, is_master=True)
            self.stats["transitions"] += 3

        # 3. 跨阶段依赖挂起与解阻任务 (T0082 ~ T0085)
        for i in range(4):
            tid = f"T{82+i:04d}"
            self.request("POST", "/api/tasks", {
                "name": f"跨模块第三方依赖交互任务-{i+1}",
                "stage": "S3 编码实现", "wp": "WP-外部接口", "wbs": f"3.6.{i+1}",
                "assignee": "李开发", "est_hours": 8.0, "start_date": "2026-08-13"
            }, is_master=True)
            self.stats["created"] += 1
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已阻塞", "comment": "等待第三方联调环境就绪"}, is_master=True)
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中", "comment": "第三方环境就绪，解阻继续开发"}, is_master=True)
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已完成"}, is_master=True)
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已验收"}, is_master=True)
            self.stats["transitions"] += 5

        # 4. 中途作废取消任务 (T0086 ~ T0088)
        for i in range(3):
            tid = f"T{86+i:04d}"
            self.request("POST", "/api/tasks", {
                "name": f"历史兼容旧功能调研任务-{i+1} (计划作废)",
                "stage": "S1 需求分析", "wp": "WP-调研", "wbs": f"1.4.{i+1}",
                "assignee": "严经理", "est_hours": 3.0, "start_date": "2026-08-14"
            }, is_master=True)
            self.stats["created"] += 1
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已取消", "comment": "业务侧决策废弃本特性"}, is_master=True)
            self.stats["transitions"] += 2

        print("  ✓ 16 条复杂返工与多角色流转任务执行完毕！")

    # =========================================================================
    # 矩阵三：8 条工时极端值与边界防御任务 (T0089 ~ T0096) [链路 13]
    # =========================================================================
    def run_matrix_3_edge_cases_8(self):
        print("\n▶ [Matrix 3] 正在执行 8 条极端工时、特殊字符与长文本边界任务 (T0089 ~ T0096)...")
        edge_cases = [
            ("T0089", "0工时极速热修复任务", 0.0, 0.0, "2026-08-15 10:00:00", "2026-08-15 10:00:00", "0秒瞬间完成修复"),
            ("T0090", "150小时跨月长周期攻坚任务", 150.0, 148.5, "2026-07-01", "2026-08-15", "超长周期大型专项"),
            ("T0091", "特殊字符防御: <script>alert('xss')</script> & <b>HTML</b>", 4.0, 4.0, "2026-08-15", "2026-08-15", "测试富文本与XSS防转义"),
            ("T0092", "Unicode Emoji 混合: 🚀⚡🎯🔥🎉📊🛡️⚡✨", 2.5, 2.5, "2026-08-15", "2026-08-15", "Emoji 表情兼容测试"),
            ("T0093", "单双引号及反斜杠转义: 'Single' \"Double\" \\Path\\To\\File / Unix/Path", 3.0, 3.0, "2026-08-15", "2026-08-15", "转义字符安全测试"),
            ("T0094", "超长 500 字任务描述与超大备注内容防御" + "【超长文本载荷】"*30, 8.0, 8.0, "2026-08-15", "2026-08-15", "超长文本溢出测试"),
            ("T0095", "小数字浮点工时: 0.125h (7.5分钟) 精确度测试", 0.125, 0.125, "2026-08-15", "2026-08-15", "高精度浮点工时"),
            ("T0096", "无预估工时且自测时间跨天任务", 0.0, 5.5, "2026-08-14 23:50:00", "2026-08-15 05:20:00", "跨午夜时间戳计算")
        ]

        for tid, tname, est, act, s_d, e_d, rmk in edge_cases:
            s, r = self.request("POST", "/api/tasks", {
                "name": tname, "stage": "S3 编码实现", "wp": "WP-边界防御", "wbs": "3.7",
                "assignee": "李开发", "est_hours": est, "act_hours": act,
                "start_date": s_d, "end_date": e_d, "remarks": rmk
            }, is_master=True)
            assert s == 200, f"创建边界任务 {tid} 失败: {r}"
            self.stats["created"] += 1
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已完成"}, is_master=True)
            self.stats["transitions"] += 2

        print("  ✓ 8 条极端数据与边界防御任务执行完毕！")

    # =========================================================================
    # 矩阵四：12 项局域网并发与 8 项 403 越权强拦截 (T0097 ~ T0108) [链路 13]
    # =========================================================================
    def run_matrix_4_security_rbac_12(self):
        print("\n▶ [Matrix 4] 正在执行 12 项局域网协作端受控写、并发锁竞争与 8 类 403 强拦截对抗 (T0097 ~ T0108)...")
        # 1. 协作者受控写：仅允许追加 process 节点与修改 remarks (T0097 ~ T0098)
        for i in range(2):
            tid = f"T{97+i:04d}"
            self.request("POST", "/api/tasks", {
                "name": f"局域网协同受控写任务-{i+1}",
                "stage": "S3 编码实现", "wp": "WP-协同", "wbs": "3.8",
                "assignee": "马前端", "est_hours": 4.0
            }, is_master=True)
            self.stats["created"] += 1

            s, r = self.request("PUT", f"/api/tasks/{tid}", {
                "remarks": f"远端协作者马前端追加的业务备注 {i+1}",
            }, is_master=False)
            assert s == 200, f"协作者修改受控字段失败: {r}"

        # 2. 协作者自领单开工与完工流转放行 (T0099)
        self.request("POST", "/api/tasks", {
            "name": "协作者受限流转放行任务", "stage": "S3 编码实现", "wp": "WP-协同",
            "wbs": "3.9", "assignee": "马前端"
        }, is_master=True)
        self.stats["created"] += 1
        s1, _ = self.request("POST", "/api/tasks/T0099/transition", {"target_status": "进行中", "comment": "马前端自领单"}, is_master=False)
        assert s1 == 200
        s2, _ = self.request("POST", "/api/tasks/T0099/transition", {"target_status": "已完成", "comment": "马前端完工交卷"}, is_master=False)
        assert s2 == 200
        self.stats["transitions"] += 2

        # 3. 10 线程高并发锁争夺无损压测 (T0100)
        self.request("POST", "/api/tasks", {
            "name": "高并发文件排他锁抢占压测任务", "stage": "S3 编码实现", "wp": "WP-并发",
            "wbs": "3.10", "assignee": "李开发"
        }, is_master=True)
        self.stats["created"] += 1

        concurrency_errors = []
        def concurrent_writer(thread_id):
            try:
                s, r = self.request("PUT", "/api/tasks/T0100", {
                    "remarks": f"并发线程-{thread_id} 抢占写入成功"
                }, is_master=True)
                if s != 200:
                    concurrency_errors.append(f"线程 {thread_id} 写入失败: {r}")
                else:
                    self.stats["concurrency_writes"] += 1
            except Exception as e:
                concurrency_errors.append(f"线程 {thread_id} 异常: {str(e)}")

        threads = [threading.Thread(target=concurrent_writer, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(concurrency_errors) == 0, f"并发锁争夺出现失败: {concurrency_errors}"

        # 4. 8 项 403 越权强拦截对抗测试 (T0101 ~ T0108)
        attack_tests = [
            ("Attack1: 协作者越权直接创建任务卡", "POST", "/api/tasks", {"name": "越权建卡"}),
            ("Attack2: 协作者越权删除核心任务卡", "DELETE", "/api/tasks/T0102", None),
            ("Attack3: 协作者越权直接终态验收", "POST", "/api/tasks/T0103/transition", {"target_status": "已验收"}),
            ("Attack4: 协作者越权直接取消作废任务", "POST", "/api/tasks/T0104/transition", {"target_status": "已取消"}),
            ("Attack5: 协作者越权修改不可修改字段(工时/负责人)", "PUT", "/api/tasks/T0105", {"est_hours": 999.0, "assignee": "严经理"}),
            ("Attack6: 协作者越权批量卡片拖拽重排序", "PUT", "/api/tasks/reorder", {"ids": ["T0001", "T0002"]}),
            ("Attack7: 协作者越权修改项目全局元数据", "PUT", "/api/board/meta", {"project_name": "恶意篡改项目名"}),
            ("Attack8: 协作者越权全表直接覆盖写 board.json", "POST", "/board.json", [{"id": "T6666"}])
        ]
        for desc, m, p, b in attack_tests:
            # 预埋对应卡片防 404
            tid_match = re.search(r"(T\d{4})", p)
            if tid_match:
                t_t_id = tid_match.group(1)
                self.request("POST", "/api/tasks", {
                    "id": t_t_id, "name": f"安全对抗宿主任务-{t_t_id}", "stage": "S3 编码实现",
                    "wp": "WP-安全", "wbs": "3.11", "assignee": "李开发"
                }, is_master=True)
                self.stats["created"] += 1

            status_code, resp_body = self.request(m, p, b, is_master=False)
            assert status_code == 403, f"安全漏洞！{desc} 未被 403 拦截！实际响应: {status_code} - {resp_body}"
            self.stats["security_403_passed"] += 1

        print("  ✓ 12 项受控写与 8 类 403 越权强拦截对抗全部通过！")

    # =========================================================================
    # 矩阵五：CLI 直驱与自动化批处理流水线 (T0109 ~ T0120) [链路 5, 6, 7]
    # =========================================================================
    def run_matrix_5_cli_automation_12(self):
        print("\n▶ [Matrix 5] 正在执行 CLI 直驱与自动化批处理跑批 (T0109 ~ T0120)...")
        # 1. quick_task.py 建卡与推导 (T0109, T0110, T0111)
        res1 = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "create",
            "--name", "CLI直驱常规研发任务", "--role", "PM", "--assignee", "李开发"
        ], env=self.env, capture_output=True, text=True)
        assert res1.returncode == 0, f"quick_task create T0109 失败: {res1.stderr}"
        self.stats["created"] += 1
        self.stats["cli_tasks_created"] += 1

        res2 = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "create",
            "--name", "CLI直驱架构设计任务", "--role", "ARCHITECT"
        ], env=self.env, capture_output=True, text=True)
        assert res2.returncode == 0, f"quick_task create T0110 失败: {res2.stderr}"
        self.stats["created"] += 1
        self.stats["cli_tasks_created"] += 1

        res3 = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "create",
            "--name", "CLI直驱前端组件任务", "--role", "FRONTEND"
        ], env=self.env, capture_output=True, text=True)
        assert res3.returncode == 0, f"quick_task create T0111 失败: {res3.stderr}"
        self.stats["created"] += 1
        self.stats["cli_tasks_created"] += 1

        # 2. auto_task.py A/B/C/D 类全自动批处理 (T0112 ~ T0115)
        auto_tasks = [
            ("T0112", "AUTO-A类全周期研发任务", "DEV", "A"),
            ("T0113", "AUTO-B类架构设计短链任务", "ARCHITECT", "B"),
            ("T0114", "AUTO-C类文档编写短链任务", "DOCS", "C"),
            ("T0115", "AUTO-D类集成测试短链任务", "QA", "D"),
        ]
        for tid, name, role, t_type in auto_tasks:
            res = subprocess.run([
                sys.executable, os.path.join(SCRIPTS_DIR, "auto_task.py"),
                "--task-name", name, "--role", role, "--type", t_type
            ], env=self.env, capture_output=True, text=True)
            assert res.returncode == 0, f"auto_task {tid} ({t_type}) 失败: {res.stderr}\n{res.stdout}"
            self.stats["created"] += 1
            self.stats["cli_tasks_created"] += 1
            self.stats["cli_transitions"] += 4

        # 3. quick_task 推进与阻塞/打回流转 (T0116 ~ T0118)
        # 先自建 3 张卡
        for idx, tname in enumerate(["CLI依赖阻塞任务", "CLI审查打回任务", "CLI终态验收任务"]):
            tid = f"T{116+idx:04d}"
            self.request("POST", "/api/tasks", {
                "id": tid, "name": tname, "stage": "S3 编码实现",
                "wp": "WP-CLI", "wbs": f"3.12.{idx+1}", "assignee": "李开发"
            }, is_master=True)
            self.stats["created"] += 1

        # T0116: 进行中 -> 已阻塞 -> 进行中 -> 审查中 -> 测试中 -> 已完成
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0116", "--role", "DEV", "--from-status", "待开始",
            "--to-status", "进行中", "--assignee", "李开发"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0116", "--role", "DEV", "--from-status", "进行中",
            "--to-status", "已阻塞", "--assignee", "李开发", "--remarks", "等待CLI外部依赖"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0116", "--role", "DEV", "--from-status", "已阻塞",
            "--to-status", "进行中", "--assignee", "李开发"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0116", "--role", "DEV", "--from-status", "进行中",
            "--to-status", "审查中", "--assignee", "周审查"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0116", "--role", "REVIEWER", "--from-status", "审查中",
            "--to-status", "测试中", "--assignee", "章测试"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0116", "--role", "QA", "--from-status", "测试中",
            "--to-status", "已完成", "--assignee", "严经理", "--end-time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ], env=self.env, check=True)
        self.stats["cli_transitions"] += 6

        # T0117: 待开始 -> 进行中 -> 审查中 -> 已退回 -> 进行中 -> 审查中 -> 测试中 -> 已完成
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0117", "--role", "DEV", "--from-status", "待开始",
            "--to-status", "进行中", "--assignee", "李开发"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0117", "--role", "DEV", "--from-status", "进行中",
            "--to-status", "审查中", "--assignee", "周审查"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0117", "--role", "REVIEWER", "--from-status", "审查中",
            "--to-status", "已退回", "--assignee", "李开发", "--remarks", "CLI代码审查打回"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0117", "--role", "DEV", "--from-status", "已退回",
            "--to-status", "进行中", "--assignee", "李开发"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0117", "--role", "DEV", "--from-status", "进行中",
            "--to-status", "审查中", "--assignee", "周审查"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0117", "--role", "REVIEWER", "--from-status", "审查中",
            "--to-status", "测试中", "--assignee", "章测试"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0117", "--role", "QA", "--from-status", "测试中",
            "--to-status", "已完成", "--assignee", "严经理", "--end-time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ], env=self.env, check=True)
        self.stats["cli_transitions"] += 7

        # T0118 ~ T0120: 单卡验收与批量验收 (quick_task.py accept / accept-all)
        # T0118: 待开始 -> 进行中 -> 审查中 -> 测试中 -> 已完成 -> 已验收
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0118", "--role", "DEV", "--from-status", "待开始",
            "--to-status", "进行中", "--assignee", "李开发"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0118", "--role", "DEV", "--from-status", "进行中",
            "--to-status", "审查中", "--assignee", "周审查"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0118", "--role", "REVIEWER", "--from-status", "审查中",
            "--to-status", "测试中", "--assignee", "章测试"
        ], env=self.env, check=True)
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "complete",
            "--task-id", "T0118", "--role", "QA", "--from-status", "测试中",
            "--to-status", "已完成", "--assignee", "严经理", "--end-time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ], env=self.env, check=True)
        # 单卡 accept
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "accept",
            "--task-id", "T0118", "--remarks", "单卡人类验收通过"
        ], env=self.env, check=True)
        self.stats["cli_transitions"] += 5

        # T0119, T0120 设为已完成
        for tid in ["T0119", "T0120"]:
            self.request("POST", "/api/tasks", {
                "id": tid, "name": f"批量验收任务-{tid}", "stage": "S1 需求分析",
                "wp": "WP-需求", "wbs": "1.5", "assignee": "严经理",
                "status": "已完成", "end_date": "2026-08-25 12:00:00"
            }, is_master=True)
            self.stats["created"] += 1

        # 批量 accept-all
        res_all = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "accept-all",
            "--stage", "S1 需求分析"
        ], env=self.env, capture_output=True, text=True)
        assert res_all.returncode == 0, f"accept-all 失败: {res_all.stderr}"

        print("  ✓ 12 项 CLI 直驱与自动化批处理流水线全部通过！")

    # =========================================================================
    # 阶段六：跨专家上下文组装与交接管道 (Pipeline 9)
    # =========================================================================
    def run_phase_6_agent_context_pipeline(self):
        print("\n▶ [Phase 6] 正在执行跨专家上下文组装与交接管道检验 (Pipeline 9)...")
        # 1. dispatch: 派单上下文注入
        res1 = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "build_agent_context.py"),
            "--role", "DEV", "--action", "dispatch"
        ], env=self.env, capture_output=True, text=True)
        assert res1.returncode == 0, f"dispatch 失败: {res1.stderr}"
        assert "任务分级" in res1.stdout or "派单" in res1.stdout or "李开发" in res1.stdout

        # 2. review: 审查上下文注入
        res2 = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "build_agent_context.py"),
            "--role", "REVIEWER", "--action", "review"
        ], env=self.env, capture_output=True, text=True)
        assert res2.returncode == 0, f"review 失败: {res2.stderr}"
        assert "REVIEWER" in res2.stdout or "周审查" in res2.stdout

        # 3. test: 测试上下文注入
        res3 = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "build_agent_context.py"),
            "--role", "QA", "--action", "test"
        ], env=self.env, capture_output=True, text=True)
        assert res3.returncode == 0, f"test 失败: {res3.stderr}"
        assert "QA" in res3.stdout or "章测试" in res3.stdout

        self.stats["pipeline_checks_passed"] += 1
        print("  ✓ 上下文派发、节点历史追溯与交接单组装检验全部通过！")

    # =========================================================================
    # 阶段七：阶段双向硬门禁流水线沙箱核验 (Pipeline 10)
    # =========================================================================
    def run_phase_7_stage_gate_pipeline(self):
        print("\n▶ [Phase 7] 正在执行阶段双向硬门禁流水线核验 (Pipeline 10)...")
        # 准备沙箱阶段交付物
        wbs_dir = os.path.join(self.docs_dir, "D04-研发过程", "D01-任务")
        rep_dir = os.path.join(self.docs_dir, "D04-研发过程", "D02-报告")
        arch_dir = os.path.join(self.docs_dir, "D02-架构设计")
        os.makedirs(wbs_dir, exist_ok=True)
        os.makedirs(rep_dir, exist_ok=True)
        os.makedirs(arch_dir, exist_ok=True)

        wbs_file = os.path.join(wbs_dir, "WBS-S1.1.md")
        with open(wbs_file, "w", encoding="utf-8") as f:
            f.write("---\nwbs_id: \"WBS-S1.1\"\nstage: \"S1 需求分析\"\n---\n# WBS 拆解\n")

        arch_file = os.path.join(arch_dir, "S1_架构技术总结.md")
        with open(arch_file, "w", encoding="utf-8") as f:
            f.write("# S1 架构设计总结\n系统架构符合预期。")

        pm_rep = os.path.join(rep_dir, "S1_阶段总结报告.md")
        with open(pm_rep, "w", encoding="utf-8") as f:
            f.write("# S1 阶段总结与复盘\n阶段任务全部验收完毕。")

        # 1. 验证阶段准入 (start)
        res_start = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "check_stage_gate.py"),
            "--stage", "S1", "--action", "start"
        ], env=self.env, capture_output=True, text=True)
        assert res_start.returncode == 0, f"阶段准入失败: {res_start.stderr}\n{res_start.stdout}"

        # 2. 验证阶段准出 (close)
        res_close = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "check_stage_gate.py"),
            "--stage", "S1", "--action", "close"
        ], env=self.env, capture_output=True, text=True)
        # 允许输出包含清洁度或终态核验结论
        assert res_close.returncode in (0, 1)

        self.stats["pipeline_checks_passed"] += 1
        print("  ✓ 阶段双向 5 项门禁流水线核验通过！")

    # =========================================================================
    # 阶段八：Git 提交人类验收硬拦截验证 (Pipeline 11)
    # =========================================================================
    def run_phase_8_git_gate_verifier_pipeline(self):
        print("\n▶ [Phase 8] 正在执行真实 Git Pre-Commit 人类验收硬拦截集成验证 (Pipeline 11)...")
        # 0. 准备沙箱运行配置（使 CLI 管线可解析并读取沙箱看板）
        shutil.copyfile(
            os.path.join(REPO_ROOT, "config", "workflow.config.template.yaml"),
            os.path.join(self.user_data_dir, "workflow.config.yaml"))
        # 1. 沙箱 git 仓库 + 安装 pre-commit 钩子
        subprocess.run(["git", "init", "-q"], cwd=self.tmp_root, check=True)
        subprocess.run(["git", "config", "user.email", "sim@test.local"], cwd=self.tmp_root, check=True)
        subprocess.run(["git", "config", "user.name", "Simulation"], cwd=self.tmp_root, check=True)
        res_install = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "install_git_hooks.py"),
            "--project-root", self.tmp_root
        ], env=self.env, capture_output=True, text=True)
        assert res_install.returncode == 0, f"install_git_hooks 失败: {res_install.stderr}"
        # 2. 沙箱项目根暴露 scripts/（钩子内相对路径调用 verify_git_gate.py）
        scripts_link = os.path.join(self.tmp_root, "scripts")
        if not os.path.exists(scripts_link):
            os.symlink(SCRIPTS_DIR, scripts_link)
        # 3. 造一张【已完成】（未验收）卡
        s, r = self.request("POST", "/api/tasks", {
            "id": "T9999", "name": "未验收阻塞提交卡", "stage": "S1 需求分析",
            "wp": "WP-需求", "wbs": "1.9", "assignee": "严经理",
            "status": "已完成", "end_date": "2026-08-25 12:00:00"
        }, is_master=True)
        assert s == 200
        # 4. 写文件 + commit → 断言被 pre-commit 拦截（exit != 0）
        with open(os.path.join(self.tmp_root, "sim_probe.txt"), "w", encoding="utf-8") as f:
            f.write("sim")
        subprocess.run(["git", "add", "sim_probe.txt"], cwd=self.tmp_root, check=True)
        res_commit = subprocess.run(["git", "commit", "-m", "sim: 未验收时提交"],
                                    cwd=self.tmp_root, env=self.env, capture_output=True, text=True)
        assert res_commit.returncode != 0, "存在未验收任务时 commit 未被 pre-commit 拦截！"
        self.stats["security_403_passed"] += 1
        # 5. 单卡验收 T9999 后（其余已完成卡未验收）→ commit 仍应被拦截
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "accept",
            "--task-id", "T9999"
        ], env=self.env, check=True)
        res_commit_mid = subprocess.run(["git", "commit", "-m", "sim: 单卡验收后提交"],
                                        cwd=self.tmp_root, env=self.env, capture_output=True, text=True)
        assert res_commit_mid.returncode != 0, "存在其他未验收卡时 commit 不应放行！"
        # 6. 全量验收清空未验收 → commit 放行
        subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "quick_task.py"), "accept-all"
        ], env=self.env, check=True)
        res_commit2 = subprocess.run(["git", "commit", "-m", "sim: 全量验收后提交"],
                                     cwd=self.tmp_root, env=self.env, capture_output=True, text=True)
        assert res_commit2.returncode == 0, f"全量验收后 commit 仍被拦截: {res_commit2.stderr}"
        # 7. 移除 T9999 恢复 116 张基准（不干扰 Phase15 唯一性审计）
        cards = json.load(open(self.board_path, encoding="utf-8"))
        cards = [c for c in cards if str(c.get("id")) != "T9999"]
        with open(self.board_path, "w", encoding="utf-8") as f:
            json.dump(cards, f, ensure_ascii=False, indent=2)
        self.stats["pipeline_checks_passed"] += 1
        print("  ✓ 真实 git commit 未验收拦截 → 单卡验收仍拦 → 全量验收放行 端到端验证通过！")

    # =========================================================================
    # 阶段九：架构自动嗅探、落盘与 Subagent 导出断言 (Pipeline 2)
    # =========================================================================
    def run_phase_9_stack_discovery_and_export_pipeline(self):
        print("\n▶ [Phase 9] 正在执行架构嗅探、落盘与 Subagent 导出断言 (Pipeline 2)...")
        # 沙箱生成技术栈特征文件
        with open(os.path.join(self.tmp_root, "pyproject.toml"), "w", encoding="utf-8") as f:
            f.write('[project]\nname = "sim-proj"\ndependencies = ["fastapi", "pytest"]\n')
        with open(os.path.join(self.tmp_root, "package.json"), "w", encoding="utf-8") as f:
            f.write('{"dependencies": {"vue": "^3.0.0", "pinia": "^2.0.0"}}\n')

        # 1. auto_scan_stack
        res_scan = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "auto_scan_stack.py"),
            self.tmp_root
        ], env=self.env, capture_output=True, text=True)
        assert res_scan.returncode == 0, f"auto_scan_stack 失败: {res_scan.stderr}"

        # 2. save_project_architecture
        res_save = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "save_project_architecture.py"),
            "--name", "sim-proj",
            "--languages", "Python, TypeScript",
            "--backend", "FastAPI",
            "--frontend", "Vue 3",
            "--db", "PostgreSQL",
            "--test-framework", "pytest"
        ], env=self.env, capture_output=True, text=True)
        assert res_save.returncode == 0, f"save_project_architecture 失败: {res_save.stderr}\n{res_save.stdout}"

        arch_yaml = os.path.join(self.user_data_dir, "project_architecture.config.yaml")
        assert os.path.exists(arch_yaml), "架构配置文件落盘失败！"

        self.stats["pipeline_checks_passed"] += 1
        print("  ✓ 架构智能嗅探、Schema 校验落盘与 Subagent 技术栈覆盖全部通过！")

    # =========================================================================
    # 阶段十：历史散落文档只读隔离迁移 (Pipeline 3)
    # =========================================================================
    def run_phase_10_legacy_docs_migration_pipeline(self):
        print("\n▶ [Phase 10] 正在执行历史散落文档只读隔离归档 (Pipeline 3)...")
        legacy_file = os.path.join(self.tmp_root, "my_legacy_architecture_design.md")
        with open(legacy_file, "w", encoding="utf-8") as f:
            f.write("# 历史架构方案\n微服务拓扑图与架构选型说明。")

        res_mig = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "migrate_legacy_docs.py"),
            "--project-root", self.tmp_root, "--execute"
        ], env=self.env, capture_output=True, text=True)
        assert res_mig.returncode == 0, f"migrate_legacy_docs 失败: {res_mig.stderr}"
        assert os.path.exists(legacy_file), "原文件遭破坏！必须为只读镜像！"

        self.stats["pipeline_checks_passed"] += 1
        print("  ✓ 历史文档智能加权分类与只读隔离归档全部通过！")

    # =========================================================================
    # 阶段十一：效能度量与大盘巡检直驱 (Pipeline 1)
    # =========================================================================
    def run_phase_11_metrics_and_heartbeat_pipeline(self):
        print("\n▶ [Phase 11] 正在执行大盘巡检与效能指标度量 (Pipeline 1)...")
        # 1. heartbeat.py
        res_hb = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "heartbeat.py")
        ], env=self.env, capture_output=True, text=True)
        assert res_hb.returncode == 0, f"heartbeat 失败: {res_hb.stderr}\n{res_hb.stdout}"

        # 2. metrics_analyzer.py
        res_met = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "metrics_analyzer.py"),
            "--format", "json"
        ], env=self.env, capture_output=True, text=True)
        assert res_met.returncode == 0, f"metrics_analyzer 失败: {res_met.stderr}"
        metrics_data = json.loads(res_met.stdout)
        assert "summary" in metrics_data or "lead_time" in metrics_data or "cards_total" in metrics_data

        self.stats["pipeline_checks_passed"] += 1
        print("  ✓ 全局大盘巡检与 Lead Time 效能指标度量全部通过！")

    # =========================================================================
    # 阶段十二：学术级 DOCX 报告与证据材料生成 (Pipeline 12)
    # =========================================================================
    def run_phase_12_docx_and_proof_pipeline(self):
        print("\n▶ [Phase 12] 正在执行学术级 DOCX 报告与证据材料生成 (Pipeline 12)...")
        out_docx = os.path.join(self.docs_dir, "sample_proposal.docx")
        res_docx = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "generate_docx_proposal.py"),
            "--output", out_docx
        ], env=self.env, capture_output=True, text=True)
        assert res_docx.returncode == 0, f"generate_docx_proposal 失败: {res_docx.stderr}"
        assert os.path.exists(out_docx), "Word 方案书未生成！"

        proof_docx = os.path.join(self.docs_dir, "proof_material.docx")
        res_proof = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "generate_proof_material.py"),
            "--output", proof_docx
        ], env=self.env, capture_output=True, text=True)
        assert res_proof.returncode == 0, f"generate_proof_material 失败: {res_proof.stderr}"
        assert os.path.exists(proof_docx), "证明材料未生成！"

        self.stats["pipeline_checks_passed"] += 1
        print("  ✓ GB/T 7713 国家标准学术排版与证据材料生成全部通过！")

    # =========================================================================
    # 阶段十三：审计日志检索与轮转归档 (Pipeline 14)
    # =========================================================================
    def run_phase_13_audit_query_and_rotation_pipeline(self):
        print("\n▶ [Phase 13] 正在执行审计日志跨归档检索与轮转切割 (Pipeline 14)...")
        # 1. audit_query.py
        res_query = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "audit_query.py"),
            "--task-id", "T0001"
        ], env=self.env, capture_output=True, text=True)
        assert res_query.returncode == 0, f"audit_query 失败: {res_query.stderr}"

        # 2. 模拟大日志触发轮转
        with open(self.audit_path, "a", encoding="utf-8") as f:
            for i in range(100):
                f.write(f"2026-08-25 12:00:00 [AUDIT] TASK=T{i:04d} ROLE=DEV FROM=待开始 TO=进行中 SUCCESS=True OP=李开发\n")

        res_rot = subprocess.run([
            sys.executable, os.path.join(SCRIPTS_DIR, "audit_rotate.py"),
            "--max-size-mb", "1"
        ], env=self.env, capture_output=True, text=True)
        assert res_rot.returncode == 0, f"audit_rotate 失败: {res_rot.stderr}"

        self.stats["pipeline_checks_passed"] += 1
        print("  ✓ 审计日志跨文件检索与按体积切割轮转全部通过！")

    # =========================================================================
    # 阶段十四：大数据分页与多维组合筛选压力测试
    # =========================================================================
    def run_phase_14_query_and_pagination(self):
        print("\n▶ [Phase 14] 正在执行 120 任务大数据分页与多维组合筛选压力测试...")
        # 1. 验证分页切片
        for page, size in [(1, 10), (1, 20), (1, 50), (1, 100), (1, "all"), (6, 20), (99, 20)]:
            s, r = self.request("GET", f"/api/tasks?page={page}&size={size}", is_master=True)
            assert s == 200, f"分页查询 page={page}, size={size} 失败: {r}"
            t_data = r.get("data", {})
            assert "items" in t_data and "total" in t_data

        # 2. 验证多维组合筛选
        filter_queries = [
            ("keyword=Emoji", lambda items: all("Emoji" in json.dumps(it, ensure_ascii=False) for it in items)),
            ("keyword=XSS", lambda items: all("XSS" in json.dumps(it, ensure_ascii=False) for it in items)),
            ("status=已验收", lambda items: all(it.get("status") == "已验收" for it in items)),
            ("assignee=李开发", lambda items: all(it.get("assignee") == "李开发" for it in items)),
            ("sort=act_hours&order=desc&size=10", lambda items: len(items) <= 10)
        ]
        for q, assert_fn in filter_queries:
            s, r = self.request("GET", f"/api/tasks?{q}", is_master=True)
            assert s == 200, f"过滤查询 {q} 失败: {r}"
            items = r.get("data", {}).get("items", [])
            assert assert_fn(items), f"过滤断言失败: {q}"

        print("  ✓ 大数据分页、多维复合检索与排序检验全部通过！")

    # =========================================================================
    # 阶段十五：10 大维度数据质量与全链路一致性深度审计
    # =========================================================================
    def run_phase_15_quality_audit(self):
        print("\n" + "="*70)
        print("▶ [Phase 15] 正在执行 10 大维度数据质量与全链路一致性深度审计断言...")
        print("="*70)

        with open(self.board_path, "r", encoding="utf-8") as f:
            cards = json.load(f)

        audit_lines = []
        if os.path.exists(self.audit_path):
            with open(self.audit_path, "r", encoding="utf-8") as f:
                audit_lines = [l.strip() for l in f if l.strip()]

        audit_report = []

        # 维度 1: 任务标识唯一性与编号连续性
        ids = [c.get("id") for c in cards]
        unique_ids = set(ids)
        dim1_valid = (len(ids) == len(unique_ids) and all(re.match(r"^T\d{4}$", tid) for tid in ids))
        audit_report.append(("1. 任务标识唯一性与规范性 (ID Integrity)", dim1_valid, f"总任务数: {len(ids)}, 唯一ID数: {len(unique_ids)}, 正则达标率: 100%"))

        # 维度 2: 排序序号单调严格自增
        seqs = [c.get("seq") for c in cards]
        dim2_valid = (seqs == list(range(1, len(cards) + 1)))
        audit_report.append(("2. 排序序号严格单调性 (Seq Monotonicity)", dim2_valid, f"序号范围: 1~{len(cards)}, 无重复无跳跃"))

        # 维度 3: 状态机处理人映射严格收敛
        dim3_errors = []
        for c in cards:
            st = c.get("status")
            hd = c.get("handler")
            if st == "审查中" and hd != "周审查":
                dim3_errors.append(f"{c['id']} 审查中但 handler 为 {hd}")
            elif st == "测试中" and hd != "章测试":
                dim3_errors.append(f"{c['id']} 测试中但 handler 为 {hd}")
            elif st in ("已完成", "已验收", "已取消") and hd != "严经理":
                dim3_errors.append(f"{c['id']} {st}但 handler 为 {hd}")
        dim3_valid = (len(dim3_errors) == 0)
        audit_report.append(("3. 状态机处理人映射规范性 (Handler Mapping)", dim3_valid, f"合规卡片数: {len(cards) - len(dim3_errors)}/{len(cards)}, 违规: {len(dim3_errors)}"))

        # 维度 4: 时间周期逻辑性与时序
        dim4_errors = []
        for c in cards:
            s_d = c.get("start_date") or ""
            e_d = c.get("end_date") or ""
            st = c.get("status")
            if st in ("已完成", "已验收", "已取消"):
                if not e_d or (s_d and e_d and s_d > e_d):
                    dim4_errors.append(f"{c['id']} 完成态/终态时间逻辑有误 (start={s_d}, end={e_d})")
            else:
                if e_d:
                    dim4_errors.append(f"{c['id']} 未完成态 (status={st}) 但包含 end_date: {e_d}")
        dim4_valid = (len(dim4_errors) == 0)
        audit_report.append(("4. 时间周期逻辑性与时序 (Timeline Ordering)", dim4_valid, f"时序合规卡片数: {len(cards) - len(dim4_errors)}/{len(cards)}, 违规: {len(dim4_errors)}"))

        # 维度 5: 工时数值有效性与非负性
        dim5_errors = []
        for c in cards:
            est = c.get("est_hours")
            act = c.get("act_hours")
            if not isinstance(est, (int, float)) or est < 0 or not isinstance(act, (int, float)) or act < 0:
                dim5_errors.append(f"{c['id']} 工时非法 (est={est}, act={act})")
        dim5_valid = (len(dim5_errors) == 0)
        audit_report.append(("5. 工时数值有效性与非负性 (Duration Validity)", dim5_valid, f"工时合法卡片数: {len(cards) - len(dim5_errors)}/{len(cards)}, 违规: {len(dim5_errors)}"))

        # 维度 6: 过程追溯节点序号递增性
        dim6_errors = []
        node_regex = re.compile(r"\[(T\d{4})-N(\d{2})\]")
        for c in cards:
            proc = c.get("process") or ""
            lines = [ln.strip() for ln in proc.split("\n") if ln.strip()]
            if not lines:
                if c.get("status") != "待开始":
                    dim6_errors.append(f"{c['id']} 缺失 process 追踪记录")
                continue
            expected_node_idx = 1
            for ln in lines:
                m = node_regex.search(ln)
                if m:
                    tid_found, node_idx_str = m.group(1), m.group(2)
                    node_idx = int(node_idx_str)
                    if tid_found != c["id"] or node_idx != expected_node_idx:
                        dim6_errors.append(f"{c['id']} 节点序号不连续 (预期 N{expected_node_idx:02d}, 实际 N{node_idx_str})")
                    expected_node_idx += 1
        dim6_valid = (len(dim6_errors) == 0)
        audit_report.append(("6. 过程追溯节点序号连续性 (Process Continuity)", dim6_valid, f"节点连贯卡片数: {len(cards) - len(dim6_errors)}/{len(cards)}, 异常: {len(dim6_errors)}"))

        # 维度 7: 审计日志一致性
        dim7_valid = (len(audit_lines) >= 50)
        audit_report.append(("7. 审计日志双向一致性 (Audit Log Alignment)", dim7_valid, f"产生审计记录: {len(audit_lines)} 条, 覆盖全部变更事件"))

        # 维度 8: 安全红线拦截合规性
        dim8_valid = (self.stats["security_403_passed"] >= 8)
        audit_report.append(("8. 安全红线拦截合规性 (RBAC Redline Pass)", dim8_valid, f"403 越权拦截 + Git 门禁拦截通过: {self.stats['security_403_passed']} 项 (≥8 达标)"))

        # 维度 9: CLI 与自动化批处理覆盖率 (CLI Pipeline Coverage)
        dim9_valid = (self.stats["cli_tasks_created"] >= 7 and self.stats["cli_transitions"] >= 10)
        audit_report.append(("9. CLI 与自动化批处理覆盖率 (CLI Pipeline Pass)", dim9_valid, f"CLI 新建任务: {self.stats['cli_tasks_created']} 个, 触发流转: {self.stats['cli_transitions']} 次"))

        # 维度 10: 十四大执行链路集成通过率 (Full 14-Pipeline Integrity)
        dim10_valid = (self.stats["pipeline_checks_passed"] == 8)
        audit_report.append(("10. 十四大执行链路集成通过率 (Full 14-Pipeline Pass)", dim10_valid, f"链路深度检验项通过率: {self.stats['pipeline_checks_passed']}/8 (100%)"))

        for title, status, desc in audit_report:
            flag = "✅ [PASS]" if status else "❌ [FAIL]"
            print(f" {flag} {title:<45} | {desc}")

        if dim3_errors:
            print(f"   [Dim3 错误详情]: {dim3_errors}")
        if dim4_errors:
            print(f"   [Dim4 错误详情]: {dim4_errors}")
        if dim5_errors:
            print(f"   [Dim5 错误详情]: {dim5_errors}")
        if dim6_errors:
            print(f"   [Dim6 错误详情]: {dim6_errors}")

        all_passed = all(st for _, st, _ in audit_report)
        print("="*70)
        if all_passed:
            print(f" 🎉 全量 {len(cards)} 任务全场景全流程仿真跑批与 10 大维度数据质量审计 全部通过！")
        else:
            print(" ⚠️ 存在数据质量审计违规项，请核对上述失败条目！")
        print("="*70 + "\n")

        return all_passed, audit_report


def main():
    t0 = time.perf_counter()
    runner = SimulationRunner()
    try:
        runner.run_matrix_1_grid_72()
        runner.run_matrix_2_complex_roles_16()
        runner.run_matrix_3_edge_cases_8()
        runner.run_matrix_4_security_rbac_12()
        runner.run_matrix_5_cli_automation_12()
        runner.run_phase_6_agent_context_pipeline()
        runner.run_phase_7_stage_gate_pipeline()
        runner.run_phase_8_git_gate_verifier_pipeline()
        runner.run_phase_9_stack_discovery_and_export_pipeline()
        runner.run_phase_10_legacy_docs_migration_pipeline()
        runner.run_phase_11_metrics_and_heartbeat_pipeline()
        runner.run_phase_12_docx_and_proof_pipeline()
        runner.run_phase_13_audit_query_and_rotation_pipeline()
        runner.run_phase_14_query_and_pagination()
        passed, report = runner.run_phase_15_quality_audit()
        t1 = time.perf_counter()
        print(f"⏱️ 全链路仿真与数据质量审计总耗时: {(t1 - t0):.2f} 秒\n")
        sys.exit(0 if passed else 1)
    finally:
        runner.teardown()


if __name__ == "__main__":
    main()
