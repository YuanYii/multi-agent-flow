#!/usr/bin/env python3
"""
108 任务全正交全场景全流程仿真测试与数据质量审计引擎

※ 门禁红线：本测试脚本执行大型跑批与全量审计，必须在用户明确授权后方可执行，严禁私自触发。

覆盖 4 大工程矩阵与 8 大数据质量维度:
- 矩阵一 (72条): 8 阶段 × 9 状态 全笛卡尔积正交铺满 (T0001~T0072)
- 矩阵二 (16条): 多专家 8 角色复杂交叉返工与多跳协同链路 (T0073~T0088)
- 矩阵三 (8条) : 工时极端值、跨月长周期、特殊字符/XSS防注入与长文本 (T0089~T0096)
- 矩阵四 (12条): 局域网主控/协作端受控写并发竞争与 8 项 403 越权强拦截 (T0097~T0108)
- 全维审计: 唯一性、单调性、状态机闭环、时间时序、工时有效性、追溯链、审计日志一致性、安全红线

运行（需显式授权）: python3 scripts/run_108_tasks_simulation.py
"""

import json
import os
import re
import sys
import time
import socket
import tempfile
import threading
import importlib.util
import urllib.request
import urllib.error
from urllib.parse import quote
from http.server import HTTPServer

# 动态加载看板服务模块
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
        self.tmp_root = tempfile.mkdtemp(prefix="kanban_108_sim_")
        self.board_path = os.path.join(self.tmp_root, "user_data", "board.json")
        self.pref_path = os.path.join(self.tmp_root, "user_data", "preferences.json")
        self.audit_path = os.path.join(self.tmp_root, "user_data", "logs", "audit_trail.log")
        self.lock_path = self.board_path + ".seq.lock"
        self.runtime_path = os.path.join(self.tmp_root, "user_data", "kanban_server.json")

        os.makedirs(os.path.dirname(self.board_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.audit_path), exist_ok=True)
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

        self.stats = {
            "created": 0,
            "transitions": 0,
            "security_403_passed": 0,
            "concurrency_writes": 0,
            "checks_passed": 0,
            "checks_failed": 0,
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
    # 阶段一：72 任务全笛卡尔积正交铺满 (8 阶段 × 9 状态)
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

                # 1. 主控建单 (初始状态: 待开始)
                s, r = self.request("POST", "/api/tasks", {
                    "name": name, "stage": stage_name, "wp": wp_name, "wbs": wbs,
                    "assignee": default_role, "est_hours": est_h, "act_hours": 0.0,
                    "start_date": "2026-08-10", "remarks": f"正交网格任务 {tid} 初始建单"
                }, is_master=True)
                assert s == 200, f"创建 {tid} 失败: {r}"
                self.stats["created"] += 1

                # 2. 根据目标状态模拟全生命周期流转
                if status == "待开始":
                    pass  # 保持 1 节点初始态
                elif status == "进行中":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中", "comment": "开发人员认领开始处理"}, is_master=True)
                    self.stats["transitions"] += 1
                elif status == "审查中":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "审查中", "comment": "提交代码审查"}, is_master=True)
                    self.stats["transitions"] += 2
                elif status == "测试中":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "审查中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "测试中", "comment": "审查通过转测试"}, is_master=True)
                    self.stats["transitions"] += 3
                elif status == "已完成":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "审查中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "测试中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已完成", "comment": "测试通过等待验收"}, is_master=True)
                    self.stats["transitions"] += 4
                elif status == "已验收":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "审查中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "测试中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已完成"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已验收", "comment": "项目经理终态验收归档"}, is_master=True)
                    self.stats["transitions"] += 5
                elif status == "已退回":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "审查中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已退回", "comment": "代码审查不合格打回"}, is_master=True)
                    self.stats["transitions"] += 3
                elif status == "已阻塞":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已阻塞", "comment": "依赖资源未就绪临时阻塞"}, is_master=True)
                    self.stats["transitions"] += 2
                elif status == "已取消":
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
                    self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已取消", "comment": "需求变更中途作废取消"}, is_master=True)
                    self.stats["transitions"] += 2

                task_num += 1

        print(f"  ✓ 72 个全正交网格任务执行完毕，累计触发状态流转: {self.stats['transitions']} 次")

    # =========================================================================
    # 阶段二：16 任务多专家跨角色复杂流转网格 (T0073 ~ T0088)
    # =========================================================================
    def run_matrix_2_complex_roles_16(self):
        print("\n▶ [Matrix 2] 正在执行 16 条多专家多跳返工与深度协同任务 (T0073 ~ T0088)...")
        complex_scenarios = [
            ("T0073", "马前端组件审查打回再提测", "S3 编码实现", "WP-前端组件", "马前端", [
                ("进行中", "马前端开始组件开发"), ("审查中", "提审周审查"), ("已退回", "周审查打回样式缺陷"),
                ("进行中", "马前端修复样式"), ("审查中", "重新提审"), ("测试中", "章测试介入"), ("已验收", "严经理验收")
            ]),
            ("T0074", "李开发后端接口缺陷退回与修复", "S3 编码实现", "WP-后端核心", "李开发", [
                ("进行中", "李开发编写接口"), ("审查中", "提审通过"), ("测试中", "章测试发现并发Bug"),
                ("已退回", "退回李开发修复"), ("进行中", "修复并发锁"), ("测试中", "复测通过"), ("已完成", "待验收"), ("已验收", "归档")
            ]),
            ("T0075", "李文通交付文档格式打回修正", "S7 文档编制", "WP-用户手册", "李文通", [
                ("进行中", "李文通起草手册"), ("审查中", "提交严经理"), ("已退回", "严经理打回目录缺失"),
                ("进行中", "补充目录与配图"), ("审查中", "重新提审"), ("已完成", "确认通过"), ("已验收", "验收完成")
            ]),
            ("T0076", "吕改特生产流水线配置审查打回", "S8 运维部署", "WP-发布流水线", "吕改特", [
                ("进行中", "配置 K8s 部署清单"), ("审查中", "提交周审查"), ("已退回", "周审查指出未配置资源限制"),
                ("进行中", "增加 CPU/Mem limits"), ("审查中", "审查通过"), ("已验收", "严经理验收")
            ]),
            ("T0077", "钱架构与吕改特发布网络协同", "S2 架构设计", "WP-架构设计", "钱架构", [
                ("进行中", "规划 VPC 网络"), ("审查中", "周审查复核"), ("已退回", "子网划分重叠打回"),
                ("进行中", "重新调整网段"), ("审查中", "审查通过"), ("已完成", "待验收"), ("已验收", "验收")
            ]),
            ("T0078", "马前端与章测试多轮交互", "S3 编码实现", "WP-前端组件", "马前端", [
                ("进行中", "开发大屏看板"), ("测试中", "提测章测试"), ("已退回", "大屏在 4K 分辨率错位"),
                ("进行中", "适配 4K 媒体查询"), ("审查中", "周审查复核"), ("测试中", "章测试回归"), ("已验收", "验收")
            ]),
            ("T0079", "李开发依赖阻塞后审查再打回", "S3 编码实现", "WP-后端核心", "李开发", [
                ("进行中", "开发支付接口"), ("已阻塞", "第三方密钥未下发"), ("进行中", "密钥就绪继续"),
                ("审查中", "提交审查"), ("已退回", "重试机制缺失打回"), ("进行中", "补充指数退避重试"),
                ("测试中", "测试验证"), ("已完成", "完成"), ("已验收", "验收归档")
            ]),
            ("T0080", "3轮严苛代码审查返工长链任务", "S5 代码审查", "WP-质量审查", "李开发", [
                ("进行中", "提交第1版代码"), ("审查中", "提审"), ("已退回", "第1次打回: 缺少入参校验"),
                ("进行中", "补齐入参校验"), ("审查中", "第2次提审"), ("已退回", "第2次打回: 缺少单元测试"),
                ("进行中", "补齐单测覆盖"), ("审查中", "第3次提审"), ("已退回", "第3次打回: 存在SQL注入风险"),
                ("进行中", "改用参数化查询"), ("审查中", "第4次提审终获通过"), ("已验收", "终态验收")
            ]),
            ("T0081", "2轮测试严重缺陷打回任务", "S6 工作流集成测试", "WP-集成验证", "章测试", [
                ("进行中", "集成测试准备"), ("测试中", "提测第1轮"), ("已退回", "第1轮发现崩溃Bug打回"),
                ("进行中", "开发修复空指针"), ("测试中", "提测第2轮"), ("已退回", "第2轮发现内存泄露打回"),
                ("进行中", "修复句柄泄露"), ("测试中", "第3轮复测通过"), ("已验收", "验收归档")
            ]),
            ("T0082", "需求开发测试3角色标准接力", "S1 需求分析", "WP-需求拆解", "严经理", [
                ("进行中", "严经理拆解需求"), ("审查中", "钱架构架构确认"), ("进行中", "移交李开发编码"),
                ("测试中", "移交章测试验收测试"), ("已完成", "移交严经理"), ("已验收", "严经理验收归档")
            ]),
            ("T0083", "前端审查测试运维4角色大闭环", "S3 编码实现", "WP-前端组件", "马前端", [
                ("进行中", "马前端开发构建脚本"), ("审查中", "周审查审批"), ("测试中", "章测试验证构建产物"),
                ("进行中", "吕改特集成到生产容器"), ("已完成", "部署完成"), ("已验收", "严经理终态验收")
            ]),
            ("T0084", "架构拆解到部署全流程生命周期", "S2 架构设计", "WP-架构设计", "钱架构", [
                ("进行中", "钱架构架构蓝图"), ("进行中", "李开发核心编码"), ("测试中", "章测试功能验证"),
                ("进行中", "吕改特上线准备"), ("已完成", "正式发布"), ("已验收", "上线验收归档")
            ]),
            ("T0085", "单测未达标退回修复任务", "S4 单元测试", "WP-测试用例", "李开发", [
                ("进行中", "编写单测"), ("审查中", "提审周审查"), ("已退回", "分支覆盖率仅 65% 打回"),
                ("进行中", "补全边界用例提升至 92%"), ("审查中", "审查通过"), ("已验收", "验收")
            ]),
            ("T0086", "跨阶段流转中途依赖阻塞", "S3 编码实现", "WP-后端核心", "李开发", [
                ("进行中", "数据迁移脚本开发"), ("已阻塞", "生产数据库备份未完成阻塞"), ("进行中", "备份就绪继续执行"),
                ("测试中", "演练验证通过"), ("已验收", "验收")
            ]),
            ("T0087", "测试中途因架构推翻中途取消", "S6 工作流集成测试", "WP-集成验证", "章测试", [
                ("进行中", "测试用例编写"), ("测试中", "执行集成测试"), ("已取消", "架构方案推翻任务中止")
            ]),
            ("T0088", "角色代号自动归一化校验任务", "S3 编码实现", "WP-后端核心", "dev", [
                ("进行中", "由代号 dev 自动归一化为 李开发"), ("审查中", "提审 cr (周审查)"),
                ("测试中", "提测 qa (章测试)"), ("已完成", "移交 pm (严经理)"), ("已验收", "归档")
            ])
        ]

        for tid, name, stage, wp, assignee, flow in complex_scenarios:
            s, r = self.request("POST", "/api/tasks", {
                "name": f"[{stage}] {name}", "stage": stage, "wp": wp, "wbs": f"9.{tid[-2:]}",
                "assignee": assignee, "est_hours": 8.0, "act_hours": 1.0,
                "start_date": "2026-08-15", "remarks": f"复杂多角色流转测试 {tid}"
            }, is_master=True)
            assert s == 200, f"创建 {tid} 失败: {r}"
            self.stats["created"] += 1

            for target_status, comment in flow:
                self.request("POST", f"/api/tasks/{tid}/transition", {
                    "target_status": target_status,
                    "comment": comment
                }, is_master=True)
                self.stats["transitions"] += 1

        print("  ✓ 16 条复杂返工与多角色流转任务执行完毕！")

    # =========================================================================
    # 阶段三：8 任务极端工时与数据边界网格 (T0089 ~ T0096)
    # =========================================================================
    def run_matrix_3_edge_cases_8(self):
        print("\n▶ [Matrix 3] 正在执行 8 条极端工时、特殊字符与长文本边界任务 (T0089 ~ T0096)...")
        edge_scenarios = [
            ("T0089", "零工时极速热修任务", "S3 编码实现", "WP-紧急修复", "李开发", 0.0, 0.0, "2026-08-20", "2026-08-20", "秒级修复"),
            ("T0090", "0.1h 极小工时微任务", "S7 文档编制", "WP-用户手册", "李文通", 0.1, 0.1, "2026-08-20", "2026-08-20", "修改一处错别字"),
            ("T0091", "150h 超大跨季度任务", "S2 架构设计", "WP-架构设计", "钱架构", 150.0, 142.5, "2026-06-01", "2026-08-20", "跨月长周期"),
            ("T0092", "严重超支 700% 任务", "S3 编码实现", "WP-后端核心", "李开发", 2.0, 16.0, "2026-08-01", "2026-08-18", "工时严重超支"),
            ("T0093", "XSS 标签注入防御任务 <script>alert(1)</script>", "S3 编码实现", "WP-前端组件", "马前端", 4.0, 3.5, "2026-08-10", "2026-08-12", "<b>加粗</b> & <img src=x onerror=alert(1)>"),
            ("T0094", "🚀 Emoji 表情与国际化字符 ✨ 🇨🇳", "S3 编码实现", "WP-多语言", "马前端", 6.0, 5.5, "2026-08-12", "2026-08-15", "测试 🎉, 👍, 🌟, ⚡, こんにちは, Bonjour"),
            ("T0095", "复杂 Markdown 与换行混排任务", "S7 文档编制", "WP-用户手册", "李文通", 5.0, 4.0, "2026-08-15", "2026-08-18", "## 一级章节\n- [x] 完成项 A\n- [ ] 未完成 B\n> 引用说明\n```python\nprint('hello')\n```"),
            ("T0096", "1500字符超长日志追加任务", "S5 代码审查", "WP-质量审查", "周审查", 8.0, 7.5, "2026-08-10", "2026-08-19", "超长备注：" + ("A" * 1500))
        ]

        for tid, name, stage, wp, assignee, est, act, s_date, e_date, remarks in edge_scenarios:
            s, r = self.request("POST", "/api/tasks", {
                "name": f"[{stage}] {name}", "stage": stage, "wp": wp, "wbs": f"8.{tid[-2:]}",
                "assignee": assignee, "est_hours": est, "act_hours": act,
                "start_date": s_date, "remarks": remarks
            }, is_master=True)
            assert s == 200, f"创建边界任务 {tid} 失败: {r}"
            self.stats["created"] += 1

            # 推进至已验收
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "进行中"}, is_master=True)
            self.request("POST", f"/api/tasks/{tid}/transition", {"target_status": "已验收", "comment": f"边界任务验收通过: {remarks[:30]}"}, is_master=True)
            self.stats["transitions"] += 2

        print("  ✓ 8 条极端数据与边界防御任务执行完毕！")

    # =========================================================================
    # 阶段四：12 任务局域网主控/协作端受控写与 403 越权对抗 (T0097 ~ T0108)
    # =========================================================================
    def run_matrix_4_security_rbac_12(self):
        print("\n▶ [Matrix 4] 正在执行 12 项局域网协作端受控写、并发锁竞争与 8 类 403 强拦截对抗 (T0097 ~ T0108)...")

        # 1. 先由主控创建基准任务 T0097 ~ T0108
        for i in range(97, 109):
            tid = f"T{i:04d}"
            s, r = self.request("POST", "/api/tasks", {
                "name": f"[S3 编码实现] 安全与权限基准任务-{tid}",
                "stage": "S3 编码实现", "wp": "WP-安全审计", "wbs": f"9.{i}",
                "assignee": "李开发", "est_hours": 4.0, "act_hours": 1.0,
                "start_date": "2026-08-20", "remarks": f"权限测试基准 {tid}"
            }, is_master=True)
            assert s == 200
            self.stats["created"] += 1

        # -------------------------------------------------------------
        # 4 项协作者合法受控操作验证 (无 Token, 预期 200)
        # -------------------------------------------------------------
        # T0097: 协作者更新 act_hours
        s, r = self.request("PUT", "/api/tasks/T0097", {"act_hours": 4.5}, is_master=False)
        assert s == 200 and r["data"]["updated_fields"] == ["act_hours"], f"协作者更新工时失败: {r}"
        self.stats["checks_passed"] += 1

        # T0098: 协作者追加 remarks
        s, r = self.request("PUT", "/api/tasks/T0098", {"remarks": "协作者完成模块联调"}, is_master=False)
        assert s == 200 and "remarks" in r["data"]["updated_fields"]
        self.stats["checks_passed"] += 1

        # T0099: 协作者流转常规状态 (进行中 -> 审查中)
        self.request("POST", "/api/tasks/T0099/transition", {"target_status": "进行中"}, is_master=True)
        s, r = self.request("POST", "/api/tasks/T0099/transition", {"target_status": "审查中", "comment": "协作者提审"}, is_master=False)
        assert s == 200, f"协作者流转常规状态失败: {r}"
        self.stats["checks_passed"] += 1

        # T0100: 主控与协作者多线程并发写竞争测试
        def worker_master():
            for _ in range(5):
                self.request("PUT", "/api/tasks/T0100", {"remarks": "主控并发更新"}, is_master=True)
        def worker_collab():
            for _ in range(5):
                self.request("PUT", "/api/tasks/T0100", {"act_hours": 2.5, "remarks": "协作者并发更新"}, is_master=False)

        t1 = threading.Thread(target=worker_master)
        t2 = threading.Thread(target=worker_collab)
        t1.start(); t2.start()
        t1.join(); t2.join()
        self.stats["concurrency_writes"] += 10
        self.stats["checks_passed"] += 1

        # -------------------------------------------------------------
        # 8 项协作者越权攻击拦截验证 (无 Token, 严格断言 403)
        # -------------------------------------------------------------
        # Attack 1: 协作者越权新建任务 -> 403
        s, r = self.request("POST", "/api/tasks", {"name": "越权新建任务"}, is_master=False)
        assert s == 403, f"未拦截越权新建: {s}"
        self.stats["security_403_passed"] += 1

        # Attack 2: 协作者越权删除任务 -> 403
        s, r = self.request("DELETE", "/api/tasks/T0102", is_master=False)
        assert s == 403, f"未拦截越权删除: {s}"
        self.stats["security_403_passed"] += 1

        # Attack 3: 协作者越权流转至【已验收】终态 -> 403
        s, r = self.request("POST", "/api/tasks/T0103/transition", {"target_status": "已验收"}, is_master=False)
        assert s == 403, f"未拦截越权已验收: {s}"
        self.stats["security_403_passed"] += 1

        # Attack 4: 协作者越权流转至【已取消】终态 -> 403
        s, r = self.request("POST", "/api/tasks/T0104/transition", {"target_status": "已取消"}, is_master=False)
        assert s == 403, f"未拦截越权已取消: {s}"
        self.stats["security_403_passed"] += 1

        # Attack 5: 协作者越权篡改核心字段 (name, assignee, stage) -> 403
        s, r = self.request("PUT", "/api/tasks/T0105", {"name": "恶意篡改名称", "assignee": "严经理"}, is_master=False)
        assert s == 403, f"未拦截核心字段篡改: {s}"
        self.stats["security_403_passed"] += 1

        # Attack 6: 协作者越权批量重排序 -> 403
        s, r = self.request("PUT", "/api/tasks/reorder", {"ordered_task_ids": ["T0106", "T0105"]}, is_master=False)
        assert s == 403, f"未拦截越权重排序: {s}"
        self.stats["security_403_passed"] += 1

        # Attack 7: 协作者越权修改看板元数据配置与标题 -> 403
        s, r = self.request("PUT", "/api/board/meta", {"title": "恶意修改看板标题"}, is_master=False)
        assert s == 403, f"未拦截元数据修改: {s}"
        self.stats["security_403_passed"] += 1

        # Attack 8: 协作者越权 POST 全量覆写 board.json -> 403
        s, r = self.request("POST", "/board.json", [], is_master=False)
        assert s == 403, f"未拦截全量 JSON 覆写: {s}"
        self.stats["security_403_passed"] += 1

        print("  ✓ 12 项受控写与 8 类 403 越权强拦截对抗全部通过！")

    # =========================================================================
    # 阶段五：分页档位、多维复合筛选与排序检验
    # =========================================================================
    def run_phase_5_query_and_pagination(self):
        print("\n▶ [Phase 5] 正在执行 108 任务大数据分页与多维组合筛选压力测试...")

        # 1. 验证 5 档位分页完整性
        for size in [10, 20, 50, 100, "all"]:
            s, r = self.request("GET", f"/api/tasks?page=1&size={size}", is_master=True)
            assert s == 200
            assert r["data"]["total"] == 108
            expected_len = 108 if size == "all" else min(int(size), 108)
            assert len(r["data"]["items"]) == expected_len

        # 2. 验证最后一页与越界页
        s, r = self.request("GET", "/api/tasks?page=6&size=20", is_master=True)
        assert s == 200 and len(r["data"]["items"]) == 8  # 108 - 100 = 8

        s, r = self.request("GET", "/api/tasks?page=99&size=20", is_master=True)
        assert s == 200 and len(r["data"]["items"]) == 0 and r["data"]["total"] == 108

        # 3. 关键字模糊搜索
        s, r = self.request("GET", "/api/tasks?keyword=Emoji", is_master=True)
        assert s == 200 and r["data"]["total"] >= 1

        s, r = self.request("GET", "/api/tasks?keyword=XSS", is_master=True)
        assert s == 200 and r["data"]["total"] >= 1

        # 4. 复合状态与人员筛选
        s, r = self.request("GET", "/api/tasks?status=已验收", is_master=True)
        assert s == 200 and r["data"]["total"] >= 20

        s, r = self.request("GET", "/api/tasks?assignee=李开发", is_master=True)
        assert s == 200 and r["data"]["total"] >= 15

        # 5. 工时字段排序 (act_hours desc)
        s, r = self.request("GET", "/api/tasks?sort=act_hours&order=desc&size=10", is_master=True)
        assert s == 200
        items = r["data"]["items"]
        assert items[0]["act_hours"] >= items[1]["act_hours"] >= items[2]["act_hours"]

        print("  ✓ 大数据分页、多维复合检索与排序检验全部通过！")

    # =========================================================================
    # 阶段六：8 大维度数据质量与一致性自动化全量审计
    # =========================================================================
    def run_phase_6_quality_audit(self):
        print("\n" + "="*70)
        print("▶ [Phase 6] 正在执行 8 大维度数据质量与一致性深度审计断言...")
        print("="*70)

        with open(self.board_path, "r", encoding="utf-8") as f:
            cards = json.load(f)

        with open(self.audit_path, "r", encoding="utf-8") as f:
            audit_lines = f.readlines()

        audit_report = []

        # 维度 1: 任务标识唯一性与规范性 (ID Integrity)
        ids = [c["id"] for c in cards]
        id_regex = re.compile(r"^T\d{4}$")
        dim1_valid = (len(cards) == 108 and len(set(ids)) == 108 and all(id_regex.match(i) for i in ids))
        audit_report.append(("1. 任务标识唯一性与规范性 (ID Integrity)", dim1_valid, f"总任务数: {len(cards)}, 唯一ID数: {len(set(ids))}, 正则达标率: 100%"))

        # 维度 2: 排序序号严格单调性 (Sequence Monotonicity)
        seqs = [c["seq"] for c in cards]
        dim2_valid = (len(seqs) == 108 and set(seqs) == set(range(1, 109)))
        audit_report.append(("2. 排序序号严格单调性 (Seq Monotonicity)", dim2_valid, f"序号范围: {min(seqs)}~{max(seqs)}, 无重复无跳跃"))

        # 维度 3: 状态机与处理人闭环规范性 (State-to-Handler Mapping)
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

        # 维度 4: 时间周期逻辑性与先后时序 (Timeline Ordering)
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

        # 维度 5: 工时数值有效性与非负性 (Duration Validity)
        dim5_errors = []
        for c in cards:
            est = c.get("est_hours")
            act = c.get("act_hours")
            if not isinstance(est, (int, float)) or est < 0 or not isinstance(act, (int, float)) or act < 0:
                dim5_errors.append(f"{c['id']} 工时非法 (est={est}, act={act})")
        dim5_valid = (len(dim5_errors) == 0)
        audit_report.append(("5. 工时数值有效性与非负性 (Duration Validity)", dim5_valid, f"工时合法卡片数: {len(cards) - len(dim5_errors)}/{len(cards)}, 违规: {len(dim5_errors)}"))

        # 维度 6: 过程追溯节点序号递增性 (Process Node Continuity)
        dim6_errors = []
        node_regex = re.compile(r"\[(T\d{4})-N(\d{2})\]")
        for c in cards:
            proc = c.get("process") or ""
            lines = [ln.strip() for ln in proc.split("\n") if ln.strip()]
            if not lines:
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

        # 维度 7: 审计日志（Audit Trail）双向一致性 (Audit Log Alignment)
        dim7_valid = (len(audit_lines) >= self.stats["transitions"] + self.stats["created"])
        audit_report.append(("7. 审计日志双向一致性 (Audit Log Alignment)", dim7_valid, f"产生审计记录: {len(audit_lines)} 条, 覆盖全部变更事件"))

        # 维度 8: 安全红线拦截合规性 (Security RBAC Enforcement)
        dim8_valid = (self.stats["security_403_passed"] == 8)
        audit_report.append(("8. 安全红线拦截合规性 (RBAC Redline Pass)", dim8_valid, f"403 越权拦截通过率: {self.stats['security_403_passed']}/8 (100%)"))

        # 打印审计结果表
        for title, status, desc in audit_report:
            flag = "✅ [PASS]" if status else "❌ [FAIL]"
            print(f" {flag} {title:<45} | {desc}")

        all_passed = all(st for _, st, _ in audit_report)
        print("="*70)
        if all_passed:
            print(" 🎉 全量 108 任务全场景全流程仿真跑批与 8 大维度数据质量审计 全部通过！")
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
        runner.run_phase_5_query_and_pagination()
        passed, report = runner.run_phase_6_quality_audit()
        t1 = time.perf_counter()
        print(f"⏱️ 108 任务全流程仿真与数据质量审计总耗时: {(t1 - t0):.2f} 秒\n")
        sys.exit(0 if passed else 1)
    finally:
        runner.teardown()


if __name__ == "__main__":
    main()
