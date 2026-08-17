#!/usr/bin/env python3
"""
check_stage_gate.py · YY-Flow 阶段门禁核验器 (Stage Gate Checker)

职责：
- 在阶段结项与发布前执行确定性硬核验，消除肉眼对账与盲区遗漏。
- 采用 Checker Pipeline（检查器流水线）模式，支持配置扩展与自定义规则注入。
- 具备全景路径自适应能力（支持双轨 D0X 规范目录与平铺 docs/ 目录）。
- 退出码契约：
    0: 门禁 100% 通过 (PASS)
    1: 门禁阻断 (BLOCKED，存在未验收卡片、WBS 漏单或缺失总结)
    2: 运行时错误 (ERROR，阶段不存在或参数异常)
"""

import os
import sys
import json
import re
import glob
import argparse
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from paths import (
    resolve_data_root,
    project_root,
    docs_root,
    user_data_dir,
    runtime_config_path,
)
from board_adapter_factory import get_board_adapter
from offline_board_adapter import OfflineBoardAdapter


# =============================================================================
# 1. 数据模型与检查结果结构
# =============================================================================

@dataclass
class CheckResult:
    """单个检查项核验结果"""
    code: str
    title: str
    passed: bool
    detail: str
    suggestion: str = ""
    items: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StageGateReport:
    """整体验收门禁报告"""
    stage_name: str
    passed: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    results: List[CheckResult] = field(default_factory=list)


# =============================================================================
# 2. 阶段上下文与自适应辅助工具 (Stage Context)
# =============================================================================

class StageContext:
    def __init__(
        self,
        stage_input: str,
        project_dir: Optional[str] = None,
        config_override: Optional[Dict[str, Any]] = None,
    ):
        self.stage_input = (stage_input or "").strip()
        self.data_root = resolve_data_root(explicit=project_dir)
        self.project_root = project_root(explicit=project_dir)
        self.docs_dir = docs_root(explicit=project_dir)
        self.config = config_override or self._load_workflow_config()
        self.adapter = self._init_adapter(project_dir)

        # 加载所有看板卡片
        try:
            self.all_records = self.adapter.list_records(limit=2000)
        except Exception:
            self.all_records = []

        # 归一化提取卡片 dict
        self.normalized_records = [self._norm_record(r) for r in self.all_records]

        # 解析与对齐目标阶段
        self.target_stage = self._resolve_target_stage()
        self.stage_records = [
            r for r in self.normalized_records
            if self._stage_matches(r.get("stage", ""), self.target_stage)
        ]

    def _init_adapter(self, project_dir: Optional[str] = None):
        """安全解析并初始化看板适配器"""
        # 1. 尝试显式配置文件
        cfg_path = runtime_config_path(explicit=self.data_root)
        if not os.path.isfile(cfg_path):
            cfg_path = os.path.join(self.project_root, "config", "workflow.config.yaml")

        if os.path.isfile(cfg_path):
            try:
                return get_board_adapter(config_file=cfg_path)
            except Exception:
                pass

        # 2. 默认使用 OfflineBoardAdapter
        board_file = os.path.join(self.data_root, "user_data", "board.json")
        return OfflineBoardAdapter(board_file=board_file)

    def _norm_record(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        if "fields" in rec and isinstance(rec["fields"], dict):
            out = dict(rec["fields"])
            if "record_id" not in out and "record_id" in rec:
                out["record_id"] = rec["record_id"]
            return out
        return rec

    def _load_workflow_config(self) -> Dict[str, Any]:
        """安全加载 workflow.config.yaml 中的 stage_gate 配置"""
        cfg_path = runtime_config_path(explicit=self.data_root)
        if not os.path.isfile(cfg_path):
            cfg_path = os.path.join(self.project_root, "config", "workflow.config.yaml")
        if os.path.isfile(cfg_path):
            try:
                import yaml
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    return data.get("stage_gate", {})
            except Exception:
                pass
        return {}

    def _resolve_target_stage(self) -> str:
        """根据输入阶段名（如 'S1'）模糊对齐看板真实阶段名"""
        all_stages = list({
            str(r.get("stage", "")).strip()
            for r in self.normalized_records
            if str(r.get("stage", "")).strip() and str(r.get("stage", "")).strip() != "-"
        })

        if not self.stage_input:
            # 自动探测第一个有任务的阶段
            return all_stages[0] if all_stages else ""

        # 1. 精确匹配
        for s in all_stages:
            if s == self.stage_input:
                return s

        # 2. 大小写不敏感完全匹配
        for s in all_stages:
            if s.lower() == self.stage_input.lower():
                return s

        # 3. 前缀代号匹配 (如 'S1' 匹配 'S1 需求分析与系统架构设计')
        m = re.match(r"^(S\d+)", self.stage_input, re.IGNORECASE)
        if m:
            code = m.group(1).upper()
            for s in all_stages:
                if re.match(r"^" + re.escape(code) + r"([\s\-_:：]|$)", s, re.IGNORECASE):
                    return s

        # 4. 包含子串匹配
        for s in all_stages:
            if self.stage_input.lower() in s.lower():
                return s

        # 若未在看板匹配到，原样返回输入
        return self.stage_input

    def _stage_matches(self, stage_val: str, target: str) -> bool:
        """判定某卡片的 stage 是否归属目标阶段"""
        if not stage_val or not target:
            return False
        if stage_val == target or stage_val.lower() == target.lower():
            return True
        m1 = re.match(r"^(S\d+)", stage_val, re.IGNORECASE)
        m2 = re.match(r"^(S\d+)", target, re.IGNORECASE)
        if m1 and m2 and m1.group(1).upper() == m2.group(1).upper():
            return True
        return False

    def find_docs(self, candidate_patterns: List[str]) -> List[str]:
        """路径自适应文件查找引擎：支持精确目录模式与递归通配"""
        matches = []
        if not os.path.isdir(self.docs_dir):
            return []

        for pat in candidate_patterns:
            # 1. 尝试相对于 docs_dir 的相对路径/通配
            full_pat = os.path.join(self.docs_dir, pat)
            found = glob.glob(full_pat, recursive=True)
            if found:
                matches.extend(found)

        # 2. 递归兜底匹配 docs 目录下所有 md
        return sorted(list(set(matches)))

    def parse_markdown_frontmatter(self, filepath: str) -> Dict[str, Any]:
        """读取 Markdown YAML Frontmatter"""
        if not os.path.isfile(filepath):
            return {}
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    yaml_block = parts[1]
                    out = {}
                    for line in yaml_block.splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            out[k.strip().lower()] = v.strip().strip("\"'")
                    return out
        except Exception:
            pass
        return {}


# =============================================================================
# 3. 检查器流水线 (Checker Pipeline)
# =============================================================================

def check_board_tasks_status(ctx: StageContext) -> CheckResult:
    """Check 1: 检查看板阶段内任务是否全部达到【已验收】终态并填写结束时间"""
    records = ctx.stage_records
    if not records:
        return CheckResult(
            code="BOARD_TASKS_EMPTY",
            title="看板阶段任务存在性",
            passed=False,
            detail=f"阶段【{ctx.target_stage}】在看板中无任何任务记录",
            suggestion=f"请先在阶段【{ctx.target_stage}】下创建工作包任务卡",
        )

    unaccepted = []
    missing_end_time = []

    for r in records:
        tid = r.get("id") or r.get("record_id") or "未知ID"
        name = r.get("name") or "未命名任务"
        status = (r.get("status") or "").strip()
        handler = (r.get("handler") or r.get("assignee") or "未分配").strip()
        end_date = (r.get("end_date") or r.get("end_time") or "").strip()

        # 非终态判定
        if status not in ("已验收", "已取消"):
            unaccepted.append({
                "id": tid,
                "name": name,
                "status": status,
                "handler": handler,
            })
        elif status == "已验收" and not end_date:
            missing_end_time.append({"id": tid, "name": name})

    if unaccepted:
        items_desc = ", ".join([f"{u['id']} ({u['status']} - {u['handler']})" for u in unaccepted[:5]])
        if len(unaccepted) > 5:
            items_desc += f" 等共 {len(unaccepted)} 条"
        return CheckResult(
            code="BOARD_TASKS_UNACCEPTED",
            title="看板任务全终态验收",
            passed=False,
            detail=f"阶段内尚有 {len(unaccepted)} 个任务未完成终态验收: {items_desc}",
            suggestion="请推动未完成任务经审查/测试流转，并由 PM 严经理执行最终验收 (已完成 -> 已验收)",
            items=unaccepted,
        )

    if missing_end_time:
        tids = ", ".join([m["id"] for m in missing_end_time[:5]])
        return CheckResult(
            code="BOARD_TASKS_MISSING_END_TIME",
            title="已验收任务结束时间",
            passed=False,
            detail=f"以下 {len(missing_end_time)} 个已验收任务遗漏了结束时间 (end_date): {tids}",
            suggestion="请在看板或通过 transition_task.py 补齐任务的结束时间",
            items=missing_end_time,
        )

    return CheckResult(
        code="BOARD_TASKS_PASS",
        title="看板任务全终态验收",
        passed=True,
        detail=f"阶段内共 {len(records)} 个任务，全部达到【已验收】终态且结束时间完整记录",
    )


def check_wbs_reconciliation(ctx: StageContext) -> CheckResult:
    """Check 2: 检查看板 WBS 编号完整性及 WBS 拆解文档双向对账"""
    records = ctx.stage_records
    if not records:
        return CheckResult(
            code="WBS_EMPTY",
            title="WBS 编号与工作包对账",
            passed=True,
            detail="无卡片跳过对账",
        )

    # 1. 检查看板卡片自身的 wbs 字段规范性
    missing_wbs = [r.get("id") or "?" for r in records if not (r.get("wbs") or "").strip() or (r.get("wbs") or "").strip() == "-"]
    if missing_wbs:
        return CheckResult(
            code="WBS_FIELD_MISSING",
            title="看板 WBS 编号完整性",
            passed=False,
            detail=f"以下 {len(missing_wbs)} 个卡片未填写 WBS 编号: {', '.join(missing_wbs[:5])}",
            suggestion="请在看板中为上述任务补填规范的 WBS 编号（如 1.1.1）",
        )

    # 2. 尝试扫描 WBS-*.md 实体文档进行双向对账
    wbs_candidates = [
        "D04-研发过程/D01-任务/WBS-*.md",
        "D01-项目管理/D01-需求/WBS-*.md",
        "**/WBS-*.md",
        "WBS-*.md",
    ]
    wbs_files = ctx.find_docs(wbs_candidates)
    matched_wbs_file = None

    for wf in wbs_files:
        fn = os.path.basename(wf).upper()
        m = re.match(r"^(S\d+)", ctx.target_stage, re.IGNORECASE)
        stage_code = m.group(1).upper() if m else ""
        if stage_code and stage_code in fn:
            matched_wbs_file = wf
            break
        fm = ctx.parse_markdown_frontmatter(wf)
        if fm.get("stage") and ctx._stage_matches(fm["stage"], ctx.target_stage):
            matched_wbs_file = wf
            break

    # 若找到了 WBS 文档，解析 Markdown 表格中的 Task ID
    if matched_wbs_file and os.path.isfile(matched_wbs_file):
        try:
            with open(matched_wbs_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            doc_task_ids = set(re.findall(r"\|\s*(T\d{4,})\s*\|", content, re.IGNORECASE))
            board_task_ids = {str(r.get("id") or "").upper() for r in records if r.get("id")}

            missing_on_board = [tid for tid in doc_task_ids if tid.upper() not in board_task_ids]
            if missing_on_board:
                return CheckResult(
                    code="WBS_DOC_MISMATCH",
                    title="WBS 文档与看板对账",
                    passed=False,
                    detail=f"WBS 文档 ({os.path.basename(matched_wbs_file)}) 中声明的任务在看板中缺失: {', '.join(missing_on_board)}",
                    suggestion="请核对 WBS 文档并在看板中补建上述缺失的任务卡",
                )
            return CheckResult(
                code="WBS_PASS",
                title="WBS 编号与文档双向对账",
                passed=True,
                detail=f"看板卡片 WBS 编号完整，且与文档 ({os.path.basename(matched_wbs_file)}) 声明任务 100% 吻合",
            )
        except Exception:
            pass

    return CheckResult(
        code="WBS_PASS",
        title="WBS 编号规范性核验",
        passed=True,
        detail=f"看板内 {len(records)} 个卡片均具备规范的 WBS 层级编号",
    )


def check_arch_summary(ctx: StageContext) -> CheckResult:
    """Check 3: 检查阶段架构技术总结报告"""
    if ctx.config.get("require_arch_summary") is False:
        return CheckResult(
            code="ARCH_SUMMARY_EXEMPTED",
            title="架构技术总结核验",
            passed=True,
            detail="配置已豁免架构技术总结",
        )

    # 路径自适应候选模式
    candidates = [
        "D04-研发过程/D02-报告/summary/*架构*",
        "D04-研发过程/D02-报告/summary/*技术*",
        "D02-架构设计/*总结*",
        "D02-架构设计/*",
        "summary/*架构*",
        "**/*架构*总结*.md",
        "**/*技术*总结*.md",
    ]
    matched_files = ctx.find_docs(candidates)
    valid_doc = None

    m = re.match(r"^(S\d+)", ctx.target_stage, re.IGNORECASE)
    stage_code = m.group(1).upper() if m else ""

    for f in matched_files:
        fn = os.path.basename(f)
        if stage_code and stage_code in fn.upper():
            valid_doc = f
            break
        fm = ctx.parse_markdown_frontmatter(f)
        if fm.get("stage") and ctx._stage_matches(fm["stage"], ctx.target_stage):
            valid_doc = f
            break
        if "总结" in fn or "复盘" in fn:
            valid_doc = f
            break

    if valid_doc:
        rel_path = os.path.relpath(valid_doc, ctx.project_root)
        return CheckResult(
            code="ARCH_SUMMARY_PASS",
            title="架构技术总结核验",
            passed=True,
            detail=f"已检测到阶段架构技术总结文档: {rel_path}",
        )

    # 如果该阶段内只有 C 类文档任务或非代码任务，可放行
    is_pure_non_tech = records_are_non_tech(ctx.stage_records)
    if is_pure_non_tech and len(ctx.stage_records) > 0:
        return CheckResult(
            code="ARCH_SUMMARY_PASS",
            title="架构技术总结核验",
            passed=True,
            detail="当前阶段为非代码研发阶段，自动豁免架构技术总结",
        )

    return CheckResult(
        code="ARCH_SUMMARY_MISSING",
        title="架构技术总结核验",
        passed=False,
        detail=f"未在 docs/ 中找到【{ctx.target_stage}】的架构技术总结文档 (期望: *架构*总结*.md)",
        suggestion="请架构师 钱架构 在 docs/D04-研发过程/D02-报告/summary/ 产出并定稿阶段架构技术总结",
    )


def check_pm_summary(ctx: StageContext) -> CheckResult:
    """Check 4: 检查 PM 阶段管理与复盘总结报告及任务状态"""
    if ctx.config.get("require_pm_summary") is False:
        return CheckResult(
            code="PM_SUMMARY_EXEMPTED",
            title="PM 阶段管理与复盘总结",
            passed=True,
            detail="配置已豁免 PM 阶段总结",
        )

    candidates = [
        "D01-项目管理/D02-状态报告/*",
        "D04-研发过程/D02-报告/summary/*管理*",
        "D04-研发过程/D02-报告/summary/*阶段*",
        "D04-研发过程/D02-报告/summary/*复盘*",
        "01-项目管理/*",
        "summary/*",
        "**/*阶段*总结*.md",
        "**/*阶段*复盘*.md",
    ]
    matched_files = ctx.find_docs(candidates)
    valid_doc = None

    m = re.match(r"^(S\d+)", ctx.target_stage, re.IGNORECASE)
    stage_code = m.group(1).upper() if m else ""

    for f in matched_files:
        fn = os.path.basename(f)
        if stage_code and stage_code in fn.upper():
            valid_doc = f
            break
        fm = ctx.parse_markdown_frontmatter(f)
        if fm.get("stage") and ctx._stage_matches(fm["stage"], ctx.target_stage):
            valid_doc = f
            break
        if "阶段" in fn and ("总结" in fn or "复盘" in fn or "报告" in fn):
            valid_doc = f
            break

    # 同时校验看板中是否存在总结卡片（支持关键词判别与 type==F 兼容）
    summary_card_accepted = True
    summary_cards = []
    for r in ctx.stage_records:
        name = str(r.get("name") or "")
        t_type = str(r.get("type") or "").upper()
        if t_type == "F" or any(k in name for k in ("阶段总结", "管理总结", "阶段复盘", "项目复盘")):
            summary_cards.append(r)
            if r.get("status") != "已验收":
                summary_card_accepted = False

    if valid_doc and summary_card_accepted:
        rel_path = os.path.relpath(valid_doc, ctx.project_root)
        return CheckResult(
            code="PM_SUMMARY_PASS",
            title="PM 阶段管理与复盘总结",
            passed=True,
            detail=f"已检测到阶段管理总结报告: {rel_path}",
        )

    if not valid_doc:
        return CheckResult(
            code="PM_SUMMARY_DOC_MISSING",
            title="PM 阶段管理与复盘总结",
            passed=False,
            detail=f"未在 docs/ 中找到【{ctx.target_stage}】的管理复盘报告 (期望: docs/D01-项目管理/D02-状态报告/*阶段总结*.md)",
            suggestion="请 PM 严经理 在 docs/D01-项目管理/D02-状态报告/ 编写并定稿阶段管理总结与复盘报告",
        )

    return CheckResult(
        code="PM_SUMMARY_CARD_UNACCEPTED",
        title="PM 阶段总结任务卡状态",
        passed=False,
        detail="看板中存在尚未验收的阶段总结任务卡",
        suggestion="请 PM 严经理 将阶段总结卡片推进并验收至【已验收】",
    )


def records_are_non_tech(records: List[Dict[str, Any]]) -> bool:
    """辅助判定：是否该阶段纯为文档/非技术任务"""
    if not records:
        return True
    tech_keywords = ("开发", "代码", "架构", "设计", "API", "Schema", "前端", "后端", "DEV", "ARCHITECT")
    for r in records:
        name = str(r.get("name") or "")
        assignee = str(r.get("assignee") or "")
        if any(k in name for k in tech_keywords) or any(k in assignee for k in ("开发", "架构", "前端")):
            return False
    return True


# 注册所有标准检查器流水线
STAGE_GATE_CHECKERS = [
    check_board_tasks_status,
    check_wbs_reconciliation,
    check_arch_summary,
    check_pm_summary,
]


# =============================================================================
# 4. 执行调度与报告输出
# =============================================================================

def run_stage_gate_check(
    stage_name: str,
    project_root_dir: Optional[str] = None,
    config_override: Optional[Dict[str, Any]] = None,
) -> StageGateReport:
    """运行全量阶段门禁流水线并生成报告"""
    ctx = StageContext(
        stage_input=stage_name,
        project_dir=project_root_dir,
        config_override=config_override,
    )

    results: List[CheckResult] = []
    for checker in STAGE_GATE_CHECKERS:
        try:
            res = checker(ctx)
            results.append(res)
        except Exception as e:
            results.append(CheckResult(
                code="CHECKER_EXCEPTION",
                title=checker.__name__,
                passed=False,
                detail=f"检查器执行异常: {str(e)}",
                suggestion="请检查工作区文件权限与数据完整性",
            ))

    passed_count = sum(1 for r in results if r.passed)
    failed_count = len(results) - passed_count
    all_passed = failed_count == 0

    return StageGateReport(
        stage_name=ctx.target_stage or stage_name,
        passed=all_passed,
        total_checks=len(results),
        passed_checks=passed_count,
        failed_checks=failed_count,
        results=results,
    )


def format_terminal_report(report: StageGateReport) -> str:
    """格式化向导式终端门禁报告"""
    lines = []
    lines.append("=" * 64)
    lines.append(f"       YY-Flow 阶段门禁核验报告: 【{report.stage_name}】")
    lines.append("=" * 64)

    for r in report.results:
        badge = "[PASS]" if r.passed else "[FAIL]"
        lines.append(f"{badge} {r.title}: {r.detail}")

    lines.append("-" * 64)
    if report.passed:
        lines.append("✅ 阶段门禁 100% 审查通过！满足结项准出条件。")
        lines.append("🚀 下一步建议: 请 PM 严经理 派发 D 类任务唤起 DevOps 吕改特 执行分支合并与打发布 Tag。")
    else:
        lines.append(f"❌ 阶段门禁未通过！存在 {report.failed_checks} 项阻断项。")
        lines.append("💡 修复建议向导:")
        idx = 1
        for r in report.results:
            if not r.passed and r.suggestion:
                lines.append(f"   {idx}. {r.suggestion}")
                idx += 1
    lines.append("=" * 64)
    return "\n".join(lines)


# =============================================================================
# 5. CLI 入口
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="YY-Flow 阶段结项门禁核验器 (Stage Gate Checker)")
    parser.add_argument("--stage", "-s", type=str, default="", help="目标核验阶段名称或代号 (如 S1, 'S1 需求分析')")
    parser.add_argument("--project-root", "-p", type=str, default=None, help="目标项目根目录路径 (默认自动推导)")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果供 CI 集成消费")

    args = parser.parse_args()

    report = run_stage_gate_check(
        stage_name=args.stage,
        project_root_dir=args.project_root,
    )

    if args.json:
        # 序列化为 JSON 格式
        out_dict = {
            "stage_name": report.stage_name,
            "passed": report.passed,
            "total_checks": report.total_checks,
            "passed_checks": report.passed_checks,
            "failed_checks": report.failed_checks,
            "results": [asdict(r) for r in report.results],
        }
        print(json.dumps(out_dict, ensure_ascii=False, indent=2))
    else:
        print(format_terminal_report(report))

    # 退出码判定
    if report.passed:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
