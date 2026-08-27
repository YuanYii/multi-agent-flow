# Multi-Agent Flow · 全量代码审查与冗余逻辑分析报告

> **处置进度（2026-08-27 复审）**：死代码 #1~#3 已在 commit a94f44a 清除；死代码 #4（docx_academic_styler 未闭环）与重复逻辑 #2（Word 排版函数多头维护）已合并处置——两个 docx 生成脚本已重构为消费 `_lib/core/docx_academic_styler.py` 公共模块；重复逻辑 #1（角色归一化双头维护）已收敛至 `scripts/enums.py` 单一来源。

> **报告版本**：v1.0.0  
> **审查日期**：2026-08-26  
> **审查范围**：全量 Python 源码 (`scripts/`、`scripts/_lib/`)、测试套件 (`tests/`)、Web 看板 (`kanban/js/`) 与前端资源  
> **审查工具与方法**：AST 抽象语法树静态分析、跨模块调用拓扑扫描、词边界引用检索与运行态验证  

---

## 一、 审查综述与统计

经对代码库 77 个 Python 文件、13 个前端 JS 文件及全部测试资产的系统性扫描，项目整体架构分层清晰，模块职责明确。本次审查重点聚焦于**未调用的死代码 (Dead Code)**、**多头维护的重复逻辑 (Duplicate Logic)**、**冗余导入 (Unused Imports)** 以及 **未闭环的公共排版模块**。

### 核心发现统计

| 审查维度 | 发现数量 | 影响等级 | 核心涉及模块 |
| :--- | :---: | :---: | :--- |
| **明确的废弃方法与死代码** | 4 处 | 中 (冗余开销) | `build_agent_context.py`, `file_lock.py`, `board_adapter_factory.py`, `docx_academic_styler.py` |
| **跨模块同名与重复逻辑** | 2 组 | 中 (维护一致性隐患) | `start_kanban_server.py` 角色归一化、Word 排版辅助函数 |
| **未使用的冗余 Import** | 10+ 处 | 低 (代码整洁度) | `auto_task.py`, `check_secrets.py`, `transition_task.py`, `test_domain_packages.py` 等 |

---

## 二、 明确的废弃方法与死代码清单

以下方法与全局变量在整个代码库（包括所有业务脚本、适配器与测试套件）中**无任何有效调用或消费**：

### 1. `scripts/build_agent_context.py` 中的 `read_markdown_section`
- **文件路径**：[`scripts/build_agent_context.py`](../scripts/build_agent_context.py)
- **位置**：第 37 ~ 42 行
- **代码片段**：
  ```python
  def read_markdown_section(filepath: str, max_lines: int = 40) -> str:
      if os.path.exists(filepath):
          with open(filepath, "r", encoding="utf-8") as f:
              lines = [line for line in f if line.strip() and not line.startswith('# ')]
              return "".join(lines[:max_lines])
      return ""
  ```
- **现状分析**：该函数原意为从 Markdown 文档截取段落，但 Prompt 上下文合成已全部重构为结构化字典与 YAML 模板，该函数全库 **0 调用**；同时头部定义的常量 `RULES_DIR`、`REFERENCES_DIR` 及 `import sys` 也未被使用。
- **处置建议**：删除该函数、未使用常量及冗余导入。

### 2. `scripts/_lib/core/file_lock.py` 中的 `read_lock_meta`
- **文件路径**：[`scripts/_lib/core/file_lock.py`](../scripts/_lib/core/file_lock.py)
- **位置**：第 174 ~ 193 行
- **代码片段**：
  ```python
  def read_lock_meta(lock_path):
      """读取锁文件元数据 {pid, ts}；文件不存在或不可读时返回空 dict。"""
      # ...
  ```
- **现状分析**：用于解析锁文件内部的 PID 和时间戳。但当前 `FileLock` 争抢判定与 `safe_unlink_lock` 均采用 POSIX/Windows 独占非阻塞试锁机制，未消费该函数，属**未接入的死代码**。
- **处置建议**：可安全移除，或在心跳检测孤儿锁时接入。

### 3. `scripts/_lib/boards/board_adapter_factory.py` 中的 `exponential_backoff_retry`
- **文件路径**：[`scripts/_lib/boards/board_adapter_factory.py`](../scripts/_lib/boards/board_adapter_factory.py)
- **位置**：第 18 ~ 34 行
- **代码片段**：
  ```python
  def exponential_backoff_retry(max_retries: int = 3, initial_delay: float = 1.0):
      """通用 API 请求指数退避重试装饰器"""
      # ...
  ```
- **现状分析**：定义了通用网络重试装饰器，但实际的三大远程适配器（`FeishuBaseAdapter` / `JiraAdapter` / `GitHubProjectsAdapter`）各自实现了独立的超时/重试控制，**该装饰器未被任何适配器挂载**。
- **处置建议**：删除该多余定义，或将其重构为三大远程适配器的公共装饰器。

### 4. `scripts/_lib/core/docx_academic_styler.py` 公共模块未闭环
- **文件路径**：[`scripts/_lib/core/docx_academic_styler.py`](../scripts/_lib/core/docx_academic_styler.py)
- **位置**：第 18 ~ 135 行（`init_academic_document`、`add_academic_title`、`add_academic_h1`、`set_academic_cell` 等）
- **现状分析**：该模块本意作为国标 GB/T 7713 学术排版的公共引擎，但实际生成脚本 `generate_docx_proposal.py` 与 `generate_proof_material.py` 未使用该公共模块，导致该文件整体处于**未引用状态**。
- **处置建议**：保留该模块，重构两个 Word 生成脚本以导入并复用本模块。

---

## 三、 多头维护与重复冗余逻辑清单

### 1. 角色名归一化逻辑的多头维护
- **涉及文件**：
  - [`scripts/transition_task.py`](../scripts/transition_task.py)（第 101 行）调用 `_lib/core/validate_transition.py` 的 `normalize_role`；
  - [`scripts/start_kanban_server.py`](../scripts/start_kanban_server.py)（第 380~391 行）私自硬编码维护了一份 20+ 项的 `ROLE_NAME_MAP` 字典与 `normalize_role_name` 函数。
- **隐患分析**：两处分别硬编码维护角色映射表，若后续增加新角色别名，容易发生映射不一致（漂移）。
- **处置建议**：`start_kanban_server.py` 移除局部字典，统一导入 `from _lib.core.validate_transition import normalize_role`。

### 2. Word 生成脚本间的重复函数定义
- **涉及文件**：
  - [`scripts/generate_docx_proposal.py`](../scripts/generate_docx_proposal.py)（第 52~95 行）
  - [`scripts/generate_proof_material.py`](../scripts/generate_proof_material.py)（第 43~80 行）
- **重复内容**：`clear_paragraph`、`format_academic_run`、`format_paragraph`、`set_cell` 约 60 行代码完全同构。
- **处置建议**：统一重构引用 `_lib/core/docx_academic_styler.py`。

---

## 四、 未使用的冗余导入 (Unused Imports) 清单

经 AST 语法树扫描，以下生产与测试代码存在未引用的 import：

| 文件路径 | 行号 | 未使用的导入项 | 备注 |
| :--- | :---: | :--- | :--- |
| `scripts/auto_task.py` | 35 | `check_duplicate_tasks` | 查重逻辑已下沉至底层 pipeline |
| `scripts/check_secrets.py` | 13 | `SECRET_PATTERNS`, `scan_file` | 直接调用了 `run_secrets_scan` |
| `scripts/transition_task.py` | 14, 26 | `Dict`, `TaskStatus`, `TaskType`, `RoleEnum` | 局部未直接消费的类型 |
| `scripts/build_agent_context.py` | 6 | `sys` | 未使用 |
| `scripts/audit_rotate.py` | 24 | `get_archive_dir` | 未使用 |
| `scripts/migrate_legacy_docs.py` | 12 | `EXCLUDE_DIRS`, `CATEGORY_KEYWORDS`, `classify_document` | 顶层 CLI 未消费底层局部常量 |
| `tests/test_domain_packages.py` | 5, 7, 18, 28, 31 | `os`, `pytest`, `run_secrets_scan`, `discover_feishu_fields`, `EXCLUDE_DIRS`, `CATEGORY_KEYWORDS` | 单测初期遗留导入 |
| `tests/test_kanban_api_v2.py` | 20, 21 | `subprocess`, `sys` | 未使用 |

---

## 五、 代码整洁度与重构建议路线图

- **阶段一：死代码与无用 Import 清理**：删除 4 处确认死代码，清理 10+ 处无用导入；
- **阶段二：消除多头维护与重复定义**：统一角色归一化至 core 模块，复用 Word 排版库；
- **阶段三：自动化静态扫描守卫**：配置代码检查规则，防止死代码再次合入。

---

## 六、 决策者关注清单 (Decision Points)

1. **死代码清理授权**：建议统一对 `read_markdown_section`、`read_lock_meta`、`exponential_backoff_retry` 及未使用的 Imports 进行批量精简。
2. **公共模块收敛**：将 `start_kanban_server.py` 角色字典收敛至 `_lib/core/validate_transition.py`，保持单一真实数据源（Single Source of Truth）。
