# ==============================================================================
# 多专家协同研发工作流 - 状态查看与巡检脚本 (Windows PowerShell)
# ==============================================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ConfigFile = Join-Path $ScriptDir "..\config\workflow.config.yaml"

if (-not (Test-Path $ConfigFile)) {
    $ConfigFile = Join-Path $ScriptDir "..\config\workflow.config.template.yaml"
}

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "          🤖 Multi-Agent Team Workflow · 状态巡检面板 (Windows)" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

if (Test-Path $ConfigFile) {
    Write-Host "  配置文件: $ConfigFile" -ForegroundColor Green
    Write-Host "  已配置角色: PM, ARCHITECT, DEV, REVIEWER, QA, DOCS, DEVOPS" -ForegroundColor Yellow
} else {
    Write-Host "  [WARN] 未找到配置文件，请先从 template 复制生成" -ForegroundColor Red
}

Write-Host "========================================================================" -ForegroundColor Cyan
