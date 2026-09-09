# Multi-Agent Team Workflow (多专家协同研发工作流 · YY-Flow)

<p align="center">
  <a href="https://yuanyii.github.io/multi-agent-flow/"><img src="https://img.shields.io/badge/Official_Site-Live_Demo-7C6CF0?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Official Website"></a>
  <a href="https://github.com/YuanYii/multi-agent-flow"><img src="https://img.shields.io/github/stars/YuanYii/multi-agent-flow?style=for-the-badge&logo=github&color=38BDF8" alt="GitHub Stars"></a>
  <a href="https://github.com/YuanYii/multi-agent-flow/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-10B981?style=for-the-badge" alt="License"></a>
  <a href="https://yuanyii.github.io/multi-agent-flow/"><img src="https://img.shields.io/badge/Theme-Dark%20%2F%20Light-F59E0B?style=for-the-badge" alt="Theme Support"></a>
  <a href="https://github.com/YuanYii/multi-agent-flow/actions/workflows/tests.yml"><img src="https://img.shields.io/badge/Tests-396%20Passed-10B981?style=for-the-badge" alt="Tests"></a>
  <a href="https://github.com/YuanYii/multi-agent-flow"><img src="https://img.shields.io/badge/Version-v2.2.0-8B5CF6?style=for-the-badge" alt="Version"></a>
</p>

<p align="center">
  <b><a href="https://yuanyii.github.io/multi-agent-flow/">点击访问官方互动主页 &amp; 在线看板全景演示 (GitHub Pages)</a></b>
</p>

> **“不要让 CV 工程师变成 YES 工程师”** —— 契约驱动的 AI 多角色协同研发微内核技能包。以十大 Agent 协同红线与五层防错门控实现 8 位 AI 专家的严密交叉制衡；同时提供局域网多端看板、主控鉴权与独立视图，赋能人类团队高效协作。

---

## 核心特性概览

- **8 位专属 AI 专家矩阵**：严经理 (PM)、钱架构 (架构师)、李开发 (后端)、马前端 (前端)、周审查 (审查员)、章测试 (测试)、李文通 (文档)、吕改特 (运维)，开箱自动扫描项目技术栈并自适应注入。
- **十大协同红线与五层防错门禁**：代码级 Fail-Closed 拦截越权操作；阶段开工核验清洁度，阶段结项强制输出架构技术总结（ADR）与敏捷复盘总结；工作区存在未验收代码时物理阻断 `git commit`。
- **统一入口网关与 L0–L2 智能分流**：控制台指令直通底层运维，业务需求经分级三问网关前置判定（L0即时问答直出、L1短链交付、L2全流程制衡）；强制执行单一职责（SRP）审查（工时 ≤ 8.0h）。
- **项目级强关联与多 Agent 终端适配**：数据私有落盘于 `.yy-flow/` 目录随 Git 流转，原生兼容 Google Antigravity、Claude Code、Cursor、OpenAI Codex、OpenCode、ZCode 等主流终端与 IDE。
- **396 项自动化测试全绿保障**：微内核调度、状态转移、多周分片存储、高熵令牌鉴权与并发锁具备严密的自动化测试覆盖（396 项测试用例经查验符合预期）。

**完整特性演示与交互体验请访问**：[https://yuanyii.github.io/multi-agent-flow/](https://yuanyii.github.io/multi-agent-flow/)

---

## 全景架构与执行链路全息图鉴

本项目现已提供开箱即用的离线原生可视化全景图鉴：

- **图鉴文件**：[`docs/0-系统架构/multi-agent-flow-全景架构与执行链路图鉴.html`](../docs/0-系统架构/multi-agent-flow-全景架构与执行链路图鉴.html)
- **技术亮点**：
  - **八层微内核架构拓扑**：网关入口、调度编排、状态机内核、存储适配、安全门禁、上下文连续性协议 (CCP)、Web 看板与度量巡检 8 大业务域；
  - **端到端 10 阶段研发时序**：从自然语言需求、PM 分级建卡、专家派发、物理隔离编码到单测提审、打回熔断、终态验收与 Git 结项；
  - **代码物理行号 Hover 浮窗**：鼠标悬停在任意架构节点或执行步骤上，即时展示其对应的物理源文件、行号区间（`Lxx-Lxx`）与核心类/函数符号，支持点击锁定检查；
  - **现代扁平化矢量设计**：内嵌 28 个纯矢量 SVG 图标（0 拟物/0 Emoji），默认优雅高对比度亮色背景，支持深浅主题持久化切换，0 外部网络与 CDN 依赖。

---

## 快速开始 (Quick Start)

无论使用哪种 AI 环境，均支持**在 AI 对话框中直接输入自然语言三步完成挂载与启动**：

### 三步极简流水线

#### STEP 1 · 自然语言安装技能包 (全平台通用)
在 AI 对话框中直接发送：
```text
帮我安装skill https://github.com/YuanYii/multi-agent-flow
```
> **全自动挂载**：自动导入 8 位专属 AI 专家角色，适配 Claude Code、Antigravity、Cursor、Codex 等主流环境。

#### STEP 2 · 架构扫描与初始化
在 AI 对话框中发送初始化口令：
```text
初始化yy-flow
```
> **智能适配**：自动嗅探当前项目依赖（FastAPI / Spring / Vue / Go 等）并注入技术栈专属能力。

#### STEP 3 · 研发协同与生效机制 (按环境分流)
- **模式 1：CLI 终端 Agent** *(Claude Code / Codex / OpenCode / ZCode 等)*  
  首次安装需**重启一次 CLI 进程**完成专家拓扑挂载，随后支持斜杠指令（如 `/yy-flow help`）或自然语言直接对话推进。
- **模式 2：桌面端 IDE Agent** *(Cursor / Windsurf / AutoClaw / WorkBuddy 等)*  
  **免重启**，工作区文件热重载直接生效，在聊天框发送 `使用yy-flow 帮我开始做这个需求并拆解任务` 即可即刻开始敏捷研发。

---

### 两种使用模式对比

| 交互维度 | 模式 1：CLI 终端 Agent *(Claude Code / Codex 等)* | 模式 2：桌面端 IDE Agent *(Cursor / Windsurf 等)* |
| :--- | :--- | :--- |
| **安装方式** | 对话输入：`帮我安装skill https://github.com/YuanYii/multi-agent-flow` | 对话输入：`帮我安装skill https://github.com/YuanYii/multi-agent-flow` |
| **初始化口令** | 对话输入：`初始化yy-flow` *(未生效前统一使用纯自然语言)* | 对话输入：`初始化yy-flow` *(未生效前统一使用纯自然语言)* |
| **生效方式** | 首次安装需**重启一次 CLI 进程**加载专家拓扑 | **免重启**，工作区热重载直接生效 |
| **日常协同** | **双通道**：斜杠指令 (`/yy-flow status`) 或 自然语言 | **纯自然语言驱动**：直接在对话框沟通推进研发流 |

---

### 命令行脚本安装备选（针对无自然语言安装能力的终端）

```bash
cd /path/to/your-project

# 方式 A: npx degit 安装（推荐）
npx -y degit YuanYii/multi-agent-flow /tmp/yy-flow-stage && mkdir -p .yy-flow && mv /tmp/yy-flow-stage .yy-flow/skill

# 方式 B: tarball 脚本安装（免 Node 环境）
mkdir -p .yy-flow/skill && curl -L https://github.com/YuanYii/multi-agent-flow/archive/refs/heads/main.tar.gz | tar xz -C .yy-flow/skill --strip-components=1
```

> **依赖说明**：核心引擎优先使用 Python 标准库实现，运行时仅依赖 PyYAML 与 python-docx 两项：`python3 -m pip install -r requirements.txt`（本地跑测试再加装 `requirements-dev.txt`）。`init_skill.sh` 已内置依赖自检，检测到缺失时会尽力自动补装。

### 多项目共享安装（全局部署）

在同时维护多个项目、不希望每个项目都复制一份 Skill 代码时，使用全局共享安装器（Linux/macOS: `install_global.sh`，Windows: `install_global.ps1`）：

```bash
# Linux/macOS：安装/更新最新版本（或指定分支/标签）
./scripts/install_global.sh            # 默认最新版本
./scripts/install_global.sh v1.0.0     # 固定版本
```

- **正本位置**：代码物化至 `~/agent-skills/multi-agent-flow`（degit 拉取，无 Node 环境自动回退 tarball），只读共享；
- **安全守卫**：正本目录若被污染（含 `user_data/board.json`）直接拒绝安装，防止 legacy 数据误判串项目；安装后写入 `.yy-flow-shared` 共享标记；
- **跨平台挂载**：`verify_and_export_agents.py --global` 自动探测 8 大主流宿主（Antigravity / Claude Code / Cursor / OpenCode / ZCode / Pi / Universal / Codex）并挂载用户级技能与子代理；
- **数据隔离**：共享安装下每个项目的运行数据（`user_data/`、锁、审计）仍独立落在各自项目根（解析链：`--project-root` > `YY_FLOW_PROJECT_ROOT` > `.yy-flow` 自定位 > legacy > CWD），`docs/` 恒定锚定项目根随 Git 流转。

> 在项目内首次使用请执行该项目的初始化（对话输入 `初始化yy-flow`）。

---

## 统一 CLI 门面与快捷指令

系统已收敛至统一 CLI 门面（`python3 scripts/cli.py`），对齐统一参数命名与调用体验：

| 业务场景 | 统一 CLI 门面 (`cli.py`) | 底层专用脚本 | 核心作用与参数 |
| :--- | :--- | :--- | :--- |
| **创建任务卡** | `python3 scripts/cli.py task create ...` | `scripts/quick_task.py create` | `--name "..." --assignee "..." --stage "..." --type "A" --target "..." --criteria "..."` |
| **代码化派单** | `python3 scripts/cli.py dispatch --task-id T00xx` | `scripts/dispatch_task.py` | 校验依赖与并发，推至【进行中】，输出 Subagent 载荷 |
| **推进任务流转** | `python3 scripts/cli.py task start/finish ...` | `scripts/transition_task.py` | 结合角色与五层门控执行推进，支持 `--remarks` 打回记录 |
| **人类终态验收** | `python3 scripts/cli.py task accept ...` | `scripts/quick_task.py accept` | `--task-id T00xx`（**人类用户专属**，严禁 Agent 越权自签） |
| **启动看板** | `python3 scripts/cli.py kanban` | `scripts/start_kanban_server.py` | 默认启动于 `http://127.0.0.1:32886/`，打印安全 Token |
| **健康度巡检** | `python3 scripts/cli.py status` | `scripts/heartbeat.py` | 输出大盘健康度、阻塞卡片与效能统计指标 |
| **连续性校验** | `python3 scripts/cli.py ccp ...` | `scripts/cli.py ccp` | 校验 Agent 上下文交接完整性与前置依赖产物 |

### 快捷指令映射总览

| 快捷指令 | 自然语言口令示例 | 核心功能 |
| :--- | :--- | :--- |
| **`/yy-flow help`** | “查看工作流使用帮助” 或 “yy-flow有哪些命令” | 查看全景指令帮助手册、8 大专家职责与协同流转规范 |
| **`/yy-flow start`** | “初始化yy-flow” 或 “帮我初始化这个项目的研发流” | 执行 7 步标准初始化：凭据扫描、架构嗅探、专家注入与 PM 编排 |
| **`/yy-flow status`** | “看下项目进度与巡检大盘” | 一键输出项目总体进度、Lead Time 交付周期与风险告警 |
| **`/yy-flow kanban`** | “使用yy-flow，启动看板” 或 “启动看板” | 启动本地/局域网可视化看板（默认 32886 端口），输出主控与协作链接 |
| **`/yy-flow sync-pr`** | “检查 PR 状态解阻任务” | 监听 GitHub PR Merged 状态，自动推进至【已完成】并提请验收 |
| **`/yy-flow auto`** | “使用yy-flow 帮我开始做这个需求并拆解任务” | 自动执行完整生命周期至【已完成】并提请人类核验验收 |

> **日常协同全走自然语言**：需求拆解、阶段结项、认领、提审、测试打回等均可直接自然语言沟通，专家在后台自主调度底层脚本。

---

## 可视化看板

```bash
# 启动本地/局域网实时看板服务
python3 scripts/start_kanban_server.py
```
> 控制台将自动输出本地直达链接（`http://127.0.0.1:32886/`）、局域网协作链接与 Master Token。

内置 **数据表格**、**状态泳道**、**专家负载**、**阶段工作包** 4 套视图，支持多终端独立偏好与离线/局域网双模。

[![Multi-Agent Flow 数据表格视图](https://fastly.jsdelivr.net/gh/YuanYii/multi-agent-flow@main/kanban/screenshots/table-view.png)](https://yuanyii.github.io/multi-agent-flow/)

---

## 安全边界（Security Boundary）

- **本看板与 CLI 引擎面向个人 / 团队内网环境设计，请勿将服务端口直接暴露到公网**。看板默认绑定 `0.0.0.0` 并在控制台打印局域网协作链接；如需跨互联网协作，请自行置于 VPN 或反向代理 + 认证之后。
- **Master Token 是全权凭据**：启动时打印于控制台，持有者可对看板数据执行全部写操作（增删改、导入覆写、批量删除）。请勿粘贴到公开聊天、截图或代码仓库中；多端协同时仅分发给可信成员。
- **鉴权模型为单层主控制**：LAN 协作端默认只读视角，无用户级账号体系与细粒度 RBAC；浏览器本地保存的偏好相互隔离，但权限以「是否持 Token」唯一判定。
- **CORS 默认放开**以便局域网内多端访问，网络边界防护依赖部署环境（内网/防火墙）而非应用层。
- **合规自扫描**：`scripts/check_secrets.py` 在初始化时扫描技能包自身，不会读取或上传你的业务代码。

## 目录架构说明

```text
.yy-flow/skill/              # 技能代码（只读资产）
├── SKILL.md                 # 技能主入口（统一网关、快捷指令与编排协议）
├── README.md                # 产品说明与架构全景文档
├── rules/                   # 协同红线与防错规约
├── agents/                  # 8 大专家角色 YAML 定义
├── kanban/                  # 离线与 Web 可视化看板（HTML/JS/CSS）
├── references/              # 模块化规约体系
│   ├── 01-gateway/          # 网关分流与单一职责审查规约
│   ├── 02-bootstrap/        # 冷启动与环境初始化 SOP
│   ├── 03-engine/           # 状态转移机、防错门禁与熔断仲裁
│   ├── 04-ccp/              # 上下文连续性协议 (CCP) 规范
│   ├── 05-kanban/           # 看板服务运维与 PR 监听规范
│   └── 06-governance/       # Git 提交阻断门禁与审计度量
├── tests/                   # 396 项自动化测试套件 (实测全量通过)
└── scripts/                 # 流转/门禁/巡检/看板服务 CLI 引擎

# 初始化后在目标项目生成：
.yy-flow/user_data/          # 运行态数据（board.json / weekly 分片 / 审计日志 / 并发锁）
docs/                        # 交付文档骨架
└── 0-系统架构/
    └── multi-agent-flow-全景架构与执行链路图鉴.html # 离线全息架构与链路图鉴
```

---

## 模块化规约索引

- [官方交互主页 & 在线演示](https://yuanyii.github.io/multi-agent-flow/)
- [全景架构与执行链路图鉴 (本地打开)](../docs/0-系统架构/multi-agent-flow-全景架构与执行链路图鉴.html)
- [技能主入口 SKILL.md](SKILL.md) — 统一网关、分级三问、指令契约与角色矩阵
- [网关分级规约](references/01-gateway/01-task_classification.md) — 业务需求 L0–L2 判决与单一职责审查
- [初始化 SOP 规约](references/02-bootstrap/01-initialization_sop.md) — 冷启动自检与架构自适应
- [状态流转与门控规约](references/03-engine/01-state_flow_rules.md) — 8 状态转移、五层立体防错与连续 3 次打回熔断
- [上下文连续性协议规约](references/04-ccp/01-ccp_protocol_spec.md) — 跨 Agent 无损 Handoff 契约
- [看板与 PR 同步规约](references/05-kanban/01-kanban_and_pr_sync.md) — 多端协同与 PR 监听解阻
- [Git 门禁与审计度量规约](references/06-governance/01-git_and_audit_spec.md) — 无工单不 Git 拦截与交付度量

---

## License

MIT
