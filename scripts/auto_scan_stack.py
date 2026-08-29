#!/usr/bin/env python3
"""
项目架构技术栈与 README 自动物理预扫描工具 (Auto Scan Stack CLI)

Windows 调用约定：
- 调用请用相对路径（如 `python scripts/auto_scan_stack.py .`）或 Windows 形式 `C:/...`，
  避免 `python /c/.../script.py`（Git Bash 会把 `/c` 翻成 `C:\\c` 导致文件找不到）。
- PYTHONPATH 分隔符用 `;`（类 Unix 用 `:`）；入口脚本已自引导 sys.path，通常无需手工设置。
"""
import os
import sys
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.discovery.stack_scanner import scan_project_stack


def main():
    parser = argparse.ArgumentParser(description="项目架构技术栈与 README 自动物理预扫描工具")
    parser.add_argument("target_dir", nargs="?", default=None,
                        help="目标项目目录（默认：当前工作目录）")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出供管道消费")
    args = parser.parse_args()

    info = scan_project_stack(args.target_dir)

    print("==============================================================================")
    print(f"[PRE-SCAN]   Multi-Agent Flow · 项目技术架构物理预扫描结果")
    print("==============================================================================")
    print(f"• 识别项目名称: {info['project_name']}")
    if info.get("readme_title"):
        print(f"• README 标题: {info['readme_title']}")
    print(f"• 探测主语言: {', '.join(info['languages']) if info['languages'] else '未识别'}")
    print(f"• 后端技术栈: {', '.join(info['backend_frameworks']) if info['backend_frameworks'] else '未识别'}")
    print(f"• 前端技术栈: {', '.join(info['frontend_frameworks']) if info['frontend_frameworks'] else '未识别'}")
    print(f"• 存储/数据库: {', '.join(info['storage']) if info['storage'] else '未识别'}")
    print(f"• 测试框架: {info['testing_framework']}")
    print(f"• 构建/部署: {', '.join(info['build_tools']) if info['build_tools'] else '未识别'}")
    print("==============================================================================")

    # 格式化输出供管道消费
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
