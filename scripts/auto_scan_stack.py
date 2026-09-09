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
    """
    技术栈自动扫描 CLI 主入口。
    嗅探目标项目根目录的项目构建文件与依赖声明，推断语言、框架与技术能力。
    """
    parser = argparse.ArgumentParser(description="项目架构技术栈与 README 自动物理预扫描工具")
    parser.add_argument("target_dir", nargs="?", default=None,
                        help="目标项目目录（默认：当前工作目录）")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出供管道消费")
    parser.add_argument("--merge", action="store_true",
                        help="策略 B: 自动将探测到的新技术栈静默增量合并至架构配置")
    args = parser.parse_args()

    info = scan_project_stack(args.target_dir)

    # 策略 B: 静默合并增量技术栈
    if args.merge:
        from update_project_profile import load_or_init_arch_config, merge_detected_tech_stack
        from _lib.discovery.arch_persister import save_architecture_config
        arch_data = load_or_init_arch_config()
        added = merge_detected_tech_stack(arch_data, info, silent=args.json)
        save_architecture_config(arch_data, skip_export=True)
        if not args.json and added:
            print(f"[AUTO-MERGE] 策略 B 自动静默合并新发现技术栈: {', '.join(added)}")

    # 管道消费模式：仅输出纯 JSON，避免 Banner 文本污染 stdout 导致 jq / json.loads 解析失败
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return

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


if __name__ == "__main__":
    main()
