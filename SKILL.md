---
name: yy-flow
description: 适用于 AI 多 Agent 与人类团队协同研发的多角色状态流转、质量审计、防错闭环与看板自动化工作流技能包。可通过 /yy-flow、/yy-flow start、/yy-flow status、/yy-flow kanban、/yy-flow metrics 快捷指令或自然语言唤醒。
version: 1.0.0
---

# Multi-Agent Team Workflow Skill (YY-Flow)

> 契约驱动的多角色 Agent 协同研发技能包 —— 消除越权、打回碎片化与状态悬挂。

---

## 快捷唤醒指令 (Slash Commands)

本 Skill 注册了专有零冲突快捷唤醒指令 **`/yy-flow`**，输入即可 100% 确定性触发对应行为：

| 快捷指令 | 触发行为与职责 | 核心联动 |
| :--- | :--- | :--- |
| **`/yy-flow`** 或 **`/yy-flow start`** | **一键激活工作流**：自动执行初始化 7 步 SOP 并唤起 PM 严经理进行项目鉴定与任务编排 | 运行 `init_skill.sh`，生成 `user_data/` 并导出 8 大专家 |
| **`/yy-flow status`** | **心跳巡检与看板状态**：输出在手任务与告警（工单列表仅展示倒序最新 5 条） | 运行 `heartbeat.py`，检测超时滞留与并发超限 |
| **`/yy-flow kanban`** | **看板 Web 服务就绪**：启动内置离线看板 HTTP 服务并输出访问链接与概览（工单列表仅展示倒序最新 5 条） | 运行 `start_kanban_server.py`（默认 32886 起自动探测，同项目实例复用，以实际输出端口为准） |
| **`/yy-flow metrics`** | **效能度量报告**：一键计算并输出前置交付周期 (Lead Time)、吞吐量与卡点分析 | 运行 `metrics_analyzer.py` |
| **`/yy-flow create`** | **显式建单**：创建任务卡【待开始】并分配处理人（PM 可派发任意；非 PM 仅可自建） | 运行 `transition_task.py --create` / `quick_task.py create` |
| **`/yy-flow auto`** | **自动任务**：一条指令自动完成完整生命周期至已验收——全类型链（A–G）、任意节点续跑、已阻塞前置验证（【解除】记录）、重复任务校验 | 运行 `auto_task.py` |
| **`/yy-flow gate [stage]`** 或 **`/yy-flow close-stage`** | **阶段结项门禁核验**：执行阶段准出 4 项硬核验（看板全验收、WBS 对账、架构总结、管理复盘） | 运行 `check_stage_gate.py`，全绿放行后派发 DevOps 吕改特合流打 Tag |

---

## 核心契约与全局规则 (Global Rules & Contracts)

当 Agent 调用或执行本 Skill 时，必须加载并遵循 [`rules/`](rules/) 目录下的规则约束与交互协议：

1. **团队协作红线与按需加载** -> 调阅 [`rules/AGENTS.md`](rules/AGENTS.md)
2. **8 大专家身份与人设定义** -> 调阅 [`rules/IDENTITY.md`](rules/IDENTITY.md)
3. **安全控制心脏与防错原则** -> 调阅 [`rules/SOUL.md`](rules/SOUL.md)
4. **看板巡检与卡顿监控 CheckList** -> 调阅 [`rules/HEARTBEAT.md`](rules/HEARTBEAT.md)
5. **工具链与 CLI 适配指引** -> 调阅 [`rules/TOOLS.md`](rules/TOOLS.md)
6. **用户自领取与代行授权协议** -> 调阅 [`rules/USER.md`](rules/USER.md)

---

## 初次加载：技术架构自动识别 SOP (Architecture Discovery)

当 Agent **初次在此工作区调阅/加载本 Skill**（检测到 `config/project_architecture.config.yaml` 不存在，**或**其 `meta.initialized != true`）时，必须自动执行以下操作并遵循响应契约：

> [NOTICE] **【显式响应与 Token 预警契约】**
> Agent 在启动初始化时，**必须第一时间在回复中显式输出以下提示**：
> 1. **初始化声明**：“正在为您初始化 `multi-agent-flow` 工作流并识别当前项目技术架构...”
> 2. **Token 消耗提示**：“[NOTE] **提示**：初次初始化需要全面扫描与解析全局项目配置文件（如 `package.json`/`pyproject.toml`/`go.mod`/`Dockerfile` 等）并同步更新专家团队规则，**本次操作可能会消耗较多 Token**。初始化完成后配置将持久落盘，后续使用无需重新扫描。”
> 3. **步骤清单展示**：向用户展示即将自动执行的 8 大初始化动作。

### 初始化自动执行步骤：

1. **核验配置文件**：检查 `config/project_architecture.config.yaml` 是否已存在。
2. **代码物理强拦截与 Subagent 官方规范落盘**：
   - **【代码层物理拦截】**：必须运行 `python3 scripts/verify_and_export_agents.py`。该脚本按 `config/agent_platforms.yaml` 声明的各平台官方导出路径与格式完成 8 大专家子代理落盘。
   - **本地格式断言 (Fail-Closed)**：脚本在导出后逐份执行确定性校验——Markdown frontmatter 可被 YAML 解析、Codex TOML 可被 tomllib 解析、`name`/`description` 必填、8 角色齐全；任一不满足即 `exit(1)` 阻断初始化（挂载失败降级为 WARN 提示）。此机制不依赖网络，从代码层解耦对 AI 纯文本“记忆力”的依赖。
3. **自动扫描与识别**（若不存在配置文件）：
   - 自动扫描工作区配置文件（如 `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Dockerfile`, `README.md` 等）。
   - 识别应用类型、开发语言、核心框架、单测/构建工具及目录架构模式。
4. **模板复制与落库**：
   - 复制模板 [`config/project_architecture.template.yaml`](config/project_architecture.template.yaml) 生成 `user_data/project_architecture.config.yaml`（落**数据根** `.yy-flow/user_data`；存量内嵌安装为 Skill 目录，零迁移）。
   - 将扫描识别出的真实技术架构结构化填充写入 `project_architecture.config.yaml`，作为后续 DEV / ARCHITECT / QA 等专家角色的统一技术事实依据。
5. **项目工程文档骨架建立与原项目历史文档自动归档**：
   - 在目标项目下自动校验/建立 `docs/` 目录规范骨架（包含 `D01-项目管理/`(含D01-需求/D02-状态报告), `D02-架构设计/`, `D03-业务模块/`, `D04-研发过程/`(含D01-任务/D02-报告/D03-操作手册), `D05-规范标准/`, `D06-文档模板/` 及 `草稿箱/`）。
   - **历史文档隔离归档**：运行 `python3 scripts/migrate_legacy_docs.py` 自动扫描原项目中散落的历史文档，在对应的分类目录下创建 **`原项目文档/`** 专用文件夹进行拷贝分类隔离。
   - 在目标项目 `.gitignore` 中确保排除 `草稿箱/` 隔离区。
6. **专家团队技术栈自动同步**：
   - 运行脚本 `python3 scripts/update_agent_tech_stacks.py` 触发重新导出。
   - 技术栈在**导出时**合并至各平台 Subagent 产物（6 个技术角色的职责与栈定制；PM/文档角色无技术栈绑定）；`agents/*.yaml` 为只读模板，不再被改写——多项目共享同一份 Skill 时互不覆盖。
7. **唤起 PM 专家进行项目定位鉴定与显式响应契约**：
   - 自动加载 `agents/01-pm.yaml` 身份，扫描解析当前项目的 `README.md`、配置文件与源码入口。
   - 分析认定项目主要用途与核心功能，**强制在回复顶部输出标志行与官方查证凭据**：
     > **`【已识别 xxxx 项目】`**
     >  **官方 Subagent 规范查证凭据**：`https://antigravity.google/docs/...` (查证物理路径：`{workspace}/.agents/agents/{name}/agent.md`)
   - **显式输出 8 大专家子 Agent 列表与完整写权限矩阵**：
     强制在回复中输出 Markdown 表格，清晰呈现所有子 Agent 标识、角色名称（前端专家【马前端】）、工具权限（已装配完整读写与 `run_command`）与合法状态流转区间：
     | 子代理标识 | 角色名称 | 核心职责 | 工具权限 | 合法状态流转区间 |
     | :--- | :--- | :--- | :--- | :--- |
     | `@flow-pm` | 严经理 (项目经理) | 需求拆解、并发控制与终态验收 | 完整读写 + run_command | 待开始->进行中 / 已完成->已验收 |
     | `@flow-architect` | 钱架构 (系统架构师) | 系统总体架构设计与 ADR 接口契约 | 完整读写 + run_command | 待开始->进行中 / 进行中->已完成 |
     | `@flow-dev` | 李开发 (开发工程师) | 后端/全栈核心编码与单测实现 | 完整读写 + run_command | 待开始->进行中 / 进行中->审查中 (并发≤3) |
     | `@flow-frontend` | 马前端 (前端开发工程师) | 现代 Web/UI 组件与交互体验开发 | 完整读写 + run_command | 待开始->进行中 / 进行中->审查中 (并发≤3) |
     | `@flow-reviewer` | 周审查 (代码审查专家) | 代码规范、安全扫描与质量门控 | 完整读写 + run_command | 审查中->测试中 / 审查中->已退回 |
     | `@flow-qa` | 章测试 (测试工程师) | 集成测试、边界场景与质量准出 | 完整读写 + run_command | 测试中->已完成 / 测试中->已退回 |
     | `@flow-docs` | 李文通 (文档工程师) | 文档架构治理、用户手册与规范 | 完整读写 + run_command | 待开始->进行中 / 进行中->已完成 |
     | `@flow-devops` | 吕改特 (运维管理员) | 分支合流、发布构建与 CI 巡检 | 完整读写 + run_command | 待开始->进行中 / 进行中->已完成 |
   - **看板进度查看提示**：在创建任务或完成状态流转后，显式提示用户通过 Web 看板实时查看（如 `http://127.0.0.1:{实际端口}/`）。

---

## 动态流转协议 (Dynamic Routing Protocol)

当 Agent 收到任务流转、领单、审查、测试或提权指令时，按需调阅 [`references/`](references/) 目录下的规约文档：

0. **任务分级判定 (L0/L1/L2 三问)** -> 调阅 [`references/02-State-Flow-Rules.md §二`](references/02-State-Flow-Rules.md)
1. **识别任务与角色边界** -> 调阅 [`references/01-AI-Team-Workflow-Index.md`](references/01-AI-Team-Workflow-Index.md)
2. **推导合法下一状态** -> 调阅 [`references/02-State-Flow-Rules.md`](references/02-State-Flow-Rules.md)
3. **校验角色权限与门控** -> 调阅 [`references/03-Anti-Error-Mechanism.md`](references/03-Anti-Error-Mechanism.md)
4. **校验分支与 Git 规范** -> 调阅 [`references/04-Git-Workflow-Spec.md`](references/04-Git-Workflow-Spec.md)
5. **校验文档结构与元数据** -> 调阅 [`references/05-Document-Management-Spec.md`](references/05-Document-Management-Spec.md)
6. **校验交接契约、Message 载荷与虚拟角色通知边界** -> 调阅 [`references/06-Inter-Agent-Handover-Protocol.md`](references/06-Inter-Agent-Handover-Protocol.md)

---

## 模块索引与工具链

- [`rules/`](rules/)：工作区核心规则与交互契约（`AGENTS.md` ~ `USER.md`）。
- [`config/`](config/)：技术架构模板/ Schema（`project_architecture.schema.json`）与看板角色配置模板。
- [`agents/`](agents/)：8 大角色 YAML 定义 (`01-pm.yaml` ~ `08-frontend.yaml`)。
- [`references/`](references/)：6 大全量提炼参考规约（路由、流转规则、防错闭环、Git 规范、文档治理规范、交接协议）。
- [`templates/`](templates/)：标准化开发/审查/测试任务报告与工程文档模板。
- [`scripts/`](scripts/)：顶层为 CLI 入口与基石模块（门控流转 `transition_task.py`、报告生成器 `generate_report.py`、凭证安全扫描 `check_secrets.py`、动态 Prompt 上下文合成器 `build_agent_context.py`、数据根解析 `paths.py`、枚举 `enums.py`）；内部纯模块按职责归入私有包 `scripts/_lib/`（`_lib/boards/` 看板适配器与工厂、`_lib/audit/` 审计日志、`_lib/core/` 门控强校验 `validate_transition.py` / 文件锁 `file_lock.py` / 技术栈覆盖层 `agent_tech_overlay.py`，Agent 不应直接调用）。数据根统一解析 (`paths.py`：`--project-root`/`YY_FLOW_PROJECT_ROOT` > `.yy-flow` 自定位 > legacy > CWD；安装于 `.yy-flow/skill` 时数据自动落 `.yy-flow/user_data`，docs/ 留项目根)；多项目共享安装器 (`install_global.sh` / `.ps1`，详见 README「共享安装」)。

