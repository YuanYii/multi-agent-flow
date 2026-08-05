# Multi-Agent Team Workflow (多专家协同研发工作流)

> 契约驱动的多角色 Agent 协同研发技能包 —— 消除跨角色越权、打回碎片化与状态悬挂，让 AI 团队协作严丝合缝。

解耦、高可靠、具备防错闭环机制的 AI 多专家协同研发工作流技能包。基于成熟的软件工程实践，将项目管理、系统架构、代码开发、代码审查、功能测试、技术文档与 Git/运维整理解耦为 7 大标准职能角色，提供防错门控、打回不拆单、报告复验追加与看板自动化流转等能力。

---

## 快速使用

### 前置要求

- 任一 AI Agent：Antigravity CLI / Codex / Claude Code / Cursor / 或其他支持加载 Markdown 规范的 Agent
- (可选) 飞书 Base / Jira / GitHub Projects 看板凭证

### 安装

将本 Skill 包克隆或复制到项目或 AI Agent 技能目录下：

```bash
cd /path/to/your-project

# 克隆技能包到 skills 目录
git clone --depth 1 https://github.com/YuanYii/multi-agent-team-workflow.git skills/multi-agent-flow && rm -rf skills/multi-agent-flow/.git
```

### 项目初始化与架构识别

1. **技术架构自动识别**：当 Agent 初次在项目中调阅本 Skill 时，将自动扫描项目工程文件（如 `package.json`, `pyproject.toml`, `go.mod` 等），复制 [`config/project_architecture.template.yaml`](config/project_architecture.template.yaml) 生成并落库 `config/project_architecture.config.yaml`。
2. **专家团队技术栈自动同步**：运行 `python3 scripts/update_agent_tech_stacks.py`，将扫描到的技术栈自动同步落盘至 `agents/*.yaml` 配置文件，使开发、审查、测试专家角色与项目真实语言工具链高精对齐。
3. **看板配置初始化**：复制配置模板并使用适配器快速初始化：

```bash
cd skills/multi-agent-flow

# 复制看板配置模板
cp config/workflow.config.template.yaml config/workflow.config.yaml

# (可选) 自动扫描看板获取动态字段 ID
python3 scripts/init_field_mapping.py --base-token <YOUR_BASE_TOKEN> --table-id <YOUR_TABLE_ID>
```

### 🔌 连接在线数据看板的必要信息与凭证指南

在将 Agent 与线上数据看板建立连接时，需在 [`config/workflow.config.yaml`](config/workflow.config.template.yaml) 及系统环境变量中配置以下必备 API 鉴权与连接参数：

#### 1. 飞书多维表格 (Feishu Base) —— 推荐
- **配置文件参数** (`config/workflow.config.yaml`)：
  - `board.provider`: `"feishu_base"`
  - `board.base_token`: **Base Token**（多维表格浏览器 URL `https://feishu.cn/base/【Base_Token】?table=...` 中 `base/` 后方的字符串）
  - `board.table_id`: **Table ID**（多维表格 URL `...table=【tbl_ID】` 中 `table=` 后方的字符串）
- **系统环境变量凭证**（API 授权使用）：
  - `FEISHU_APP_ID`: 飞书开放平台自建应用的 App ID（示例：`cli_a1b2c3d4e5`）
  - `FEISHU_APP_SECRET`: 飞书开放平台自建应用的 App Secret 密钥

#### 2. Jira 看板
- **配置文件参数**：
  - `board.provider`: `"jira"`
  - `board.domain`: Jira 实例域名（示例：`https://your-domain.atlassian.net`）
  - `board.project_key`: 项目 Project Key（示例：`PROJ`）
- **系统环境变量凭证**：
  - `JIRA_USER_EMAIL`: Atlassian 账号邮箱
  - `JIRA_API_TOKEN`: Atlassian 账号后台生成的 API Token

#### 3. GitHub Projects (v2)
- **配置文件参数**：
  - `board.provider`: `"github_projects"`
  - `board.owner`: GitHub 组织名或用户名
  - `board.project_number`: Project 编号（示例：`1`）
- **系统环境变量凭证**：
  - `GITHUB_TOKEN`: 具备 `repo` 和 `project` 读写权限的 Personal Access Token (PAT)

---

### 任务流转与指令交互

在与 Agent 对话时，只需在 Prompt 中唤起 `multi-agent-flow` 技能标识，Agent 将自动调阅 `SKILL.md` 并动态加载 `rules/` 下的核心规则与防错契约：

#### 1. 开发人员自领取任务
> **“使用 multi-agent-flow，自领取下一个待开始任务”**

```text
→ Agent 自动核验并发上限 (≤3) 与领用顺序 (按编号从小到大)
→ 先将看板状态置为【进行中】，确认成功落库后再启动编码
```

#### 2. 开发完成提交审查
> **“使用 multi-agent-flow，提交 T0001 代码审查”**

```text
→ 自动撰写/更新开发任务报告 (按工作包归档)
→ 原子级更新看板状态为【审查中】，处理人移交【Reviewer】
```

#### 3. 审查与测试通过/打回
> **“使用 multi-agent-flow，审查 T0001”**

```text
→ 若审查通过：状态推至【测试中】，处理人移交【QA】
→ 若审查不通过：打回原任务，状态变【已退回】，处理人改回【原负责人】
  并在看板「备注」中结构化写入 DEF-T0001-1 缺陷信息（不派生新任务编号）
```

#### 4. 项目经理验收
> **“使用 multi-agent-flow，验收已完成任务”**

```text
→ 检查结束时间强校验，状态更新为【已验收】，末处理人保持【PM】
```

---

## 📜 核心契约与防错规则 (`rules/`)

技能包在 [`rules/`](rules/) 目录下内置了全套标准化交互契约与防错规则，在调用 Skill 时自动按需装载：

- 🚩 [`rules/AGENTS.md`](rules/AGENTS.md)：**多专家团队协作契约** —— 规定 4 大协作红线、看板状态不变量与动态按需加载协议。
- 🎭 [`rules/IDENTITY.md`](rules/IDENTITY.md)：**专家团多面人设与身份契约** —— 定义 PM、ARCHITECT、DEV、REVIEWER、QA、DOCS、DEVOPS 7 大专家身份及其提权代行规约。
- ⚡ [`rules/SOUL.md`](rules/SOUL.md)：**行为原则与防错控制心脏** —— 规定事实高于推论、原子更新、缺陷溯源不切碎等安全控制核心。
- 💓 [`rules/HEARTBEAT.md`](rules/HEARTBEAT.md)：**看板状态巡检与卡顿监控** —— 规定滞留任务、并发上限及状态处理人一致性等巡检 Checklist。
- 🛠️ [`rules/TOOLS.md`](rules/TOOLS.md)：**看板与工程工具链指引** —— 描述 `init_field_mapping.py`、`feishu_base_adapter.py` 等脚本说明。
- 🤝 [`rules/USER.md`](rules/USER.md)：**用户交互协议与协同契约** —— 规定自领取筛选规则、跨角色提权代行交互及打回确认流程。

---

## 为什么需要多专家协同规范？

在多 Agent 或 AI 与人类团队协同研发中，常见痛点：

- **乱越权改看板**：开发 Agent 自作主张把任务改成“已验收”，导致未经过测试的代码直接上产线。
- **打回派生孤儿任务**：代码审查不通过就新建 `T0103-fix` 等碎片任务，导致上下文断裂、历史不可追溯。
- **报告满天飞**：每次复审复测都新建《XXX_复审报告2.md》，文档严重离散。
- **状态与处理人不同步**：只改了状态为“审查中”，但处理人忘记改，导致下游角色看不到任务（任务悬挂）。

`multi-agent-flow` 将软件工程的严肃协同纪律融入 Agent 交互协议中 —— **不是限制 AI，而是确保 AI 团队协同严丝合缝**。

---

## 核心架构与 7 大抽象角色

每个节点由独立的专家角色（Role Agent）执行，详见角色路由表：
👉 [`references/01-AI-Team-Workflow-Index.md`](references/01-AI-Team-Workflow-Index.md)

- **PM**：WBS 维护、建单、终态验收、阶段总结
- **ARCHITECT**：系统架构设计、ADR、技术总结
- **DEV**：API/数据库编码、单测 (coverage>80%)、环境治理
- **REVIEWER**：代码规范、安全漏洞、性能与 Pydantic v2 核验
- **QA**：集成测试、端到端测试、缺陷回写 (带结束时间)
- **DOCS**：操作手册、API 帮助文档、技术总结
- **DEVOPS**：分支合并 (`feature → stage → main`)、SemVer 打 Tag

---

## 7 类任务生命周期 (A-G 分类流转模型)

全量 A-G 类任务流转链路图与退回规则详见：
👉 [`references/02-State-Flow-Rules.md`](references/02-State-Flow-Rules.md)

---

## 🛡️ 防错闭环机制 (§九 守护原则)

完整四层防错门控、拦截处理与提权代行逻辑详见：
👉 [`references/03-Anti-Error-Mechanism.md`](references/03-Anti-Error-Mechanism.md)

1. **状态与处理人原子绑定 (Atomic Update)**：修改状态必须同步修改处理人。
2. **打回不拆单原则 (Non-Fragmented Defect)**：打回一律在原任务上置为 `已退回` 并追加 `DEF-TXXX-N`。
3. **报告复验追加原则 (Appended Audit)**：复审/复测结论强制追加至原报告。
4. **四层防错门控 (Anti-Error Protocol)**：路径推导 ➔ 角色门控 ➔ 提权协议 ➔ 指令分派。

---

## 📋 目录结构与规范

```text
2_多专家协同研发工作流/
└── multi-agent-flow/                  # [技能核心包]
    ├── SKILL.md                       # 技能主入口指令与 Prompt
    ├── README.md                      # 本说明文档
    ├── rules/                         # [核心规则与契约]
    │   ├── AGENTS.md                  # [核心] 多专家团队 Agent 协作契约
    │   ├── IDENTITY.md                # [角色] 7大专家 Agent 身份定义与多面人设
    │   ├── SOUL.md                    # [控制] 状态流转防错闭环心脏 (§九)
    │   ├── TOOLS.md                   # [工具] 看板工具与 CLI 适配层使用指引
    │   ├── USER.md                    # [协议] 自领取规则与跨角色提权代行协议
    │   └── HEARTBEAT.md               # [巡检] 看板巡检与状态不变量核验规则
    ├── agents/                        # 7 大专家 Agent YAML 描述 (01-pm.yaml ~ 07-devops.yaml)
    ├── config/                        # 零硬编码配置模板 (workflow.config & project_architecture)
    ├── references/                    # 4 大全量提炼参考规约 (路由/流转/防错/Git)
    ├── templates/                     # 开发/审查/测试报告模版
    └── scripts/                       # 自动化脚本与看板适配器 (feishu_base_adapter.py 等)
```

---

## License

MIT
