"""
task_spec.py · 任务常规元数据缺省值自动推导与 WBS 编号规范模块

职责：
当用户/Agent 新建任务卡未显式指定 stage (项目阶段)、wp (工作包)、wbs (WBS 编号) 时：
1. 阶段 (stage)：自动探测并继承看板中最新/最大序号的活跃阶段（如已有 S1/S2 取 S2；无任务时取 S1 需求分析与系统架构设计）；
2. 工作包 (workpackage)：按照规范自动命名为 'WP-{StageCode}-01 常规研发工作包'（如 'WP-S1-01 常规研发工作包'）；
3. WBS 编号 (wbs_id)：按照三段式分解规范生成 '{StageNum}.1.{Seq}'（如 '1.1.1', '1.1.2', '2.1.1' 等）。
"""
import re
from typing import List, Dict, Any, Optional, Tuple


def resolve_default_stage_wp_wbs(
    existing_cards: List[Dict[str, Any]],
    stage: Optional[str] = None,
    wp: Optional[str] = None,
    wbs: Optional[str] = None,
    default_fallback_stage: str = "S1 需求分析与系统架构设计",
) -> Tuple[str, str, str]:
    """
    自动推导并规范化任务卡片的 stage, wp, wbs 三元组。

    参数：
        existing_cards: 当前看板中已存在的所有任务记录列表
        stage: 用户显式传入的阶段（可选）
        wp: 用户显式传入的工作包（可选）
        wbs: 用户显式传入的 WBS 编号（可选）
        default_fallback_stage: 看板为空时的缺省阶段

    返回：
        (resolved_stage, resolved_wp, resolved_wbs)
    """
    # 1. 规范化已有卡片列表
    norm_records = []
    for c in (existing_cards or []):
        if isinstance(c, dict):
            if "fields" in c and isinstance(c["fields"], dict):
                norm_records.append(c["fields"])
            else:
                norm_records.append(c)

    # 2. 阶段 (Stage) 智能推导
    resolved_stage = (stage or "").strip()
    if not resolved_stage or resolved_stage == "-":
        # 收集所有非空阶段
        all_stages = []
        for r in norm_records:
            stg = str(r.get("stage") or "").strip()
            if stg and stg != "-":
                all_stages.append(stg)

        if all_stages:
            # 优先按 S(\d+) 数字最大提取最新阶段
            stage_map = {}
            for s in all_stages:
                m = re.match(r"^S(\d+)", s, re.IGNORECASE)
                if m:
                    idx = int(m.group(1))
                    stage_map[idx] = s
            if stage_map:
                max_idx = max(stage_map.keys())
                resolved_stage = stage_map[max_idx]
            else:
                resolved_stage = all_stages[-1]
        else:
            resolved_stage = default_fallback_stage

    # 提取阶段代号与数字 (如 'S1' -> 1, 'S2' -> 2)
    m_stage = re.match(r"^S(\d+)", resolved_stage, re.IGNORECASE)
    if m_stage:
        stage_num = int(m_stage.group(1))
        stage_code = f"S{stage_num}"
    else:
        stage_num = 1
        stage_code = "S1"

    # 3. 工作包 (Work Package) 常规规范推导: WP-{StageCode}-01 常规研发工作包
    resolved_wp = (wp or "").strip()
    if not resolved_wp or resolved_wp == "-":
        resolved_wp = f"WP-{stage_code}-01 常规研发工作包"

    # 4. WBS 编号 (WBS ID) 常规规范推导: {StageNum}.1.{Seq}
    resolved_wbs = (wbs or "").strip()
    if not resolved_wbs or resolved_wbs == "-":
        # 计算当前阶段下已有卡片的数量
        stage_tasks_count = 0
        for r in norm_records:
            stg = str(r.get("stage") or "").strip()
            if stg == resolved_stage or (m_stage and re.match(r"^" + re.escape(stage_code) + r"([\s\-_:：]|$)", stg, re.IGNORECASE)):
                stage_tasks_count += 1
        seq = stage_tasks_count + 1
        resolved_wbs = f"{stage_num}.1.{seq}"

    return resolved_stage, resolved_wp, resolved_wbs
