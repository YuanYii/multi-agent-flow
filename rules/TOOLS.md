# TOOLS.md - 看板与工程工具链指引

本工作区配备的自动化工具与适配层说明：

## 1. 字段映射初始化工具
- **路径**：`multi-agent-flow/scripts/init_field_mapping.py`
- **用途**：自动扫描飞书 Base 提取字段 ID，生成 `workflow.config.yaml`。
- **用法**：`python3 init_field_mapping.py --base-token XXX --table-id YYY`

## 2. 看板 API / CLI 抽象适配器
- **路径**：`multi-agent-flow/scripts/feishu_base_adapter.py`
- **核心类**：`FeishuBaseAdapter`
- **主要 API**：
  - `list_records(filter_json, limit, offset)`：支持防截断分页拉取；
  - `update_record(record_id, fields)`：原子更新状态与处理人；
  - `create_record(fields)`：建单 SOP 工具。

## 3. 通用多 Agent 专家导出与自适应发现适配器
- **路径**：`multi-agent-flow/scripts/export_agent_adapters.py`
- **用途**：识别目前已知的（Cursor, Claude Code, Antigravity, Codex, Pi, OpenCode, Windsurf, Copilot）及未知/全新的 AI Agent 工具，自动完成专家人设导出与挂载。
- **机制**：
  1. 自动匹配预设 Agent 配置路径；
  2. 自动搜索工作区中的隐藏配置文件夹（包含 `prompts`, `rules`, `agents`, `subagents` 等关键词）；
  3. 降级导出至通配路径 `.agents/`；
  4. 支持手动指定路径：`python3 export_agent_adapters.py --custom-dir .mytool/agents --syntax /`

## 4. 状态巡检脚本
- **路径**：`multi-agent-flow/scripts/status.sh` / `status.ps1`
- **用途**：一键拉取并展示当前项目中各专家领取的任务列表与卡顿预警。
