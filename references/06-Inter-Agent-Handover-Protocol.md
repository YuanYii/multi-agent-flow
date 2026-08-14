# 06-Inter-Agent-Handover-Protocol.md (专家 Agent 间任务交接与消息总线协议)

> 规范多 Agent 协同流转时的上下文 Payload 载荷结构、记忆持久化与交接契约。

---

## 📡 1. 消息总线与交接 Payload 契约

当上一阶段角色完成任务并将控制权移交给下一个角色（如 DEV ➔ REVIEWER，或 REVIEWER ➔ QA）时，必须在交接消息或存储中携带**强类型结构化 Context Payload**：

```json
{
  "protocol_version": "2.0",
  "task_id": "T0001",
  "wbs_id": "1.1.1",
  "task_name": "核心解析模块编码与校验",
  "sender": {
    "role": "DEV",
    "agent_id": "flow-dev"
  },
  "recipient": {
    "role": "REVIEWER",
    "agent_id": "flow-reviewer"
  },
  "artifacts": {
    "modified_files": [
      "src/parser.py",
      "tests/test_parser.py"
    ],
    "report_path": "docs/reports/dev/DEV_T0001_Report.md",
    "coverage_rate": "86.5%"
  },
  "handover_context": {
    "state_transition": "进行中 -> 审查中",
    "defect_history": [
      "DEF-T0001-1 (修复完成)"
    ],
    "notes_for_next_role": "单测集中在 test_parser.py 中，重点审查异常数据类型的流转路径。"
  }
}
```

---

## 🔄 2. 8 大角色标准交接动作矩阵

| 流转方向 | 发起角色 | 接收角色 | 必填交接产物 (Required Artifacts) | 门控校验脚本调用命令 |
| :--- | :--- | :--- | :--- | :--- |
| **自领取** | PM/看板 | DEV / FRONTEND | WBS 任务包条目、需求约束 | `python3 scripts/transition_task.py --role DEV --from-status 待开始 --to-status 进行中 ...` (FRONTEND 同命令,仅 `--role` 改) |
| **提代码审查**| DEV / FRONTEND | REVIEWER | 修改代码列表、单测结果、开发任务报告 (前端含 UX 验收清单) | `python3 scripts/transition_task.py --role DEV --from-status 进行中 --to-status 审查中 ...` (FRONTEND 同命令) |
| **审查通过** | REVIEWER | QA | 审查报告、安全/规范评估 (前端含可访问性/响应式) | `python3 scripts/transition_task.py --role REVIEWER --from-status 审查中 --to-status 测试中 ...` |
| **审查打回** | REVIEWER | DEV / FRONTEND | 结构化缺陷信息 `DEF-TXXX-N` | `python3 scripts/transition_task.py --role REVIEWER --from-status 审查中 --to-status 已退回 ...` |
| **测试通过** | QA | PM | 测试报告、功能点复验覆盖表、`end_time` | `python3 scripts/transition_task.py --role QA --from-status 测试中 --to-status 已完成 ...` |
| **PM 验收终态**| PM | 终态记录 | 终态验收评级、文档结项 | `python3 scripts/transition_task.py --role PM --from-status 已完成 --to-status 已验收 ...` |

---

## 💾 3. 记忆持久化与状态共享

1. **绝对禁止隐式口头传达**：所有的流转说明必须显式写落盘至 `docs/reports/` 中的 Markdown 报告或看板 `remarks` 字段中。
2. **上下文按需载入**：接收角色激活时，使用 `view_file` 仅调阅上一阶段角色提交的 `report_path` 与对应的代码改动 `modified_files`，保持 Token 上下文精准精简。
