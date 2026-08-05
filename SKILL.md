---
name: multi-agent-team-workflow
description: 适用于 AI 多 Agent 与人类团队协同研发的多角色状态流转、质量审计、防错闭环与看板自动化工作流技能包。
version: 1.0.0
---

# 🤖 Multi-Agent Team Workflow Skill

> 契约驱动的多角色 Agent 协同研发技能包 —— 消除越权、打回碎片化与状态悬挂。

---

## ⚡ 动态流转协议 (Dynamic Routing Protocol)

当 Agent 收到任务流转、领单、审查、测试或提权指令时，按需调阅 [`references/`](references/) 目录下的规约文档：

1. **识别任务与角色边界** ➔ 调阅 [`references/01-AI-Team-Workflow-Index.md`](references/01-AI-Team-Workflow-Index.md)
2. **推导合法下一状态** ➔ 调阅 [`references/02-State-Flow-Rules.md`](references/02-State-Flow-Rules.md)
3. **校验角色权限与门控** ➔ 调阅 [`references/03-Anti-Error-Mechanism.md`](references/03-Anti-Error-Mechanism.md)
4. **校验分支与 Git 规范** ➔ 调阅 [`references/04-Git-Workflow-Spec.md`](references/04-Git-Workflow-Spec.md)

---

## 📂 模块索引与工具链

- [`config/workflow.config.template.yaml`](config/workflow.config.template.yaml)：看板与角色配置文件模板。
- [`agents/`](agents/)：7 大角色 YAML 定义 (`01-pm.yaml` ~ `07-devops.yaml`)。
- [`references/`](references/)：4 大全量提炼参考规约（路由、流转规则、防错闭环、Git 规范）。
- [`templates/`](templates/)：标准化开发/审查/测试任务报告模板。
- [`scripts/`](scripts/)：看板 API/CLI 自动化交互与状态巡检脚本。
