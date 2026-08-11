#!/bin/bash
# 局域网分享启动脚本（零依赖，仅用 Python 自带 http.server）
# 用法: ./start.sh [端口]   （默认 28888）
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SERVER="$(cd "${SCRIPT_DIR}/../scripts" && pwd)/start_kanban_server.py"

if [ -f "${PYTHON_SERVER}" ]; then
    python3 "${PYTHON_SERVER}" --port 32886
else
    cd "${SCRIPT_DIR}"
    python3 -m http.server 32886
fi
