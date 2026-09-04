"""
CCP 8 大状态切片与核心传输对象模型 (基于 Python 原生 dataclasses，零外部依赖)
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import json


@dataclass
class RequirementsSlice:
    """上下文切片：需求定义与验收标准 (Requirements Slice)。"""
    functional: List[Dict[str, Any]] = field(default_factory=list)
    non_functional: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ConstraintsSlice:
    """上下文切片：工程边界与硬约束规则 (Constraints Slice)。"""
    hard: List[str] = field(default_factory=list)
    soft: List[str] = field(default_factory=list)


@dataclass
class InvariantsSlice:
    """上下文切片：架构不变式与业务铁律 (Invariants Slice)。"""
    rules: List[Dict[str, str]] = field(default_factory=list)  # rule, severity


@dataclass
class DecisionsSlice:
    """上下文切片：已落地的技术选型与 ADR 决策记录 (Decisions Slice)。"""
    decisions: List[Dict[str, Any]] = field(default_factory=list)  # id, decision, rationale, status, source


@dataclass
class CurrentStateSlice:
    """上下文切片：当前执行状态与流转上下文 (Current State Slice)。"""
    completed: List[str] = field(default_factory=list)
    in_progress: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)


@dataclass
class AssumptionsSlice:
    """上下文切片：显式假设与未决依赖 (Assumptions Slice)。"""
    assumptions: List[Dict[str, Any]] = field(default_factory=list)  # id, assumption, confidence


@dataclass
class UnknownsSlice:
    """上下文切片：未知探索项与阻断问题清单 (Unknowns Slice)。"""
    unknowns: List[Dict[str, Any]] = field(default_factory=list)  # id, question, blocking


@dataclass
class ArtifactsSlice:
    """上下文切片：产出物文件路径与凭据索引 (Artifacts Slice)。"""
    artifacts: List[Dict[str, Any]] = field(default_factory=list)  # id, ref, version, authority


@dataclass
class ContextState:
    """CCP 上下文全量状态切片聚合实体 (Context State Root)。"""
    task_id: str
    version: int = 1
    last_updated: str = ""
    requirements: RequirementsSlice = field(default_factory=RequirementsSlice)
    constraints: ConstraintsSlice = field(default_factory=ConstraintsSlice)
    invariants: InvariantsSlice = field(default_factory=InvariantsSlice)
    decisions: DecisionsSlice = field(default_factory=DecisionsSlice)
    state: CurrentStateSlice = field(default_factory=CurrentStateSlice)
    assumptions: AssumptionsSlice = field(default_factory=AssumptionsSlice)
    unknowns: UnknownsSlice = field(default_factory=UnknownsSlice)
    artifacts: ArtifactsSlice = field(default_factory=ArtifactsSlice)

    def to_dict(self) -> Dict[str, Any]:
        """
        将上下文实体状态序列化导出为结构化字典。

        返回:
            dict: 结构化字典数据。
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextState":
        """
        从结构化字典反序列化生成 ContextState 实体。

        参数:
            data (dict): 原始字典数据。

        返回:
            ContextState: 实体对象。
        """
        return cls(
            task_id=data.get("task_id", "UNKNOWN"),
            version=data.get("version", 1),
            last_updated=data.get("last_updated", ""),
            requirements=RequirementsSlice(**data.get("requirements", {})),
            constraints=ConstraintsSlice(**data.get("constraints", {})),
            invariants=InvariantsSlice(**data.get("invariants", {})),
            decisions=DecisionsSlice(**data.get("decisions", {})),
            state=CurrentStateSlice(**data.get("state", {})),
            assumptions=AssumptionsSlice(**data.get("assumptions", {})),
            unknowns=UnknownsSlice(**data.get("unknowns", {})),
            artifacts=ArtifactsSlice(**data.get("artifacts", {})),
        )


@dataclass
class HandoffContext:
    """跨 Agent 交接载荷容器 (Handoff Context)。"""
    handoff_id: str
    task_id: str
    parent_agent: str
    child_agent: str
    snapshot_id: str
    base_version: int
    payload: Dict[str, Any] = field(default_factory=dict)
    must_know: List[str] = field(default_factory=list)
    useful_to_know: List[str] = field(default_factory=list)


@dataclass
class ResultDelta:
    """单次流转产生的差量产出物快照 (Result Delta)。"""
    task_id: str
    base_version: int
    status: str  # completed, failed, blocked
    physical_changes: Dict[str, Any] = field(default_factory=dict)
    cognitive_delta: Dict[str, Any] = field(default_factory=dict)
    state_transitions: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ValidationReport:
    """连续性责任链门禁核验结果报告实体。"""
    status: str  # READY, INCOMPLETE, AMBIGUOUS, CONFLICTED
    missing_fields: List[str] = field(default_factory=list)
    blocking_unknowns: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    test_results: Dict[str, str] = field(default_factory=dict)
