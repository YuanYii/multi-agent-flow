# 看板服务 Windows PowerShell 启动脚本（零依赖，仅 Python 标准库）
# 用法: .\start.ps1 [端口]
param(
    [string]$Port = ""
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$PythonServer = Join-Path (Split-Path -Parent $ScriptDir) "scripts\start_kanban_server.py"

if ($Port -ne "") {
    python "$PythonServer" --port "$Port"
} else {
    python "$PythonServer"
}
