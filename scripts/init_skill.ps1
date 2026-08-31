# Multi-Agent Flow 技能包一键化 SOP 初始化脚本 (Windows PowerShell 强物理凭据版)
# 数据根解析与 init_skill.sh 同链: YY_FLOW_PROJECT_ROOT 环境变量 > legacy(skill 内含
# user_data/board.json) > 当前目录。共享安装下数据落宿主项目根。
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$SkillRoot = Resolve-Path "$ScriptDir\.."

# 数据根解析：优先 env；否则问 paths.py（含 legacy 判定）
$DataRoot = $null
if ($env:YY_FLOW_PROJECT_ROOT) {
    $DataRoot = $env:YY_FLOW_PROJECT_ROOT
} else {
    $DataRoot = & python "$ScriptDir\paths.py" 2>$null
    if (-not $DataRoot -or $LASTEXITCODE -ne 0) { $DataRoot = (Get-Location).Path }
}
$env:YY_FLOW_PROJECT_ROOT = $DataRoot

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "[START]  开始执行 multi-agent-flow 标准 SOP 初始化流程 (PowerShell)..." -ForegroundColor Cyan
Write-Host "  数据根 (DATA_ROOT): $DataRoot" -ForegroundColor Cyan
Write-Host "  技能根 (SKILL_ROOT): $SkillRoot" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

Write-Host "[SETUP]     [Step 0/7] 校验 Python 环境与第三方依赖 (requirements.txt)..." -ForegroundColor Yellow
if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command python3 -ErrorAction SilentlyContinue)) {
    Write-Host "[FATAL]     未检测到 Python 运行环境，请先安装 Python 3.9+ 并加入 PATH 后重试。" -ForegroundColor Red
    exit 1
}
$pyCmd = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "python3" }
& $pyCmd -c "import yaml, docx" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[DEPS]      检测到依赖缺失，尝试自动安装 requirements.txt ..." -ForegroundColor Cyan
    & $pyCmd -m pip install -r "$SkillRoot\requirements.txt" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARN]      自动安装失败，请手动执行: $pyCmd -m pip install -r `"$SkillRoot\requirements.txt`"" -ForegroundColor Yellow
    }
}

Write-Host "[SECURITY]  [Step 1/7] 强执行敏感凭据泄露安全扫描 (check_secrets.py)..." -ForegroundColor Yellow
python "$ScriptDir\check_secrets.py"

Write-Host "[SECURITY]  [Step 2/7] 动态 Agent 环境探测、官方文档实时查证与 Subagent 强规范落盘..." -ForegroundColor Yellow
python "$ScriptDir\verify_and_export_agents.py"

Write-Host "[SCAN]  [Step 3/7] 自动代码物理扫描工程基础设施、依赖文件与语言技术栈配置 (只读预检)..." -ForegroundColor Yellow
python "$ScriptDir\auto_scan_stack.py"

Write-Host "[CONFIG]  [Step 4/7] 初始化宿主数据资产目录 user_data/ 并生成工作流与架构配置..." -ForegroundColor Yellow
$UserDataDir = "$DataRoot\user_data"
$UserDataLogs = "$DataRoot\user_data\logs"
$UserDataLocks = "$DataRoot\user_data\locks"
foreach ($d in @($UserDataDir, $UserDataLogs, $UserDataLocks)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
}

$WorkflowConfig = "$UserDataDir\workflow.config.yaml"
$WorkflowTpl = "$SkillRoot\config\workflow.config.template.yaml"
if (-not (Test-Path $WorkflowConfig)) {
    Copy-Item $WorkflowTpl $WorkflowConfig
    Write-Host "  - 已成功生成 user_data\workflow.config.yaml 物理配置" -ForegroundColor Green
} else {
    Write-Host "  - 已存在工作流配置 user_data\workflow.config.yaml，保持原状。" -ForegroundColor Gray
}

$ArchConfig = "$UserDataDir\project_architecture.config.yaml"
$ArchTpl = "$SkillRoot\config\project_architecture.template.yaml"
if (-not (Test-Path $ArchConfig)) {
    Copy-Item $ArchTpl $ArchConfig
    Write-Host "  - 已成功生成 user_data\project_architecture.config.yaml 物理配置" -ForegroundColor Green
} else {
    Write-Host "  - 已存在架构配置，保持原有技术架构配置。" -ForegroundColor Gray
}

$BoardJson = "$UserDataDir\board.json"
if (-not (Test-Path $BoardJson)) {
    "[]" | Out-File -FilePath $BoardJson -Encoding utf8
    Write-Host "  - 已成功初始化空看板工单 user_data\board.json" -ForegroundColor Green
}

# [NOTICE] 若通过 git clone 安装，Skill 目录内会残留 .git；初始化不做任何删除，
# 仅提示由用户自行决定（degit/tarball 安装方式天然无此目录）
if (Test-Path "$SkillRoot\.git") {
    Write-Host "[TIP]  检测到 Skill 目录内存在 .git（git clone 安装残留），保留未动。" -ForegroundColor Yellow
    Write-Host "       如需清理可手动执行: Remove-Item -Recurse -Force `"$SkillRoot\.git`"" -ForegroundColor Yellow
}

Write-Host "[DOCS]  [Step 5/7] 项目工程文档骨架建立树与原项目历史文档只读隔离归档..." -ForegroundColor Yellow
# docs 是项目交付物 → 落项目根（.yy-flow 布局下为 DataRoot 上一级；legacy 下即 DataRoot）
$DocsRoot = Join-Path (Split-Path $DataRoot -Parent) "docs"
if (-not (Split-Path $DataRoot -Leaf) -eq ".yy-flow") {
    $DocsRoot = Join-Path $DataRoot "docs"
}
$DocsDirs = @(
    "$DocsRoot\D01-项目管理\D01-需求",
    "$DocsRoot\D01-项目管理\D02-状态报告",
    "$DocsRoot\D02-架构设计",
    "$DocsRoot\D03-业务模块",
    "$DocsRoot\D04-研发过程\D01-任务",
    "$DocsRoot\D04-研发过程\D02-报告",
    "$DocsRoot\D04-研发过程\D03-操作手册",
    "$DocsRoot\D05-规范标准",
    "$DocsRoot\D06-文档模板",
    "$DocsRoot\草稿箱"
)
foreach ($dir in $DocsDirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
    }
}

python "$ScriptDir\migrate_legacy_docs.py"

Write-Host "[MIGRATE]  [Step 5.5/7] 检测存量看板工单并执行自然周无损平滑迁移 (migrate_legacy_board.py)..." -ForegroundColor Yellow
python "$ScriptDir\migrate_legacy_board.py"

Write-Host "[SYNC]  [Step 6/7] 专家团队技术栈同步（导出时合并至各平台 Subagent）..." -ForegroundColor Yellow
python "$ScriptDir\update_agent_tech_stacks.py"

Write-Host "[PM]  [Step 7/7] 物理生成项目架构全景鉴定基线工单 (AUTO 自动编号) 并唤起 PM 调度..." -ForegroundColor Yellow
python "$ScriptDir\quick_task.py" create --name "项目技术架构全景鉴定与选型定版" --role PM --assignee 钱架构 --type B

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "[SUCCESS]  [SOP 7 步全量就绪] multi-agent-flow 物理初始化顺利完成！" -ForegroundColor Cyan
Write-Host "  运行数据目录: $DataRoot\user_data" -ForegroundColor Cyan
Write-Host "  项目文档目录: $DocsRoot" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan
