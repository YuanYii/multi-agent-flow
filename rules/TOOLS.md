# TOOLS.md - 看板与工程工具链指引

本工作区配备的自动化工具与适配层说明：

## 1. 字段映射初始化工具
- **路径**：`multi-agent-flow/scripts/init_field_mapping.py`
- **用途**：自动扫描飞书 Base 提取字段 ID，生成 `workflow.config.yaml`。
- **用法**：`python3 init_field_mapping.py --base-token XXX --table-id YYY`

## 2. 看板 API / CLI 抽象适配器
- **路径**：`multi-agent-flow/scripts/_lib/boards/feishu_base_adapter.py`
- **核心类**：`FeishuBaseAdapter`
- **主要 API**：
  - `list_records(filter_json, limit, offset)`：支持防截断分页拉取；
  - `update_record(record_id, fields)`：原子更新状态与处理人；
  - `create_record(fields)`：建单 SOP 工具。

## 3. 通用多 Agent 专家导出与自适应发现适配器
- **路径**：`multi-agent-flow/scripts/verify_and_export_agents.py`（唯一导出入口）
- **配置**：平台清单与导出路径由 `multi-agent-flow/config/agent_platforms.yaml` 声明式驱动，当前支持：Antigravity、Claude Code、Cursor、Codex、OpenCode、ZCode、Pi、Agent Skills 开放标准 (agentskills.io)。
- **机制**：
  1. 按 `detect_dirs`/环境变量自动侦测当前激活平台；
  2. 按平台官方格式（Markdown+Frontmatter / Codex TOML）序列化 8 大专家并导出至各平台原生路径（如 `.claude/agents/`、`.agents/agents/`）；
  3. 工具声明按平台映射为原生工具名（Claude Code → `Bash/Edit/Read/Write/Grep/Glob`）；
  4. 导出时把项目技术栈（`user_data/project_architecture.config.yaml`）合并进各专家职责——`agents/*.yaml` 模板保持只读；
  5. 导出后执行本地格式断言：frontmatter/TOML 可解析、`name`/`description` 必填、8 角色齐全，任一失败 `exit(1)` 阻断（Fail-Closed）。
- **用法**：
  - 项目级（默认）：`python3 scripts/verify_and_export_agents.py`（任意 CWD；宿主项目目录自动探测）
  - 全局共享：`python3 scripts/verify_and_export_agents.py --global`（挂载各宿主用户级技能目录；子代理导出为通用版，防跨项目泄漏）

## 3.1 数据根解析器与全局安装器
- **路径**：`multi-agent-flow/scripts/paths.py` / `install_global.sh` / `install_global.ps1`
- **数据根解析链**（所有脚本统一）：`--project-root` 参数 > `YY_FLOW_PROJECT_ROOT` 环境变量 > legacy 判定（skill 拷贝内含 `user_data/board.json` → skill 即数据根，存量安装零迁移）> 当前工作目录。
- **共享安装**：`install_global.sh` 落正本至 `~/agent-skills/multi-agent-flow`（含零数据守卫与 `.yy-flow-shared` 标记），各项目数据仍落各自项目根，互不串扰。

## 4. 状态巡检脚本
- **路径**：`multi-agent-flow/scripts/status.sh` / `status.ps1`
- **用途**：一键拉取并展示当前项目中各专家领取的任务列表与卡顿预警。
