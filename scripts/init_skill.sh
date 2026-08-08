#!/usr/bin/env bash
# ==============================================================================
# Multi-Agent Flow 技能包一键化 SOP 7 步初始化脚本 (完全对齐 SKILL.md 定义)
# 自动打通：
# 1.核验配置 ➔ 2.Subagent物理强校验导出 ➔ 3.物理代码技术栈扫描 ➔ 4.模板生成落库
# ➔ 5.文档骨架与旧文档只读归档 ➔ 6.专家技术栈同步 ➔ 7.PM 识别展示【已识别 xxxx 项目】
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=============================================================================="
echo "🚀 开始执行 multi-agent-flow 标准 7 大 SOP 初始化流程..."
echo "=============================================================================="

echo "🔍 [Step 1/7] 检查与核验工程配置文件 (project_architecture.config.yaml)..."
if [ -f "${PROJECT_ROOT}/config/project_architecture.config.yaml" ]; then
    echo "  - 已检测到已存在的工程配置文件，跳过首次创建。"
else
    echo "  - 未检测到配置文件，将在 Step 4 中自动基于模板进行构建。"
fi

echo "🔒 [Step 2/7] 动态 Agent 环境探测、官方文档实时查证与 Subagent 强规范落盘..."
python3 "${SCRIPT_DIR}/verify_and_export_agents.py"

echo "🔎 [Step 3/7] 自动代码扫描工程基础设施、依赖文件与语言技术栈配置..."
python3 "${SCRIPT_DIR}/auto_scan_stack.py"

echo "📝 [Step 4/7] 复制模板并落库生成 project_architecture.config.yaml..."
if [ ! -f "${PROJECT_ROOT}/config/project_architecture.config.yaml" ]; then
    cp "${PROJECT_ROOT}/config/project_architecture.template.yaml" "${PROJECT_ROOT}/config/project_architecture.config.yaml"
    echo "  - 已成功生成 config/project_architecture.config.yaml 物理配置"
fi

echo "📂 [Step 5/7] 项目工程文档骨架建立树与原项目历史文档只读隔离归档..."
mkdir -p "${PROJECT_ROOT}/docs/01-architecture" \
         "${PROJECT_ROOT}/docs/02-modules" \
         "${PROJECT_ROOT}/docs/03-operations" \
         "${PROJECT_ROOT}/docs/04-standards" \
         "${PROJECT_ROOT}/docs/05-templates" \
         "${PROJECT_ROOT}/docs/.drafts"

python3 "${SCRIPT_DIR}/migrate_legacy_docs.py"

echo "🔄 [Step 6/7] 专家团队技术栈自动同步至 agents/*.yaml..."
python3 "${SCRIPT_DIR}/update_agent_tech_stacks.py"

echo "👑 [Step 7/7] 唤起 PM 专家物理扫描 README.md 进行项目定位鉴定与标志打印..."
python3 "${SCRIPT_DIR}/auto_scan_stack.py"

echo "=============================================================================="
echo "✅ [SOP 7 步全量就绪] multi-agent-flow 物理初始化顺利完成！"
echo "=============================================================================="
