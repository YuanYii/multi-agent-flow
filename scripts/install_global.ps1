# ==============================================================================
# Multi-Agent Flow · 全局共享安装器 (Windows PowerShell)
# 正本落 $HOME\agent-skills\multi-agent-flow（中立位置，只读共享），
# 再由 verify_and_export_agents.py --global 挂载到各 Agent 宿主的用户级技能目录。
#
# 用法:
#   powershell -ExecutionPolicy Bypass -File .\install_global.ps1              # 默认最新 release_v8
#   powershell -ExecutionPolicy Bypass -File .\install_global.ps1 main        # 指定分支
# ==============================================================================
param(
    [string]$Ref = "release_v8"
)

$ErrorActionPreference = "Stop"
$CanonicalRoot = Join-Path $HOME "agent-skills\multi-agent-flow"

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "[INSTALL] Multi-Agent Flow 全局共享安装 (ref: $Ref)" -ForegroundColor Cyan
Write-Host "  正本位置: $CanonicalRoot" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

# 1. 创建目录并物化正本 (npx degit 优先，git clone 兜底)
if (-not (Test-Path $CanonicalRoot)) {
    New-Item -ItemType Directory -Path $CanonicalRoot -Force | Out-Null
}

$hasNpx = (Get-Command npx -ErrorAction SilentlyContinue) -ne $null
if ($hasNpx) {
    Write-Host "[FETCH]  使用 degit 拉取 YuanYii/multi-agent-flow#$Ref ..." -ForegroundColor Yellow
    npx -y degit "YuanYii/multi-agent-flow#$Ref" "$CanonicalRoot" --force
} else {
    Write-Host "[FETCH]  无 Node 环境，使用 git 拉取 ..." -ForegroundColor Yellow
    if (Test-Path "$CanonicalRoot\.git") {
        git -C "$CanonicalRoot" pull origin "$Ref"
    } else {
        git clone -b "$Ref" https://github.com/YuanYii/multi-agent-flow.git "$CanonicalRoot"
    }
}

# 2. 安全守卫：正本必须是"无数据"的纯净代码
$BoardJson = Join-Path $CanonicalRoot "user_data\board.json"
if (Test-Path $BoardJson) {
    Write-Host "[FAILED] [Guard] 正本目录含 user_data\board.json（被污染为某项目的数据副本）！" -ForegroundColor Red
    Write-Host "         全局共享安装要求正本零数据。请人工检查 $CanonicalRoot\user_data\ 后重试。" -ForegroundColor Red
    exit 1
}

# 3. 写入共享标记
$SharedMarker = Join-Path $CanonicalRoot ".yy-flow-shared"
"" | Out-File -FilePath $SharedMarker -Encoding utf8

# 4. 执行全局挂载（各宿主用户级技能目录 + 用户级 Subagent）
Write-Host "[MOUNT]  执行各宿主用户级全局挂载..." -ForegroundColor Yellow
$ExportScript = Join-Path $CanonicalRoot "scripts\verify_and_export_agents.py"
python "$ExportScript" --global

Write-Host ""
Write-Host "[TIP] 全局共享安装完成。使用须知：" -ForegroundColor Green
Write-Host "  - 每个项目的运行数据（user_data\、docs\、锁）仍落各自项目根（YY_FLOW_PROJECT_ROOT 或 CWD）" -ForegroundColor Green
Write-Host "  - 在项目内首次使用请执行该项目的 7 步初始化（/yy-flow start）" -ForegroundColor Green
Write-Host "  - 更新技能：重跑本安装器即可；看板服务更新后需重启" -ForegroundColor Green
Write-Host "  - 卸载：删除各宿主目录软链 + $HOME\agent-skills\multi-agent-flow" -ForegroundColor Green
Write-Host "[SUCCESS] 全局共享安装完成！" -ForegroundColor Cyan
