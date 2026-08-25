# Multi-Agent Flow · 系统执行链路全景分析与流转规范（V2.0 完整整合版）

> 本文档基于 Multi-Agent Flow 代码库全量组件、SKILL.md 与 8 大专家提示词契约、references 六大规约、rules 规则与测试体系，系统性梳理 **5 大维度、26 条端到端执行链路 (Execution Pipelines)** 与 **8 项提示词场景契约**。
>
> V2.0 相对 V1.0（14 条链路）的变更：**新增 12 条链路**（V1.0 中 6 条完全缺失 + 深扫新增 5 条 + 初始化 SOP 从控制台链路拆分为独立链路）、**补齐 2 个异常分支**（人类验收打回、PR 关闭未合入）、**修正 5 处表述错误**、**增补 8 项提示词契约**。

---

## 一、二十六条执行链路全景矩阵

| 链路维度 | 链路代号与名称 | 触发源 (Trigger) | 核心流经模块与组件 | 最终状态与交付物 |
| :--- | :--- | :--- | :--- | :--- |
| **一、运维与工程初始化** (8 条) | **链路 1**：控制台运维直通链路 | `/yy-flow [cmd]` 快捷指令 | 网关前缀识别 ➔ 顶层 CLI 门面（heartbeat / kanban server / metrics / gate / sync-pr / auto） | 实时健康大盘 / Web 守护进程 / 12 类告警码 / 退出码 0·1·2 |
| | **链路 2**：初始化 7 步 SOP 一键启动链路 | `/yy-flow start` / 首次加载 | `init_skill.sh/.ps1` 7 步（凭据扫描 ➔ 平台探测导出 ➔ 架构预扫描 ➔ 配置落库 ➔ docs 骨架 ➔ 架构鉴定建卡 ➔ 深度鉴定验收） | 数据落盘 `user_data/` / 8 大专家子代理 / 响应契约【已识别 xxxx 项目】 |
| | **链路 3**：架构嗅探与能力注入链路 | 初始化 / 架构重检 | `stack_scanner` ➔ `arch_persister`(Schema 强校验) ➔ `tech_capability_expander`(6 技术角色×3~5 项) ➔ `agent_tech_overlay`(导出时覆盖) ➔ `verify_and_export_agents` | `project_architecture.config.yaml` / 携带技术栈的 Subagent 产物 |
| | **链路 4**：历史文档隔离归档链路 | 初始化 / 文档治理 | `legacy_migrator` ➔ 语义权重矩阵（父目录 +10 / 文件名 +5 / 正文 +1）➔ 只读镜像 | 归档至 `docs/D0X/原项目文档/` 物理隔离区 |
| | **链路 5**：敏感凭证安全扫描门禁链路 | 初始化 Step 1 / 评审前置 / 手动巡检 | `check_secrets.py` ➔ `secrets_checker`（5 类密钥模式、`${}` 占位符豁免） | 命中即 `exit 1` 阻断 / 扫描 6 类目录 |
| | **链路 6**：Git Hooks 安装链路 | 项目接入 / 门禁部署 | `install_git_hooks.py` ➔ `hooks_installer`（pre-commit 复制 + chmod +x） | `.git/hooks/pre-commit` 就绪；无 `.git` 则 `exit 1` |
| | **链路 7**：全局共享安装与跨平台挂载链路 | 多项目复用安装 | `install_global.sh/.ps1`（degit release_v6、board.json 污染守卫、`.yy-flow-shared` 标记）➔ `verify_and_export_agents.py --global` ➔ 数据根解析链 | 正本落 `~/agent-skills/` / 9 平台用户级挂载 / 各项目独立数据根 |
| | **链路 8**：千问办公插件打包与合规发布链路 | QwenWork/Qoder 套件发布 | `package_qwen_plugin.py` ➔ `qwen_packager`（图标 200×200 ≤2MB、manifest 校验、排除模式） | `dist/multi-agent-flow-qwen.zip` / `.qoder-plugin/plugin.json` |
| **二、业务正向研发** (5 条) | **链路 9**：L0 纯文本咨询直答链路 | 技术咨询 / 代码问答 | 网关分级三问判定 L0 ➔ 首行【任务分级: L0】➔ 豁免建卡 ➔ 草稿箱归档 | 纯文本解答 / 临时产物归档 `草稿箱/` |
| | **链路 10**：L1 单文件轻量闭环链路 | 局部 Fix / 单文件修改 | 网关判定 L1 ➔ 建卡硬门禁（含 `check_duplicate_tasks` 0.8 查重）➔ 编码 ➔ `step_summary` 自动总结 ➔ 完工推进 | 【待开始】➔【进行中】➔【已完成】短链 ➔ 人类验收 |
| | **链路 11**：L2 标准全周期研发链路 | 多文件 / 架构 / 强制升格 | PM 拆解 ➔ DEV 编码 ➔ REVIEWER 审查 ➔ QA 测试 ➔ PM 复核 | A 类强制全链闭环 ➔ 人类终态验收 |
| | **链路 12**：CLI / 批处理自动流转链路 | `quick_task` / `auto_task` | CLI 入口 ➔ 类型自动装配（A~G 全链）➔ 10+ 项门控校验 ➔ 适配器原子写入 | 自动批处理流转 / 断点续跑 / 解阻前置验证 / 代行注入 |
| | **链路 13**：[HOTFIX] 紧急修复直通链路 | 生产事故 / 紧急热修 | 任务名含 `[HOTFIX]` ➔ 门控解锁 DEV/FRONTEND「进行中 ➔ 已完成」直推 | 跳过审查测试直达验收；PM 直推已验收仍被禁止 |
| **三、异常返工与权限治理** (5 条) | **链路 14**：异常打回、多跳返工与阻塞恢复链路 | 审查退回 / 测试失败 / 验收不通过 / 依赖阻塞 / PR 事件 | `validate_transition`（打回处理人定向、**打回不拆单** + DEF 缺陷编号）➔ `sync_pr_status` | 5 分支：审查打回 / 测试打回 / 阻塞解阻(+PR 合流) / **人类验收打回** / **PR CLOSED 告警打回** |
| | **链路 15**：任务取消终态链路 | 需求变更 / 功能作废 | 门控校验（仅 PM 或 USER 代行）➔ 必填取消原因 + end_time ➔ 经办人收敛严经理 | 终态【已取消】只读锁定，禁止逆向流转 |
| | **链路 16**：孤儿产出检测与升格回捞链路 | 例行巡检 / 交付物悬挂 | `heartbeat` ORPHAN_OUTPUT（48h 新增文件无卡片）➔ 处置分流 | L0 归档草稿箱 / 有交付物升格 L1/L2 补卡；TIME_SKEW 防冲卡 |
| | **链路 17**：代行授权与指令拆分门控链路 | 跨角色指令 / 越权请求 | `DELEGATION_ALLOW_MATRIX` 白名单（8 角色仅接受 PM+USER 代行）➔ `--delegated-by` 声明留痕 ➔ 审计落字段 ➔ 单次生效；未授权走指令拆分 SOP | [WARN] 权限拦截与任务转交清单；**已验收禁 Agent 自签** |
| | **链路 18**：跨专家上下文组装与交接管道 | PM 派单 / 跨角色移交 | `build_agent_context`（dispatch / task_context / handover）➔ Payload v2.0 契约 ➔ 流程节点 `T0001-N01` 双标识 | 派单 Prompt / 交接载荷（artifacts / handover_context / defect_history） |
| **四、质量门控与交付验收** (5 条) | **链路 19**：阶段双向硬门禁核验链路 | 阶段结项 close / 开工准入 start | `stage_gate_checker`（结项 5 项核验 + 开工前置依赖核验 `check_stage_start_predecessors`） | 准予开工/结项（`exit 0/1`）+ `--json` CI 消费 |
| | **链路 20**：Git 提交人类验收拦截链路 | `git commit` / DevOps | `.git/hooks/pre-commit` ➔ `verify_git_gate`（经适配器层扫描）➔ 人类验收专属物理拦截（非 USER 授权禁止验收） | 物理阻断未验收提交入库（`exit 1`）；`accept` 后放行 |
| | **链路 21**：模板化任务报告生成链路 | 各专家交付 / 复审复测 | `generate_report.py`（8 角色 × 7 模板映射、占位符清洗、[SYNC] 追加复验模式） | 报告归档 `docs/D04-研发过程/D02-报告/{type}/`，防孤儿报告 |
| | **链路 22**：学术级 DOCX 报告与证据材料生成 | 立项方案 / 阶段报告 / 投标 | `docx_academic_styler`（GB/T 7713）➔ `generate_docx_proposal` / `generate_proof_material` | 宋体+Times New Roman 学术 Word / 证据链材料 |
| | **链路 23**：双层质量保障测试体系链路 | 回归验证（需显式授权） | pytest 244 项基准用例 ➔ `run_108_tasks_simulation`（4 大矩阵 + 8 维数据质量审计） | 状态机闭环 / 越权对抗 / 审计一致性断言通过 |
| **五、看板协同、平台适配与合规审计** (3 条) | **链路 24**：多后端看板适配与字段映射链路 | 看板读写（全部 8 个脚本入口） | `board_adapter_factory`（Fail-Closed + config.schema.json + 指数退避）➔ Feishu/Jira/GitHub/Offline 适配器 ➔ `field_mapper` | 任意后端统一读写接口 / 字段自动映射 |
| | **链路 25**：Web 看板协同与只读保护链路 | 浏览器拖拽 / 局域网访问 / REST API | HTTP 服务 ➔ Bearer/Master Token 鉴权 ➔ IP 403 禁写 ➔ `FileLock` ➔ `validate_transition` ➔ SSE 广播 + If-Match 乐观锁 | 局域网只读保护 / 多端偏好 / 4 视图 + 离线双模 |
| | **链路 26**：审计检索与轮转归档数据链路 | 合规检查 / 故障回溯 / 后台轮转 | `audit_logger`（含代行字段）➔ `audit_query`（task/role/success/时间窗/归档）➔ `audit_rotate`（日切分 + 50MB 双触发 + gzip） | 结构化审计记录 / 历史归档 `logs/archive/*.log.gz` |

---

## 二、维度一：运维与工程初始化链路 (Pipelines 1 ~ 8)

### 链路 1：控制台运维直通链路
1. **触发源**：`/yy-flow` 全家族快捷指令（start / status / kanban / sync-pr / auto / gate）。
2. **执行路径**：
   - SKILL.md 统一入口网关识别前缀，0 前置分级直通运维通道；
   - `/yy-flow status` → `heartbeat.py`：**6 类巡检 12 告警码**（滞留 STALE_IN_PROGRESS/STALE_REVIEW_OR_TEST、并发超限 DEV/FRONTEND_CONCURRENCY_EXCEEDED、处理人一致性 ASSIGNEE_MISMATCH_*、终态缺时间 MISSING_END_DATE、孤儿产出 ORPHAN_OUTPUT、时序防冲卡 TIME_SKEW_INSTANT、PR 联动 PR_MERGED_READY_UNBLOCK/PR_CLOSED_UNMERGED），阈值可配、`--json` 输出、退出码 0/1/2；
   - `/yy-flow kanban` → `start_kanban_server.py` 拉起 HTTP 守护进程（默认 32886）；
   - `/yy-flow metrics` → `metrics_analyzer.py` 效能卡点分析；`/yy-flow sync-pr` → `sync_pr_status.py`；`/yy-flow gate` → `check_stage_gate.py`。

### 链路 2：初始化 7 步 SOP 一键启动链路
1. **触发源**：`/yy-flow start` 或首次加载检测到 `project_architecture.config.yaml` 缺失。
2. **执行路径**（`init_skill.sh` / `init_skill.ps1` 物理执行）：
   - **Step 1 凭据扫描**：`check_secrets.py` 强执行（联动链路 5）；
   - **Step 2 平台探测与导出**：`verify_and_export_agents.py` 按 `agent_platforms.yaml` 探测激活平台、导出子代理并做**本地格式断言 Fail-Closed**（frontmatter YAML / Codex TOML 可解析、name/description 必填、8 角色齐全，任一不满足 exit 1）；
   - **Step 3 架构预扫描**：`auto_scan_stack.py` 只读预检工程依赖；
   - **Step 4 配置落库**：复制 `workflow.config.template.yaml` / `project_architecture.template.yaml` 至 `user_data/`（数据根解析链见链路 7）；
   - **Step 5 docs 骨架**：建立 D01~D06 目录规范 + `草稿箱/`，`.gitignore` 排除草稿箱；`migrate_legacy_docs.py` 归档历史文档（联动链路 4）；
   - **Step 6 物理建卡**：`quick_task.py create --name "项目技术架构全景鉴定与选型定版"` 建【待开始】工单；
   - **Step 7 深度鉴定与响应契约**：钱架构领单 ➔ 编写 D02 架构文档 ➔ `save_project_architecture.py` 落盘（联动链路 3）➔ PM 验收 ➔ 输出【已识别 xxxx 项目】标志行 + 官方查证凭据 + 8 大专家写权限矩阵表格。

### 链路 3：架构嗅探与能力注入链路
1. **触发源**：项目接入初始化或架构师执行技术栈同步。
2. **执行路径**：
   - `stack_scanner.py` 解析 `pyproject.toml` / `package.json` / `Dockerfile` 等，输出技术画像；
   - `arch_persister.py` 经 `project_architecture.schema.json` 强校验后写入 `user_data/project_architecture.config.yaml`；
   - `tech_capability_expander.py` 为 **6 个技术角色**（DEV/FRONTEND/REVIEWER/QA/ARCHITECT/DEVOPS，PM/DOCS 不注入）动态推导 3~5 项专属能力；
   - `agent_tech_overlay.py` 在【导出时】覆盖能力到各平台 Subagent 产物（agents/*.yaml 模板保持只读，共享安装下不互串）；
   - `update_agent_tech_stacks.py` 校验架构配置后重触发导出；物理读取导出文件 Fail-Closed 断言。

### 链路 4：历史文档隔离归档链路
1. **触发源**：初始化 Step 5 或历史文档治理。
2. **执行路径**：`legacy_migrator.py` 深度扫描项目根；父目录名权重 +10、文件名特征 +5、正文前 2KB 语义 +1 综合判定归属 D01~D06；以只读镜像复制到 `docs/{D01-D06}/原项目文档/` 物理隔离区（D02 架构类加分、D03 业务模块兜底）。

### 链路 5：敏感凭证安全扫描门禁链路
1. **触发源**：初始化 Step 1（强制先行）、周审查评审前置（三平台 agent.md 均要求"必须先运行"）、手动巡检/CI。
2. **执行路径**：`check_secrets.py` 扫描 config/scripts/agents/docs/kanban + 数据根 user_data 的 yaml/json/py/sh/md 文件；正则匹配 5 类密钥（飞书 App ID `cli_`、App Secret、GitHub PAT `ghp_`、Jira Token `ATATT3`、RSA 私钥）；`${VAR}` 规范占位符豁免；发现问题脱敏展示并 `exit 1` 阻断，全通过 `exit 0`。

### 链路 6：Git Hooks 安装链路
1. **触发源**：项目接入安装门禁钩子。
2. **执行路径**：`install_git_hooks.py` → `hooks_installer` 校验 `.git` 目录存在（缺失即 exit 1 + 修复指引）、将 `scripts/hooks/pre-commit` 复制至 `.git/hooks/` 并 chmod +x；后续 `git commit` 自动唤起 `verify_git_gate.py`（联动链路 20）。

### 链路 7：全局共享安装与跨平台挂载链路
1. **触发源**：多项目共享安装（`install_global.sh` / `.ps1`）。
2. **执行路径**：
   - 正本物化至 `~/agent-skills/multi-agent-flow`（npx degit 拉取 release_v6，无 Node 则 tarball 兜底）；
   - **board.json 污染守卫**：正本含数据即拒绝（防 legacy 数据误判）；写入 `.yy-flow-shared` 共享标记；
   - `verify_and_export_agents.py --global` 按 **9 平台矩阵**挂载用户级技能与子代理（Antigravity `.agents`+`~/.gemini`、Claude Code `.claude`、Cursor `cursor_mdc`→`.cursor/rules/*.mdc`、Codex `.codex` TOML、OpenCode `.opencode`、ZCode `.zcode`+`~/.zcode/agents`、Pi `.pi`、Universal `.agents`、QwenWork `qwen_plugin`→`.qoder-plugin/plugin.json`），挂载类型 symlink / cursor_mdc / qwen_plugin 三种；
   - **数据根解析链**（paths.py，全部落盘行为的地基）：显式 `--project-root` / `YY_FLOW_PROJECT_ROOT` 环境变量 > `.yy-flow` 布局自定位（skill 位于 `<X>/.yy-flow/skill` → 数据落 `<X>/.yy-flow/user_data`）> legacy 判定（skill 内含 board.json 且无共享标记）> CWD；docs/ 恒定锚定项目根，代码/数据分离。

### 链路 8：千问办公插件打包与合规发布链路
1. **触发源**：QwenWork/Qoder 专家套件发布。
2. **执行路径**：`package_qwen_plugin.py` → `qwen_packager`：校验图标必须 200×200 且 ≤2MB、manifest（`.qoder-plugin/plugin.json`）name 必须 ASCII 字母数字（连字符/下划线允许）、version/description 必填；按排除模式（.git/.venv/__pycache__/dist/node_modules 等）组装并产出 `dist/multi-agent-flow-qwen.zip`；任一项不合规 `exit 1`。

---

## 三、维度二：业务正向研发协同链路 (Pipelines 9 ~ 13)

### 链路 9：L0 纯文本咨询与技术调研直答链路
1. **触发源**：纯只读咨询（"怎么配置"、"分析报错原因"、"查阅设计"）。
2. **执行路径**：网关分级三问判定"无持久化文件写入" → Agent 首行输出【任务分级: L0】→ 豁免建卡直接作答；临时代码/草稿统一归档 `草稿箱/`（联动链路 16 孤儿产出检测，L0 产物不触发告警）。

### 链路 10：L1 单文件轻量闭环链路
1. **触发源**：局部 Bug 修复、单文件配置微调、单一文档修订。
2. **执行路径**：
   - 网关判定 L1，首行输出【任务分级: L1】；
   - **动工前硬门禁**：`transition_task.py --create` 建卡（含 `check_duplicate_tasks` 相似度 0.8 查重拦截，`--force`/`--no-dup-check` 可显式跳过）；
   - 编码修改；**完工后硬门禁**：推进【已完成】必填工时与产出路径（`step_summary.py` 自动生成阶段总结，杜绝过程描述空心化）；
   - 自动跳过审查与测试（B/C/D/F/G 短链类型），直接提请人类验收【已验收】（E 类用户自执行任务为"进行中/待开始 → 已验收"直验，豁免 end_time）。

### 链路 11：L2 标准全周期研发链路
1. **触发源**：复杂特性、多文件重构、公共核心模块修改（强制升格 L2）。
2. **执行路径**：PM 严经理 WBS 拆解批量建卡 → 李开发/马前端领单编码 → 提审（审查中）→ 周审查评审通过（测试中）→ 章测试回归（已完成 + 工时/测试产出）→ PM 复核提请人类最终验收（已验收）。A 类任务强制全链：DEV/FRONTEND 直推已完成、PM 直推已验收均被门控物理拒绝。

### 链路 12：CLI / 批处理自动流转链路
1. **触发源**：`quick_task.py`（create/accept/accept-all/complete）或 CI 调用 `auto_task.py`。
2. **执行路径**：
   - 解析 `--role` / `--type`（A~G 七类：A 全链六步、B/C/D/F/G 特权短链、E 直验）；
   - `auto_task.py` 附加能力：任意节点断点续跑、已退回需处理 DEF 后恢复、已阻塞需前置验证（备注含【解除】且晚于【阻断】）、已取消拒绝恢复、已验收幂等、`--simulate` 不落库、链级锁防并发、代行注入（--delegated-by/--delegation-reason）；
   - 经 `validate_transition` **10+ 项门控**：代行白名单、终态防篡改、HOTFIX 解锁、类型特权、assignee 必填、打回处理人定向（禁退回自身）、【阻断】原因必填、【取消】原因必填、已验收人类专属、end_time 强校验、全角色 WIP 并发上限（≤3）、A 类越权拦截；
   - `quick_task.py accept-all` 支持按阶段批量人类验收（detagated_by=USER 批量代签）。
3. 经看板适配器层原子写入并落审计日志（联动链路 24/26）。

### 链路 13：[HOTFIX] 紧急修复直通通道
1. **触发源**：生产事故、紧急缺陷（任务名显式含 `[HOTFIX]` 标记）。
2. **执行路径**：validate_transition 检测 `is_hotfix` → 为 DEV/FRONTEND 解锁「进行中 → 已完成」直推（跳过审查与测试环节），并豁免 A 类"执行角色直推已完成"越权拦截；**PM 直推已验收仍被禁止**，热修同样必须经过人类验收终态。

---

## 四、维度三：异常返工与权限治理链路 (Pipelines 14 ~ 18)

### 链路 14：异常打回、多跳返工与阻塞恢复链路（5 分支）
1. **触发源**：代码审查不达标、测试执行失败、人类验收不通过、外部依赖阻塞、PR 合入/关闭。
2. **执行路径**：
   - **分支 1（审查打回）**：审查中 → 已退回，经办人回退原负责人（DEV/FRONTEND/ARCHITECT），附结构化缺陷 `DEF-TXXX-N`；
   - **分支 2（测试打回）**：测试中 → 已退回，回退原开发负责人修复；
   - **分支 3（依赖阻塞与解阻）**：置【已阻塞】必填 `【阻断】<原因>` 备注；解阻走 unblock 恢复进行中；绑定 PR 时 `sync_pr_status.py` 探测合流自动解阻至已完成，落盘 Merge Commit SHA / 目标分支 / 合流审计凭据；
   - **分支 4（人类验收打回）**：已完成 → 已退回，按类型回退（A/B/G → 原开发负责人；C → DOCS；D → DEVOPS）；
   - **分支 5（PR 关闭未合入）**：CLOSED → 高危告警 PR_CLOSED_UNMERGED，支持可选自动打回至【已退回】通知原开发者；
   - **打回不拆单铁律**：一律原单打回 + DEF 编号，严禁派生 `T0103-fix` 等孤儿任务；报告追加原则：开发报告追加 §9 返工记录、审查报告追加 §8 复审结论、测试报告追加 §9 复测结论，严禁新建独立《复审/复测报告》碎片文件。

### 链路 15：任务取消终态链路
1. **触发源**：需求变更、功能作废、误建卡。
2. **执行路径**：仅 PM 严经理（或 USER 显式代行）可发起；推进至【已取消】必须携带取消原因 remarks + end_time，经办人强制收敛严经理；终态只读锁定（validate 防篡改层），禁止任何逆向流转；已取消任务在 auto_task 中被拒绝恢复。

### 链路 16：孤儿产出检测与升格回捞链路
1. **触发源**：heartbeat 例行巡检。
2. **执行路径**：检测近 `orphan_output_hours`（默认 48h）新增交付文件无对应任务卡 → ORPHAN_OUTPUT 告警 → 处置分流：L0 纯文本产出归档 `草稿箱/`；存在代码/文档交付物则升格 L1/L2 补卡；配套 TIME_SKEW_INSTANT 防秒级冲卡（开工时间解耦：建卡时 start_date 置空、首次进【进行中】才落盘、打回重领保留原始 start_date）。

### 链路 17：代行授权与指令拆分门控链路
1. **触发源**：跨角色指令（如 DEV 收到"帮我把 T0001 验收掉"）。
2. **执行路径**：
   - **强行拦截**：角色 ∉ 合法操作人集合且无显式授权 → 拒绝执行；
   - **显式授权协议**：用户明确授权后，Agent 声明 [NOTICE] 代行留痕；CLI 强制传 `--delegated-by` + `--delegation-reason`；
   - **白名单硬校验**：`DELEGATION_ALLOW_MATRIX`——8 角色均只接受 PM + USER 代行；USER（人类用户授权）优先级最高；同级互代行（DEV↔FRONTEND）禁止；白名单外 Fail-Closed 拒绝；
   - **留痕与限制**：看板注明 [代行记录]、审计日志落 delegated_by/delegation_reason、经办人仍为目标合法角色、授权单次生效；
   - **指令拆分 SOP**：未授权时只执行权限内部分，越权部分输出 [WARN] 权限拦截与任务转交清单（结构化表）；
   - **人类验收专属**：流转至【已验收】必须 role=USER 或 delegated_by=USER，Agent 严禁自签验收终态。

### 链路 18：跨专家上下文组装与交接管道
1. **触发源**：PM 派单、专家认领、跨角色提审与交接。
2. **执行路径**：
   - `build_agent_context.py`：`--action dispatch`（注入分级三问、完工红线、角色规约 + "绝对禁止孤儿报告"纪律）/ `--action task_context`（任务历史 process 节点 + 状态 + 技术栈能力）/ `--action handover`（改动文件清单、自测证据、待评审关注点）；
   - **消息总线 Payload v2.0 契约**：强类型载荷（protocol_version / sender / recipient / artifacts / handover_context / defect_history / notes_for_next_role）；
   - **流程节点双标识**：每次流转追加 `{任务ID}-N{序号}`（如 T0001-N03），锁内 max(N)+1 分配、单调递增只追加、回滚烧号不复用、建卡不占号；
   - **虚拟角色边界与通知通道铁律**：8 大专家均为虚拟子代理，严禁外部 IM（飞书/钉钉/企微/Slack）按虚拟人名检索或私信；内部法定通知载体 = transition_task 指派 + 子代理消息总线；仅配置了群机器人 Webhook 才广播、仅显式人类责任人（USER/绑定 OpenID/邮箱）才走外部通知。

---

## 五、维度四：质量门控与交付验收链路 (Pipelines 19 ~ 23)

### 链路 19：阶段双向硬门禁核验链路
1. **触发源**：阶段结项准出（`--action close`）或阶段开工准入（`--action start`）。
2. **执行路径**：`stage_gate_checker.py` 加载上下文；**结项 5 项**（① 全卡已验收且结束时间完整 ② WBS 编号规范 + docs 双向对账 ③ 架构技术总结存在 ④ PM 阶段复盘报告存在 + 总结卡验收 ⑤ Git 工作区清洁）；**开工准入核验**（前置阶段依赖 `check_stage_start_predecessors`）；全通过 exit 0 / 任一失败 exit 1 + 修复向导；`--json` 供 CI 消费，`--ignore-git` 可豁免清洁度。

### 链路 20：Git 提交人类验收拦截链路
1. **触发源**：开发者或吕改特触发 `git commit`。
2. **执行路径**：`.git/hooks/pre-commit` 唤起 `verify_git_gate.py` → 经**看板适配器层**扫描未验收/进行中任务 → 打印阻断清单 exit 1 物理中止提交 → 人类执行 `quick_task.py accept`（含验收专属权限拦截：已验收必须 USER 或 delegated_by=USER）后放行入库；`accept-all` 支持批量验收。配套"无工单不 Git"与三层分支模型、Conventional Commits、SemVer 版本标签规范（references/04）。

### 链路 21：模板化任务报告生成链路
1. **触发源**：各专家交付时（agent.md 固定契约：dev/frontend 提交审查前 `--type dev/frontend`、reviewer `--type review`、qa `--type qa`）。
2. **执行路径**：`generate_report.py` 按 8 角色映射 7 模板（pm→wbs_breakdown、arch→module_design、dev/frontend→dev_task_report、reviewer→code_review、qa→qa_test_report、docs→documentation、devops→troubleshooting，兼容别名 review）；清洗元数据占位符防 `${...}` 残留；报告已存在时 [SYNC] 追加复验/复测记录（配合报告追加原则）；自动归档 `docs/D04-研发过程/D02-报告/{type}/`；不支持类型 exit 1 Fail-Closed。

### 链路 22：学术级 DOCX 报告与证据材料生成链路
1. **触发源**：立项方案书、阶段技术报告、完工证明材料（李文通）。
2. **执行路径**：`generate_docx_proposal.py` / `generate_proof_material.py` 依托 `docx_academic_styler.py` 执行 GB/T 7713 排版（宋体 + Times New Roman 底层 XML rFonts 强绑定、五级字号行距、A4 页边距 2.54/2.8cm）；自动组装任务完成记录、测试报告与代码 Diff 输出 .docx。

### 链路 23：双层质量保障测试体系链路
1. **触发源**：发布前回归验证（**必须用户显式授权**，run_108_tasks_simulation.py 头部红字门禁）。
2. **执行路径**：第一层 pytest 244 项基准用例（HTTP 路由/筛选/白名单/双层文件锁/RBAC）；第二层 `run_108_tasks_simulation.py` 4 大矩阵：① 72 条 8 阶段 × 9 状态全笛卡尔积 ② 16 条多角色交叉返工多跳（含 3 轮连续打回追溯链 11 节点）③ 8 条工时极值/跨月/XSS/Unicode/超长文本边界 ④ 12 条局域网并发写 + 8 项 403 越权拦截；全维断言 8 项（唯一性、单调性、状态机闭环、时间时序、工时有效性、追溯链、审计日志一致性、安全红线）。

---

## 六、维度五：看板协同、平台适配与合规审计链路 (Pipelines 24 ~ 26)

### 链路 24：多后端看板适配与字段映射链路
1. **触发源**：所有看板读写入口（transition_task / quick_task / auto_task / heartbeat / metrics_analyzer / sync_pr_status / git_gate_verifier / stage_gate_checker 共 8 个）；初始化字段映射。
2. **执行路径**：
   - `board_adapter_factory.get_board_adapter()`：配置缺失 Fail-Closed 抛 FileNotFoundError（提示先 init）、`config.schema.json` Schema 断言、API 调用指数退避重试（3 次，1s→2s→4s）；
   - 按 `workflow.config.yaml` 的 `board.provider` 路由 4 适配器：飞书多维表格（@larksuite/cli record-list/get/create/update + filter 防截断）、Jira（REST JQL 分页 + Basic Auth 环境变量）、GitHub Projects v2（GraphQL 严格 Fail-Closed，无 Token 拒物理操作）、离线 board.json（读改写 flock 排他锁 + tmp+os.replace 原子替换 + 锁内自增任务编号）；
   - `field_mapper.discover_feishu_fields` / `init_field_mapping.py` 自动探测字段名→ID 映射矩阵。
3. **说明**：本链路是 26 条链路中 20+ 条的数据底座；board.json 仅是 local provider 的存储文件（V1.0 文档"原子更新 board.json"表述由此修正）。

### 链路 25：Web 看板协同与只读保护链路
1. **触发源**：浏览器拖拽、协同端 REST API（GET /api/tasks、/api/tasks/{id}、/api/board/meta、/api/preferences、/api/version、/api/health；POST /api/tasks、/api/tasks/batch-delete、/api/tasks/{id}/transition；PUT /api/tasks/reorder、/api/board/meta、/api/tasks/{id}）。
2. **执行路径**：HTTP 服务鉴权（Master Token / Bearer 头）→ 客户端 IP 校验（非 Localhost 写操作物理 403）→ 跨进程文件排他锁 `file_lock.py` → `validate_transition` 门控 → 更新落库 → SSE 实时广播；If-Match / version 乐观锁防并发覆盖；/api/health 端口复用存活判定；4 视图（数据表格/状态泳道/专家负载/阶段工作包）+ `/offline_board.html` 离线单机双模 + 多终端偏好持久化（kanban_server.json）。

### 链路 26：审计检索与轮转归档数据链路
1. **触发源**：合规检查、故障回溯、后台定时轮转。
2. **执行路径**：
   - **记录分支**：`audit_logger.record_audit_event` 落 `logs/audit_trail.log`，字段含 task_id/role/from/to/assignee/success/delegated_by/delegation_reason；
   - **查询分支**：`audit_query.py` 按 task_id/role/success/时间窗跨当前日志 + `logs/archive/*.log.gz` 全量检索，支持 `--delegated-by` 代行记录追踪、`--format json/table`；
   - **轮转分支**：`audit_rotate.py` 日切分 + 单文件 ≥50MB 大小切分（默认 max_size_mb=50），gzip 归档至 `logs/archive/`，`--dry-run` 预判；轮转持文件锁防并发。
3. **修正说明**：V1.0 声称的"自动清理超过 30 天过期归档"在代码中不存在（无删除逻辑），本版已移除该描述；阈值 10MB 修正为 50MB。

---

## 七、提示词场景契约（8 项）

| # | 契约名称 | 载体 | 核心内容 |
| :--- | :--- | :--- | :--- |
| 1 | 网关三问与分级豁免/升格 | SKILL.md §2/§3 | L0/L1/L2 分级决策树；执行态 Task ID 豁免（防死循环建卡）；复合指令管道化（先控制台后业务）；公共核心库/认证授权/数据库迁移强制升格 L2 |
| 2 | 十大协同红线与分派即建单 | rules/AGENTS.md | 团队协作 10 大红线；分派即建单协议（派发即物理建卡）；极简特权通道 Fast-Track |
| 3 | 时序真实性与防冲卡 | references/03 §五 | 建卡 start_date 置空、首进【进行中】落盘、打回保留原始 start_date、严禁秒级连续冲卡 |
| 4 | 打回不拆单 + DEF 缺陷编号 + 报告追加 | references/02 §四、references/03 §六 | 禁派生孤儿修复任务；DEF-TXXX-N 结构化缺陷；§8 复审/§9 复测追加原则，禁新建独立复审报告 |
| 5 | 消息总线 Payload v2.0 与记忆持久化 | references/06 §1/§3 | 强类型交接载荷；禁隐式口头传达，流转说明必须落盘 reports/ 或 remarks |
| 6 | 虚拟角色边界与通知通道铁律 | references/06 §4 | 8 专家为虚拟子代理，禁外部 IM 检索虚拟人名；法定通知载体；Webhook/真人白名单 |
| 7 | 文档治理规范 | references/05 | D01~D06 目录层级；Frontmatter 标签元数据；命名后缀规约；维护责任矩阵；原项目文档只读保留原则 |
| 8 | 跨平台执行与数据布局规范 | SKILL.md NOTE、paths.py | Windows 下 python3 ↔ python 替换；.yy-flow 代码/数据分离布局；共享安装每项目独立数据根 |

---

## 八、V2.0 审计修正清单（相对 V1.0）

| # | 位置 | V1.0 表述 | V2.0 修正 |
| :--- | :--- | :--- | :--- |
| 1 | 链路 26 | "自动清理超过 30 天的过期归档" | 代码无删除逻辑，移除该功能描述（如需保留需补实现） |
| 2 | 链路 26 | "单文件超过 10MB 自动切割" | 默认 50MB；日切分 + 大小双触发；归档至 logs/archive/ |
| 3 | 链路 3 | "动态注入 8 大专家 Subagent" | 技术栈能力注入 6 个技术角色（PM/DOCS 不注入），导出时 overlay 覆盖 |
| 4 | 链路 12 | "五层门控拦截校验" | 10+ 项校验明细（代行白名单/终态防篡改/HOTFIX 解锁/类型特权/打回定向/备注必填/人类验收专属/end_time/WIP 并发） |
| 5 | 链路 12/20/19 | "原子更新底层 board.json" / "物理扫描看板数据" | 统一经看板适配器层读写（多后端），board.json 仅 local provider |

---

## 九、审计依据与覆盖说明

- 覆盖范围：`scripts/` 全部 37 个 CLI/模块、`_lib/` 全部子包、`config/` 全部配置、`references/` 六大规约、`rules/` 六项规则、8 大专家 agent 提示词（.agents/.claude/.zcode 三平台）、`templates/`、`tests/` 测试体系、`kanban/` 前端、README/SKILL.md 提示词场景。
- 版本基线：multi-agent-flow release_v6（工作区 .yy-flow 全家桶布局 + 看板适配器层架构）。
- 本版共 26 条链路：V1.0 原 14 条全部保留（含分支/细节补强），新增 12 条（链路 2、5、6、7、8、13、15、16、17、21、23、24）。