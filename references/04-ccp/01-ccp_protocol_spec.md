# 04-上下文连续性协议规约 (Context Continuity Protocol Spec)

> 详细架构方案请参阅项目设计方案库中的标准规范：
> `docs/1-方案设计/08-Context_Continuity_Protocol_上下文连续性协议架构设计方案.md`

## 一、 CCP 核心哲学与三元对象

1. **Context State (全局事实源)**：项目的真实状态，涵盖需求、约束、不变量、决策、状态、假设、未知与产物。
2. **Handoff Context (最小充分投影)**：针对特定 Agent 与 Task 裁剪的最小必要信息，杜绝对话全量复制带来的上下文膨胀。
3. **Result Delta (结构化增量回写)**：任务完成后提取的物理变更（Git diff）与认知事实（新决策、新假设），原子合并回 Context State。

---

## 二、 连续性校验 4 大状态

- **READY**：上下文完备，无二义性与冲突，放行执行；
- **INCOMPLETE**：缺少 `must_know` 关键字段，自动退回上游补全；
- **AMBIGUOUS**：存在阻断性未知项或多重解释，触发定向排歧提问；
- **CONFLICTED**：多源事实逻辑冲突，触发架构仲裁或人工介入。
