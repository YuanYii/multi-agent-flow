"""
连续性验证责任链管道 (Stage 1 确定性 Schema + Stage 2 语义门禁)
"""
from typing import List, Dict, Any
from ..interfaces import IContinuityValidator
from ..models import HandoffContext, ValidationReport


class ContinuityValidationPipeline(IContinuityValidator):
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
    # 构造轻量预检上下文
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
