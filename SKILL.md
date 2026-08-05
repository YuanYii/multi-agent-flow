---
name: multi-agent-team-workflow
description: 适用于 AI 多 Agent 与人类团队协同研发的多角色状态流转、质量审计、防错闭环与看板自动化工作流技能包。
version: 1.0.0
---

# 🤖 Multi-Agent Team Workflow Skill

> 契约驱动的多角色 Agent 协同研发技能包 —— 消除越权、打回碎片化与状态悬挂。

---

## 📜 核心契约与全局规则 (Global Rules & Contracts)

当 Agent 调用或执行本 Skill 时，必须加载并遵循 [`rules/`](rules/) 目录下的规则约束与交互协议：

1. **团队协作红线与按需加载** ➔ 调阅 [`rules/AGENTS.md`](rules/AGENTS.md)
2. **7 大专家身份与人设定义** ➔ 调阅 [`rules/IDENTITY.md`](rules/IDENTITY.md)
3. **安全控制心脏与防错原则** ➔ 调阅 [`rules/SOUL.md`](rules/SOUL.md)
4. **看板巡检与卡顿监控 CheckList** ➔ 调阅 [`rules/HEARTBEAT.md`](rules/HEARTBEAT.md)
5. **工具链与 CLI 适配指引** ➔ 调阅 [`rules/TOOLS.md`](rules/TOOLS.md)
6. **用户自领取与代行授权协议** ➔ 调阅 [`rules/USER.md`](rules/USER.md)

---

## 🔍 初次加载：技术架构自动识别 SOP (Architecture Discovery)

当 Agent **初次在此工作区调阅/加载本 Skill**（检测到 `config/project_architecture.config.yaml` 不存在）时，必须自动执行以下操作并遵循响应契约：

> 📢 **【显式响应与 Token 预警契约】**
> Agent 在启动初始化时，**必须第一时间在回复中显式输出以下提示**：
> 1. **初始化声明**：“正在为您初始化 `multi-agent-flow` 工作流并识别当前项目技术架构...”
> 2. **Token 消耗提示**：“💡 **提示**：初次初始化需要全面扫描与解析全局项目配置文件（如 `package.json`/`pyproject.toml`/`go.mod`/`Dockerfile` 等）并同步更新专家团队规则，**本次操作可能会消耗较多 Token**。初始化完成后配置将持久落盘，后续使用无需重新扫描。”
> 3. **步骤清单展示**：向用户展示即将自动执行的 4 大初始化动作。

### 初始化自动执行步骤：

1. **核验配置文件**：检查 `config/project_architecture.config.yaml` 是否已存在。
2. **自动扫描与识别**（若不存在）：
   - 自动扫描工作区配置文件（如 `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Dockerfile`, `README.md` 等）。
   - 识别应用类型、开发语言、核心框架、单测/构建工具及目录架构模式。
3. **模板复制与落库**：
   - 复制模板 [`config/project_architecture.template.yaml`](config/project_architecture.template.yaml) 生成 `config/project_architecture.config.yaml`。
   - 将扫描识别出的真实技术架构结构化填充写入 `project_architecture.config.yaml`，作为后续 DEV / ARCHITECT / QA 等专家角色的统一技术事实依据。
4. **专家团队技术栈自动同步**：
   - 运行脚本 `python3 scripts/update_agent_tech_stacks.py`（或由 Agent 依据 `project_architecture.config.yaml` 直接修改 `agents/*.yaml`）。
   - 将扫描到的真实语言、框架、单测框架与 CI/CD 工具自动落盘同步至 `agents/03-dev.yaml` ~ `07-devops.yaml`，完成专家团队技术栈的高精定制。

---

## ⚡ 动态流转协议 (Dynamic Routing Protocol)

当 Agent 收到任务流转、领单、审查、测试或提权指令时，按需调阅 [`references/`](references/) 目录下的规约文档：

1. **识别任务与角色边界** ➔ 调阅 [`references/01-AI-Team-Workflow-Index.md`](references/01-AI-Team-Workflow-Index.md)
2. **推导合法下一状态** ➔ 调阅 [`references/02-State-Flow-Rules.md`](references/02-State-Flow-Rules.md)
3. **校验角色权限与门控** ➔ 调阅 [`references/03-Anti-Error-Mechanism.md`](references/03-Anti-Error-Mechanism.md)
4. **校验分支与 Git 规范** ➔ 调阅 [`references/04-Git-Workflow-Spec.md`](references/04-Git-Workflow-Spec.md)

---

## 📂 模块索引与工具链

- [`rules/`](rules/)：工作区核心规则与交互契约（`AGENTS.md` ~ `USER.md`）。
- [`config/`](config/)：技术架构模板/ Schema（`project_architecture.schema.json`）与看板角色配置模板。
- [`agents/`](agents/)：7 大角色 YAML 定义 (`01-pm.yaml` ~ `07-devops.yaml`)。
- [`references/`](references/)：4 大全量提炼参考规约（路由、流转规则、防错闭环、Git 规范）。
- [`templates/`](templates/)：标准化开发/审查/测试任务报告模板。
- [`scripts/`](scripts/)：看板工厂适配器 (`board_adapter_factory.py`)、门控强校验 (`validate_transition.py`)、报告生成器 (`generate_report.py`)、凭证安全扫描 (`check_secrets.py`) 与动态 Prompt 上下文合成器 (`build_agent_context.py`)。
