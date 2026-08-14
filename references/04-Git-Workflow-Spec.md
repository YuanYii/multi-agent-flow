# 04 - Git 分支模型与版本发布规范

> **全规约导航**：[01 主索引](01-AI-Team-Workflow-Index.md) | [02 状态推导](02-State-Flow-Rules.md) | [03 防错机制](03-Anti-Error-Mechanism.md) | [05 文档管理](05-Document-Management-Spec.md) | [06 交接协议](06-Inter-Agent-Handover-Protocol.md)

---

> **本文件说明**：定义软件研发团队的分支模型、命名约定与 Commit 提交规范。

---

## 一、三层分支模型

```text
main (定版) ───────只接受来自 stage 的合并 (发布打 Tag)
  ↑
stage/S<阶段> ─────只接受来自 feature 的合并 (集成测试)
  ↑
feature/S<阶段>-<功能> ──功能负责人开发提交
```

| 分支层级 | 命名约定 | 生命周期 | 权限与保护 |
|---------|----------|----------|-----------|
| **主分支** | `main` | 永久保护 | 禁止直接 push，仅限 DevOps 阶段发布合并 |
| **阶段分支** | `stage/S<阶段号>` (如 `stage/S1`) | 阶段结束后保留 | 仅限 DevOps 合并 |
| **功能分支** | `feature/S<阶段号>-<功能>` (如 `feature/S1-event-router`) | 合并后保留作为历史 | 开发专家 (DEV/FRONTEND) 自由提交 |
| **前端功能分支** | `feature/fe-S<阶段号>-<功能>` (如 `feature/fe-S1-kanban-board`) | 合并后保留作为历史 | 前端专家 (FRONTEND) 自由提交 |
| **热修复** | `hotfix/<问题描述>` (如 `hotfix/fix-token-leak`) | 临时，修复后合并 | 仅限 DevOps 合并 |

---

## 二、Commit 规范 (Conventional Commits)

### 1. 提交格式
```text
<类型>(<范围>): <简短描述>
```

### 2. 推荐 Type 类型

| Type 类型 | 含义 | 示例 |
|-----------|------|------|
| `feat` | 新功能/新特性 | `feat(api): 新增事件路由 HTTP endpoint` |
| `feat(fe)` | 前端新功能/UI 组件 | `feat(fe): 新增看板任务详情 Modal` |
| `fix` | Bug 修复 | `fix(parser): 修复空日志行反序列化异常` |
| `fix(fe)` | 前端 Bug 修复 | `fix(fe): 修复看板筛选条件持久化丢失` |
| `test` | 单元测试/集成测试 | `test(w1): 新增风暴检测单元测试` |
| `docs` | 技术文档/报告更新 | `docs: 更新 S1 阶段技术方案` |
| `refactor` | 代码重构 (不改变外部行为) | `refactor(schema): 简化 Pydantic v2 模型` |
| `chore` | 构建/工具链/环境配置 | `chore: 更新 pyproject.toml 依赖` |

### 3. 描述要求
- 使用中文表达清晰，说明“做了什么”，不超过 25 个字符；
- 末尾不加句号；
- 不在 Commit 中硬编码密码、Token 等敏感数据。

---

## 三、版本标签规范 (SemVer)

阶段集成完成后，DevOps 在 `main` 分支统一打版本标签：
```text
v<主版本>.<次版本>.<修订版本>-S<阶段号>
```
**示例**：`v1.0.0-S1`，`v1.2.0-S2`
