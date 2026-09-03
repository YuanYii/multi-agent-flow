---
name: yy-flow
description: 适用于 AI 多 Agent 与人类团队协同研发的多角色状态流转、质量审计、防错闭环与看板自动化工作流技能包。可通过 /yy-flow help、/yy-flow start、/yy-flow status、/yy-flow kanban 快捷指令或自然语言唤醒。
version: 2.2.0
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
   │      │            └─ 是 ───────────────► 【L1 轻量任务】（建卡走短链：单角色完成 → 提请用户验收）
   │      │
   │      └─ 是 ──► 3. 需要多角色协作、修改核心业务代码或变更公共基础库吗？
   │                   ├─ 否 ───────────────► 【L1 轻量任务】
   │                   └─ 是 ───────────────► 【L2 标准研发任务】（建卡走全链：DEV 编码 → Reviewer 审查 → QA 测试 → 提请用户验收）
```

- 凡属于 L1/L2 业务需求，网关强制执行单一职责审查（工时 ≤ 8.0h，单一原子交付物）。跨正交领域需求必须拆解建卡。
- 执行态 Task ID（如 `T0001`）直接穿透网关进入状态机推进，严禁二次建卡。

---

## 核心命令速查表 (CLI Command Quick Reference)

| 业务场景 | 统一 CLI 门面 (`cli.py`) | 底层专用脚本 | 核心作用与参数 |
| :--- | :--- | :--- | :--- |
| **创建任务卡** | `python3 scripts/cli.py task create ...` | `python3 scripts/quick_task.py create ...` | `--name "..." --assignee "..." --stage "..." --type "A" --target "..." --criteria "..."` |
| **代码化派单** | `python3 scripts/cli.py dispatch --task-id T00xx` | `python3 scripts/dispatch_task.py` | 校验依赖与并发，推至【进行中】，输出 Subagent 载荷 |
| **推进任务流转** | `python3 scripts/transition_task.py ...` | `python3 scripts/transition_task.py ...` | `--task-id T00xx --role DEV --from-status 进行中 --to-status 审查中 --remarks "..."` |
| **人类终态验收** | `python3 scripts/cli.py task accept ...` | `python3 scripts/quick_task.py accept ...` | `--task-id T00xx`（**人类用户专属**，严禁 Agent 代签） |
| **启动看板** | `python3 scripts/cli.py kanban` | `python3 scripts/start_kanban_server.py` | 默认启动于 `http://127.0.0.1:32886/` |
| **健康度巡检** | `python3 scripts/cli.py status` | `python3 scripts/heartbeat.py` | 输出大盘健康度、阻塞卡片与效能指标 |
| **连续性校验** | `python3 scripts/cli.py ccp ...` | `python3 scripts/cli.py ccp ...` | `--task-id T00xx --stage 审查中` 校验上下文连续性 |

---

## 8 大专家子代理写权限与流转区间矩阵

> [!IMPORTANT]
> **物理隔离铁律**：主 Agent (PM 严经理) 严禁在主会话中自扮演研发编写业务代码！涉及代码变更的任务，**必须通过 `invoke_subagent` 派发对应专家子代理在独立进程中完成**。

| 子代理标识 | 角色名称 | 核心职责 | 合法状态流转区间 | 退出契约 |
| :--- | :--- | :--- | :--- | :--- |
| `@flow-pm` | 严经理 (项目经理) | 需求拆解、分级判定与派单 | 待开始 ➔ 进行中 / 提请验收 | 终态停在【已完成】，提请人类验收 |
| `@flow-architect`| 钱架构 (系统架构师) | 系统总体架构、接口契约与选型 | 待开始 ➔ 进行中 ➔ 已完成 | 产出 ADR 与架构方案文档 |
| `@flow-dev` | 李开发 (开发工程师) | 后端/全栈核心编码与单测实现 | 待开始 ➔ 进行中 ➔ 审查中 | 必须运行单测，生成开发报告 |
| `@flow-frontend` | 马前端 (前端开发工程师) | Web/UI 组件与前端体验实现 | 待开始 ➔ 进行中 ➔ 审查中 | 验证组件渲染与交互，生成报告 |
| `@flow-reviewer` | 周审查 (代码审查专家) | 代码规范、安全扫描与质量门控 | 审查中 ➔ 测试中 / 审查中 ➔ 已退回 | 静态扫描无告警，产出审查意见 |
| `@flow-qa` | 章测试 (测试工程师) | 集成测试、边界用例与质量准出 | 测试中 ➔ 已完成 / 测试中 ➔ 已退回 | 编写测试用例，记录实际工时 |
| `@flow-docs` | 李文通 (文档工程师) | 交付物文档治理与用户手册 | 待开始 ➔ 进行中 ➔ 已完成 | 遵循 GB/T 7713 学术与工程规范 |
| `@flow-devops` | 吕改特 (运维管理员) | 分支合流、发布构建与 CI 巡检 | 待开始 ➔ 进行中 ➔ 已完成 | 验证流水线通过，解决 PR 阻塞 |

---

## 模块化规约实体索引 (按需查阅具体规范文件)

当且仅当进入特定业务场景时，Agent 必须调用 `view_file` 查阅对应规约的实体 Markdown 文件：
- **初次加载 / 冷启动 SOP**：调阅 [`references/02-bootstrap/01-initialization_sop.md`](references/02-bootstrap/01-initialization_sop.md)
- **创建任务 / 单一职责判定**：调阅 [`references/01-gateway/01-task_classification.md`](references/01-gateway/01-task_classification.md)
- **任务流转 / 门控规则 / 角色权限**：调阅 [`references/03-engine/01-state_flow_rules.md`](references/03-engine/01-state_flow_rules.md)
- **上下文交接 / 跨 Agent Handoff (CCP)**：调阅 [`references/04-ccp/01-ccp_protocol_spec.md`](references/04-ccp/01-ccp_protocol_spec.md)
- **看板服务运维 / PR 自动解阻**：调阅 [`references/05-kanban/01-kanban_and_pr_sync.md`](references/05-kanban/01-kanban_and_pr_sync.md)
- **Git 分支合流 / 审计日志与度量**：调阅 [`references/06-governance/01-git_and_audit_spec.md`](references/06-governance/01-git_and_audit_spec.md)
