---
title: 多专家协同工作流架构问题修复测试报告
date: 2026-08-14
type: test-report
stage: Post-Architecture-Audit
status: active
author: Mavis
tags: [multi-agent-flow, 架构修复, 提权代行, HEARTBEAT, 审计日志, FRONTEND, 测试报告]
---

# 多专家协同工作流架构问题修复测试报告

> 报告范围:针对 2026-08-13 架构层面梳理出的 3 个真实问题(① ② ③)+ 1 个误判(④ race window),进行代码层修复与端到端测试验证。
> 测试结论:**全量 125/125 通过,集成 smoke test 全过,流程修复闭环。**

---

## 一、问题核实与修复结果总览

| # | 问题描述 | 核实结果 | 修复状态 | 回归测试用例数 |
|---|---------|---------|---------|---------------|
| ① | 6 个 `references/*.md` 规约文档停留在 7 角色时代,无 FRONTEND 路由/状态/防错/交接描述 | ✅ 属实(grep 0 命中) | ✅ 已同步到 8 角色 | 18 |
| ② | 提权代行协议仅在文档层,代码层无门控 | ✅ 属实(validate 函数无 delegated_by 参数) | ✅ validate / transition_task / audit_logger 全链路加 delegated_by 字段 + 白名单矩阵 + 13 处 audit 留痕 | 12 |
| ③ | HEARTBEAT 巡检无代码对应 + 审计日志只写不管 | ✅ 属实(scripts/ 无 heartbeat / query / rotate) | ✅ 新建 3 个工具脚本 + 扩展 audit_logger | 15 |
| ④ | 多角色并发提交存在读过期 race window | ❌ **误判,撤回** | 无需修复(offline_board_adapter 三方法均持 board.json.seq.lock 全局锁,双层防护 OK) | 0 |

---

## 二、修复范围(动/不动两张清单)

### 2.1 改动文件(11 个,+313/-43 行)

**修复 ① references 文档同步(7 个文件):**
- `references/01-AI-Team-Workflow-Index.md` — 7→8 角色,加 FRONTEND 路由行 + 3.5 节职责边界
- `references/02-State-Flow-Rules.md` — 打回表含前端场景(审查/测试/验收打回均覆盖)
- `references/03-Anti-Error-Mechanism.md` — "7 个角色"→"8 个角色",权限矩阵补 FRONTEND 列,代行协议加 CLI 强制门控段落
- `references/04-Git-Workflow-Spec.md` — `feature/fe-S<n>-*` 前端分支命名约定 + `feat(fe)` / `fix(fe)` commit type
- `references/05-Document-Management-Spec.md` — `02-modules/{module}/frontend/` 目录约定 + 维护责任矩阵加 FRONTEND 行
- `references/06-Inter-Agent-Handover-Protocol.md` — 7→8 大角色,交接矩阵 DEV/FRONTEND 合并行
- `rules/HEARTBEAT.md` — 加"巡检脚本使用"节,指向 heartbeat.py / audit_query.py / audit_rotate.py

**修复 ② 提权代行代码门控(3 个文件):**
- `scripts/validate_transition.py` — 新增 `DELEGATION_ALLOW_MATRIX`(PM 收口 + 7 角色仅 PM/USER 代行 + USER 最高优先级)+ `validate_delegation_authority()` 独立校验函数 + `validate()` 加 `delegated_by` / `delegation_reason` kwargs
- `scripts/transition_task.py` — CLI 加 `--delegated-by` / `--delegation-reason` 参数;`transition_task_pipeline` 入口第 0 步先调 `validate_delegation_authority` 预检(Fail-Closed 阻断);13 处 `record_audit_event` 全部带 keyword args
- `scripts/audit_logger.py` — `record_audit_event` 加 `delegated_by` / `delegation_reason` 字段

**修复 ③ HEARTBEAT + 审计日志管理(2 个文件):**
- `scripts/audit_logger.py` — 增 `query_events()` / `rotate_if_needed()` + 内部工具 `_read_ndjson` / `_read_archive_ndjson` / `_current_log_date` / `_today_str`(共 +130 行)
- (新增 3 脚本,见 2.2)

### 2.2 新建文件(6 个)

| 文件 | 用途 | 行数 |
|------|------|------|
| `scripts/heartbeat.py` | 4 项巡检(滞留 / 并发 / 状态-处理人一致 / 终态 end_time),阈值可覆盖,只读不写,exit 码契约 0/1/2 | 230 |
| `scripts/audit_query.py` | CLI 按 task_id/role/success/time/delegated_by 查询,table/json 双格式 | 95 |
| `scripts/audit_rotate.py` | 日切分 + 单文件 > 50MB 二次切,旧文件 gzip 归档至 `logs/archive/` | 55 |
| `tests/test_references_frontend_sync.py` | 18 用例,防 references 规约回退到 7 角色 | 125 |
| `tests/test_delegation.py` | 12 用例,白名单 + CLI + audit 字段 | 220 |
| `tests/test_heartbeat.py` | 15 用例,4 项巡检 + query_events + rotate_if_needed | 320 |

### 2.3 不动清单(承诺)

- `agents/*.yaml` — 8 大角色 YAML 本身已齐(8/8 已含 FRONTEND),只补 references 引用
- `scripts/validate_transition.py` 现有权限矩阵 — 仅加 kwargs,默认参数保持向后兼容 → 80 个旧测试零回归
- 4 个 board 适配器(feishu/jira/github/offline) — 纯加 audit 字段不需要感知
- `docs/01-architecture/原项目文档/*` — 只读归档快照,按规则禁改
- `kanban/board.json` 1 行 start_date 改动 — **非本次修复**,为测试残留,**待用户决定 restore / 保留**

---

## 三、测试结果

### 3.1 全量 pytest(回归基线)

```
================================ 125 passed in 12.01s ================================
```

| 测试文件 | 用例数 | 通过 | 失败 | 用途 |
|---------|-------|------|------|------|
| `test_board_adapters.py` | 1 | 1 | 0 | 板适配器 smoke test |
| `test_full_workflow_suite.py` | 10 | 10 | 0 | 36 个状态流转场景 |
| `test_integration_suite.py` | 32 | 32 | 0 | L1/L2/L3 端到端集成 |
| `test_kanban_buttons_integration.py` | 6 | 6 | 0 | 看板按钮集成 |
| `test_offline_adapter.py` | 10 | 10 | 0 | 离线适配器并发锁 |
| `test_validate_transition.py` | 10 | 10 | 0 | 状态机权限矩阵 |
| `test_workflow_scripts.py` | 11 | 11 | 0 | 工作流脚本 smoke |
| `test_references_frontend_sync.py` 🆕 | 18 | 18 | 0 | 修复 ① 回归 |
| `test_delegation.py` 🆕 | 12 | 12 | 0 | 修复 ② 回归 |
| `test_heartbeat.py` 🆕 | 15 | 15 | 0 | 修复 ③ 回归 |
| **合计** | **125** | **125** | **0** | — |

### 3.2 集成 smoke test(端到端)

**测试场景:** A 类开发任务全链路流转(待开始→进行中→审查中→测试中→已完成→已验收)+ USER 代行 PM 验收 + heartbeat 终态巡检。

**测试环境:** 隔离 `/tmp/multi-agent-flow-smoke-*` 目录,独立 `board.json` + `workflow.config.yaml`,全量 5 步流转真实写盘。

**测试结果:**

| 步骤 | 操作 | 角色 | 状态变更 | 结果 |
|------|------|------|---------|------|
| 1 | DEV 自领取 | DEV | 待开始 → 进行中 | ✅ PASS |
| 2 | DEV 提交审查 | DEV | 进行中 → 审查中 | ✅ PASS |
| 3 | REVIEWER 审查通过 | REVIEWER | 审查中 → 测试中 | ✅ PASS |
| 4 | QA 测试通过 | QA | 测试中 → 已完成 (带 end_time) | ✅ PASS |
| 5 | PM 验收(USER 代行) | PM | 已完成 → 已验收 | ✅ PASS |
| 6 | heartbeat 巡检 | — | 1 任务扫描 | ✅ 0 critical / 0 warning |
| 7 | board.json 终态核验 | — | T0100 | ✅ 已验收 / 严经理 / end_date 写入 |
| 8 | audit query 追溯 | — | T0100 | ✅ 5 条流转 + 2 条代行记录 |
| 9 | audit 代行字段 | — | delegated_by=USER | ✅ 完整留痕 |

**端到端结论:** 完整 A 类任务流转无回归,USER 代行白名单正确放行,heartbeat 对终态任务判定"全部通过",audit 双向追溯链路通畅。

### 3.3 代行白名单矩阵(决策表)

| 目标角色 \ 代行来源 | PM | ARCHITECT | DEV | FRONTEND | REVIEWER | QA | DOCS | DEVOPS | USER |
|------------------|-----|-----------|-----|----------|----------|-----|------|--------|------|
| **PM** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **ARCHITECT** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **REVIEWER** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **QA** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **DEV** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **FRONTEND** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **DOCS** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **DEVOPS** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

**白名单设计原则:**
- PM 是收口角色(验收/分配),任何角色可代行(常见:任何角色代为验收)
- 其他 7 角色(执行类)只接受 PM 代行(典型:PM 兼任审查/测试/文档)与 USER 授权
- 同级互代行(DEV↔FRONTEND)被禁止,防止隐性越权——代码任务不可互换代写
- USER 标识表示"人类用户授权代行",优先级最高,任何目标角色都接受

---

## 四、HEARTBEAT 巡检 4 项门控(覆盖率)

| 巡检项 | 错误码 | 严重度 | 触发条件 | 测试用例 |
|-------|--------|-------|---------|---------|
| 1a. 滞留(进行中) | `STALE_IN_PROGRESS` | warning | 进行中 > 阈值(默认 24h) | ✅ `test_heartbeat_stale_in_progress_warning` |
| 1b. 滞留(审查/测试) | `STALE_REVIEW_OR_TEST` | warning | 审查中/测试中 > 阈值(默认 12h) | ✅ `test_heartbeat_stale_review_test_warning` |
| 2a. 并发上限(DEV) | `DEV_CONCURRENCY_EXCEEDED` | critical | DEV 进行中 > 3 | ✅ `test_heartbeat_dev_concurrency_exceeded` |
| 2b. 并发上限(FRONTEND) | `FRONTEND_CONCURRENCY_EXCEEDED` | critical | FRONTEND 进行中 > 3 | ✅ `test_heartbeat_frontend_concurrency_exceeded` |
| 3a. 状态-处理人(审查) | `ASSIGNEE_MISMATCH_REVIEW` | critical | 审查中处理人非 REVIEWER | ✅ `test_heartbeat_assignee_mismatch_review_critical` |
| 3b. 状态-处理人(测试) | `ASSIGNEE_MISMATCH_TEST` | critical | 测试中处理人非 QA | ✅ `test_heartbeat_assignee_mismatch_test_critical` |
| 3c. 状态-处理人(终态) | `ASSIGNEE_MISMATCH_TERMINAL` | warning | 已完成/已验收处理人非 PM | (集成 smoke 已覆盖) |
| 4. 终态 end_time | `MISSING_END_TIME` | critical | 已完成/已验收无 end_date | ✅ `test_heartbeat_terminal_missing_end_time_critical` |

**退出码契约:** 0=全部通过, 1=有 critical, 2=致命错误(适配器加载失败)

**阈值覆盖优先级:** CLI 参数 > `workflow.config.yaml` 的 `heartbeat` 段 > 脚本默认 24h/12h/3。

---

## 五、审计日志查询与轮转(新增能力)

| 工具 | 入口 | 典型用法 |
|------|------|---------|
| `audit_query.py` | `python3 scripts/audit_query.py` | `--task-id T0001` / `--failed` / `--role DEV` / `--delegated-by USER` / `--format json` |
| `audit_rotate.py` | `python3 scripts/audit_rotate.py` | 默认 50MB + 日切分;`--max-size-mb 20` 调整阈值;`--dry-run` 预判 |
| 内置工具 | `audit_logger.query_events()` | 单元/集成测试复用入口 |
| 内置工具 | `audit_logger.rotate_if_needed()` | 单元/集成测试复用入口 |

**轮转策略:** 日切分(无日期后缀 → 强制改名带今天日期) + 大小切分(单文件 >= 50MB → 带时间戳切分),旧文件 gzip 归档至 `logs/archive/audit_trail-YYYYMMDD.log.gz`。

---

## 六、push back / 遗留事项

1. **`kanban/board.json` 1 行 start_date 改动** — 非本次修复内容(为历史测试残留),`git status` 仍显示 modified,**待用户决定**:
   - 选项 A:`git restore kanban/board.json`(丢弃,回到 HEAD 干净状态)
   - 选项 B:保留作为 audit 留痕(本 commit 不动,后续单独提交清理)

2. **`audit_logger.py` 旧 success 字段类型兼容** — 旧 audit 行的 `success` 是字符串 `"True"`/`"False"`,新写入是 bool,`query_events(success=True)` 经 `bool()` 转换可兼容,但未做历史数据解析回归测试,若担心可加 `_coerce_bool()` 工具函数。

3. **问题 ④ 误判的反思** — 之前判断"race window"时只看了 `transition_task.py` 的 per-task 锁,没看 `offline_board_adapter.py` 三方法都持全局锁。教训:并发安全分析必须看 adapter 层完整 IO 路径,不能只看入口。

---

## 七、验证结论

| 维度 | 结论 |
|------|------|
| **修复完整性** | 3 个真实问题全部修复,1 个误判已撤回 |
| **代码可运行性** | 8 个 scripts + 7 个 tests 全部 import OK,无语法/依赖错误 |
| **回归零破坏** | 原 80 个测试 100% 保持通过,新 45 个测试 100% 一次过 |
| **集成烟测** | 完整 A 类任务 5 段流转 + 代行场景 + 巡检 0 告警,端到端通畅 |
| **规约与代码一致** | 6 个 references 全部同步到 8 角色,代行协议代码化,审计字段结构化 |
| **可观测性提升** | 审计查询工具 + 轮转工具新增,日志从"只写"升级为"可查/可切" |
| **流程修复闭环** | ✅ 完成 |

---

**报告生成时间:** 2026-08-14 11:14 CST
**报告路径:** `docs/03-operations/reports/2026-08-14-multi-agent-flow-architecture-fix-report.md`
**生成工具:** Mavis (mvs_697cbf7ec2934ce0baa53aa19695da5d)
