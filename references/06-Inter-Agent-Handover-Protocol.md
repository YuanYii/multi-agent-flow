# 06-Inter-Agent-Handover-Protocol.md (专家 Agent 间任务交接与消息总线协议)

> 规范多 Agent 协同流转时的上下文 Payload 载荷结构、记忆持久化与交接契约。

---

## 1. 消息总线与交接 Payload 契约

当上一阶段角色完成任务并将控制权移交给下一个角色（如 DEV -> REVIEWER，或 REVIEWER -> QA）时，必须在交接消息或存储中携带**强类型结构化 Context Payload**：

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
    "test_summary": {
      "exit_code": 0,
      "total": 8,
      "passed": 8
    },
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

## [SYNC] 2. 8 大角色标准交接动作矩阵

> [!NOTE]
> **跨平台提示**：以下命令在 Linux/macOS 下使用 `python3`，Windows 环境请自动替换为 `python`。

| 流转方向 | 发起角色 | 接收角色 | 必填交接产物 (Required Artifacts) | 门控校验脚本调用命令 |
| :--- | :--- | :--- | :--- | :--- |
| **自领取** | PM/看板 | DEV / FRONTEND | WBS 任务包条目、需求约束 | `python3 scripts/transition_task.py --role DEV --from-status 待开始 --to-status 进行中 ...` (FRONTEND 同命令,仅 `--role` 改) |
| **提代码审查**| DEV / FRONTEND | REVIEWER | 修改代码列表、单测退出码 0 与通过数凭据 (回写 remarks 或工单 return_contract) | `python3 scripts/transition_task.py --role DEV --from-status 进行中 --to-status 审查中 --remarks "单测全部通过(退出码0)" ...` |
| **审查通过** | REVIEWER | QA | 审查结论通过项、安全/规范评估 (回写看板 remarks) | `python3 scripts/transition_task.py --role REVIEWER --from-status 审查中 --to-status 测试中 --remarks "代码审查通过，静态扫描合规" ...` |
| **审查打回** | REVIEWER | DEV / FRONTEND | 结构化缺陷信息 `DEF-TXXX-N` | `python3 scripts/transition_task.py --role REVIEWER --from-status 审查中 --to-status 已退回 --remarks "【打回】DEF-TXXX-1 根因与修复指引" ...` |
| **测试通过** | QA | PM | 功能与集成用例复验凭据、实际工时、`end_time` | `python3 scripts/transition_task.py --role QA --from-status 测试中 --to-status 已完成 --end-time "..." --remarks "集成用例通过" ...` |
| **人类验收终态**| PM / 人类用户 | 终态归档 | 阶段交付总结与验收标准结项 (Agent 严禁代签) | 由人类用户在终端执行 `python3 scripts/quick_task.py accept --task-id <ID>` 或在 Web 看板点击验收 |

---

## 3. 记忆持久化与状态共享

1. **绝对禁止隐式口头传达**：日常流转说明必须显式回写至看板 `remarks` 字段、工单流转节点或结构化回执中；阶段性重大里程碑（阶段架构技术总结/PM复盘报告）归档至**项目文档的阶段总结目录**（推荐 `<docs_root>/D04-研发过程/D02-报告/summary/`，或项目配置声明的 `summary_dir`，自适应宿主既有文档架构）。
2. **上下文按需载入**：接收角色激活时，直接调阅任务工单契约、上一阶段角色提交的自测凭据与对应的代码改动，保持 Token 上下文精准精简。

---

## 4. 虚拟角色边界与通知通道铁律 (Virtual Agent vs. External IM Boundary)

1. **虚拟专家身份定界**：
   - 工作流内 8 大专家角色（严经理/钱架构/李开发/马前端/周审查/章测试/李文通/吕改特）均为**系统虚拟 AI 专家子代理 (Subagent)**，绝非企业真实通讯录中的自然人。
   - [FAILED] **严禁**调用任何外部 IM 工具（如飞书、钉钉、企业微信、Slack 等 MCP 通讯录接口）在通讯录中按虚拟人名检索（如搜索“吕改特”、“李开发”）或发起单聊私信。
2. **内部协同法定通知载体**：
   - [SUCCESS] **看板任务卡指派即通知**：调用 `transition_task.py` 更新状态与处理人（`--assignee`）是系统内唯一法定任务分派与通知凭据。
   - [SUCCESS] **子代理消息总线**：进程内通过 `invoke_subagent` 或上下文 Payload 进行无缝调度。
3. **外部通信通道与白名单**：
   - 仅在配置文件（`workflow.config.yaml`）中开启了群机器人 Webhook 时，允许向项目群广播阶段性流转卡片；
   - 仅在用户显式指定人类负责人（如 `USER` 或配置文件中绑定的真实人类 OpenID/邮箱）时，方可向真实自然人发送外部通知。
