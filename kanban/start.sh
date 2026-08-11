#!/bin/bash
# 局域网分享启动脚本（零依赖，仅用 Python 自带 http.server）
# 用法: ./start.sh [端口]   （默认 28888）
cd "$(dirname "$0")"
PORT="${1:-28888}"
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "本机IP")
echo "=============================================="
echo "  看板服务已启动 (端口 $PORT)"
echo "  本机访问:   http://127.0.0.1:$PORT/offline_board.html"
echo "  局域网访问: http://$IP:$PORT/offline_board.html"
echo "  停止服务:   Ctrl+C"
echo "=============================================="
exec python3 -m http.server "$PORT" --bind 0.0.0.0 --directory "$(pwd)"
