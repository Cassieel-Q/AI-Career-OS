#Requires -Version 5.1
<#
.SYNOPSIS
    在同一次会话内：启动本地服务 → 运行一个 node 脚本 → 停止服务。

.DESCRIPTION
    本机受控终端在命令结束时会回收子进程，服务无法跨调用存活，
    因此端到端脚本必须和「启动/停止」放在同一次 PowerShell 调用里跑完。

.EXAMPLE
    run-with-services.ps1 -NodeScript apps\web\scripts\e2e-boss-local-app.cjs
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$NodeScript,
    [switch]$Dev,
    [switch]$KeepRunning
)

$ErrorActionPreference = 'Stop'
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$Launcher    = Join-Path $ScriptDir 'career-app.ps1'

Write-Host ''
Write-Host "== 启动本地服务 ==" -ForegroundColor Cyan
if ($Dev) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $Launcher -Action start -NoBrowser -Dev
} else {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $Launcher -Action start -NoBrowser
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] 服务启动失败，中止" -ForegroundColor Red
    exit 1
}

$node = (Get-Command 'node.exe' -ErrorAction SilentlyContinue).Source
if (-not $node) { Write-Host '[X] 找不到 node.exe' -ForegroundColor Red; exit 1 }

$target = $NodeScript
if (-not [System.IO.Path]::IsPathRooted($target)) { $target = Join-Path $ProjectRoot $target }
if (-not (Test-Path -LiteralPath $target)) {
    Write-Host "[X] 找不到脚本: $target" -ForegroundColor Red
    exit 1
}

Write-Host ''
Write-Host "== 运行 $NodeScript ==" -ForegroundColor Cyan
Push-Location $ProjectRoot
try {
    & $node $target
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

if (-not $KeepRunning) {
    Write-Host ''
    Write-Host '== 停止本地服务 ==' -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File $Launcher -Action stop
}

Write-Host ''
Write-Host ("== 结束，脚本退出码 {0} ==" -f $code) -ForegroundColor Cyan
exit $code
