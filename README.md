# Multi-Agent Team Workflow (多专家协同研发工作流 · YY-Flow)

> 契约驱动的 AI 多角色协同研发工作流技能包 —— 将项目管理、架构、开发、前端、审查、测试、文档、运维拆分为 8 大专家角色，以五层防错门控、阶段准出核验与现代可视化看板，彻底消除跨角色越权、打回碎片化与状态悬挂。

---

## 🌟 核心产品特性

- 👥 **8 大虚拟专家协同**：内置 PM（严经理）、架构师（钱架构）、后端开发（李开发）、前端开发（马前端）、审查员（周审查）、测试工程师（章测试）、文档工程师（李文通）、运维管理员（吕改特），各司其职、严守红线。
- 🎯 **L0/L1/L2 任务分级体系**：派单前执行“分级三问”，L0 即时问答无卡直答（免建卡且不产生冗余），L1 轻量任务走短链快速交付验收，L2 核心代码走开发-审查-测试全流程。
- 🚪 **阶段结项门禁核验 (Stage Gate)**：提供确定性阶段准出核验（`check_stage_gate.py`），自动断言看板全验收、WBS 双向对账、架构技术总结与 PM 复盘报告，条件不满足坚决阻断结项。
- 📊 **现代交互看板与偏好持久化**：支持纯静态离线与本地 Web 服务双模（默认 32886 端口），支持筛选/排序条件持久化保持、卡片字段按需展示、右上角主题切换与按 Tab 智能工具栏联动。
- 🛡️ **五层防错门控与并发安全**：状态与处理人原子绑定、代码层越权硬拦截（Fail-Closed）、打回不拆单（在原卡追加 `DEF-TXXX-N` 缺陷）、过程报告原位追加防孤儿、全局排他锁并发防重号。

---

## ⚡ 常用快捷指令

| 快捷指令 | 功能描述 |
| :--- | :--- |
| **`/yy-flow`** 或 **`/yy-flow start`** | **一键激活工作流**：执行 7 步标准初始化并唤起 PM 严经理进行项目鉴定与编排 |
| **`/yy-flow gate [stage]`** | **阶段结项门禁核验**：执行阶段准出 4 项硬核验（看板全验收、WBS 对账、总结报告） |
| **`/yy-flow status`** | **看板与卡顿巡检**：运行心跳检查，输出在手任务、超时滞留与并发告警 |
| **`/yy-flow kanban`** | **启动看板 Web 服务**：本地启动可视化看板服务并输出实际访问链接 |
| **`/yy-flow metrics`** | **效能度量报告**：一键计算交付周期 (Lead Time)、吞吐量与卡点分析 |
| **`/yy-flow create`** | **标准建卡**：创建任务卡【待开始】并分配处理人 |
| **`/yy-flow auto`** | **自动化单任务**：一条指令全自动执行任务生命周期直至已验收 |

---

## 🚀 快速开始（Agent 初始化）

**前置要求**：任一支持 Markdown/Skill 规范的 AI Agent（Antigravity CLI / Codex / Claude Code / Cursor 等）；离线看板模式**无需任何外部依赖或 Token 凭证**。

### 1. 安装技能包到项目 `.yy-flow/skill`

```bash
cd /path/to/your-project

# 方式 A: degit 安装（推荐，Linux / macOS / Windows）
npx -y degit YuanYii/multi-agent-flow /tmp/yy-flow-stage && mkdir -p .yy-flow && mv /tmp/yy-flow-stage .yy-flow/skill

# 方式 B: tarball 安装（无 Node 环境时，Linux / macOS）
mkdir -p .yy-flow/skill && curl -L https://github.com/YuanYii/multi-agent-flow/archive/refs/heads/main.tar.gz | tar xz -C .yy-flow/skill --strip-components=1

# 方式 C: Windows PowerShell 安装
git clone https://github.com/YuanYii/multi-agent-flow.git .yy-flow\skill
powershell -ExecutionPolicy Bypass -File .yy-flow\skill\scripts\init_skill.ps1
```

安装后目录布局（数据与技能同根，升级删 `.yy-flow/skill` 重装不伤数据；`docs/` 是项目交付物留项目根）：
```text
<project>/
├── .yy-flow/            # 工具私有根（建议整体加入 .gitignore）
│   ├── skill/           # 技能代码
│   └── user_data/       # 初始化后生成：board/审计/锁
└── docs/                # 项目工程文档骨架（交付物，提交 git）
```

<details>
<summary><b>多项目共享安装（可选，单份只读正本 + 全局软链）</b></summary>

```bash
# Linux / macOS 一次性全局共享安装：
bash scripts/install_global.sh

# Windows PowerShell 一次性全局共享安装：
powershell -ExecutionPolicy Bypass -File .\scripts\install_global.ps1
```
- **代码共享**：`~/agent-skills/multi-agent-flow` 正本只读；
- **数据隔离**：每个项目的 `user_data/` 自动锚定各自项目根。

</details>

### 2. 在 Agent 对话中触发初始化

输入指令：**`/yy-flow`** 或 **`/yy-flow start`**（或直接说：“*使用 multi-agent-flow 初始化当前项目*”）。

Agent 将自动执行 7 步标准初始化：
1. 敏感凭据安全扫描（`check_secrets.py`）；
2. 导出 8 大专家子代理至 `.agents/agents/`；
3. 扫描项目技术架构识别语言与框架；
4. 生成宿主专属 `user_data/`（看板、工作流配置与审计日志）；
5. 建立 `docs/` 规范目录骨架并镜像归档历史文档；
6. 同步专家团队技术栈；
7. 唤起 PM 严经理输出项目定位与权限矩阵。

---

## 📋 任务流转示例

| 场景 | 示例 Prompt | 预期行为 |
| :--- | :--- | :--- |
| **L0 即时问答** | “解释一下项目架构” / “查找接口契约” | 分级三问判定为 L0 → 直接作答，免建卡且不调用 CLI |
| **L1 轻量任务** | “更新部署说明文档” / “调整数据库配置” | 走短链（B/C/D/F/G）：【待开始】→【进行中】→【已完成】→ PM【已验收】 |
| **L2 标准任务** | “实现用户登录接口与 JWT 鉴权” | 走全链（A 类）：【待开始】→【进行中】→【审查中】→【测试中】→【已完成】→【已验收】 |
| **自领取任务** | “自领取下一个待开始任务” | 核验并发上限（≤3）→ 状态先推【进行中】落库 → 开始编码 |
| **提交审查** | “提交 T0001 代码审查” | 状态推【审查中】，处理人原子移交 Reviewer 周审查 |
| **审查与测试** | “审查 T0001” | 通过→【测试中】/【已完成】；不通过→【已退回】回原责任人，备注写入 `DEF-T0001-1` |
| **阶段结项** | “结束当前阶段 S1” / `/yy-flow gate S1` | 自动运行 `check_stage_gate.py` 进行 4 项硬核验，全绿后触发 DevOps 合流打 Tag |

---

## 🚀 本地可视化看板启动

无需安装任何第三方库或 Node 依赖，一行命令启动本地实时可视化看板：

```bash
# Linux / macOS
./kanban/start.sh

# Windows PowerShell
.\kanban\start.ps1

# Windows CMD
.\kanban\start.bat

# 或直接运行 Python 核心脚本（全平台通用）
python scripts/start_kanban_server.py
```
启动后在浏览器打开控制台输出的本地 Web URL（默认 `http://127.0.0.1:32886/`）即可。

---

## 🖥️ 看板界面预览

看板内置四套视图，同一份数据自由切换（以下为本地 Web 服务实时界面截图，截至 2026-08-18）：

**数据表格视图** —— 任务明细列表，支持筛选、排序、搜索、批量删除与 JSON 导入导出：

![数据表格视图](kanban/screenshots/table-view.png)

**看板-按状态视图** —— 按任务状态分组，卡片跨列拖拽即触发流转审计：

![看板-按状态视图](kanban/screenshots/kanban-status.png)

**看板-按负责人视图** —— 按专家角色查看各自任务负载：

![看板-按负责人视图](kanban/screenshots/kanban-assignee.png)

**看板-按阶段工作包视图** —— 按阶段工作包（S1–S6）查看任务分布：

![看板-按阶段工作包视图](kanban/screenshots/kanban-stage.png)

---

## 📁 目录架构说明

```text
.yy-flow/skill/              # 技能代码（只读资产）
├── SKILL.md                 # 技能主入口（快捷指令与编排协议）
├── README.md                # 产品说明文档
├── rules/                   # 协作红线与防错规约（AGENTS/IDENTITY/SOUL/TOOLS/USER/HEARTBEAT）
├── agents/                  # 8 大专家角色 YAML 定义
├── kanban/                  # 离线与 Web 可视化看板（HTML/JS/CSS）
├── config/                  # 工作流与架构配置模板
├── references/              # 6 大核心规范（路由/流转/防错/Git/文档/交接）
├── templates/               # 标准化报告与文档模板
├── tests/                   # 134 项自动化测试套件
└── scripts/                 # 初始化/流转/门禁/度量/看板服务 CLI 引擎

# 初始化后在目标项目生成：
.yy-flow/user_data/          # 运行态数据（看板数据 board.json / 审计日志 / 并发锁）
docs/                        # D01-项目管理 ~ D06-文档模板 六分类工程文档骨架
```

---

## 📖 参考规约索引

- [技能主入口 SKILL.md](SKILL.md) — 指令契约、初始化 SOP 与动态流转
- [AI 团队协同索引](references/01-AI-Team-Workflow-Index.md) — 8 大角色职责矩阵与流转总表
- [状态流转与打回规范](references/02-State-Flow-Rules.md) — 8 状态定义、A-G 任务类型与三问判定
- [五层防错门控机制](references/03-Anti-Error-Mechanism.md) — 越权拦截与代行授权协议
- [分支与版本发布规范](references/04-Git-Workflow-Spec.md) — 三层分支模型与 SemVer 标签
- [项目文档管理规范](references/05-Document-Management-Spec.md) — 目录骨架与元数据 Frontmatter 标准

---

## License

MIT
