#!/usr/bin/env bash
# ==============================================================================
# Multi-Agent Flow 技能包一键化 SOP 初始化脚本
# 自动打通：环境物理查验 ➔ 架构扫描 ➔ 配置生成 ➔ 旧文档归档 ➔ 专家技术栈同步
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "🚀 [Step 1/5] 执行 Subagent 官方物理强校验与导出程序..."
python3 "${SCRIPT_DIR}/verify_and_export_agents.py"

echo "📂 [Step 2/5] 建立项目标准工程文档骨架树 (docs/)..."
mkdir -p "${PROJECT_ROOT}/docs/01-architecture" \
         "${PROJECT_ROOT}/docs/02-modules" \
         "${PROJECT_ROOT}/docs/03-operations" \
         "${PROJECT_ROOT}/docs/04-standards" \
         "${PROJECT_ROOT}/docs/05-templates" \
         "${PROJECT_ROOT}/docs/.drafts"

echo "📦 [Step 3/5] 执行历史旧文档扫描与只读隔离归档..."
python3 "${SCRIPT_DIR}/migrate_legacy_docs.py"

echo "🛠️ [Step 4/5] 检查与初始化项目架构配置文件..."
if [ ! -f "${PROJECT_ROOT}/config/project_architecture.config.yaml" ]; then
    cp "${PROJECT_ROOT}/config/project_architecture.template.yaml" "${PROJECT_ROOT}/config/project_architecture.config.yaml"
    echo "  - 已根据模板生成 config/project_architecture.config.yaml"
fi

echo "🔄 [Step 5/5] 执行专家团队技术栈自动同步..."
python3 "${SCRIPT_DIR}/update_agent_tech_stacks.py"

echo "=============================================================================="
echo "✅ [SOP 初始化完成] multi-agent-flow 已成功就绪！"
echo "👉 请在 Agent 对话中唤起 PM 专家鉴定项目模式：【使用 multi-agent-flow 初始化当前项目】"
echo "=============================================================================="
