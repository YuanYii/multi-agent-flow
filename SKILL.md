---
name: yy-flow
description: 适用于 AI 多 Agent 与人类团队协同研发的多角色状态流转、质量审计、防错闭环与看板自动化工作流技能包。可通过 /yy-flow、/yy-flow start、/yy-flow status、/yy-flow kanban、/yy-flow metrics 快捷指令或自然语言唤醒。
version: 1.0.0
---

# Multi-Agent Team Workflow Skill (YY-Flow)

> **“不要让CV工程师变成YES工程师”** —— 契约驱动的多角色 Agent 协同研发技能包，消除越权、打回碎片化与状态悬挂。

---

## 统一入口网关协议 (Unified Gateway Protocol)

所有调用本 Skill 的指令（包括专有 Slash 指令与日常自然语言需求）统一收敛至本网关入口，按如下双支线规则分流与判定：

### 1. 双支线分流矩阵

| 分支类型 | 触发特征与指令 | 处理机制与响应契约 | 典型场景 |
| :--- | :--- | :--- | :--- |
| **分支 A：系统控制台操作** | `/yy-flow start`<br>`/yy-flow status`<br>`/yy-flow kanban`<br>`/yy-flow sync-pr`<br>`/yy-flow gate` | **直通底层运维引擎**（0 前置分级），直接执行对应脚本并输出系统状态。 | 初始化 SOP、启动看板、大盘巡检、PR 解阻、阶段门禁核验 |
| **分支 B：业务研发与交互意图** | 自然语言需求、代码修改、特性开发、缺陷修复、排查排障、`/yy-flow auto` | **强制前置执行【分级三问】**，并在回复首行显式输出分级标识：<br>`【任务分级: L0 即时问答 / L1 短链任务 / L2 标准研发】` | “写个登录接口”、“优化下正则”、“解释函数逻辑” |

### 2. 业务需求【分级三问】决策流

```text
[业务需求输入]
   │
   ├─► 1. 会留下代码/文档/配置等仓库文件修改吗？
   │      ├─ 否 ──► 2. 结论需要作为后续工程依据事后追溯吗？
   │      │            ├─ 否 ───────────────► 【L0 即时问答】（无卡直接作答，0 毫秒 CLI 延迟，草稿入草稿箱）
   │      │            └─ 是 ───────────────► 【L1 轻量任务】（建卡走短链：B/C/D/F/G）
   │      │
   │      └─ 是 ──► 3. 需要多角色协作、修改核心业务代码或变更公共基础库吗？
   │                   ├─ 否 ───────────────► 【L1 轻量任务】（建卡走短链：单角色完成 → PM 严经理终态验收）
   │                   └─ 是 ───────────────► 【L2 标准研发任务】（建卡走全链：DEV 编码 → Reviewer 审查 → QA 测试 → PM 验收）
```

### 3. 核心豁免与升格防线

- 🛡️ **执行态 Task ID 豁免（防死循环建卡）**：指令若显式携带明确 Task ID（如 `T0001`、`DEF-T0001-1`）或属于专家子代理在执行内部流转（如周审查提审、章测试提交），**直接穿透网关进入状态机推进，严禁二次建卡**。
- 🔄 **复合指令管道化**：若用户同时下达控制台指令与业务需求（如“启动看板并写个接口”），网关优先执行控制台操作，随后将伴随的业务需求送入分级三问网关。
- ⚠️ **核心模块与高危操作强制升格 L2**：凡涉及公共核心库、认证授权/密钥变更、数据库迁移或多下游影响的代码变更，即便属于单文件修改，**一律强制升格为 L2 全流程多专家制衡**。

---

## 快捷唤醒指令 (Slash Commands)

本 Skill 注册了专有快捷唤醒指令 **`/yy-flow`**，输入即可触发对应行为：

| 快捷指令 | 触发行为与职责 | 核心联动 |
| :--- | :--- | :--- |
| **`/yy-flow`** 或 **`/yy-flow start`** | **一键激活工作流**：自动执行初始化 7 步 SOP 并唤起 PM 严经理进行项目鉴定与任务编排 | 运行 `init_skill.sh`，生成 `user_data/` 并导出 8 大专家 |
| **`/yy-flow status`** | **看板全局大盘与健康巡检**：一键输出项目完成进度、交付周期 Lead Time、专家负荷与风险阻断告警 | 运行 `heartbeat.py`，整合大盘统计、超时滞留与并发告警 |
| **`/yy-flow kanban`** | **看板 Web 服务就绪**：启动内置可视化看板 HTTP 服务并输出访问链接（默认 32886 端口） | 运行 `start_kanban_server.py`，支持多视图切换与 PR/Issue 徽标渲染 |
| **`/yy-flow sync-pr`** | **PR 状态监听与合流自动解阻**：扫描【已阻塞】任务卡，检测 GitHub PR Merged 自动推进至【已完成】并唤起 PM 验收 | 运行 `sync_pr_status.py` / `heartbeat.py --sync-pr` |
| **`/yy-flow auto <需求>`** | **全自动多专家研发流水线**：由主 Agent 串行调度多专家子代理（DEV ➔ REVIEWER ➔ QA ➔ PM）进行实体代码开发、审查与测试，在【已完成】主动停机交付（严禁代签验收，最多自愈打回 2 轮；代码保留在本地工作区，严禁擅自 git commit） | 运行 `auto_task.py --task "<需求>"` |
| **`/yy-flow test-pipeline`** | **底层管道冒烟测试**：通过生成临时测试任务卡，全流程遍历状态机节点（从 0 状态到终态）并强制校验门禁逻辑，确保工具链环境健康 | 运行 `pytest scripts/test_pipeline.py` |

> 💡 **业务流转与协同全走自然语言**：任务拆解建卡、阶段开工（`check_stage_gate.py --action start`）、阶段结项（`check_stage_gate.py --action close`）、认领、提审、测试与打回等日常研发生命周期，直接使用自然语言与 Agent 对话沟通，由对应专家在后台自主调度底层脚本。

---

> [!NOTE]
> **跨平台 Python 解释器执行规范**：本文档与所有规则中涉及的 CLI 命令示例统一使用 Unix/macOS 的 `python3` 格式表述；在 **Windows 操作系统** 下，Agent 与用户执行时必须自动替换为 **`python`**（如 `python scripts/transition_task.py ...`）。

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
3. **自动代码物理预扫描**：
   - 运行 `python3 scripts/auto_scan_stack.py` 对工作区工程依赖、配置文件与 README 进行只读预检分析。
4. **模板复制与落库**：
   - 复制模板 [`config/project_architecture.template.yaml`](config/project_architecture.template.yaml) 生成 `user_data/project_architecture.config.yaml`（落**数据根** `.yy-flow/user_data`；存量内嵌安装为 Skill 目录，零迁移）。
5. **项目工程文档骨架建立与原项目历史文档自动归档**：
   - 在目标项目下自动校验/建立 `docs/` 目录规范骨架（包含 `D01-项目管理/`(含D01-需求/D02-状态报告), `D02-架构设计/`, `D03-业务模块/`, `D04-研发过程/`(含D01-任务/D02-报告/D03-操作手册), `D05-规范标准/`, `D06-文档模板/` 及 `草稿箱/`）。
   - **历史文档隔离归档**：运行 `python3 scripts/migrate_legacy_docs.py` 自动扫描原项目中散落的历史文档，在对应的分类目录下创建 **`原项目文档/`** 专用文件夹进行拷贝分类隔离。
   - 在目标项目 `.gitignore` 中确保排除 `草稿箱/` 隔离区。
6. **物理派发架构全景鉴定工单与专家技术栈同步**：
   - 运行 `python3 scripts/quick_task.py create --name "项目技术架构全景鉴定与选型定版" --role PM --assignee 钱架构 --type B` 物理建卡【待开始】（AUTO 自动编号防冲突）。
   - 初始导出 8 大专家子代理至 `.agents/agents/`。
7. **架构师深度鉴定、能力拓展与 PM 终态验收**：
   - PM 严经理通过 `invoke_subagent` 派发任务至 **钱架构 (`@flow-architect`)**；
   - 钱架构领单置为【进行中】，通读源码入口与依赖，编写 `docs/D02-架构设计/01-系统总体架构与技术栈选型.md`；
   - 钱架构调用 `python3 scripts/save_project_architecture.py` 安全落盘，自动派生 6 大技术角色 3~5 项专属能力并刷新导出；
   - 钱架构提交【已完成】，PM 严经理验收置为【已验收】，并在回复顶部输出标志行与官方查证凭据：
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

