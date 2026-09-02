"""
CCP 8 大状态切片与核心传输对象模型 (基于 Python 原生 dataclasses，零外部依赖)
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import json


@dataclass
class RequirementsSlice:
    functional: List[Dict[str, Any]] = field(default_factory=list)
    non_functional: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ConstraintsSlice:
    hard: List[str] = field(default_factory=list)
    soft: List[str] = field(default_factory=list)


@dataclass
class InvariantsSlice:
    rules: List[Dict[str, str]] = field(default_factory=list)  # rule, severity


@dataclass
class DecisionsSlice:
    decisions: List[Dict[str, Any]] = field(default_factory=list)  # id, decision, rationale, status, source


@dataclass
class CurrentStateSlice:
    completed: List[str] = field(default_factory=list)
    in_progress: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)


@dataclass
class AssumptionsSlice:
    assumptions: List[Dict[str, Any]] = field(default_factory=list)  # id, assumption, confidence


@dataclass
class UnknownsSlice:
    unknowns: List[Dict[str, Any]] = field(default_factory=list)  # id, question, blocking


@dataclass
class ArtifactsSlice:
    artifacts: List[Dict[str, Any]] = field(default_factory=list)  # id, ref, version, authority


@dataclass
class ContextState:
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
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextState":
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
    task_id: str
    base_version: int
    status: str  # completed, failed, blocked
    physical_changes: Dict[str, Any] = field(default_factory=dict)
    cognitive_delta: Dict[str, Any] = field(default_factory=dict)
    state_transitions: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ValidationReport:
    status: str  # READY, INCOMPLETE, AMBIGUOUS, CONFLICTED
    missing_fields: List[str] = field(default_factory=list)
    blocking_unknowns: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    test_results: Dict[str, str] = field(default_factory=dict)
