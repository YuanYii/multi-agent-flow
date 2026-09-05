"""
连续性验证责任链管道与本地确定性代码门禁 (CCP V2.0 Continuity Gate Pipeline)

包含两大核心确定性代码门禁：
1. 派单准入门禁 (Pre-Dispatch Gate)：
   - 基础字段健全性 (target >= 5 字符, acceptance_criteria >= 1 条)；
   - 前置断言 (preconditions) 静态扫描 (文件物理存在性与模型字段探测)；
   - 依赖闭环与 Tier-1 契约完整性断言。
2. 提审查准出门禁 (Pre-Review Gate)：
   - 物理 Git 变更白名单比对 (scope.in_scope 与 new_files_policy 防越界破坏)；
   - 结案交付回执四件套存在性与机读标头结构校验；
   - P5-1 自测凭据与验收标准 (AC) 逐条映射核验。
"""
import os
import re
import sys
import subprocess
from typing import List, Dict, Any, Tuple, Optional
import paths
from ..interfaces import IContinuityValidator
from ..models import HandoffContext, ValidationReport

_FILE_PATH_RE = re.compile(r"[\w\-\./]+\.(?:py|yaml|yml|json|md|sh|sql|ts|js|html|css)")


def _normalize_path(p: str, proj_root: str) -> str:
    """规范化相对路径"""
    clean_p = p.strip().strip("'\"`")
    if os.path.isabs(clean_p):
        return clean_p
    return os.path.abspath(os.path.join(proj_root, clean_p))


def validate_pre_dispatch(task: Dict[str, Any], proj_root: Optional[str] = None) -> Tuple[bool, List[str]]:
    """
    派单准入门禁 (Pre-Dispatch Gate)
    在派发任务前执行本地确定性校验，任一断言失败直接拦截派单。
    """
    errors: List[str] = []
    root = proj_root or paths.project_root()

    # 1. 基础字段非空与规范校验
    target = str(task.get("target") or task.get("name") or "").strip()
    if len(target) < 5:
        errors.append(f"[REJECT 目标描述过短] task target 长度必须 ≥ 5 字符，当前为 '{target}'")

    raw_criteria = task.get("acceptance_criteria") or task.get("criteria") or []
    if isinstance(raw_criteria, str):
        crit_list = [c.strip() for c in re.split(r"[;\n；]", raw_criteria) if c.strip()]
    elif isinstance(raw_criteria, list):
        crit_list = [str(c).strip() for c in raw_criteria if str(c).strip()]
    else:
        crit_list = []

    if len(crit_list) < 1:
        errors.append("[REJECT 缺少验收标准] task acceptance_criteria 至少需要包含 1 条明确的验收标准")

    # 2. Tier 等级与契约完整性校验
    tier = str(task.get("tier") or "Tier-1").strip()
    contract = task.get("contract") or {}

    if tier == "Tier-1" and contract:
        # Tier-1 核心研发任务强制校验必备区块
        if not contract.get("scope"):
            errors.append("[REJECT 契约不完整] Tier-1 任务 contract 必须包含 scope (in_scope 白名单)")

    # 3. 前置断言真实性静态扫描 (Preconditions Probe)
    preconditions = contract.get("preconditions") or []
    if isinstance(preconditions, list):
        for pre in preconditions:
            pre_str = str(pre).strip()
            if not pre_str:
                continue

            # 探测断言中引用的文件路径
            found_files = _FILE_PATH_RE.findall(pre_str)
            for fpath in found_files:
                abs_f = _normalize_path(fpath, root)
                if not os.path.exists(abs_f):
                    errors.append(
                        f"[REJECT 前置断言不满足] 契约声明依赖文件 '{fpath}' 存在，但工作区未检索到物理文件！"
                    )
                else:
                    # 探测字段存在性断言（如 "users 表已存在 is_active 字段" 或 "包含 is_active 字段"）
                    m_field = re.search(r"(?:已存在\s+([a-zA-Z0-9_]+)\s+字段|字段\s+([a-zA-Z0-9_]+)\s+已存在|包含\s+([a-zA-Z0-9_]+)\s+字段)", pre_str)
                    if m_field:
                        field_name = next(g for g in m_field.groups() if g)
                        try:
                            with open(abs_f, "r", encoding="utf-8", errors="ignore") as af:
                                content = af.read()
                            if field_name not in content:
                                errors.append(
                                    f"[REJECT 前置断言不满足] 契约声明 '{fpath}' 中已存在 '{field_name}' 字段，但文件中未检索到该定义！"
                                )
                        except Exception as e:
                            errors.append(f"[WARN] 检查断言文件 {fpath} 异常: {e}")
    elif isinstance(preconditions, dict):
        # 结构化字典形式：files_required 与 fields_required
        files_required = preconditions.get("files_required") or []
        for fpath in files_required:
            abs_f = _normalize_path(str(fpath), root)
            if not os.path.exists(abs_f):
                errors.append(
                    f"[REJECT 前置断言不满足] 契约声明依赖文件 '{fpath}' 存在，但工作区未检索到物理文件！"
                )
        fields_required = preconditions.get("fields_required") or []
        for field_def in fields_required:
            field_name = str(field_def).strip()
            if files_required and field_name:
                found_in_any = False
                for fpath in files_required:
                    abs_f = _normalize_path(str(fpath), root)
                    if os.path.exists(abs_f):
                        try:
                            with open(abs_f, "r", encoding="utf-8", errors="ignore") as af:
                                if field_name in af.read():
                                    found_in_any = True
                                    break
                        except Exception:
                            pass
                if not found_in_any:
                    errors.append(
                        f"[REJECT 前置断言不满足] 契约声明必须包含 '{field_name}' 字段，但在依赖文件中未检索到！"
                    )

    passed = len(errors) == 0
    return passed, errors


def validate_pre_review(task: Dict[str, Any], proj_root: Optional[str] = None) -> Tuple[bool, List[str]]:
    """
    提审查准出门禁 (Pre-Review Gate)
    在开发提审（转为【审查中】）前执行本地确定性校验，拦截越界改动与不合规交付。
    """
    errors: List[str] = []
    tier = str(task.get("tier") or "").strip()
    contract = task.get("contract") or {}
    return_contract = task.get("return_contract") or {}

    # 若任务未配置任何 CCP 契约且未显式指定 Tier-1/Tier-2，直接放行 (兼容存量与普通无契约任务)
    if not contract and not return_contract and tier not in ("Tier-1", "Tier-2"):
        return True, []

    # Tier-3 轻量维护任务走 Fast-Path 快速放行
    if tier == "Tier-3":
        return True, []

    root = proj_root or paths.project_root()

    # 1. 交付回执报告物理文件与结构四件套核验
    report_path = return_contract.get("report_path")
    if report_path:
        abs_report = _normalize_path(report_path, root)
        if not os.path.exists(abs_report):
            errors.append(
                f"[REJECT 交付回执缺失] return_contract.report_path 指定的交付报告未找到物理文件: '{report_path}'"
            )
        else:
            try:
                with open(abs_report, "r", encoding="utf-8", errors="ignore") as rf:
                    report_content = rf.read()

                # 四件套核心标头结构检查
                has_diff = any(kw in report_content for kw in ["变更文件", "Diff", "diff", "文件清单"])
                has_test = any(kw in report_content for kw in ["测试结果", "自动化测试", "单测", "测试用例"])
                has_deviation = any(kw in report_content for kw in ["偏离点", "与契约的偏离", "偏离说明"])
                has_issues = any(kw in report_content for kw in ["遗留问题", "决策项", "需决策"])

                missing_sections = []
                if not has_diff:
                    missing_sections.append("一、变更文件清单与 Diff 摘要")
                if not has_test:
                    missing_sections.append("二、自动化测试结果凭据")
                if not has_deviation:
                    missing_sections.append("三、与契约的偏离点及原因说明")
                if not has_issues:
                    missing_sections.append("四、遗留问题与决策项")

                if missing_sections:
                    errors.append(
                        f"[REJECT 交付回执结构缺失] 交付报告 '{report_path}' 缺少以下标准四件套小节: {', '.join(missing_sections)}"
                    )

                # P5-1 自测凭据深度核查 (用例数、通过数、AC 映射)
                has_test_metrics = re.search(r"(用例数|通过|passed|Exit Code|退出码|exit code)", report_content, re.IGNORECASE)
                if not has_test_metrics:
                    errors.append(
                        f"[REJECT P5-1 自测凭据缺失] 交付报告 '{report_path}' 缺少测试用例数、通过数或退出码等运行态凭据！"
                    )

                has_ac_mapping = any(kw in report_content for kw in ["AC-", "验收项", "验收标准", "[x]", "[ ]"])
                if not has_ac_mapping and tier == "Tier-1":
                    errors.append(
                        f"[REJECT P5-1 验收映射缺失] Tier-1 交付报告 '{report_path}' 必须包含与 Acceptance Criteria 的逐条映射核对凭据！"
                    )

            except Exception as e:
                errors.append(f"[REJECT 读取交付报告异常] 无法解析 '{report_path}': {e}")
    elif tier == "Tier-1":
        errors.append("[REJECT 缺少交付契约] Tier-1 任务必须在工单中声明 return_contract.report_path 并在提审前交付！")

    # 2. Git 差异白名单与黑名单比对 (Scope Boundary Enforcement)
    scope = contract.get("scope") or {}
    in_scope = scope.get("in_scope") or []
    out_of_scope_patterns = scope.get("out_of_scope") or []
    new_files_policy = contract.get("new_files_policy") or []

    if in_scope or out_of_scope_patterns:
        allowed_exact = set()
        for p in in_scope:
            allowed_exact.add(os.path.normpath(p.strip().strip("'\"`")))
        for p in new_files_policy:
            f_matches = _FILE_PATH_RE.findall(str(p))
            for fm in f_matches:
                allowed_exact.add(os.path.normpath(fm.strip()))

        forbidden_exact = set()
        for o in out_of_scope_patterns:
            matches = _FILE_PATH_RE.findall(str(o))
            for m in matches:
                forbidden_exact.add(os.path.normpath(m.strip()))

        # 读取本地 Git 差异文件
        try:
            diff_out = subprocess.check_output(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=root, stderr=subprocess.DEVNULL, timeout=5
            ).decode("utf-8").strip().splitlines()

            status_out = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=root, stderr=subprocess.DEVNULL, timeout=5
            ).decode("utf-8").strip().splitlines()

            modified_files = set()
            for line in diff_out:
                if line.strip():
                    modified_files.add(os.path.normpath(line.strip()))
            for line in status_out:
                if line.strip():
                    parts = line.strip().split(maxsplit=1)
                    if len(parts) == 2:
                        modified_files.add(os.path.normpath(parts[1].strip()))

            # 过滤框架内部与文档维护文件
            ignored_prefixes = (
                "user_data/", "docs/", ".git", "templates/",
                ".tasks_index.json", ".agents/", ".claude/"
            )

            out_of_scope_violations = []
            forbidden_violations = []
            for f in modified_files:
                if any(f.startswith(pfx) for pfx in ignored_prefixes):
                    continue

                # 优先检查显式禁用黑名单 (out_of_scope)
                for fb in forbidden_exact:
                    if f == fb or f.endswith("/" + fb) or fb.endswith("/" + f):
                        forbidden_violations.append(f)
                        break

                # 检查是否匹配允许的白名单
                if in_scope:
                    matched = False
                    for a in allowed_exact:
                        if f == a or f.endswith("/" + a) or a.endswith("/" + f):
                            matched = True
                            break
                    if not matched:
                        out_of_scope_violations.append(f)

            if forbidden_violations:
                errors.append(
                    f"[REJECT 触犯红线禁区] 检测到修改了 scope.out_of_scope 明确禁止的文件: {', '.join(forbidden_violations)}"
                )

            if out_of_scope_violations:
                errors.append(
                    f"[REJECT Git 差异越界] 检测到 {len(out_of_scope_violations)} 个文件不在 scope.in_scope 白名单内: {', '.join(out_of_scope_violations)}"
                )
        except Exception:
            # 非 Git 仓库或命令超时环境容错
            pass

    passed = len(errors) == 0
    return passed, errors


class ContinuityValidationPipeline(IContinuityValidator):
    """上下文连续性验证责任链管道，兼容 CCP V1.0 接口并内嵌 V2.0 确定性门禁"""

    def validate(self, handoff: HandoffContext) -> ValidationReport:
        missing = []
        blocking = []
        conflicts = []
        test_results = {}

        # 1. 必填字段存在性强校验 (Syntactic Check)
        for req_field in handoff.must_know:
            val = handoff.payload.get(req_field)
            if val is None or val == "" or val == []:
                missing.append(req_field)
                test_results[req_field] = "FAIL"
            else:
                test_results[req_field] = "PASS"

        # 2. 阻断性 Unknown 校验
        unknowns = handoff.payload.get("unknowns", [])
        if isinstance(unknowns, list):
            for u in unknowns:
                if isinstance(u, dict) and u.get("blocking") is True:
                    blocking.append(u.get("question", "Unknown Blocking Issue"))

        # 3. 冲突项判定
        explicit_conflicts = handoff.payload.get("conflicts", [])
        if isinstance(explicit_conflicts, list):
            conflicts.extend(explicit_conflicts)

        # 4. 综合判定状态
        if missing:
            status = "INCOMPLETE"
        elif blocking:
            status = "AMBIGUOUS"
        elif conflicts:
            status = "CONFLICTED"
        else:
            status = "READY"

        return ValidationReport(
            status=status,
            missing_fields=missing,
            blocking_unknowns=blocking,
            conflicts=conflicts,
            test_results=test_results,
        )


def check_continuity_gate(task_id: str, target_stage: str) -> ValidationReport:
    """供外部状态机调用的只读预检辅助函数"""
    pipeline = ContinuityValidationPipeline()
    dummy_handoff = HandoffContext(
        handoff_id=f"GATE-{task_id}",
        task_id=task_id,
        parent_agent="SYSTEM",
        child_agent="TARGET",
        snapshot_id="",
        base_version=1,
        payload={"task_id": task_id, "target_stage": target_stage},
        must_know=["task_id"]
    )
    return pipeline.validate(dummy_handoff)
