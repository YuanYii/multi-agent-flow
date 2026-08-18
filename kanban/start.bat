@echo off
rem 看板服务 Windows 批处理启动脚本（零依赖，仅 Python 标准库）
rem 用法: start.bat [端口]

set SCRIPT_DIR=%~dp0
set PYTHON_SERVER=%SCRIPT_DIR%..\scripts\start_kanban_server.py

if "%~1"=="" (
    python "%PYTHON_SERVER%"
) else (
    python "%PYTHON_SERVER%" --port "%~1"
)
