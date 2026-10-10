# Scripts / Migrations (历史数据迁移工具归档)

本目录集中收纳 Multi-Agent Flow 历史版本迭代过程中的存量数据迁移与离线转换脚本。

---

## 1. 归档工具清单

| 工具脚本 | 职责与迁移目标 | 触发场景 |
| :--- | :--- | :--- |
| [`migrate_legacy_board.py`](file:///Users/yuanyi/MyProject/vibeP/skills-design/2_多专家协同研发工作流/multi-agent-flow/scripts/migrations/migrate_legacy_board.py) | 将早期单体 `user_data/board.json` 结构平滑迁移并自动分流至按周划分的存储格式（`YYYY-Www.yaml`），同时生成物理备份。 | 历史升级手动执行或一次性运维 |

---

## 2. 关键安全与依赖边界说明

> [!IMPORTANT]
> **关于 `migrate_legacy_docs.py` 与 `migrate_to_chunked_storage.py` 保留于 `scripts/` 根层的架构决策**：
>
> 1. **`scripts/migrate_to_chunked_storage.py`**：
>    - 被 [`start_kanban_server.py`](file:///Users/yuanyi/MyProject/vibeP/skills-design/2_多专家协同研发工作流/multi-agent-flow/scripts/start_kanban_server.py) 服务启动自愈逻辑、`init_skill.sh` 以及测试套件动态引用。为保证服务启动时零依赖探测与自愈鲁棒性，严禁物理移动其位置。
>
> 2. **`scripts/migrate_legacy_docs.py`**：
>    - 被 `tests/test_domain_packages.py`、`tests/test_second_review_fixes.py`、`agents/06-docs.yaml`（文档工程师工作流指令）强绑定调用，必须保持在原目录。

---

## 3. 向后兼容性保障

为了确保外部既有自动化脚本与 CI 不发生破坏性中断，根目录 [`scripts/migrate_legacy_board.py`](file:///Users/yuanyi/MyProject/vibeP/skills-design/2_多专家协同研发工作流/multi-agent-flow/scripts/migrate_legacy_board.py) 仍保留了轻量级转发垫片（Shim）。
