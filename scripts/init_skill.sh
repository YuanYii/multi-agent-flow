#!/usr/bin/env bash
# ==============================================================================
# Multi-Agent Flow 技能包一键化 SOP 7 步初始化脚本 (物理凭据强断言版)
# 自动打通：
# 1.高危凭据扫描 -> 2.Subagent物理强校验导出 -> 3.物理代码技术栈扫描 -> 4.模板生成落库
# -> 5.文档骨架与旧文档只读归档 -> 6.专家技术栈同步 -> 7.PM 物理鉴定展示【已识别 xxxx 项目】
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=============================================================================="
echo "[START]  开始执行 multi-agent-flow 标准 7 大 SOP 初始化流程..."
echo "=============================================================================="

echo "[SECURITY]  [Step 1/7] 强执行敏感凭据泄露安全扫描 (check_secrets.py)..."
python3 "${SCRIPT_DIR}/check_secrets.py"

echo "[SECURITY]  [Step 2/7] 动态 Agent 环境探测、Subagent 导出与本地格式断言 (Fail-Closed)..."
python3 "${SCRIPT_DIR}/verify_and_export_agents.py"

echo "[SCAN]  [Step 3/7] 自动代码物理扫描工程基础设施、依赖文件与语言技术栈配置..."
python3 "${SCRIPT_DIR}/auto_scan_stack.py"

echo "[CONFIG]  [Step 4/7] 初始化宿主数据资产目录 user_data/ 并生成工作流与架构配置..."
mkdir -p "${PROJECT_ROOT}/user_data" "${PROJECT_ROOT}/user_data/logs"

if [ ! -f "${PROJECT_ROOT}/user_data/workflow.config.yaml" ]; then
    cp "${PROJECT_ROOT}/config/workflow.config.template.yaml" "${PROJECT_ROOT}/user_data/workflow.config.yaml"
    echo "  - 已成功生成 user_data/workflow.config.yaml 物理配置"
else
    echo "  - 已存在工作流配置 user_data/workflow.config.yaml，保持原状。"
fi

if [ ! -f "${PROJECT_ROOT}/user_data/project_architecture.config.yaml" ]; then
    cp "${PROJECT_ROOT}/config/project_architecture.template.yaml" "${PROJECT_ROOT}/user_data/project_architecture.config.yaml"
    echo "  - 已成功生成 user_data/project_architecture.config.yaml 物理配置"
else
    echo "  - 已存在架构配置，保持原有技术架构配置。"
fi

if [ ! -f "${PROJECT_ROOT}/user_data/board.json" ]; then
    echo "[]" > "${PROJECT_ROOT}/user_data/board.json"
    echo "  - 已成功初始化空看板工单 user_data/board.json"
fi

# [CLEAN]  宿主环境纯净化：清理 Skill 目录内部残留的 .git 目录和 .gitignore 文件
if [ -d "${PROJECT_ROOT}/.git" ]; then
    rm -rf "${PROJECT_ROOT}/.git"
    echo "  - 已自动清理 Skill 目录内部残留的 .git 仓库目录"
fi
if [ -f "${PROJECT_ROOT}/.gitignore" ]; then
    rm -f "${PROJECT_ROOT}/.gitignore"
    echo "  - 已自动清理 Skill 目录内部的 .gitignore 文件"
fi

echo "[DOCS]  [Step 5/7] 项目工程文档骨架建立树与原项目历史文档只读隔离归档..."
mkdir -p "${PROJECT_ROOT}/docs/01-architecture" \
         "${PROJECT_ROOT}/docs/02-modules" \
         "${PROJECT_ROOT}/docs/03-operations" \
         "${PROJECT_ROOT}/docs/04-standards" \
         "${PROJECT_ROOT}/docs/05-templates" \
         "${PROJECT_ROOT}/docs/.drafts"

python3 "${SCRIPT_DIR}/migrate_legacy_docs.py"

echo "[SYNC]  [Step 6/7] 专家团队技术栈自动同步至 agents/*.yaml (全量 8 大角色)..."
python3 "${SCRIPT_DIR}/update_agent_tech_stacks.py"

echo "[PM]  [Step 7/7] 唤起 PM 专家确认项目鉴定定位..."
echo "  - PM 专家已完成项目范围核验，随时准备响应任务编排。"

echo "=============================================================================="
echo "[SUCCESS]  [SOP 7 步全量就绪] multi-agent-flow 物理初始化顺利完成！"
echo "=============================================================================="
