# 开发任务报告（按工作包归档）

> **阶段**：${STAGE_NAME}
> **工作包**：${WORKPACKAGE_NAME}
> **负责人**：${DEV_NAME}
> **起始日期**：${START_DATE}

---

## 任务详情：${TASK_ID} - ${TASK_NAME}

| 字段 | 值 |
|------|-----|
| 执行人 | ${DEV_NAME} |
| 日期 | ${DATE} |
| 状态 | [OK] 已开发 · 待审查（待 REVIEWER） |
| 关联任务 ID | ${TASK_ID} |

### 1. 问题背景
${PROBLEM_BACKGROUND}

### 2. 解决方案
${SOLUTION_DESCRIPTION}

### 3. 关键实现（片段）
```python
# 示例代码实现片段
```

### 4. 影响范围
- **修改文件**：${MODIFIED_FILES}
- **测试文件**：${TEST_FILES}

### 5. 单元测试结果
- ${UNIT_TEST_RESULTS} (覆盖率需 > 80%)

---

## 9. 返工 / 修订记录

### 轮次 1：退回缺陷针对性修复（${DATE}）
- **退回来源**：周审查代码审查 / 章测试集成测试
- **缺陷编号**：`DEF-${TASK_ID}-1`
- **修复说明**：${FIX_SUMMARY}
- **复验结果**：单元测试通过
