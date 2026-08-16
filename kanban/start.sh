#!/usr/bin/env bash
# 看板服务启动脚本（零依赖，仅 Python 标准库）
# 用法: ./start.sh [端口]
#   不带参数：默认 32886 起自动探测空闲端口（被其他项目占用则向上递增）
#   带端口  ：固定使用该端口，被占用且非本项目实例则直接失败
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SERVER="$(cd "${SCRIPT_DIR}/../scripts" && pwd)/start_kanban_server.py"

if [ "$#" -ge 1 ]; then
    exec python3 "${PYTHON_SERVER}" --port "$1"
else
    exec python3 "${PYTHON_SERVER}"
fi
