# Multi-Agent Team Workflow (多专家协同研发工作流 · YY-Flow)

<p align="center">
  <a href="https://yuanyii.github.io/multi-agent-flow/"><img src="https://img.shields.io/badge/🌐_Official_Site-Live_Demo-7C6CF0?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Official Website"></a>
  <a href="https://github.com/YuanYii/multi-agent-flow"><img src="https://img.shields.io/github/stars/YuanYii/multi-agent-flow?style=for-the-badge&logo=github&color=38BDF8" alt="GitHub Stars"></a>
  <a href="https://github.com/YuanYii/multi-agent-flow/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-10B981?style=for-the-badge" alt="License"></a>
  <a href="https://yuanyii.github.io/multi-agent-flow/"><img src="https://img.shields.io/badge/Theme-Dark%20%2F%20Light-F59E0B?style=for-the-badge" alt="Theme Support"></a>
  <a href="https://github.com/YuanYii/multi-agent-flow/actions/workflows/tests.yml"><img src="https://github.com/YuanYii/multi-agent-flow/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
</p>

<p align="center">
  <b><a href="https://yuanyii.github.io/multi-agent-flow/">👉 点击访问官方互动主页 &amp; 在线看板全景演示 (GitHub Pages) 👈</a></b>
</p>

> **“不要让 CV 工程师变成 YES 工程师”** —— 契约驱动的 AI 多角色协同研发工作流技能包。以十大 Agent 协同红线与五层防错门控实现 8 位 AI 专家的严密交叉制衡；同时提供局域网多端看板、主控鉴权与独立视图，赋能人类团队高效协作。

---

## 🌟 核心特性概览

- 👥 **8 位专属 AI 专家矩阵**：严经理 (PM)、钱架构 (架构师)、李开发 (后端)、马前端 (前端)、周审查 (审查员)、章测试 (测试)、李文通 (文档)、吕改特 (运维)，开箱自动扫描项目技术栈并自适应注入。
- 🛡️ **十大协同红线与五层防错门禁**：代码级 Fail-Closed 拦截越权操作；阶段开工核验清洁度，阶段结项强制输出架构技术总结（ADR）与敏捷复盘总结；工作区存在未验收代码时物理阻断 `git commit`。
- 🎯 **统一入口网关与 L0–L2 智能分流**：控制台指令直通底层运维，业务需求经分级三问网关前置判定（L0即时问答直出、L1短链交付、L2全流程制衡）；全自动流水线支持 A–G 全类型链断点续跑。
- 🔌 **项目级强关联与多 Agent 终端适配**：数据完全私有落盘于 `.yy-flow/` 目录随 Git 流转，原生兼容 Google Antigravity、Claude Code、Cursor、OpenAI Codex 及阿里千问办公等主流终端。

👉 **完整特性演示与交互体验请访问**：[https://yuanyii.github.io/multi-agent-flow/](https://yuanyii.github.io/multi-agent-flow/)

---

## 🚀 快速开始

### 1. 一行命令安装到项目

```bash
cd /path/to/your-project

# 方式 A: npx degit 安装（推荐）
npx -y degit YuanYii/multi-agent-flow /tmp/yy-flow-stage && mkdir -p .yy-flow && mv /tmp/yy-flow-stage .yy-flow/skill

# 方式 B: tarball 脚本安装（免 Node 环境）
mkdir -p .yy-flow/skill && curl -L https://github.com/YuanYii/multi-agent-flow/archive/refs/heads/main.tar.gz | tar xz -C .yy-flow/skill --strip-components=1

# 方式 C: Windows PowerShell 安装
git clone https://github.com/YuanYii/multi-agent-flow.git .yy-flow\skill
powershell -ExecutionPolicy Bypass -File .yy-flow\skill\scripts\init_skill.ps1
```

> 💡 **依赖说明**：核心引擎优先使用 Python 标准库实现，运行时仅依赖 PyYAML 与 python-docx 两项：`python3 -m pip install -r requirements.txt`（本地跑测试再加装 `requirements-dev.txt`）。`init_skill.sh` 已内置依赖自检，检测到缺失时会尽力自动补装。

### 2. 在 Agent 对话中初始化

在 AI 编程终端中输入快捷指令或自然语言口令：
> 💬 `/yy-flow start` 或 *“帮我初始化这个项目的研发流”*

### 3. 多项目共享安装（全局部署）

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

> 在项目内首次使用请执行该项目的初始化（`/yy-flow start`）。

---

## ⚡ 快捷指令与自然语言口令

| 快捷指令 | 自然语言口令示例 | 核心功能 |
| :--- | :--- | :--- |
| **`/yy-flow help`** | “查看工作流使用帮助” 或 “yy-flow有哪些命令” | 查看全景指令帮助手册、8 大专家职责与协同流转规范 |
| **`/yy-flow start`** | “帮我初始化这个项目的研发流” | 执行 7 步标准初始化：凭据扫描、架构嗅探、专家注入与 PM 编排 |
| **`/yy-flow status`** | “看下项目进度与巡检大盘” | 一键输出项目总体进度、Lead Time 交付周期与风险告警 |
| **`/yy-flow kanban`** | “启动看板” 或 “打开协作大盘” | 启动本地/局域网可视化看板（默认 32886 端口），输出主控与协作链接 |
| **`/yy-flow sync-pr`** | “检查 PR 状态解阻任务” | 监听 GitHub PR Merged 状态，自动推进至【已完成】并提请验收 |
| **`/yy-flow auto`** | “把任务 T0001 全自动跑完” | 全自动执行完整生命周期至【已完成】并提请人类核验验收 |

> 💡 **日常协同全走自然语言**：需求拆解、阶段结项、认领、提审、测试打回等均可直接自然语言沟通，专家在后台自主调度底层脚本。

---

## 📊 可视化看板

```bash
# 启动本地/局域网实时看板服务
python3 scripts/start_kanban_server.py
```
> 控制台将自动输出本地直达链接（`http://127.0.0.1:32886/`）、局域网协作链接与 🔑 Master Token。

内置 **数据表格**、**状态泳道**、**专家负载**、**阶段工作包** 4 套视图，支持多终端独立偏好与离线/局域网双模。

[![Multi-Agent Flow 数据表格视图](https://fastly.jsdelivr.net/gh/YuanYii/multi-agent-flow@main/kanban/screenshots/table-view.png)](https://yuanyii.github.io/multi-agent-flow/)

---

## 🔐 安全边界（Security Boundary）

- **本看板与 CLI 引擎面向个人 / 团队内网环境设计，请勿将服务端口直接暴露到公网**。看板默认绑定 `0.0.0.0` 并在控制台打印局域网协作链接；如需跨互联网协作，请自行置于 VPN 或反向代理 + 认证之后。
- **Master Token 是全权凭据**：启动时打印于控制台，持有者可对看板数据执行全部写操作（增删改、导入覆写、批量删除）。请勿粘贴到公开聊天、截图或代码仓库中；多端协同时仅分发给可信成员。
- **鉴权模型为单层主控制**：LAN 协作端默认只读视角，无用户级账号体系与细粒度 RBAC；浏览器本地保存的偏好相互隔离，但权限以「是否持 Token」唯一判定。
- **CORS 默认放开**以便局域网内多端访问，网络边界防护依赖部署环境（内网/防火墙）而非应用层。
- **合规自扫描**：`scripts/check_secrets.py` 在初始化时扫描技能包自身，不会读取或上传你的业务代码。

## 📁 目录架构说明

```text
.yy-flow/skill/              # 技能代码（只读资产）
├── SKILL.md                 # 技能主入口（快捷指令与编排协议）
├── README.md                # 产品说明文档
├── rules/                   # 协同红线与防错规约
├── agents/                  # 8 大专家角色 YAML 定义
├── kanban/                  # 离线与 Web 可视化看板（HTML/JS/CSS）
├── references/              # 6 大核心规范（路由/流转/防错/Git/文档/交接）
├── tests/                   # 349 项自动化测试套件
└── scripts/                 # 流转/门禁/巡检/看板服务 CLI 引擎

# 初始化后在目标项目生成：
.yy-flow/user_data/          # 运行态数据（board.json / 审计日志 / 并发锁）
docs/                        # D01-项目管理 ~ D06-文档模板 交付文档骨架
```

---

## 📖 参考规约索引

- [官方交互主页 & 在线演示](https://yuanyii.github.io/multi-agent-flow/)
- [技能主入口 SKILL.md](SKILL.md) — 指令契约、初始化 SOP 与动态流转
- [AI 团队协同索引](references/01-AI-Team-Workflow-Index.md) — 8 大角色职责矩阵与流转总表
- [状态流转与打回规范](references/02-State-Flow-Rules.md) — 8 状态定义与 A–G 任务类型链
- [五层防错门控机制](references/03-Anti-Error-Mechanism.md) — 越权拦截与代行授权协议

---

## License

MIT
