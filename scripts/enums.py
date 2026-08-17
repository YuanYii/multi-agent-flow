#!/usr/bin/env python3
"""
Multi-Agent Team Workflow (YY-Flow) - 全局领域模型枚举与标签元数据定义 (Single Source of Truth)
固化 任务状态 (TaskStatus)、任务类型 (TaskType)、专家角色 (RoleEnum) 及其色彩与流转元数据。
"""
from enum import Enum
from typing import Dict, List, Set, Any, Optional
import json
import os


class TaskStatus(str, Enum):
    """任务生命周期状态枚举 (9 态)"""
    TODO = "待开始"
    IN_PROGRESS = "进行中"
    IN_REVIEW = "审查中"
    IN_TEST = "测试中"
    COMPLETED = "已完成"
    ACCEPTED = "已验收"
    REJECTED = "已退回"
    BLOCKED = "已阻塞"
    CANCELLED = "已取消"

    @classmethod
    def all_values(cls) -> List[str]:
        return [item.value for item in cls]

    @classmethod
    def terminal_statuses(cls) -> Set[str]:
        """终态集合：到达后经办人默认收敛至 PM 严经理"""
        return {cls.COMPLETED.value, cls.ACCEPTED.value, cls.CANCELLED.value}

    @classmethod
    def active_statuses(cls) -> Set[str]:
        """活跃推进中状态集合"""
        return {cls.IN_PROGRESS.value, cls.IN_REVIEW.value, cls.IN_TEST.value}

    @classmethod
    def is_valid(cls, val: str) -> bool:
        return val in cls.all_values()


class TaskType(str, Enum):
    """任务类型枚举 (7 类)"""
    A = "A"  # 常规代码开发任务（走全生命周期链：进行中 -> 审查中 -> 测试中 -> 已完成 -> 已验收）
    B = "B"  # 架构设计 / 专项代码审计任务（短链直提验收：进行中 -> 已完成 -> 已验收）
    C = "C"  # 文档工程任务（短链直提验收：进行中 -> 已完成 -> 已验收）
    D = "D"  # Git / 运维部署任务（短链直提验收：进行中 -> 已完成 -> 已验收）
    E = "E"  # 用户自执行任务（快捷直验：待开始 / 进行中 -> 已验收）
    F = "F"  # 阶段总结任务（短链直提验收：进行中 -> 已完成 -> 已验收）
    G = "G"  # 环境治理 / 搭建任务（短链直提验收：进行中 -> 已完成 -> 已验收）

    @classmethod
    def all_values(cls) -> List[str]:
        return [item.value for item in cls]

    @classmethod
    def short_chain_types(cls) -> Set[str]:
        """无需代码审查与测试、可直接由进行中推至已完成的类型"""
        return {cls.B.value, cls.C.value, cls.D.value, cls.F.value, cls.G.value}

    @classmethod
    def is_valid(cls, val: str) -> bool:
        return val.upper() in cls.all_values()


class RoleEnum(str, Enum):
    """8 大虚拟专家与人员角色枚举 (规范中文名)"""
    PM = "严经理"
    ARCHITECT = "钱架构"
    DEV = "李开发"
    FRONTEND = "马前端"
    REVIEWER = "周审查"
    QA = "章测试"
    DOCS = "李文通"
    DEVOPS = "吕改特"
    USER = "用户"

    @classmethod
    def all_values(cls) -> List[str]:
        return [item.value for item in cls]

    @classmethod
    def expert_roles(cls) -> List[str]:
        """8 大 AI 专家角色集合"""
        return [
            cls.PM.value, cls.ARCHITECT.value, cls.DEV.value, cls.FRONTEND.value,
            cls.REVIEWER.value, cls.QA.value, cls.DOCS.value, cls.DEVOPS.value
        ]


# 角色别名与英文代码归一化映射表
ROLE_NORMALIZE_MAP: Dict[str, str] = {
    # PM
    "flow-pm": "严经理", "pm": "严经理", "PM": "严经理", "pm_user": "严经理", "严经理": "严经理",
    # ARCHITECT
    "flow-architect": "钱架构", "architect": "钱架构", "ARCHITECT": "钱架构", "architect_user": "钱架构", "钱架构": "钱架构",
    # DEV
    "flow-dev": "李开发", "dev": "李开发", "DEV": "李开发", "dev_user": "李开发", "dev_user_1": "李开发", "dev_user_2": "李开发", "李开发": "李开发",
    # FRONTEND
    "flow-frontend": "马前端", "frontend": "马前端", "FRONTEND": "马前端", "前端开发": "马前端", "frontend_user": "马前端", "马前端": "马前端",
    # REVIEWER
    "flow-reviewer": "周审查", "reviewer": "周审查", "REVIEWER": "周审查", "reviewer_user": "周审查", "reviewer_user_1": "周审查", "周审查": "周审查",
    # QA
    "flow-qa": "章测试", "qa": "章测试", "QA": "章测试", "qa_user": "章测试", "章测试": "章测试",
    # DOCS
    "flow-docs": "李文通", "docs": "李文通", "DOCS": "李文通", "docs_user": "李文通", "李文通": "李文通",
    # DEVOPS
    "flow-devops": "吕改特", "devops": "吕改特", "DEVOPS": "吕改特", "devops_user": "吕改特", "吕改特": "吕改特",
    # USER
    "user": "用户", "USER": "用户", "用户": "用户"
}


def normalize_role(val: Optional[str]) -> str:
    """将任意角色代码/英文/别名归一化为规范中文角色名"""
    if not val:
        return "未分配"
    s = str(val).strip()
    return ROLE_NORMALIZE_MAP.get(s) or ROLE_NORMALIZE_MAP.get(s.lower()) or ROLE_NORMALIZE_MAP.get(s.upper()) or s


# 状态与标签标准配色字典（供前后端统一消费）
STATUS_COLORS: Dict[str, Dict[str, str]] = {
    "待开始": {"bg": "#f2f3f5", "text": "#4e5969"},
    "进行中": {"bg": "#e8f0fe", "text": "#3370ff"},
    "审查中": {"bg": "#e8eaff", "text": "#3a5bdb"},
    "测试中": {"bg": "#e6fffb", "text": "#08979c"},
    "已完成": {"bg": "#e8ffea", "text": "#00a854"},
    "已验收": {"bg": "#e6fae8", "text": "#2f9e44"},
    "已退回": {"bg": "#fff7e6", "text": "#d97706"},
    "已阻塞": {"bg": "#fff1f0", "text": "#f53f3f"},
    "已取消": {"bg": "#f5f5f5", "text": "#8c8c8c"}
}

ROLE_COLORS: Dict[str, Dict[str, str]] = {
    "严经理": {"bg": "#e6f6eb", "text": "#248a3d"},
    "钱架构": {"bg": "#e1eaff", "text": "#3a5bdb"},
    "李开发": {"bg": "#fff0e0", "text": "#d97706"},
    "马前端": {"bg": "#e0e7ff", "text": "#4338ca"},
    "周审查": {"bg": "#e0f2fe", "text": "#0284c7"},
    "章测试": {"bg": "#fce8f8", "text": "#c21897"},
    "李文通": {"bg": "#fff7e6", "text": "#b45309"},
    "吕改特": {"bg": "#f0f0f0", "text": "#595959"},
    "用户":   {"bg": "#f3e8ff", "text": "#7c3aed"},
    "未分配": {"bg": "#f2f3f5", "text": "#8c8c8c"}
}

TASK_TYPE_COLORS: Dict[str, Dict[str, str]] = {
    "A": {"bg": "#e6f4ff", "text": "#0958d9", "label": "A (常规开发)"},
    "B": {"bg": "#f9f0ff", "text": "#722ed1", "label": "B (架构/审计)"},
    "C": {"bg": "#fff7e6", "text": "#d46b08", "label": "C (文档工程)"},
    "D": {"bg": "#e6fffb", "text": "#08979c", "label": "D (运维/Git)"},
    "E": {"bg": "#f6ffed", "text": "#389e0d", "label": "E (用户自建)"},
    "F": {"bg": "#feffe6", "text": "#7cb305", "label": "F (阶段总结)"},
    "G": {"bg": "#fff0f6", "text": "#c41d7f", "label": "G (环境治理)"}
}


def dump_enums_dict() -> Dict[str, Any]:
    """生成全量枚举与色彩元数据字典（用于导出 JSON 或向前端透传）"""
    return {
        "task_statuses": [
            {"key": k, "label": k, "colors": STATUS_COLORS.get(k, {})}
            for k in TaskStatus.all_values()
        ],
        "task_types": [
            {"key": k, "label": TASK_TYPE_COLORS.get(k, {}).get("label", k), "colors": TASK_TYPE_COLORS.get(k, {})}
            for k in TaskType.all_values()
        ],
        "roles": [
            {"key": k, "label": k, "colors": ROLE_COLORS.get(k, {})}
            for k in RoleEnum.all_values()
        ],
        "terminal_statuses": list(TaskStatus.terminal_statuses()),
        "short_chain_types": list(TaskType.short_chain_types()),
        "role_normalize_map": ROLE_NORMALIZE_MAP
    }


def export_enums_json(target_path: Optional[str] = None) -> str:
    """将枚举元数据固化导出为 JSON 文件"""
    if not target_path:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target_path = os.path.join(base_dir, "kanban", "json", "enums.json")
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    data = dump_enums_dict()
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return target_path


if __name__ == "__main__":
    out = export_enums_json()
    print(f"[SUCCESS] 成功导出枚举元数据: {out}")
