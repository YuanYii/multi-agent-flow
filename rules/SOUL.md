# SOUL.md - 行为原则与防错控制心脏

> 本文档是 Multi-Agent Team Workflow Skill 的安全控制核心，任何 Agent 均不得违反本文件定义的红线。

---

## ⚡ 核心原则 (Core Tenets)

1. **事实高于推论 (Fact > Impression)**：
   反驳或判断状态必须以代码、单测输出、日志或看板真实 API 返回为依据，严禁凭印象乱判断。
2. **状态与处理人同生共死 (Atomic Update)**：
   每次变更看板 `状态` 时，必须原子级同步更新 `处理人` (Assignee)。
3. **缺陷溯源不切碎 (Non-Fragmented Defect Tracking)**：
   打回绝不派生新任务编号，缺陷结构化写入原任务 `备注`。
4. **复验结论追加不割裂 (Appended Audit)**：
   复审与复测结论直接追加至原报告，禁止独立新建孤儿复审/复测文件。

---

## 🛡️ 状态防错矩阵

完整的防错门控、拦截处理与提权代行逻辑详见指引：
👉 [`../references/03-Anti-Error-Mechanism.md`](../references/03-Anti-Error-Mechanism.md)
