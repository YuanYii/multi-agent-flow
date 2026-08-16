# 项目通用文档管理规范标准 (V2.0 现代精简版)

> **全规约导航**：[01 主索引](01-AI-Team-Workflow-Index.md) | [02 状态推导](02-State-Flow-Rules.md) | [03 防错机制](03-Anti-Error-Mechanism.md) | [04 Git规范](04-Git-Workflow-Spec.md) | [06 交接协议](06-Inter-Agent-Handover-Protocol.md)

> 本规范定义了项目工程文档的扁平化目录架构、Frontmatter 元数据格式、模块化划分与过程草稿隔离机制。

---

## 目录与层级约束 (Flat & Semantic)

项目工程文档（存放于 `docs/` 或 `项目文档/`）遵循以下层级与分类原则：

1. **路径深度约束**：从 `docs/` 根目录算起的路径深度绝对**不得超过 3 级**（如：`docs/{一级分类}/{二级目录或模块}/{文件}.md`）。
2. **统一语义命名**：废除 `A01`, `B01` 等抽象代号，目录定义统一使用中文语义化命名。
### 3. 临时文档与隔离机制
* 禁止在项目根目录或 `docs/` 顶层直接散落临时笔记或测试导出的 markdown 文件。
* 未定稿草稿与中间过程调试产出统一放置在 `草稿箱/` 目录。
* 项目根目录的 `.gitignore` 必须显式忽略 `草稿箱/`。

### 4. 原项目文档只读保留原则 (Read-Only Legacy Governance)
* **绝对禁止改动源文档**：初始化归档采用纯只读镜像拷贝（`copy2`），原路径下的源文档与 `docs/*/原项目文档/` 下的副本均属于只读历史资产。
* **禁止覆盖或剪切**：Agent 在执行任务时，绝对禁止修改、剪切、删除或覆写原项目文档中的任何文字、结构与标头。

### 标准目录架构

```text
docs/
├── README.md                          # 全局文档入口与导航地图
├── CONTRIBUTING.md                    # 文档贡献与维护指南
├── 01-架构设计/                        # 系统级架构与技术方案
│   ├── 原项目文档/                     # 原工程历史架构/设计文档归档区
│   ├── 01-系统总体架构设计.md
│   ├── 02-技术选型与可行性分析.md
│   └── 03-数据结构与接口规约.md
├── 02-业务模块/                        # 业务模块目录（按功能内聚）
│   ├── 原项目文档/                     # 原工程历史模块设计归档区
│   ├── {module-A}/                    # 业务模块 A（例如：log-parser）
│   │   ├── README.md                  # 模块功能概述
│   │   ├── design.md                  # 模块详细设计规格
│   │   ├── frontend/                  # [FRONTEND 角色专属] UI/组件/微交互产出
│   │   │   ├── components.md          # 组件清单与接口契约
│   │   │   └── ux-spec.md             # UX 交互规格与可访问性约束
│   │   └── troubleshooting.md         # 模块专属踩坑与排查记录
├── 03-研发过程/                        # 研发过程管理与交付产出
│   ├── 原项目文档/                     # 原工程历史任务/部署/报告归档区
│   ├── 任务/                          # 任务拆解与工作包 (Work Packages)
│   ├── 报告/                          # 阶段测试/代码审查/质量总结报告
│   └── 操作手册/                       # 平台部署与操作手册
├── 04-规范标准/                        # 规范体系（工程、流程、协作）
│   └── 原项目文档/                     # 原工程历史编码/流程规范归档区
├── 05-文档模板/                        # 各类文档标准化模板
└── 草稿箱/                            # 临时文档与草稿中转区（写入 .gitignore）
```

---

## 标签与 Frontmatter 元数据规范

所有存放于仓库中的 Markdown 文档，顶部**必须**附带标准 YAML 元数据标头：

```markdown
---
title: 日志解析引擎详细设计规格
module: log-parser
stage: Phase-2
type: design-spec
status: active
author: 张架构
updated_at: 2026-08-07
tags: [架构, 日志处理, 解析器]
---
```

### 关键字段说明
* `title`: 文档标题。
* `module`: 归属的具体业务模块（适用于 `modules/` 目录下的文档）。
* `stage`: 关联的开发阶段或 Milestone（如 `Phase-1`, `S2`）。
* `type`: 文档类型分类（`design-spec` | `test-report` | `task` | `guide` | `standard`）。
* `status`: 文档生命周期状态（`draft` 草稿 | `active` 生效中 | `deprecated` 已废弃）。

---

## 命名后缀与分类规约

* **模板文件**：统一添加后缀 `-template.md`（如 `task-breakdown-template.md`）。
* **强制规范**：统一添加后缀 `-standard.md`（如 `git-workflow-standard.md`）。
* **指导建议**：统一添加后缀 `-guide.md`。

---

## 维护与更新责任矩阵

| 触发场景 | 更新责任人 | 更新要求 |
| :--- | :--- | :--- |
| **整体架构/选型变更** | 架构师 (ARCHITECT) | 24 小时内更新 `01-架构设计/` 下对应文档，同步修改相关 Frontmatter 版本。 |
| **模块内部设计变更** | 开发工程师 (DEV) | 同步更新 `02-业务模块/{module-name}/design.md`。 |
| **前端 UI/组件变更** | 前端工程师 (FRONTEND) | 同步更新 `02-业务模块/{module-name}/frontend/components.md` 与 `ux-spec.md`。 |
| **阶段/里程碑完成** | 运维/质量/PM | 在 `03-研发过程/报告/` 集中输出阶段报告，清理 `草稿箱/` 中的临时草稿。 |
| **文档生态维护与治理** | 文档工程师 (DOCS) | 负责全局术语标准化、Frontmatter 校验与导航入口 (`README.md`) 维护。 |
