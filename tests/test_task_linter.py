"""
test_task_linter.py · 任务卡单一职责原则 (Single Responsibility Principle) 单元测试套件
"""
import pytest
import os
import sys

SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPT_DIR)

from _lib.core.task_linter import (
    lint_task_single_responsibility,
    adversarial_srp_lint,
    apply_one_pass_srp_loop,
    DOMAIN_KEYWORDS
)


class TestTaskLinterSingleResponsibility:
    """单一任务原则核心校验引擎测试"""

    # --- 1. 正向原子任务测试 (Positive Cases) ---

    @pytest.mark.parametrize("task_name, assignee, task_type", [
        ("待办工作台高性能聚合架构方案设计 (ADR)", "钱架构", "B"),
        ("重构待办列表SQL批量聚合查询下推消除内存全量加载", "李开发", "B"),
        ("抽离单车历史沟通记录时间轴弹窗组件", "马前端", "B"),
        ("执行待办重构全量接口契约与前端E2E自动化测试准出回归", "章测试", "A"),
        ("配置Nginx反向代理与静态资源Gzip压缩", "吕改特", "D"),
        ("编写待办工作台业务操作指引手册", "李文通", "C"),
        ("修复空指针异常导致的用户登录失败", "李开发", "A"),
        ("抽离挂机10秒极简留痕录入四宫格磁贴弹窗组件", "马前端", "B"),
        ("补齐任务拒付停运接口经办人与主管RBAC防越权校验", "李开发", "B"),
    ])
    def test_valid_atomic_tasks(self, task_name, assignee, task_type):
        """合法原子任务校验通过"""
        is_valid, v_type, reasons, suggestions = lint_task_single_responsibility(
            name=task_name,
            assignee=assignee,
            task_type=task_type,
            est_hours=2.0
        )
        assert is_valid is True
        assert v_type == "OK"
        assert len(reasons) == 0

    # --- 2. 同领域合理并列词组白名单测试 (Safe Phrases) ---

    @pytest.mark.parametrize("safe_name, assignee", [
        ("重构待办列表筛选与排序接口", "李开发"),
        ("实现用户登录与登出状态机流转", "李开发"),
        ("客户基础信息增删改查接口编写", "李开发"),
        ("支持车辆数据导入和导出功能", "李开发"),
        ("账号启用与禁用状态切换", "李开发"),
        ("待办工作台前后端组件化与性能重构工作包", "严经理"),
    ])
    def test_safe_conjunction_phrases_not_blocked(self, safe_name, assignee):
        """同领域内合理的并列词不被误拦截"""
        is_valid, v_type, reasons, suggestions = lint_task_single_responsibility(
            name=safe_name,
            assignee=assignee,
            task_type="B",
            est_hours=3.0
        )
        assert is_valid is True
        assert v_type == "OK"
        assert len(reasons) == 0

    @pytest.mark.parametrize("test_prefix_name, assignee", [
        ("E2E-登录接口开发", "李开发"),
        ("E2E-用户手册编制", "李文通"),
        ("E2E-看板首页样式", "马前端"),
        ("E2E-总体架构设计", "钱架构"),
        ("E2E-发布流水线阻塞", "吕改特"),
        ("[TEST] 订单接口实现", "李开发"),
        ("MOCK-数据表结构设计", "钱架构"),
    ])
    def test_test_namespace_prefixes_not_misclassified_as_qa(self, test_prefix_name, assignee):
        """测试命名空间前缀（E2E-、TEST-、MOCK- 等）不误判为 QA 领域冲突"""
        is_valid, v_type, reasons, suggestions = lint_task_single_responsibility(
            name=test_prefix_name,
            assignee=assignee,
            task_type="A",
            est_hours=2.0
        )
        assert is_valid is True
        assert v_type == "OK"
        assert len(reasons) == 0

    # --- 3. 跨领域复合任务拦截测试 (Cross-Domain Composite) ---

    @pytest.mark.parametrize("composite_name", [
        "编写架构方案并开发前后端页面",
        "重构SQL接口并设计Vue表格弹窗组件",
        "设计ADR选型方案并且完成Nginx部署",
        "开发用户接口并编写E2E自动化测试用例并部署K8s",
        "编写SQL聚合查询并编写操作指引文档",
    ])
    def test_cross_domain_composite_tasks_blocked(self, composite_name):
        """跨领域混合大卡必须被拦截并给出拆分建议"""
        is_valid, v_type, reasons, suggestions = lint_task_single_responsibility(
            name=composite_name,
            assignee="李开发",
            task_type="A"
        )
        assert is_valid is False
        assert v_type in ("COMPOSITE_TASK", "TYPE_ROLE_MISMATCH")
        assert len(reasons) >= 1
        assert len(suggestions) >= 1
        assert any("跨领域" in r or "连词" in r for r in reasons)

    # --- 4. 复合动作连词拦截测试 (Conjunction Patterns) ---

    @pytest.mark.parametrize("conj_name", [
        "开发待办接口并且开发短信弹窗",
        "优化数据库查询以及完成测试用例",
        "编写接口同时实现Vue页面",
        "重构后端代码并部署上线",
        "修改样式顺便优化SQL查询",
        "实现鉴权且上线部署",
    ])
    def test_conjunction_patterns_blocked(self, conj_name):
        """包含强行拼接复合连词的任务必须拦截"""
        is_valid, v_type, reasons, suggestions = lint_task_single_responsibility(
            name=conj_name,
            assignee="李开发"
        )
        assert is_valid is False
        assert v_type == "COMPOSITE_TASK"
        assert any("并列动作连词" in r or "跨领域" in r for r in reasons)
        assert len(suggestions) >= 1

    # --- 5. [HOTFIX] 应急例外通道测试 ---

    @pytest.mark.parametrize("hotfix_name", [
        "[HOTFIX] 紧急修复线上崩溃并重启Nginx与数据库",
        "[BUGFIX] 修复空指针并同步更新配置",
        "[EMERGENCY] 线上支付回调异常抢修并部署",
    ])
    def test_hotfix_bypass(self, hotfix_name):
        """带 [HOTFIX] / [BUGFIX] 前缀的应急任务支持特批放行"""
        is_valid, v_type, reasons, suggestions = lint_task_single_responsibility(
            name=hotfix_name,
            assignee="李开发",
            task_type="D"
        )
        assert is_valid is True
        assert v_type == "OK"
        assert len(reasons) == 0

    # --- 6. 任务类型与角色契约一致性测试 ---

    def test_type_e_user_or_pm_only(self):
        """E 类用户自执行任务分配给普通开发被拦截"""
        is_valid, v_type, reasons, _ = lint_task_single_responsibility(
            name="用户审批任务",
            assignee="马前端",
            task_type="E"
        )
        assert is_valid is False
        assert v_type == "TYPE_ROLE_MISMATCH"
        assert any("E 类用户自执行任务卡负责角色通常应为严经理" in r for r in reasons)

    # --- 7. 工时上限与颗粒度测试 ---

    def test_large_est_hours_warning(self):
        """超过 8.0h 的大任务触发颗粒度拆分建议"""
        is_valid, v_type, reasons, suggestions = lint_task_single_responsibility(
            name="重构待办列表SQL聚合查询",
            assignee="李开发",
            task_type="B",
            est_hours=12.0
        )
        assert is_valid is False
        assert v_type == "GRANULARITY_EXCEEDED"
        assert any("超过单卡原子颗粒度上限" in r for r in reasons)
        assert any("工作包" in s for s in suggestions)

    # --- 8. 空任务名边界测试 ---

    def test_empty_task_name(self):
        """空任务名称防御性拦截"""
        is_valid, v_type, reasons, _ = lint_task_single_responsibility(
            name="   ",
            assignee="李开发"
        )
        assert is_valid is False
        assert v_type == "EMPTY_NAME"
        assert "任务名称不能为空" in reasons[0]

    # --- 9. 自定义扩展词库测试 ---

    def test_custom_domain_keywords(self):
        """支持项目配置扩展业务领域关键词"""
        custom_cfg = {
            "domain_keywords": {
                "HARDWARE": ["北斗设备", "obd终端", "gps天线"],
                "BACKEND": ["报文解析"]
            }
        }
        is_valid, v_type, reasons, suggestions = lint_task_single_responsibility(
            name="重构obd终端报文解析并设计北斗设备硬件协议",
            assignee="李开发",
            task_type="A",
            custom_cfg=custom_cfg
        )
        # 命中 HARDWARE 与 BACKEND 两个领域
        assert is_valid is False
        assert v_type == "COMPOSITE_TASK"

    # --- 10. CLI 门禁集成测试 ---

    def test_transition_task_cli_srp_rejection_and_force(self):
        """CLI 建卡模式触发 SRP 拦截与 --force 绕过"""
        from transition_task import transition_task_pipeline

        # 1. 复合任务被拦截
        ok = transition_task_pipeline(
            config_path=None,
            current_role="PM",
            assignee="李开发",
            task_name="编写架构方案并开发前后端页面",
            create_only=True,
            force=False
        )
        assert ok is False

        # 2. 携带 force=True 强制放行
        ok_force = transition_task_pipeline(
            config_path=None,
            current_role="PM",
            assignee="李开发",
            task_name="编写架构方案并开发前后端页面",
            create_only=True,
            force=True
        )
        assert ok_force is True


class TestAdversarialSRPLoop:
    """单轮对抗性提问回环机制 (One-Pass Adversarial SRP Loop) 单元测试"""

    def test_adversarial_lint_pass_on_atomic(self):
        """标准原子任务通过蓝军挑刺质询，不可再拆"""
        is_atomic, can_split, reasons, suggestions = adversarial_srp_lint(
            name="重构待办列表筛选与排序接口",
            assignee="李开发",
            task_type="A",
            est_hours=2.0
        )
        assert is_atomic is True
        assert can_split is False
        assert len(reasons) == 0
        assert len(suggestions) == 0

    def test_adversarial_lint_challenged_on_decoupling(self):
        """契约与实现混杂、数据表与接口混杂的任务被蓝军质询命中并建议细拆"""
        # 1. 契约与实现混杂
        is_atomic, can_split, reasons, suggestions = adversarial_srp_lint(
            name="用户认证接口契约定义并实现业务逻辑",
            assignee="李开发",
            task_type="A",
            est_hours=3.5
        )
        assert is_atomic is False
        assert can_split is True
        assert any("契约/Mock定义与业务编码混杂" in r for r in reasons)
        assert len(suggestions) >= 2

        # 2. 数据表与接口混杂
        is_atomic2, can_split2, reasons2, suggestions2 = adversarial_srp_lint(
            name="订单数据表结构设计与增删改查接口编写",
            assignee="李开发",
            task_type="A",
            est_hours=3.0
        )
        assert is_atomic2 is False
        assert can_split2 is True
        assert any("数据库表结构/迁移具备独立交付性" in r for r in reasons2)

    def test_adversarial_lint_challenged_on_high_hours(self):
        """工时超过 4.0h 触发蓝军 Q4 工时质询"""
        is_atomic, can_split, reasons, suggestions = adversarial_srp_lint(
            name="重构待办列表SQL批量聚合查询下推",
            assignee="李开发",
            task_type="A",
            est_hours=6.0
        )
        assert is_atomic is False
        assert can_split is True
        assert any("超过单轮原子工时推荐上限 (4.0h)" in r for r in reasons)
        assert len(suggestions) >= 2

    def test_apply_one_pass_srp_loop_executes_single_round(self):
        """验证单轮回环调度器仅执行一轮细拆后立即收敛"""
        initial_tasks = [
            {
                "name": "用户认证接口契约定义并实现业务逻辑",
                "assignee": "李开发",
                "type": "A",
                "est_hours": 4.0
            },
            {
                "name": "编写用户操作指引手册",
                "assignee": "李文通",
                "type": "C",
                "est_hours": 2.0
            }
        ]

        refined_tasks = apply_one_pass_srp_loop(initial_tasks)

        # 第 1 个任务被单轮细拆为 2 个子任务，第 2 个任务保持不变，总数为 3
        assert len(refined_tasks) == 3

        # 校验子任务元数据
        sub_tasks = [t for t in refined_tasks if t.get("split_from") == "用户认证接口契约定义并实现业务逻辑"]
        assert len(sub_tasks) == 2
        for st in sub_tasks:
            assert st["adversarial_audit"]["challenged"] is True
            assert st["adversarial_audit"]["split_round"] == 1
            assert st["adversarial_audit"]["is_atomic"] is True
            assert st["est_hours"] == 2.0

        # 校验未细拆任务元数据
        doc_task = [t for t in refined_tasks if t["name"] == "编写用户操作指引手册"][0]
        assert doc_task["adversarial_audit"]["challenged"] is False
        assert doc_task["adversarial_audit"]["split_round"] == 0
        assert doc_task["adversarial_audit"]["is_atomic"] is True
        assert doc_task["est_hours"] == 2.0

        # 严格验证：再次执行回环调度器，任务列表不再变化（单轮即止，不重复递归）
        second_pass = apply_one_pass_srp_loop(refined_tasks)
        assert len(second_pass) == len(refined_tasks)

    def test_adversarial_lint_pattern3_implicit_composite_phase(self):
        """模式 3：隐式双动词复合阶段（设计并实现/构建且部署）被挑刺命中"""
        is_atomic, can_split, reasons, suggestions = adversarial_srp_lint(
            name="设计并实现全局异常拦截器",
            assignee="李开发",
            task_type="A",
            est_hours=3.0
        )
        assert is_atomic is False
        assert can_split is True
        assert any("包含两个不同交付阶段的动作" in r for r in reasons)
        assert len(suggestions) == 2

    def test_adversarial_lint_hotfix_bypass_and_empty_name(self):
        """验证 Hotfix 紧急通道放行与空名称防御"""
        # 1. Hotfix 放行
        is_atomic, can_split, reasons, suggestions = adversarial_srp_lint(
            name="[HOTFIX] 紧急修复接口契约定义并实现",
            assignee="李开发",
            task_type="A",
            est_hours=3.0
        )
        assert is_atomic is True
        assert can_split is False
        assert len(reasons) == 0

        # 2. 空名称拦截
        is_atomic_empty, can_split_empty, reasons_empty, _ = adversarial_srp_lint(
            name="",
            assignee="李开发"
        )
        assert is_atomic_empty is False
        assert can_split_empty is False
        assert "任务名称不能为空" in reasons_empty[0]

    def test_apply_one_pass_srp_loop_cross_domain_and_fallback(self):
        """验证基础跨领域任务在单轮回环中的拆分与建议清洗"""
        tasks = [
            {
                "name": "编写架构方案并开发前后端页面",
                "assignee": "李开发",
                "est_hours": 6.0
            }
        ]
        results = apply_one_pass_srp_loop(tasks)
        assert len(results) >= 2
        for r in results:
            assert r["adversarial_audit"]["challenged"] is True
            assert r["adversarial_audit"]["split_round"] == 1
            assert r["adversarial_audit"]["is_atomic"] is True
            assert not r["name"].startswith("拆分原子任务：")

    def test_apply_one_pass_srp_loop_empty_and_missing_fields(self):
        """验证空任务列表与缺省字段鲁棒性"""
        assert apply_one_pass_srp_loop([]) == []

        task_missing_fields = [{"name": "编写用户手册"}]
        res = apply_one_pass_srp_loop(task_missing_fields)
        assert len(res) == 1
        assert res[0]["est_hours"] == 0.0
        assert res[0]["adversarial_audit"]["is_atomic"] is True


