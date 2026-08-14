# 文档任务报告

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
| 状态 | [OK] 文档已完成 · 待 PM 验收 |
| 关联任务 ID | ${TASK_ID} |

### 1. 文档产出清单
- **产出文档**：${DOC_PATHS}
- **文档类型**：${DOC_TYPE}（如 README / 设计规格 / 操作手册 / 标准规范）
- **存放位置**：${DOC_LOCATION}

### 2. 文档结构合规性校验
- **Frontmatter 元数据**：[SUCCESS] 已包含（title / status / updated_at）
- **目录深度**：[SUCCESS] ≤ 3 级（遵循 docs/ 目录规范）
- **术语一致性**：[SUCCESS] 已统一（${TERMINOLOGY_NOTES}）

### 3. 关联引用与交叉链接
- **引用文档**：${REFERENCED_DOCS}
- **待补充链接**：${PENDING_LINKS}

### 4. 文档审阅记录
- **审阅人**：${REVIEWER_NAME}
- **审阅结论**：${REVIEW_RESULT}

---

## 9. 返工 / 修订记录

### 轮次 1：退回缺陷针对性修复（${DATE}）
- **退回来源**：PM 验收退回
- **缺陷编号**：`DEF-${TASK_ID}-1`
- **修复说明**：${FIX_SUMMARY}
- **复验结果**：文档结构校验通过
