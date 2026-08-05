#!/usr/bin/env bash
# ==============================================================================
# 多专家协同研发工作流 - 状态查看与巡检脚本 (Linux/macOS)
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config/workflow.config.yaml"

if [ ! -f "${CONFIG_FILE}" ]; then
    CONFIG_FILE="${SCRIPT_DIR}/../config/workflow.config.template.yaml"
fi

echo "========================================================================"
echo "          🤖 Multi-Agent Team Workflow · 状态巡检面板"
echo "========================================================================"

if command -v python3 &> /dev/null; then
    python3 -c "
import yaml, os

config_path = '${CONFIG_FILE}'
if os.path.exists(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
        proj = data.get('project', {}).get('name', 'N/A')
        provider = data.get('board', {}).get('provider', 'N/A')
        print(f'  项目名称: {proj}')
        print(f'  看板适配器: {provider}')
        print('  已配置角色: PM, ARCHITECT, DEV, REVIEWER, QA, DOCS, DEVOPS')
else:
    print('  [WARN] 未找到配置文件，请先执行 cp config/workflow.config.template.yaml config/workflow.config.yaml')
"
else
    echo "  [WARN] 未检测到 python3 环境"
fi

echo "========================================================================"
