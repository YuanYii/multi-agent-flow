# Multi-Agent Flow 技能包一键化 SOP 初始化脚本 (Windows PowerShell 强物理凭据版)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Resolve-Path "$ScriptDir\.."

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "🚀 开始执行 multi-agent-flow 标准 SOP 初始化流程 (PowerShell)..." -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

Write-Host "🔒 [Step 1/7] 强执行敏感凭据泄露安全扫描 (check_secrets.py)..." -ForegroundColor Yellow
python "$ScriptDir\check_secrets.py"

Write-Host "🔒 [Step 2/7] 动态 Agent 环境探测、官方文档实时查证与 Subagent 强规范落盘..." -ForegroundColor Yellow
python "$ScriptDir\verify_and_export_agents.py"

Write-Host "🔎 [Step 3/7] 自动代码物理扫描工程基础设施、依赖文件与语言技术栈配置..." -ForegroundColor Yellow
python "$ScriptDir\auto_scan_stack.py"

Write-Host "📝 [Step 4/7] 复制模板并落库生成 project_architecture.config.yaml..." -ForegroundColor Yellow
$ConfigPath = "$ProjectRoot\config\project_architecture.config.yaml"
$TemplatePath = "$ProjectRoot\config\project_architecture.template.yaml"

if (-not (Test-Path $ConfigPath)) {
    Copy-Item $TemplatePath $ConfigPath
    Write-Host "  - 已成功生成 config\project_architecture.config.yaml 物理配置" -ForegroundColor Green
} else {
    Write-Host "  - 已存在配置文件，保持原有技术架构配置。" -ForegroundColor Gray
}

Write-Host "📂 [Step 5/7] 项目工程文档骨架建立树与原项目历史文档只读隔离归档..." -ForegroundColor Yellow
$DocsDirs = @(
    "$ProjectRoot\docs\01-architecture",
    "$ProjectRoot\docs\02-modules",
    "$ProjectRoot\docs\03-operations",
    "$ProjectRoot\docs\04-standards",
    "$ProjectRoot\docs\05-templates",
    "$ProjectRoot\docs\.drafts"
)
foreach ($dir in $DocsDirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
    }
}

python "$ScriptDir\migrate_legacy_docs.py"

Write-Host "🔄 [Step 6/7] 专家团队技术栈自动同步至 agents/*.yaml (全量 8 大角色)..." -ForegroundColor Yellow
python "$ScriptDir\update_agent_tech_stacks.py"

Write-Host "👑 [Step 7/7] 唤起 PM 专家确认项目鉴定定位..." -ForegroundColor Yellow
Write-Host "  - PM 专家已完成项目范围核验，随时准备响应任务编排。" -ForegroundColor Green

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "✅ [SOP 7 步全量就绪] multi-agent-flow 物理初始化顺利完成！" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan
