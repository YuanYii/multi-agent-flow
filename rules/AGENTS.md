# AGENTS.md - 多专家团队协同研发工作区

欢迎来到 **多专家协同研发工作流 (Multi-Agent Team Workflow · YY-Flow)** 工作区。本文档定义了 AI Agent 在多角色研发环境下的交互契约与协作红线。

---

## 快捷指令响应契约 (/yy-flow)

当收到以 `/yy-flow` 开头的用户指令时，Agent 必须直接触发对应的确定性动作：
- `/yy-flow` 或 `/yy-flow start` -> 立即执行初始化 7 步 SOP 并拉起 PM 严经理；
- `/yy-flow status` -> 运行 `heartbeat.py` 巡检脚本并格式化输出在手任务与告警；
- `/yy-flow kanban` -> 后台启动 `start_kanban_server.py`（默认不带 `--port`，自动探测/复用），并以脚本输出的实际端口在回复中展示访问链接；
- `/yy-flow metrics` -> 运行 `metrics_analyzer.py` 并呈现效能报告。

---

## 动态按需加载协议 (Lazy Load Protocol)

执行协同任务或推导状态流转时，**必须按需调阅 `../references/` 中的规范文件**：
1. **角色边界**：调阅 [`../references/01-AI-Team-Workflow-Index.md`](../references/01-AI-Team-Workflow-Index.md)
2. **状态流转矩阵**：调阅 [`../references/02-State-Flow-Rules.md`](../references/02-State-Flow-Rules.md)
3. **防错闭环与提权门控**：调阅 [`../references/03-Anti-Error-Mechanism.md`](../references/03-Anti-Error-Mechanism.md)
4. **Git 与版本规范**：调阅 [`../references/04-Git-Workflow-Spec.md`](../references/04-Git-Workflow-Spec.md)
5. **文档结构与元数据规范**：调阅 [`../references/05-Document-Management-Spec.md`](../references/05-Document-Management-Spec.md)
6. **交接契约与消息总线载荷**：调阅 [`../references/06-Inter-Agent-Handover-Protocol.md`](../references/06-Inter-Agent-Handover-Protocol.md)

---

## 看板状态不变量

- **原子更新**：看板 `状态` (Status) 与 `处理人` (Assignee) 必须同步变更。
- **结束时间**：任务推至 `已完成` / `已验收` 前强制写入 `结束时间`。

---

## 团队协作 6 大红线 (Red Lines)

1. **绝对禁止越权修改状态**：不在操作人集合内的角色禁止推动状态（提权需显式声明代行协议）。
2. **打回绝对禁止新建任务编号**：任何审查/测试退回必须在**原任务**上改状态为 `已退回`，并在备注写入 `DEF-TXXX-N`。
3. **绝对禁止先干后补**：自领取任务时，必须先将看板状态修改为 `进行中` 并落库，方可开始编码。
4. **绝对禁止生成孤儿复审/复测报告**：退回修复后的结论必须追加至原报告，不新建碎片文档。
5. **绝对禁止无元数据乱建深层文档与擅改原文档**：工程文档路径深度不得超过 3 级，所有 `.md` 强校验 YAML Frontmatter 标头，过程草稿统一入 `.drafts/` 隔离；初始化归档原项目历史文档时采用**只读镜像拷贝**，绝对禁止修改、覆盖或删除原项目源文档中的任何内容。
6. **Subagent 官方标准路径实时查证原则**：初始化或挂载 Subagent 时，必须查证当前 Agent 官方最新文档，获取其原生识别子代理的物理路径与 YAML 标头规范（如 Antigravity 的 `{workspace}/.agents/agents/{name}/agent.md`），严禁凭猜测写入异构不合规路径。

---

## 极简特权通道（Fast-Track）协议

并非所有任务都需要完整的 SDLC（软件生命周期）。系统启用极简通道机制：
1. **触发标识**：任何标题前缀为 `[HOTFIX]`、`[DOCS]` 或打上 `ASS`（极简任务）标签的任务。
2. **免检放行**：此类任务属于文档勘误、纯配置修改或紧急非代码操作。协调者（PM）分配执行后，无需经过 Reviewer 审查和 QA 测试，执行方完成后可直接将状态流转为 `已完成/已验收`。
3. **红线拦截**：绝不允许任何涉及业务代码逻辑（`.py`, `.java`, `.ts` 等核心源码）的修改挂载此标签。一旦发现越权，协调者应立即阻断并剥夺其极简标签。

---

## 分派即建单协议 (Dispatch-on-Create)

> 核心原则：**看板任务卡是唯一事实来源，任何任务必须先有卡，再被执行。**

1. **建卡前置**：主代理（或任一角色）在分派任务 / 唤起子代理之前，必须先调用建单命令创建任务卡【待开始】并获取 Task ID：
   ```bash
   python3 scripts/quick_task.py create --name "<任务名称>" --role PM --assignee <处理人>
   ```
2. **Task ID 注入**：子代理 Prompt 顶部必须强制注入工单元数据标头：`【任务卡】Task ID: T000x | 状态: 待开始 | 处理人: <处理人>`
3. **开工流转**：任务开始执行时先执行 CLI 将状态推至【进行中】。
4. **完工硬门禁**：任何代码/文档/审查/测试产出完成后，最后一步必须执行流转 CLI 推进状态（A 类推至【审查中】，B/C/D/G 类推至【已完成】），否则视为未交付。
5. **防重复建单**：建卡前若看板最近 N 条任务存在名称重复，命令将终止并输出 `DUPLICATE_TASK` 候选；需用户确认后以 `--force` 重跑。
6. **任务卡必经【待开始】**：不允许直接创建为【进行中】或更高状态。
