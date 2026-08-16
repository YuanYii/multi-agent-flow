# ==============================================================================
# Multi-Agent Flow · 全局共享安装器 (Windows PowerShell)
# 正本落 ~\agent-skills\multi-agent-flow（中立位置，只读共享），
# 再由 verify_and_export_agents.py --global 挂载到各 Agent 宿主的用户级技能目录。
#
# 用法:
#   .\install_global.ps1              # 默认安装/更新最新 release_v6
#   .\install_global.ps1 <branch|tag> # 固定版本
# ==============================================================================

param(
    [string]$Ref = "release_v6"
)

$ErrorActionPreference = "Stop"

$CanonicalRoot = Join-Path $HOME "agent-skills\multi-agent-flow"

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "[INSTALL] Multi-Agent Flow 全局共享安装 (ref: $Ref)" -ForegroundColor Cyan
Write-Host "  正本位置: $CanonicalRoot" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

# 1. 物化正本（tarball 零依赖；有 Node 可改用 degit）
New-Item -ItemType Directory -Force -Path $CanonicalRoot | Out-Null
$TarUrl = "https://github.com/YuanYii/multi-agent-flow/archive/refs/heads/$Ref.tar.gz"
$TmpTar = Join-Path $env:TEMP "yy-flow-$Ref.tar.gz"
Write-Host "[FETCH]  下载 tarball: $TarUrl"
try {
    Invoke-WebRequest -Uri $TarUrl -OutFile $TmpTar -UseBasicParsing
    tar xzf $TmpTar -C $CanonicalRoot --strip-components=1
} finally {
    if (Test-Path $TmpTar) { Remove-Item $TmpTar }
}

# 2. 安全守卫：正本必须零数据（含 board.json 即拒绝，防 legacy 误判串数据）
$GuardBoard = Join-Path $CanonicalRoot "user_data\board.json"
if (Test-Path $GuardBoard) {
    Write-Host "[FAILED] [Guard] 正本目录含 user_data\board.json（被污染为某项目的数据副本）！" -ForegroundColor Red
    Write-Host "         全局共享安装要求正本零数据。请人工检查 $CanonicalRoot\user_data\ 后重试。" -ForegroundColor Red
    exit 1
}

# 3. 写入共享标记（paths.py 解析链据此否决 legacy 分支）
New-Item -ItemType File -Force -Path (Join-Path $CanonicalRoot ".yy-flow-shared") | Out-Null

# 4. 执行全局挂载
Write-Host "[MOUNT]  执行各宿主用户级全局挂载..."
python3 (Join-Path $CanonicalRoot "scripts\verify_and_export_agents.py") --global
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "[TIP] 每个项目的运行数据仍落各自项目根 (YY_FLOW_PROJECT_ROOT 或 CWD)；项目内首次使用请执行 /yy-flow start 初始化。" -ForegroundColor Yellow
Write-Host "[SUCCESS] 全局共享安装完成！" -ForegroundColor Green
