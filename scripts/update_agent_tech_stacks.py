#!/usr/bin/env python3
"""
专家技术栈同步触发器 (Tech Stack Sync Trigger)

新语义（代码/数据分离后）：
- agents/*.yaml 是只读模板，不再被改写
- 项目技术栈在【导出时】由 agent_tech_overlay.py 覆盖到各平台 Subagent 产物
- 本脚本校验架构配置就绪后，重新触发导出，使最终产物携带最新技术栈
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.core.agent_tech_overlay import load_arch_data


def main():
    arch = load_arch_data()
    if arch is None:
        print("[NOTE]  架构配置未初始化（user_data/project_architecture.config.yaml 缺失或为占位）。")
        print("        跳过技术栈覆盖导出；将先执行 auto_scan_stack.py --write 完成扫描后自动联动。")
        return 0

    proj = (arch.get("project") or {}).get("name", "未知")
    print(f"[SYNC]  [技术栈覆盖导出] 项目【{proj}】技术栈将在导出时合并至各平台 Subagent...")

    # 重新触发导出（overlay 生效点在导出器内部）
    import subprocess
    res = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "verify_and_export_agents.py")],
        capture_output=True, text=True,
    )
    if res.returncode == 0:
        print("[SUCCESS]  专家 Subagent 已携项目技术栈完成重新导出（agents/*.yaml 模板保持只读）。")
        return 0
    sys.stderr.write(res.stderr or res.stdout)
    print("[FAILED]  重新导出失败，请检查上方输出。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
