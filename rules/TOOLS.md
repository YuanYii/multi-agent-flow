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

## 3. 状态巡检脚本
- **路径**：`multi-agent-flow/scripts/status.sh` / `status.ps1`
- **用途**：一键拉取并展示当前项目中各专家领取的任务列表与卡顿预警。
