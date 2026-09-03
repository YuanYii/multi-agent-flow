# 02-架构自动识别与冷启动 SOP 规约 (Bootstrap SOP Spec)

## 一、 初次加载技术架构自动识别 SOP

当 Agent **初次在此工作区调阅/加载本 Skill**（检测到 `config/project_architecture.config.yaml` 不存在，**或**其 `meta.initialized != true`）时，必须自动执行以下操作：

### 8 大初始化自动执行步骤：

1. **核验配置文件**：检查 `config/project_architecture.config.yaml` 是否已存在。
2. **代码物理强拦截与 Subagent 官方规范落盘**：
   - 必须运行 `python3 scripts/verify_and_export_agents.py`。
   - 按各平台官方导出路径与格式完成 8 大专家子代理落盘（`.agents/agents/{role}/agent.md`）。
3. **自动代码物理预扫描**：
   - 运行 `python3 scripts/auto_scan_stack.py` 对工作区工程依赖、配置文件与 README 进行只读预检分析。
4. **模板生成与落库**：
   - 复制模板生成 `user_data/project_architecture.config.yaml`。
5. **项目工程骨架建立与原项目历史文档只读隔离归档**：
   - 建立任务与交付物规范骨架。
   - 运行 `python3 scripts/migrate_legacy_docs.py` 自动扫描原项目中散落的历史文档，分类归档至 `原项目文档/` 隔离区。
6. **物理派发架构全景鉴定工单**：
   - 运行 `python3 scripts/quick_task.py create ...` 物理建卡【待开始】。
7. **架构师深度鉴定、能力拓展与 PM 终态验收**：
   - PM 严经理通过 `invoke_subagent` 派发任务至 **钱架构 (`@flow-architect`)**；
   - 钱架构编写架构设计方案并调用 `save_project_architecture.py` 安全落盘，将任务推为【已完成】；
   - 提请人类用户 (USER) 终态验收置为【已验收】。
8. **显式输出 8 大专家子 Agent 列表与完整写权限矩阵**。

---

## 二、 8 大专家子代理权限矩阵

| 子代理标识 | 角色名称 | 核心职责 | 工具权限 | 合法状态流转区间 |
| :--- | :--- | :--- | :--- | :--- |
| `@flow-pm` | 严经理 (项目经理) | 需求拆解、并发控制与终态验收 | 完整读写 + run_command | 待开始->进行中 / 已完成->已验收 |
| `@flow-architect` | 钱架构 (系统架构师) | 系统总体架构设计与 ADR 接口契约 | 完整读写 + run_command | 待开始->进行中 / 进行中->已完成 |
| `@flow-dev` | 李开发 (开发工程师) | 后端/全栈核心编码与单测实现 | 完整读写 + run_command | 待开始->进行中 / 进行中->审查中 |
| `@flow-frontend` | 马前端 (前端开发工程师) | Web/UI 组件与交互体验开发 | 完整读写 + run_command | 待开始->进行中 / 进行中->审查中 |
| `@flow-reviewer` | 周审查 (代码审查专家) | 代码规范、安全扫描与质量门控 | 完整读写 + run_command | 审查中->测试中 / 审查中->已退回 |
| `@flow-qa` | 章测试 (测试工程师) | 集成测试、边界场景与质量准出 | 完整读写 + run_command | 测试中->已完成 / 测试中->已退回 |
| `@flow-docs` | 李文通 (文档工程师) | 交付物文档架构治理与规范 | 完整读写 + run_command | 待开始->进行中 / 进行中->已完成 |
| `@flow-devops` | 吕改特 (运维管理员) | 分支合流、发布构建与 CI 巡检 | 完整读写 + run_command | 待开始->进行中 / 进行中->已完成 |
