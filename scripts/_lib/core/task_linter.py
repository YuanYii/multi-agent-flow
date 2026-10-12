"""
task_linter.py · 任务卡单一职责原则 (Single Responsibility Principle) 校验引擎

职责：
1. 校验新建任务卡是否遵循单一职责原则（Single Role / Single Artifact / Single Type / Single Action）；
2. 识别并拦截跨领域混合、并列复合动作、任务类型与角色不匹配等粗颗粒度复合大卡；
3. 输出结构化诊断原因与智能拆卡建议 (Split Suggestions)；
4. 支持同领域合法并列操作的白名单防误判与 [HOTFIX] 应急例外通道。
"""
import re
from typing import Dict, List, Any, Optional, Tuple


# 6 大研发正交领域特征词库
DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "ARCHITECT": [
        "架构", "adr", "选型", "方案设计", "概要设计", "技术调研", "领域模型",
        "分层设计", "契约设计"
    ],
    "BACKEND": [
        "sql", "接口", "api", "orm", "repository", "controller", "service",
        "rbac", "数据库", "表结构", "后端", "dto", "dao", "entity", "中间件",
        "存储过程", "redis", "查询下推", "数据聚合"
    ],
    "FRONTEND": [
        "组件", "弹窗", "vue", "react", "页面", "ui", "css", "样式", "hook",
        "前端", "dom", "路由", "表格", "抽屉", "时间轴", "表单", "视图", "看板ui",
        "composable", "pinia", "vuex"
    ],
    "QA": [
        "压测", "e2e", "自动化测试", "回归用例", "性能测试", "测试报告", "边界测试",
        "准出测试", "端到端测试", "集成测试用例", "测试套件", "准出回归"
    ],
    "DEVOPS": [
        "nginx", "docker", "k8s", "ci/cd", "流水线", "部署", "监控", "日志系统",
        "迁移脚本", "ssl证书", "构建配置", "prometheus", "grafana"
    ],
    "DOCS": [
        "用户手册", "开发文档", "接口文档", "readme", "api文档", "操作指引",
        "帮助中心", "更新日志", "使用说明", "交付文档", "白皮书"
    ]
}

# 复合跨阶段连接词特征（用于捕获强行拼接多个动作的复合任务）
CROSS_CONJUNCTIONS: List[str] = [
    r"并且(?:开发|实现|完成|编写|设计|部署|测试|优化|配置|接入|上线|重构|集成|修复)",
    r"以及(?:开发|实现|完成|编写|设计|部署|测试|优化|配置|接入|上线|重构|集成|修复)",
    r"同时(?:开发|实现|完成|编写|设计|部署|测试|优化|配置|接入|上线|重构|集成|修复)",
    r"并(?:完成|实现|部署|测试|接入|编写|重构|配置|上线|开发|设计|优化|集成|修复)",
    r"顺便(?:完成|修改|优化|编写|调整|开发|设计)",
    r"且(?:完成|实现|编写|上线|部署|测试|开发|设计|优化|重构|集成|修复)"
]

# 同领域合理并列词组白名单（避免误判同领域内的常规操作，如“筛选与排序”）
SAFE_PHRASES: List[str] = [
    "筛选与排序", "筛选和排序", "增删改查", "导入和导出", "导入与导出",
    "登录与登出", "登录和登出", "启用与禁用", "启用和禁用", "开启与关闭",
    "上传与下载", "上传和下载", "前后端组件化", "前后端协作", "接口契约与前端e2e",
    "接口契约与e2e", "待办列表sql批量聚合", "任务拒付停运接口经办人与主管rbac",
    "前后端组件化与性能重构工作包"
]


def lint_task_single_responsibility(
    name: str,
    task_type: str = "A",
    assignee: Optional[str] = None,
    est_hours: float = 0.0,
    custom_cfg: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str, List[str], List[str]]:
    """
    核验任务卡是否遵循单一职责原则。

    参数：
        name: 任务名称
        task_type: 任务类型（A-G）
        assignee: 负责角色/人员名称
        est_hours: 预估工时（小时）
        custom_cfg: 自定义配置（可选，扩展词库与忽略项）

    返回：
        (is_valid, violation_type, reasons, split_suggestions)
        - is_valid: True 为合规原子任务，False 为违规复合任务
        - violation_type: 'OK' | 'EMPTY_NAME' | 'COMPOSITE_TASK' | 'TYPE_ROLE_MISMATCH' | 'GRANULARITY_EXCEEDED'
        - reasons: 违规原因列表
        - split_suggestions: 推荐的原子任务拆解清单
    """
    if not name or not str(name).strip():
        return False, "EMPTY_NAME", ["任务名称不能为空"], []

    name_clean = str(name).strip()
    reasons: List[str] = []
    suggestions: List[str] = []

    # 1. 紧急 Hotfix / Bugfix 例外通道
    if name_clean.upper().startswith(("[HOTFIX]", "[BUGFIX]", "[EMERGENCY]")):
        return True, "OK", [], []

    # 2. 安全短语与测试命名空间预处理
    sanitized_name = name_clean
    # 剥离测试命名空间前缀（如 E2E-、TEST-、MOCK-、[E2E]、[TEST]），避免测试套件标识被误判为 QA 领域冲突
    sanitized_name = re.sub(r"^(?:\[?(?:E2E|TEST|MOCK)\]?[-_\s:]+)", "", sanitized_name, flags=re.IGNORECASE)

    for idx, phrase in enumerate(SAFE_PHRASES):
        if phrase.lower() in sanitized_name.lower():
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            sanitized_name = pattern.sub(f"__SAFE_PHRASE_{idx}__", sanitized_name)

    # 3. 跨领域正交关键词冲突检测
    name_lower = sanitized_name.lower()
    matched_domains: List[Tuple[str, str]] = []

    # 合并自定义领域词库
    effective_domains = dict(DOMAIN_KEYWORDS)
    if custom_cfg and isinstance(custom_cfg.get("domain_keywords"), dict):
        for d_key, kws in custom_cfg["domain_keywords"].items():
            if isinstance(kws, list):
                effective_domains.setdefault(d_key, []).extend(kws)

    for domain, kw_list in effective_domains.items():
        for kw in kw_list:
            kw_clean = kw.strip().lower()
            if kw_clean and kw_clean in name_lower:
                matched_domains.append((domain, kw))
                break

    # 提取命中的唯一领域
    unique_domains = list({d[0] for d in matched_domains})
    # 领域交叉规则：如果同时命中 2 个或以上不同的正交研发领域
    if len(unique_domains) >= 2:
        domain_desc = ", ".join([f"{d[0]}(关键词: {d[1]})" for d in matched_domains])
        reasons.append(f"检测到跨领域混合任务：命中 {len(unique_domains)} 个正交研发领域 [{domain_desc}]")
        for d, kw in matched_domains:
            role_hint = {
                "ARCHITECT": "钱架构",
                "BACKEND": "李开发",
                "FRONTEND": "马前端",
                "QA": "章测试",
                "DEVOPS": "吕改特",
                "DOCS": "李文通"
            }.get(d, "对应专职专家")
            suggestions.append(f"拆分原子任务：【{kw}】相关工作由 [{role_hint}] 独立承接建卡")

    # 4. 复合连接词与多动词检测
    for pattern in CROSS_CONJUNCTIONS:
        m = re.search(pattern, sanitized_name)
        if m:
            conjunction_str = m.group(0)
            reasons.append(f"包含复合并列动作连词 [{conjunction_str}]，违反单目标原子交付原则")
            parts = re.split(pattern, name_clean, maxsplit=1)
            if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
                suggestions.append(f"子任务 1: {parts[0].strip()}")
                suggestions.append(f"子任务 2: {conjunction_str.replace('并且', '').replace('以及', '').replace('同时', '').replace('并', '')} {parts[1].strip()}")

    # 5. 任务类型与角色契约一致性校验
    clean_role = str(assignee or "").strip()
    is_mismatch = False
    if clean_role:
        clean_role_upper = clean_role.upper()
        # E 类为用户/PM自执行任务（允许 PM / USER / 外部人员自执行）
        if task_type == "E":
            if not any(k in clean_role or k in clean_role_upper for k in ("PM", "USER", "严经理", "用户", "YUANYII", "ADMIN", "OWNER")):
                reasons.append(f"E 类用户自执行任务卡负责角色通常应为严经理 (PM) 或用户 (USER)，当前指定为 [{clean_role}]")
                is_mismatch = True

    # 6. 单卡颗粒度与工时上限预警 (> 8.0h)
    is_granularity_exceeded = False
    if est_hours > 8.0:
        reasons.append(f"预估工时 {est_hours:.1f}h 超过单卡原子颗粒度上限 (8.0h)，必须分解为工作包 (Work Package) 子任务链")
        suggestions.append(f"建议建立工作包 (如 WP-XX-01)，将大任务按子功能拆分为 2~4h 的多个原子子任务")
        is_granularity_exceeded = True

    is_valid = len(reasons) == 0
    if not is_valid:
        if is_mismatch:
            violation_type = "TYPE_ROLE_MISMATCH"
        elif is_granularity_exceeded and len(reasons) == 1:
            violation_type = "GRANULARITY_EXCEEDED"
        else:
            violation_type = "COMPOSITE_TASK"
    else:
        violation_type = "OK"

    return is_valid, violation_type, reasons, suggestions


# 蓝军对抗性特征词与隐式复合解耦模式
ADVERSARIAL_DECOUPLING_PATTERNS = [
    # 模式 1: 契约/定义 与 业务实现混杂
    (
        r"(?:契约|定义|文档|spec|mock).*(?:实现|编写|开发|编码)|(?:实现|编写|开发|编码).*(?:契约|定义|文档|spec|mock)",
        "契约/Mock定义与业务编码混杂在单卡中，阻碍前端Mock先行并行协作",
        ["接口契约定义与 Mock 规范定稿", "接口后端业务逻辑实现"]
    ),
    # 模式 2: 数据表/DDL 与 业务接口混杂
    (
        r"(?:表结构|表设计|ddl|数据库迁移|迁移脚本).*(?:接口|api|service|服务)|(?:接口|api|service|服务).*(?:表结构|表设计|ddl|数据库迁移|迁移脚本)",
        "数据库表结构/迁移具备独立交付性，与上层业务接口混杂违背交付可验性",
        ["数据库表结构设计与迁移脚本编写", "业务接口及数据访问层实现"]
    ),
    # 模式 3: 隐式双动词复合阶段
    (
        r"(?:设计|编写|开发|构建)\s*(?:并|以及|且)\s*(?:实现|部署|上线|测试|验证)",
        "包含两个不同交付阶段的动作，失败时无法有效隔离回滚面",
        ["阶段性设计与规范定义", "具体功能实现与验证"]
    )
]


def adversarial_srp_lint(
    name: str,
    task_type: str = "A",
    assignee: Optional[str] = None,
    est_hours: float = 0.0,
    custom_cfg: Optional[Dict[str, Any]] = None
) -> Tuple[bool, bool, List[str], List[str]]:
    """
    单轮蓝军对抗性质询校验接口 (Adversarial SRP Challenge)。

    在基础 lint_task_single_responsibility 规则之上，站在审计者视角进行挑刺质询：
    Q1. 交付可验性：是否存在可独立交付/单测的阶段性交付物（如：表迁移与接口逻辑）；
    Q2. 依赖并行性：能否先行产出契约/Mock 提前解锁下游；
    Q3. 失败隔离性：子功能打回是否会导致不相关代码连带回滚；
    Q4. 动作单一性：是否隐含多动词、混合目标或工时 > 4.0h。

    返回:
        (is_atomic, can_split_further, challenge_reasons, split_suggestions)
        - is_atomic: True 为合规原子卡，False 为存在复合特征
        - can_split_further: True 表示被蓝军质询命中，建议执行单次二次细拆；False 为不可再拆
        - challenge_reasons: 质疑理由列表
        - split_suggestions: 细拆子任务建议清单
    """
    if not name or not str(name).strip():
        return False, False, ["任务名称不能为空"], []

    name_clean = str(name).strip()

    # 1. 紧急通道豁免
    if name_clean.upper().startswith(("[HOTFIX]", "[BUGFIX]", "[EMERGENCY]")):
        return True, False, [], []

    # 2. 先行执行标准单一职责门禁
    is_valid, violation_type, base_reasons, base_suggestions = lint_task_single_responsibility(
        name=name,
        task_type=task_type,
        assignee=assignee,
        est_hours=est_hours,
        custom_cfg=custom_cfg
    )

    challenge_reasons: List[str] = list(base_reasons)
    split_suggestions: List[str] = list(base_suggestions)

    # 3. 预处理白名单短语
    sanitized_name = name_clean
    for idx, phrase in enumerate(SAFE_PHRASES):
        if phrase.lower() in sanitized_name.lower():
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            sanitized_name = pattern.sub(f"__SAFE_PHRASE_{idx}__", sanitized_name)

    adversarial_sugs: List[str] = []
    # 4. 执行对抗性挑刺模式匹配 (Q1/Q2/Q3)
    for pat, reason, sugs in ADVERSARIAL_DECOUPLING_PATTERNS:
        if re.search(pat, sanitized_name, re.IGNORECASE):
            challenge_reasons.append(f"【对抗性质询】{reason}")
            adversarial_sugs.extend(sugs)

    # 若命中高优先级领域对抗解耦模式，优先采用高质量领域拆分建议，避免与粗糙的连词截断重复
    if adversarial_sugs:
        split_suggestions = adversarial_sugs

    # 5. 执行工时与阶段质询 (Q4)
    if est_hours > 4.0:
        challenge_reasons.append(f"【对抗性质询】预估工时 {est_hours:.1f}h 超过单轮原子工时推荐上限 (4.0h)，存在隐式复合阶段")
        if not split_suggestions:
            split_suggestions.extend([
                f"{name_clean} - 核心主干流程",
                f"{name_clean} - 异常边界与校验"
            ])

    if challenge_reasons or not is_valid:
        # 保持顺序去重建议
        dedup_sugs = list(dict.fromkeys(split_suggestions))
        return False, True, challenge_reasons, dedup_sugs

    return True, False, [], []


def apply_one_pass_srp_loop(
    tasks: List[Dict[str, Any]],
    custom_cfg: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    执行单轮对抗性回环拆解 (One-Pass Adversarial SRP Loop)：
    针对输入的初次候选任务列表，逐一执行蓝军对抗性质询；
    对命中可再拆项执行单次二次细拆；
    二次细拆完成后立即收敛，不再进行第二轮/递归质询。

    参数：
        tasks: 候选任务字典列表
        custom_cfg: 可选的自定义配置

    返回：
        refined_tasks: 收敛后的终态任务列表
    """
    refined_tasks: List[Dict[str, Any]] = []

    for task in tasks:
        name = str(task.get("name") or "").strip()
        task_type = str(task.get("type") or task.get("task_type") or "A")
        assignee = task.get("assignee") or task.get("owner")
        est_hours = float(task.get("est_hours") or 0.0)

        is_atomic, can_split, reasons, suggestions = adversarial_srp_lint(
            name=name,
            task_type=task_type,
            assignee=assignee,
            est_hours=est_hours,
            custom_cfg=custom_cfg
        )

        if can_split and suggestions:
            # Pass 2: 单次二次细拆分摊工时，下限 1.0h
            sub_count = len(suggestions)
            sub_hours = round(est_hours / sub_count, 1) if est_hours > 0 else 2.0
            if sub_hours < 1.0:
                sub_hours = 1.0

            for idx, sug in enumerate(suggestions, start=1):
                clean_name = sug
                for prefix in ("子任务 1:", "子任务 2:", "子任务 3:", "拆分原子任务："):
                    if clean_name.startswith(prefix):
                        clean_name = clean_name[len(prefix):].strip()

                sub_task = dict(task)
                sub_task["name"] = clean_name
                sub_task["est_hours"] = sub_hours
                sub_task["split_from"] = name
                sub_task["adversarial_audit"] = {
                    "challenged": True,
                    "reasons": reasons,
                    "split_round": 1,
                    "is_atomic": True  # 单轮细拆后强制收敛，不再继续拆分
                }
                refined_tasks.append(sub_task)
        else:
            # 无需拆分或已是原子任务
            atomic_task = dict(task)
            if "est_hours" not in atomic_task:
                atomic_task["est_hours"] = est_hours
            atomic_task["adversarial_audit"] = {
                "challenged": False,
                "reasons": reasons,
                "split_round": 0,
                "is_atomic": is_atomic
            }
            refined_tasks.append(atomic_task)

    return refined_tasks

