---
name: yy-flow
description: 适用于 AI 多 Agent 与人类团队协同研发的多角色状态流转、质量审计、防错闭环与看板自动化工作流技能包。可通过 /yy-flow help、/yy-flow start、/yy-flow status、/yy-flow kanban 快捷指令或自然语言唤醒。
version: 2.0.0
---

# Multi-Agent Team Workflow Skill (YY-Flow)

> **契约驱动的多角色 Agent 协同研发微内核** —— 消除越权、打回碎片化与状态悬挂。

---

## 统一入口网关协议 (Unified Gateway Protocol)

所有调用本 Skill 的指令统一收敛至本网关入口，按如下双支线规则分流与判定：

### 1. 双支线分流矩阵

| 分支类型 | 触发特征与指令 | 处理机制与响应契约 | 典型场景 |
| :--- | :--- | :--- | :--- |
| **分支 A：系统控制台操作** | `/yy-flow help`<br>`/yy-flow start`<br>`/yy-flow status`<br>`/yy-flow kanban`<br>`/yy-flow sync-pr` | **直通底层运维引擎**（0 前置分级），直接执行对应脚本并输出系统状态。 | 查看帮助手册、初始化 SOP、启动看板、大盘巡检、PR 解阻 |
| **分支 B：业务研发与交互意图** | 自然语言需求、代码修改、特性开发、缺陷修复、排查排障、`/yy-flow auto` | **强制前置执行【分级三问与单一职责拆分】**，并在回复首行显式输出双标头标识：<br>`【任务分级: L0 即时问答 / L1 短链任务 / L2 标准研发】 | 【单一职责: 合规单卡 / 复合需求需拆解为 N 个原子任务】` | “写个登录接口”、“优化下正则”、“解释函数逻辑” |

### 2. 业务需求【分级三问】决策流

```text
[业务需求输入]
   │
   ├─► 1. 会留下代码/文档/配置等仓库文件修改吗？
   │      ├─ 否 ──► 2. 结论需要作为后续工程依据事后追溯吗？
   │      │            ├─ 否 ───────────────► 【L0 即时问答】（无卡直接作答，0 毫秒 CLI 延迟，草稿入草稿箱）
   │      │            └─ 是 ───────────────► 【L1 轻量任务】（建卡走短链：单角色完成 → PM 验收）
   │      │
   │      └─ 是 ──► 3. 需要多角色协作、修改核心业务代码或变更公共基础库吗？
   │                   ├─ 否 ───────────────► 【L1 轻量任务】
   │                   └─ 是 ───────────────► 【L2 标准研发任务】（建卡走全链：DEV 编码 → Reviewer 审查 → QA 测试 → PM 验收）
```

- 凡属于 L1/L2 业务需求，网关强制执行单一职责审查（工时 ≤ 8.0h，单一原子交付物）。跨正交领域需求必须拆解建卡。
- 执行态 Task ID（如 `T0001`）直接穿透网关进入状态机推进，严禁二次建卡。

---

## 模块化规约索引 (按需调阅，禁止全量盲目加载)

当且仅当进入特定业务场景时，Agent 必须调用 `view_file` 调阅对应规约子目录：
- **初次加载 / 架构未定版**：必须调阅 [`references/02-bootstrap/`](references/02-bootstrap/) 执行 8 步 SOP
- **创建任务 / 单一职责判定**：调阅 [`references/01-gateway/`](references/01-gateway/)
- **任务流转 / 门控规则 / 角色权限**：调阅 [`references/03-engine/`](references/03-engine/)
- **上下文交接 / 跨 Agent Handoff (CCP)**：调阅 [`references/04-ccp/`](references/04-ccp/)
- **看板服务运维 / PR 自动解阻**：调阅 [`references/05-kanban/`](references/05-kanban/)
- **Git 分支合流 / 审计日志与度量**：调阅 [`references/06-governance/`](references/06-governance/)
