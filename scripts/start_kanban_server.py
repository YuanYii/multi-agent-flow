#!/usr/bin/env python3
"""
Multi-Agent Flow · 零依赖简易 HTTP 看板 Web 服务
固定服务端口：32886
提供技能包内置离线看板 (kanban/offline_board.html) 的 HTTP 访问服务
"""

import sys
import os
import argparse
import socket
from http.server import HTTPServer, SimpleHTTPRequestHandler

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
KANBAN_DIR = os.path.join(SKILL_ROOT, "kanban")

DEFAULT_PORT = 32886


def get_local_ip() -> str:
    """获取本机局域网 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


USER_DATA_BOARD = os.path.join(SKILL_ROOT, "user_data", "board.json")


class KanbanHTTPRequestHandler(SimpleHTTPRequestHandler):
    """自定义 HTTP 请求处理类：将根目录请求默认重定向至 offline_board.html，/board.json 代理至 user_data/board.json"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=KANBAN_DIR, **kwargs)

    def do_GET(self):
        # 1. 根路径重定向
        if self.path in ("/", "/index.html", "/offline_board"):
            self.path = "/offline_board.html"
            return super().do_GET()

        # 2. 路由白名单代理: /board.json 映射至 user_data/board.json
        clean_path = self.path.split("?")[0]
        if clean_path in ("/board.json", "/user_data/board.json"):
            if not os.path.exists(USER_DATA_BOARD):
                os.makedirs(os.path.dirname(USER_DATA_BOARD), exist_ok=True)
                with open(USER_DATA_BOARD, "w", encoding="utf-8") as f:
                    f.write("[]")
            try:
                with open(USER_DATA_BOARD, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                self.send_error(500, f"Failed to read board data: {e}")
                return

        return super().do_GET()

    def log_message(self, format, *args):
        # 保持控制台日志简洁
        sys.stderr.write(f" [Kanban HTTP 32886] {self.address_string()} - {format % args}\n")


def start_server(port: int = DEFAULT_PORT, host: str = "0.0.0.0"):
    """启动简易 HTTP 看板服务"""
    if not os.path.exists(KANBAN_DIR):
        print(f"[FAILED]  [ERROR] 无法找到看板目录: {KANBAN_DIR}")
        sys.exit(1)

    server_address = (host, port)
    try:
        httpd = HTTPServer(server_address, KanbanHTTPRequestHandler)
    except OSError as e:
        if e.errno == 48 or "Address already in use" in str(e):
            print(f"[WARN]  [NOTICE] 端口 {port} 已被看板服务或其他进程占用，服务已处于运行状态！")
            local_ip = get_local_ip()
            print_kanban_urls(port, local_ip)
            return
        else:
            print(f"[FAILED]  [ERROR] 启动 HTTP 服务失败: {e}")
            sys.exit(1)

    local_ip = get_local_ip()
    print_kanban_urls(port, local_ip)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP]  收到终止信号，正在关闭看板 HTTP 服务...")
        httpd.server_close()


def print_kanban_urls(port: int, local_ip: str):
    print("\n" + "=" * 70)
    print(f"[START]  Multi-Agent Flow 看板 Web 服务已就绪 (端口: {port})")
    print("=" * 70)
    print(f" 本地访问地址  : http://localhost:{port}/")
    print(f" 替代本地链接  : http://127.0.0.1:{port}/offline_board.html")
    if local_ip != "127.0.0.1":
        print(f" 局域网访问地址: http://{local_ip}:{port}/")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Flow 看板简易 HTTP 服务")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"服务端口 (默认: {DEFAULT_PORT})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听 Host (默认: 0.0.0.0)")
    args = parser.parse_args()

    start_server(port=args.port, host=args.host)


if __name__ == "__main__":
    main()
