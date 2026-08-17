# ==============================================================================
# 多专家协同研发工作流 - 状态查看与巡检脚本 (Windows PowerShell)
# ==============================================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
# 配置解析链：宿主 user_data/workflow.config.yaml > legacy skill config/ > 模板
$ConfigFile = $null
$Candidates = @(
    (Join-Path (Get-Location) "user_data\workflow.config.yaml"),
    (Join-Path $ScriptDir "..\user_data\workflow.config.yaml"),
    (Join-Path $ScriptDir "..\config\workflow.config.yaml")
)
foreach ($Cand in $Candidates) {
    if (Test-Path $Cand) { $ConfigFile = $Cand; break }
}

if (-not $ConfigFile) {
    $ConfigFile = Join-Path $ScriptDir "..\config\workflow.config.template.yaml"
}

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "           Multi-Agent Team Workflow · 状态巡检面板 (Windows)" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

if (Test-Path $ConfigFile) {
    Write-Host "  配置文件: $ConfigFile" -ForegroundColor Green
    Write-Host "  已配置角色: PM, ARCHITECT, DEV, REVIEWER, QA, DOCS, DEVOPS" -ForegroundColor Yellow
} else {
    Write-Host "  [WARN] 未找到配置文件，请先从 template 复制生成" -ForegroundColor Red
}

Write-Host "========================================================================" -ForegroundColor Cyan
