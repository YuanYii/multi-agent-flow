#!/usr/bin/env python3
"""
阶段交付总结与过程执行详情自动生成引擎 (Step Summary Generator)
供 auto_task、quick_task、transition_task 与 start_kanban_server 统一调用，
杜绝流转过程中过程描述空心化。
"""
from typing import Optional


def generate_step_summary(from_st: str, to_st: str, name: str = "", role_name: str = "") -> str:
    """生成结合具体任务名称与角色的阶段交付实质性总结"""
    clean_name = (name or "当前工作包任务").strip()

    if from_st in ("新建", "待开始") and to_st == "进行中":
        return f"认领【{clean_name}】并进入开发/执行阶段，初始化工作区与相关依赖"
    elif from_st == "进行中" and to_st == "审查中":
        return f"完成【{clean_name}】核心功能实现与模块自测，提交代码审查与规范核验"
    elif from_st == "审查中" and to_st == "测试中":
        return f"完成【{clean_name}】代码质量、安全与规范合规性审查，未见明显异常，移交测试"
    elif from_st == "测试中" and to_st == "已完成":
        return f"完成【{clean_name}】单元测试与集成冒烟验证，功能符合预期，提请人类用户核验验收"
    elif from_st == "已完成" and to_st == "已验收":
        return f"人类用户核验【{clean_name}】全部交付物与验收标准，确认闭环，完成最终验收"
    elif to_st == "进行中":
        return f"恢复【{clean_name}】至进行中状态，继续推进研发与执行"
    elif to_st == "审查中":
        return f"提交【{clean_name}】阶段成果至周审查进行代码与架构审查"
    elif to_st == "测试中":
        return f"移交【{clean_name}】至章测试进行功能验证与集成测试"
    elif to_st == "已完成":
        return f"完成【{clean_name}】任务全部交付物开发，提请核验验收"
    elif to_st == "已验收":
        return f"人类用户核验【{clean_name}】交付物合规，确认最终验收"
    elif to_st == "已取消":
        return f"经评估确认取消【{clean_name}】任务，释放在制品并发槽位"
    elif to_st == "已阻塞":
        return f"【{clean_name}】遇到外部依赖或前置阻塞，进入挂起等待"
    elif to_st == "已退回":
        return f"【{clean_name}】因评审或测试缺陷退回至进行中重新修复"
    return f"推进【{clean_name}】由【{from_st}】更新至【{to_st}】"
