"""
核心任务数据模型强类型化 (TaskRecord Dataclass)
为 23 个核心字段提供强类型注解、缺省值与双向反序列化支持。
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
import re

LEGAL_STATUSES = {
    "待开始", "进行中", "审查中", "测试中",
    "已完成", "已验收", "已退回", "已阻塞", "已取消"
}

LEGAL_ROLES = {
    "PM", "ARCHITECT", "DEV", "FRONTEND", "REVIEWER", "QA", "DOCS", "DEVOPS",
    "严经理", "钱架构", "李开发", "马前端", "周审查", "章测试", "李文通", "吕改特"
}


@dataclass
class TaskRecord:
    id: str
    name: str
    status: str = "待开始"
    stage: str = "阶段一: 需求分析"
    type: str = "A"
    assignee: str = "李开发"
    owner: str = "李开发"
    handler: str = "李开发"
    operator: str = "用户"
    creator: str = "用户"
    creator_role: str = "PM"
    workpackage: Optional[str] = None
    wbs_id: Optional[str] = None
    priority: str = "中"
    est_hours: float = 0.0
    act_hours: Optional[float] = 0.0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    pretask: Optional[str] = "无"
    target: Optional[str] = None
    acceptance_criteria: List[str] = field(default_factory=list)
    process: List[str] = field(default_factory=list)
    remarks: Optional[str] = None

    def __post_init__(self):
        # 数值与列表归一化
        try:
            self.est_hours = float(self.est_hours or 0.0)
        except (ValueError, TypeError):
            self.est_hours = 0.0

        if self.act_hours is not None:
            try:
                self.act_hours = float(self.act_hours)
            except (ValueError, TypeError):
                self.act_hours = None

        if isinstance(self.acceptance_criteria, str):
            if self.acceptance_criteria.strip():
                self.acceptance_criteria = [self.acceptance_criteria.strip()]
            else:
                self.acceptance_criteria = []
        elif not isinstance(self.acceptance_criteria, list):
            self.acceptance_criteria = list(self.acceptance_criteria or [])

        if isinstance(self.process, str):
            self.process = [self.process.strip()] if self.process.strip() else []
        elif not isinstance(self.process, list):
            self.process = list(self.process or [])

    @property
    def is_terminal(self) -> bool:
        return self.status in ["已验收", "已取消"]

    @property
    def is_active(self) -> bool:
        return self.status in ["进行中", "审查中", "测试中"]

    @property
    def is_blocked(self) -> bool:
        return self.status in ["已退回", "已阻塞"]

    def validate(self) -> List[str]:
        """物理合法性断言校验，返回错误清单"""
        errors = []
        if not re.match(r"^T\d{4,}$", self.id):
            errors.append(f"任务编号 '{self.id}' 不符合规范 (应形如 T0001)")
        if not self.name or not self.name.strip():
            errors.append("任务名称不能为空")
        if self.status not in LEGAL_STATUSES:
            errors.append(f"状态 '{self.status}' 不属于合法状态枚举")
        if self.est_hours < 0:
            errors.append(f"预估工时不能为负数: {self.est_hours}")
        if self.act_hours is not None and self.act_hours < 0:
            errors.append(f"实际工时不能为负数: {self.act_hours}")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        """序列化为存储字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRecord":
        """从字典安全反序列化并自动对齐字段"""
        if not isinstance(data, dict):
            raise ValueError(f"TaskRecord.from_dict 期望字典类型，收到: {type(data)}")

        # 解包 fields 包装
        if "fields" in data and isinstance(data["fields"], dict):
            src = dict(data["fields"])
        else:
            src = dict(data)

        task_id = str(src.get("id") or src.get("task_id") or "")
        task_name = str(src.get("name") or src.get("task_name") or "")

        return cls(
            id=task_id,
            name=task_name,
            status=str(src.get("status") or "待开始"),
            stage=str(src.get("stage") or "阶段一: 需求分析"),
            type=str(src.get("type") or src.get("task_type") or "A"),
            assignee=str(src.get("assignee") or "李开发"),
            owner=str(src.get("owner") or src.get("assignee") or "李开发"),
            handler=str(src.get("handler") or src.get("assignee") or "李开发"),
            operator=str(src.get("operator") or "用户"),
            creator=str(src.get("creator") or "用户"),
            creator_role=str(src.get("creator_role") or "PM"),
            workpackage=src.get("workpackage"),
            wbs_id=src.get("wbs_id") or src.get("wbs"),
            priority=str(src.get("priority") or "中"),
            est_hours=src.get("est_hours") or src.get("estimated_hours") or 0.0,
            act_hours=src.get("act_hours") or src.get("actual_hours"),
            start_date=src.get("start_date") or src.get("start_time"),
            end_date=src.get("end_date") or src.get("end_time"),
            pretask=src.get("pretask") or "无",
            target=src.get("target"),
            acceptance_criteria=src.get("acceptance_criteria") or src.get("criteria") or [],
            process=src.get("process") or [],
            remarks=src.get("remarks")
        )
