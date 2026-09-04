"""
Multi-Agent Flow · 钩子与拦截门禁包 (scripts/hooks)
包含平台生命周期钩子 (gate_pm_code_edit.py)、Git 版本控制钩子 (pre-commit) 及统一安装器 (hooks_installer.py)。
"""
from hooks.gate_pm_code_edit import check_tool_permission
from hooks.hooks_installer import install_hooks

__all__ = ["check_tool_permission", "install_hooks"]
