#!/usr/bin/env python3
"""
PreToolUse Hook: 主 Agent (PM) 业务源码写权限物理拦截门禁
(Gate PM Code Edit Hook)

作用：
当主会话尝试调用 write_to_file 或 replace_file_content 直接篡改业务代码时，
在工具实际执行前进行物理拦截，强制主 Agent 只能通过 dispatch_task 派单给子代理。
"""
import os
import sys
import json
import argparse

# 业务受保护路径前缀（仅允许 Subagent 专家写入，禁止 PM 主会话直写）
PROTECTED_PREFIXES = [
    "src/", "app/", "lib/", "pkg/", "packages/",
    "backend/", "frontend/", "ui/"
]

# 放行白名单路径（PM 与主会话合法文档/配置输出区）
WHITELIST_PREFIXES = [
    "docs/", "user_data/", "config/", "tests/",
    "草稿箱/", ".agents/", ".claude/", ".zcode/", ".git/"
]


def check_tool_permission(tool_name: str, target_file: str, is_subagent: bool = False) -> dict:
    """判定当前工具调用是否被放行"""
    if tool_name not in ["write_to_file", "replace_file_content"]:
        return {"decision": "allow", "reason": "Non-file-write tool"}

    if not target_file:
        return {"decision": "allow", "reason": "No target file specified"}

    # 规范化为相对路径
    norm_path = target_file.replace("\\", "/")
    # 获取相对项目根目录路径
    for marker in ["/src/", "/app/", "/lib/", "/pkg/", "/docs/", "/user_data/", "/tests/"]:
        if marker in norm_path:
            norm_path = norm_path[norm_path.find(marker) + 1:]
            break

    # 1. 优先白名单放行
    for wl in WHITELIST_PREFIXES:
        if norm_path.startswith(wl) or f"/{wl}" in norm_path:
            return {"decision": "allow", "reason": f"Whitelisted path: {wl}"}

    # 2. 如果明确处于 Subagent 子代理会话中，放行
    if is_subagent:
        return {"decision": "allow", "reason": "Authorized subagent execution"}

    # 3. 校验是否属于受保护业务源码
    is_protected = any(norm_path.startswith(p) or f"/{p}" in norm_path for p in PROTECTED_PREFIXES)

    if is_protected:
        reason_msg = (
            f"[GATE-PM-BLOCK] 🚨 物理拦截越权写入！\n"
            f"目标文件: '{target_file}' 属于核心业务源码区域。\n"
            f"根据 YY-Flow 物理隔离铁律，主 Agent (PM 严经理) 严禁在主进程中自扮演写代码！\n"
            f"请先建卡并通过代码化派单工具调起子代理:\n"
            f"  1. python3 scripts/quick_task.py create --name <任务名> --assignee 李开发 ...\n"
            f"  2. python3 scripts/dispatch_task.py --task-id <ID> (获取 invoke_subagent 参数)\n"
            f"  3. 调用 invoke_subagent 派发专家子代理在独立进程中执行修改。"
        )
        return {"decision": "deny", "reason": reason_msg}

    return {"decision": "allow", "reason": "Standard path"}


def main():
    parser = argparse.ArgumentParser(description="PreToolUse Hook: PM 业务代码写拦截门禁")
    parser.add_argument("--tool-name", default=None, help="调用的工具名")
    parser.add_argument("--target-file", default=None, help="目标文件路径")
    parser.add_argument("--subagent-mode", action="store_true", help="是否以子代理模式运行")
    args = parser.parse_args()

    tool_name = args.tool_name
    target_file = args.target_file
    is_subagent = args.subagent_mode or (os.environ.get("YY_FLOW_SUBAGENT_ACTIVE") == "1")

    # 优先从 stdin 尝试解析 JSON (平台 Hook 标准协议)
    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                hook_input = json.loads(stdin_data)
                tool_name = tool_name or hook_input.get("tool_name")
                tool_input = hook_input.get("tool_input", {})
                target_file = target_file or tool_input.get("TargetFile") or tool_input.get("target_file")
                caller_role = hook_input.get("session_context", {}).get("role", "")
                if caller_role and caller_role.lower() != "pm":
                    is_subagent = True
        except Exception:
            pass

    res = check_tool_permission(tool_name or "", target_file or "", is_subagent)
    print(json.dumps(res, ensure_ascii=False))

    if res["decision"] == "deny":
        # 输出错误至 stderr
        print(res["reason"], file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
