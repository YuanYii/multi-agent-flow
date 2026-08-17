#!/usr/bin/env bash
# ==============================================================================
# Multi-Agent Flow · 全局共享安装器 (Linux/macOS)
# 正本落 ~/agent-skills/multi-agent-flow（中立位置，只读共享），
# 再由 verify_and_export_agents.py --global 挂载到各 Agent 宿主的用户级技能目录。
#
# 用法:
#   ./install_global.sh                # 默认安装/更新最新 release_v6
#   ./install_global.sh <branch|tag>   # 固定版本
# ==============================================================================
set -e

CANONICAL_ROOT="${HOME}/agent-skills/multi-agent-flow"
REF="${1:-release_v6}"

echo "=============================================================================="
echo "[INSTALL] Multi-Agent Flow 全局共享安装 (ref: ${REF})"
echo "  正本位置: ${CANONICAL_ROOT}"
echo "=============================================================================="

# 1. 物化正本（degit 优先，tarball 兜底 —— 与 README 安装指引同源）
mkdir -p "${CANONICAL_ROOT}"
if command -v npx &> /dev/null; then
    echo "[FETCH]  使用 degit 拉取 YuanYii/multi-agent-flow#${REF} ..."
    npx -y degit "YuanYii/multi-agent-flow#${REF}" "${CANONICAL_ROOT}" --force
else
    echo "[FETCH]  无 Node 环境，使用 tarball ..."
    curl -L "https://github.com/YuanYii/multi-agent-flow/archive/refs/heads/${REF}.tar.gz" \
        | tar xz -C "${CANONICAL_ROOT}" --strip-components=1
fi

# 2. 安全守卫：正本必须是"无数据"的纯净代码——含 board.json 即拒绝（防 legacy 误判串数据）
if [ -f "${CANONICAL_ROOT}/user_data/board.json" ]; then
    echo "[FAILED] [Guard] 正本目录含 user_data/board.json（被污染为某项目的数据副本）！"
    echo "         全局共享安装要求正本零数据。请人工检查 ${CANONICAL_ROOT}/user_data/ 后重试。"
    exit 1
fi

# 3. 写入共享标记（paths.py 解析链据此否决 legacy 分支，杜绝误判）
touch "${CANONICAL_ROOT}/.yy-flow-shared"

# 4. 执行全局挂载（各宿主用户级技能目录 + 用户级 Subagent）
echo "[MOUNT]  执行各宿主用户级全局挂载..."
python3 "${CANONICAL_ROOT}/scripts/verify_and_export_agents.py" --global

cat <<'TIP'

[TIP] 全局共享安装完成。使用须知：
  - 每个项目的运行数据（user_data/、docs/、锁）仍落各自项目根（YY_FLOW_PROJECT_ROOT 或 CWD）
  - 在项目内首次使用请执行该项目的 7 步初始化（/yy-flow start）
  - 更新技能：重跑本安装器即可；看板服务更新后需重启
  - 卸载：删除各宿主目录软链 + ~/agent-skills/multi-agent-flow
TIP
echo "[SUCCESS] 全局共享安装完成！"
