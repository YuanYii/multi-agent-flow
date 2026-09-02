"""
CCP 核心抽象接口契约 (Interface Contracts)
确立 5 大核心扩展点：存储仓储、投影算子、连续性门禁、增量提取器与状态合并器。
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from .models import ContextState, HandoffContext, ResultDelta, ValidationReport


class IContextStateStore(ABC):
    """状态仓储持久化抽象"""
    @abstractmethod
    def load(self, task_id: str) -> Optional[ContextState]:
        """加载指定任务的当前全局 ContextState"""
        pass

    @abstractmethod
    def save_with_cas(self, task_id: str, state: ContextState, expected_version: int) -> bool:
        """带版本号乐观锁 (CAS) 的原子持久化"""
        pass

    @abstractmethod
    def create_snapshot(self, task_id: str) -> str:
        """创建不可变快照并返回 snapshot_id"""
        pass


class IContextProjector(ABC):
    """上下文投影编译算子抽象"""
    @abstractmethod
    def project(self, state: ContextState, task_def: Dict[str, Any], target_agent: Dict[str, Any]) -> HandoffContext:
        """将全局 ContextState 裁剪为针对特定任务与角色的最小充分上下文"""
        pass


class IContinuityValidator(ABC):
    """连续性校验门禁抽象"""
    @abstractmethod
    def validate(self, handoff: HandoffContext) -> ValidationReport:
        """执行连续性测试，返回 READY / INCOMPLETE / AMBIGUOUS / CONFLICTED 状态报告"""
        pass


class IDeltaExtractor(ABC):
    """物理与认知结果增量提取器抽象"""
    @abstractmethod
    def extract_physical(self, workspace_path: str) -> Dict[str, Any]:
        """从真实 Git 工作区与测试执行器提取确定性物理变更"""
        pass

    @abstractmethod
    def extract_cognitive(self, raw_model_response: str) -> Dict[str, Any]:
        """从模型输出中结构化提炼新增决策、假设与未解问题"""
        pass


class IStateMerger(ABC):
    """状态合并与冲突仲裁抽象"""
    @abstractmethod
    def merge(self, base_state: ContextState, current_state: ContextState, delta: ResultDelta) -> ContextState:
        """执行三向合并，若无冲突递增版本，若冲突抛出 ConflictError"""
        pass
