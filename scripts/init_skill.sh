#!/usr/bin/env bash
# ==============================================================================
# Multi-Agent Flow 技能包一键化 SOP 7 步初始化脚本 (物理凭据强断言版)
# 自动打通：
# 1.高危凭据扫描 -> 2.Subagent物理强校验导出 -> 3.物理代码技术栈扫描 -> 4.模板生成落库
# -> 5.文档骨架与旧文档只读归档 -> 6.专家技术栈同步 -> 7.PM 物理鉴定展示【已识别 xxxx 项目】
#
# 数据根解析（与 scripts/paths.py 同链）：
#   YY_FLOW_PROJECT_ROOT 环境变量 > legacy(skill 内含 user_data/board.json) > 当前目录
#   即：存量 per-project 安装行为不变；共享安装下数据落宿主项目根。
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 数据根解析：优先 env；否则问 paths.py（含 legacy 判定）
if [ -n "${YY_FLOW_PROJECT_ROOT}" ]; then
    DATA_ROOT="${YY_FLOW_PROJECT_ROOT}"
else
    DATA_ROOT="$(python3 "${SCRIPT_DIR}/paths.py" 2>/dev/null || echo "")"
    if [ -z "${DATA_ROOT}" ]; then
        DATA_ROOT="$(pwd)"
    fi
fi
export YY_FLOW_PROJECT_ROOT="${DATA_ROOT}"

echo "=============================================================================="
echo "[START]  开始执行 multi-agent-flow 标准 7 大 SOP 初始化流程..."
echo "  数据根 (DATA_ROOT): ${DATA_ROOT}"
echo "  技能根 (SKILL_ROOT): ${SKILL_ROOT}"
echo "=============================================================================="

echo "[SECURITY]  [Step 1/7] 强执行敏感凭据泄露安全扫描 (check_secrets.py)..."
python3 "${SCRIPT_DIR}/check_secrets.py"

echo "[SECURITY]  [Step 2/7] 动态 Agent 环境探测、Subagent 导出与本地格式断言 (Fail-Closed)..."
python3 "${SCRIPT_DIR}/verify_and_export_agents.py"

echo "[SCAN]  [Step 3/7] 自动代码物理扫描工程基础设施、依赖文件与语言技术栈配置..."
python3 "${SCRIPT_DIR}/auto_scan_stack.py" --write

echo "[CONFIG]  [Step 4/7] 初始化宿主数据资产目录 user_data/ 并生成工作流与架构配置..."
mkdir -p "${DATA_ROOT}/user_data" "${DATA_ROOT}/user_data/logs" "${DATA_ROOT}/user_data/locks"

if [ ! -f "${DATA_ROOT}/user_data/workflow.config.yaml" ]; then
    cp "${SKILL_ROOT}/config/workflow.config.template.yaml" "${DATA_ROOT}/user_data/workflow.config.yaml"
    echo "  - 已成功生成 user_data/workflow.config.yaml 物理配置"
else
    echo "  - 已存在工作流配置 user_data/workflow.config.yaml，保持原状。"
fi

if [ ! -f "${DATA_ROOT}/user_data/project_architecture.config.yaml" ]; then
    cp "${SKILL_ROOT}/config/project_architecture.template.yaml" "${DATA_ROOT}/user_data/project_architecture.config.yaml"
    echo "  - 已成功生成 user_data/project_architecture.config.yaml 物理配置"
else
    echo "  - 已存在架构配置，保持原有技术架构配置。"
fi

if [ ! -f "${DATA_ROOT}/user_data/board.json" ]; then
    echo "[]" > "${DATA_ROOT}/user_data/board.json"
    echo "  - 已成功初始化空看板工单 user_data/board.json"
fi

# [NOTICE]  若通过 git clone 安装，Skill 目录内会残留 .git；初始化不做任何删除，
# 仅提示由用户自行决定（degit/tarball 安装方式天然无此目录）
if [ -d "${SKILL_ROOT}/.git" ]; then
    echo "[TIP]  检测到 Skill 目录内存在 .git（git clone 安装残留），保留未动。"
    echo "       如需清理可手动执行: rm -rf \"${SKILL_ROOT}/.git\""
fi

echo "[DOCS]  [Step 5/7] 项目工程文档骨架建立树与原项目历史文档只读隔离归档..."
# docs 是项目交付物 → 落项目根（.yy-flow 布局下为 DATA_ROOT 上一级；legacy 下即 DATA_ROOT）
DOCS_ROOT="$(dirname "${DATA_ROOT}")/docs"
if [ "$(basename "${DATA_ROOT}")" != ".yy-flow" ]; then
    DOCS_ROOT="${DATA_ROOT}/docs"
fi
mkdir -p "${DOCS_ROOT}/01-architecture" \
         "${DOCS_ROOT}/02-modules" \
         "${DOCS_ROOT}/03-operations" \
         "${DOCS_ROOT}/04-standards" \
         "${DOCS_ROOT}/05-templates" \
         "${DOCS_ROOT}/.drafts"

python3 "${SCRIPT_DIR}/migrate_legacy_docs.py"

echo "[SYNC]  [Step 6/7] 专家团队技术栈同步（导出时合并至各平台 Subagent）..."
python3 "${SCRIPT_DIR}/update_agent_tech_stacks.py"

echo "[PM]  [Step 7/7] 唤起 PM 专家确认项目鉴定定位..."
echo "  - PM 专家已完成项目范围核验，随时准备响应任务编排。"

echo "=============================================================================="
echo "[SUCCESS]  [SOP 7 步全量就绪] multi-agent-flow 物理初始化顺利完成！"
echo "  运行数据目录: ${DATA_ROOT}/user_data"
echo "  项目文档目录: ${DOCS_ROOT}"
echo "=============================================================================="
