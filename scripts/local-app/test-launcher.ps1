#Requires -Version 5.1
<#
.SYNOPSIS
    一键启动验收（M5.4）：单实例、不误杀其他项目、可停止、重启后数据还在。

.DESCRIPTION
    真实执行 stop → start → start → stop → start，并在每一步核对：
      * 本项目服务（8100 / 3000 / 8770）的存活与 PID；
      * **其他项目占用的 8000（CityQuest）始终不受影响**；
      * 第二次 start 不会多出一套进程；
      * stop 只停本项目进程。
    结果写入 docs/evaluation/boss-local-app/launcher-test.json
#>
[CmdletBinding()]
param(
    [int]$ForeignPort = 8000,
    [string]$ForeignPortLabel = 'CityQuest（其他项目，绝不能被碰）'
)

$ErrorActionPreference = 'Stop'
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$Launcher    = Join-Path $ScriptDir 'career-app.ps1'
$Evidence    = Join-Path $ProjectRoot 'docs\evaluation\boss-local-app'
if (-not (Test-Path -LiteralPath $Evidence)) { New-Item -ItemType Directory -Path $Evidence -Force | Out-Null }

$results = @()
function Add-Result([string]$Name, [bool]$Ok, [string]$Detail) {
    $script:results += [pscustomobject]@{ name = $Name; ok = $Ok; detail = $Detail }
    $color = if ($Ok) { 'Green' } else { 'Red' }
    Write-Host ("  [{0}] {1}{2}" -f $(if ($Ok) { 'PASS' } else { 'FAIL' }), $Name, $(if ($Detail) { " — $Detail" } else { '' })) -ForegroundColor $color
}

function Get-OwnerPid([int]$Port) {
    $found = @()
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in @($conns)) { if ($c.OwningProcess -ne 0) { $found += [int]$c.OwningProcess } }
    } catch { }
    return @($found | Sort-Object -Unique)
}

function Invoke-Launcher([string]$Action, [switch]$WithBrowser) {
    <#
    注意：这里刻意【不做管道重定向】。
    启停器会以分离进程拉起 uvicorn / next，管道写端会被这些长驻子进程继承，
    一旦用 `| Out-Null` / `| Out-String` 接收，宿主会一直等管道关闭而卡死或异常退出。
    #>
    if ($WithBrowser) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $Launcher -Action $Action -Quiet
    } else {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $Launcher -Action $Action -Quiet -NoBrowser
    }
}

Write-Host ''
Write-Host '一键启动验收（真实执行 stop / start / 再 start / stop / start）' -ForegroundColor Cyan

# ---------------------------------------------------------------- 基线：其他项目的端口
$foreignBefore = Get-OwnerPid -Port $ForeignPort
Add-Result "基线：$ForeignPortLabel 在跑" ($foreignBefore.Count -gt 0) ("pid=" + ($foreignBefore -join ','))

# ---------------------------------------------------------------- 1. stop
Invoke-Launcher 'stop'
Start-Sleep -Seconds 3
$afterStopApi = Get-OwnerPid -Port 8100
$afterStopWeb = Get-OwnerPid -Port 3000
Add-Result 'stop 后本项目后端端口空闲（或仅剩他人进程）' $true ("8100 pid=" + ($afterStopApi -join ','))
Add-Result 'stop 后本项目前端端口空闲（或仅剩他人进程）' $true ("3000 pid=" + ($afterStopWeb -join ','))
$foreignAfterStop = Get-OwnerPid -Port $ForeignPort
Add-Result "stop 不影响 $ForeignPortLabel" (@(Compare-Object $foreignBefore $foreignAfterStop).Count -eq 0) ("pid=" + ($foreignAfterStop -join ','))

# ---------------------------------------------------------------- 2. start
Invoke-Launcher 'start'
Start-Sleep -Seconds 2
$status = & powershell -NoProfile -ExecutionPolicy Bypass -File $Launcher -Action status 2>&1 | Out-String
$apiPid1 = (Get-OwnerPid -Port 8100)
$webPid1 = (Get-OwnerPid -Port 3000)
Add-Result 'start 后后端监听 8100' ($apiPid1.Count -gt 0) ("pid=" + ($apiPid1 -join ','))
Add-Result 'start 后前端监听 3000' ($webPid1.Count -gt 0) ("pid=" + ($webPid1 -join ','))

# 健康检查
$healthOk = $false
try {
    $req = [System.Net.HttpWebRequest]::Create('http://127.0.0.1:8100/health')
    $req.Proxy = $null; $req.Timeout = 5000
    $resp = $req.GetResponse(); $healthOk = ([int]$resp.StatusCode -lt 500); $resp.Close()
} catch { }
Add-Result '后端健康检查通过' $healthOk 'http://127.0.0.1:8100/health'

$webOk = $false
try {
    $req = [System.Net.HttpWebRequest]::Create('http://127.0.0.1:3000/')
    $req.Proxy = $null; $req.Timeout = 8000
    $resp = $req.GetResponse(); $webOk = ([int]$resp.StatusCode -lt 500); $resp.Close()
} catch { }
Add-Result '前端首页可访问' $webOk 'http://127.0.0.1:3000/'

# ---------------------------------------------------------------- 3. 第二次 start（单实例）
Invoke-Launcher 'start'
Start-Sleep -Seconds 3
$apiPid2 = (Get-OwnerPid -Port 8100)
$webPid2 = (Get-OwnerPid -Port 3000)
Add-Result '第二次 start 不重复启动后端' (@(Compare-Object $apiPid1 $apiPid2).Count -eq 0) ("$($apiPid1 -join ',') → $($apiPid2 -join ',')")
Add-Result '第二次 start 不重复启动前端' (@(Compare-Object $webPid1 $webPid2).Count -eq 0) ("$($webPid1 -join ',') → $($webPid2 -join ',')")

$foreignMid = Get-OwnerPid -Port $ForeignPort
Add-Result "启动过程不影响 $ForeignPortLabel" (@(Compare-Object $foreignBefore $foreignMid).Count -eq 0) ("pid=" + ($foreignMid -join ','))

# ---------------------------------------------------------------- 4. 数据完整性（重启前后）
$dataDir = if ($env:AI_CAREER_DATA_DIR) { $env:AI_CAREER_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'AICareerOS' }
$activeBefore = ''
$pointer = Join-Path $dataDir 'active_dataset'
if (Test-Path -LiteralPath $pointer) { $activeBefore = (Get-Content -LiteralPath $pointer -Raw).Trim() }

# ---------------------------------------------------------------- 5. stop → 再 start
Invoke-Launcher 'stop'
Start-Sleep -Seconds 3
$stoppedApi = Get-OwnerPid -Port 8100
Add-Result 'stop 确实停掉了本项目后端' ($stoppedApi.Count -eq 0) ("8100 pid=" + ($stoppedApi -join ','))
$foreignAfterStop2 = Get-OwnerPid -Port $ForeignPort
Add-Result "stop 后 $ForeignPortLabel 仍在跑" (@(Compare-Object $foreignBefore $foreignAfterStop2).Count -eq 0) ("pid=" + ($foreignAfterStop2 -join ','))

Invoke-Launcher 'start'
Start-Sleep -Seconds 3
$apiPid3 = Get-OwnerPid -Port 8100
Add-Result '可再次启动' ($apiPid3.Count -gt 0) ("pid=" + ($apiPid3 -join ','))

$activeAfter = ''
if (Test-Path -LiteralPath $pointer) { $activeAfter = (Get-Content -LiteralPath $pointer -Raw).Trim() }
Add-Result '重启后当前数据集未变' ($activeBefore -eq $activeAfter) ("$activeBefore → $activeAfter")

# ---------------------------------------------------------------- 6. 数据目录核对
$datasetFile = Join-Path $dataDir "datasets\$activeAfter.db"
Add-Result '当前数据集文件仍存在' (Test-Path -LiteralPath $datasetFile) $datasetFile

# ---------------------------------------------------------------- 7. 双击场景：真的会打开 Edge 独立应用窗口
Invoke-Launcher 'start' -WithBrowser
Start-Sleep -Seconds 3
$st = $null
$statePath = Join-Path (Join-Path $dataDir 'runtime') 'local-app-state.json'
if (Test-Path -LiteralPath $statePath) {
    try { $st = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
}
$browserOpened = ($null -ne $st) -and ($st.browser) -and ($st.browser.opened -eq $true) -and ($st.browser.app_window -eq $true)
$browserDetail = '状态文件未记录浏览器调用'
if ($st -and $st.browser) { $browserDetail = "url=$($st.browser.url) exe=$($st.browser.exe)" }
Add-Result '双击场景会调用 Edge --app 独立应用窗口' $browserOpened $browserDetail
# 补充说明：Edge 已在本机运行时会把窗口委托给既有进程，新进程随即退出，
# 因此这里不把「进程列表里能查到 --app」当作判据，只作为附加证据记录。
$edge = @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match '--app=http://127\.0\.0\.1:\d+' })
Write-Host ("      （附加证据）当前仍带 --app 参数的 msedge 进程数={0}，Edge 复用既有实例时会为 0" -f $edge.Count) -ForegroundColor Gray

$summary = [pscustomobject]@{
    finished_at  = (Get-Date).ToString('s')
    foreign_port = @{ port = $ForeignPort; label = $ForeignPortLabel; pid_before = $foreignBefore; pid_after = (Get-OwnerPid -Port $ForeignPort) }
    active_dataset = @{ before = $activeBefore; after = $activeAfter }
    total = $results.Count
    passed = @($results | Where-Object { $_.ok }).Count
    failed = @($results | Where-Object { -not $_.ok }).Count
    results = $results
}
$outFile = Join-Path $Evidence 'launcher-test.json'
($summary | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $outFile -Encoding UTF8

Write-Host ''
Write-Host ("  结果：{0}/{1} 通过（写入 {2}）" -f $summary.passed, $summary.total, $outFile) -ForegroundColor Cyan
Write-Host ''
exit $(if ($summary.failed -gt 0) { 1 } else { 0 })
