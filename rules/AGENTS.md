# AGENTS.md - 多专家团队协同研发工作区

欢迎来到 **多专家协同研发工作流 (Multi-Agent Team Workflow)** 工作区。本文档定义了 AI Agent 在多角色研发环境下的交互契约与协作红线。

---

## 🧭 动态按需加载协议 (Lazy Load Protocol)

执行协同任务或推导状态流转时，**必须按需调阅 `../references/` 中的规范文件**：
1. **角色边界**：调阅 [`../references/01-AI-Team-Workflow-Index.md`](../references/01-AI-Team-Workflow-Index.md)
2. **状态流转矩阵**：调阅 [`../references/02-State-Flow-Rules.md`](../references/02-State-Flow-Rules.md)
3. **防错闭环与提权门控**：调阅 [`../references/03-Anti-Error-Mechanism.md`](../references/03-Anti-Error-Mechanism.md)
4. **Git 与版本规范**：调阅 [`../references/04-Git-Workflow-Spec.md`](../references/04-Git-Workflow-Spec.md)

---

## 🧠 看板状态不变量

- **原子更新**：看板 `状态` (Status) 与 `处理人` (Assignee) 必须同步变更。
- **结束时间**：任务推至 `已完成` / `已验收` 前强制写入 `结束时间`。

---

## 🚫 团队协作 4 大红线 (Red Lines)

1. **绝对禁止越权修改状态**：不在操作人集合内的角色禁止推动状态（提权需显式声明代行协议）。
2. **打回绝对禁止新建任务编号**：任何审查/测试退回必须在**原任务**上改状态为 `已退回`，并在备注写入 `DEF-TXXX-N`。
3. **绝对禁止先干后补**：自领取任务时，必须先将看板状态修改为 `进行中` 并落库，方可开始编码。
4. **绝对禁止生成孤儿复审/复测报告**：退回修复后的结论必须追加至原报告，不新建碎片文档。
