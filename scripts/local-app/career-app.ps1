#Requires -Version 5.1
<#
.SYNOPSIS
    AI Career OS 本地桌面应用启停器（Windows + Microsoft Edge --app）。

.DESCRIPTION
    start   启动（或复用已经属于本项目运行的）后端 / 前端 / 受控浏览器桥，
            全部健康检查通过后用 Edge 打开独立应用窗口。
    stop    只停止「属于本项目」的服务进程，绝不触碰其他项目占用的端口与进程。
    status  打印当前服务状态。
    restart stop + start。

安全约束：
    * 所有服务只监听 127.0.0.1；
    * 端口占用必须先用进程命令行证明「属于本项目」才可复用或停止，
      仅凭端口存在绝不假定是 AI Career OS（本机 8000 属于另一个项目 CityQuest）；
    * 不读取、不导出、不回传任何密钥；.env 由后端自行加载。
#>
[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'status', 'restart')]
    [string]$Action = 'start',
    [switch]$NoBrowser,
    [switch]$SkipBridge,
    [switch]$Dev,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# ---------------------------------------------------------------- 路径配置
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot  = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$ApiDir       = Join-Path $ProjectRoot 'apps\api'
$WebDir       = Join-Path $ProjectRoot 'apps\web'
$BridgeScript = Join-Path $WebDir 'scripts\browser-bridge.cjs'
$CompatShim   = Join-Path $WebDir 'scripts\next-g-drive-fs-compat.cjs'
$NextBin      = Join-Path $WebDir 'node_modules\next\dist\bin\next'
$PythonExe    = Join-Path $ApiDir '.venv\Scripts\python.exe'

if ($env:AI_CAREER_DATA_DIR -and $env:AI_CAREER_DATA_DIR.Trim()) {
    $DataDir = $env:AI_CAREER_DATA_DIR.Trim()
} else {
    $DataDir = Join-Path $env:LOCALAPPDATA 'AICareerOS'
}
$RuntimeDir = Join-Path $DataDir 'runtime'
$LogDir     = Join-Path $DataDir 'logs'
$StateFile  = Join-Path $RuntimeDir 'local-app-state.json'
$BuildInfo  = Join-Path $WebDir '.next\ai-career-build.json'

# 端口候选（按顺序尝试；被别人占用就顺延，绝不抢占）
$ApiPorts    = @(8100, 8101, 8102, 8103, 8104, 8105)
$WebPorts    = @(3000, 3001, 3002, 3003, 3004, 3005)
$BridgePorts = @(8770, 8771, 8772, 8773)

foreach ($dir in @($RuntimeDir, $LogDir)) {
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
}

# ---------------------------------------------------------------- 通用工具
function Write-Info([string]$Message) {
    if (-not $Quiet) { Write-Host "  $Message" -ForegroundColor Gray }
}
function Write-Ok([string]$Message) {
    if (-not $Quiet) { Write-Host "  [OK] $Message" -ForegroundColor Green }
}
function Write-Warn([string]$Message) {
    if (-not $Quiet) { Write-Host "  [!]  $Message" -ForegroundColor Yellow }
}
function Write-Err([string]$Message) {
    Write-Host "  [X]  $Message" -ForegroundColor Red
}
function Show-Fatal([string]$Message) {
    Write-Host ''
    Write-Host "  [X]  $Message" -ForegroundColor Red
    Write-Host ''
    # 双击启动时没有控制台窗口，用弹窗把错误明确告知用户
    try {
        $ws = New-Object -ComObject WScript.Shell
        $null = $ws.Popup($Message, 0, 'AI Career OS', 16)
    } catch { }
}

function Clear-File([string]$Path) {
    <#
    清空（而不是删除）运行时日志 / 状态文件。
    宿主环境的删除保护会在回收站不可用时把 Remove-Item 直接抛成终止错误，
    一键启动不能被这种策略问题打断；运行时文件只需要置空即可。
    #>
    try {
        [System.IO.File]::WriteAllText($Path, '')
    } catch { }
}

function Repair-DuplicateEnvironmentVars {
    <#
    Windows 进程环境块允许存在「仅大小写不同」的重复键（本机实测 HTTP_PROXY/http_proxy、
    HTTPS_PROXY/https_proxy 各两份）。PowerShell 在带输出重定向调用 Start-Process 时会用
    大小写不敏感的字典装载环境变量，遇到重复键直接抛 "已添加项" 异常，一键启动随即失败。
    这里把每个重复组收敛成唯一的大写拼写，取值保持不变；只影响当前启停器进程及其子进程。
    #>
    $names = @()
    try {
        foreach ($k in [System.Environment]::GetEnvironmentVariables().Keys) { $names += [string]$k }
    } catch { return 0 }
    $groups = @($names | Group-Object { $_.ToUpperInvariant() } | Where-Object { $_.Count -gt 1 })
    if ($groups.Count -eq 0) { return 0 }

    $fixed = 0
    foreach ($g in $groups) {
        $canonical = @($g.Group | Where-Object { $_ -ceq $_.ToUpperInvariant() } | Select-Object -First 1)
        if ($canonical.Count -eq 0) { $canonical = @((([string]$g.Group[0]).ToUpperInvariant())) }
        $canonical = [string]$canonical[0]
        $val = [System.Environment]::GetEnvironmentVariable($canonical)
        # 删除大小写不敏感，重复两条要清两遍才能真正摘干净
        for ($round = 0; $round -lt 2; $round++) {
            foreach ($n in $g.Group) {
                try { [System.Environment]::SetEnvironmentVariable([string]$n, $null) | Out-Null } catch { }
            }
        }
        if ($null -ne $val) { [System.Environment]::SetEnvironmentVariable($canonical, $val) | Out-Null }
        $fixed++
    }
    return $fixed
}

function Get-ListeningPids([int]$Port) {
    $found = @()
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in @($conns)) {
            if ($c.OwningProcess -and $c.OwningProcess -ne 0) { $found += [int]$c.OwningProcess }
        }
    } catch { }
    return @($found | Sort-Object -Unique)
}

function Get-ProcCmdLine([int]$ProcessId) {
    try {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
        if ($p) { return [string]$p.CommandLine }
    } catch { }
    return $null
}

function Test-OwnedByApp([string]$CommandLine) {
    # 只有命令行里带着本项目路径，才承认它是 AI Career OS 的进程
    if (-not $CommandLine) { return $false }
    $cl = $CommandLine.ToLowerInvariant()
    $root = $ProjectRoot.ToLowerInvariant()
    if ($cl.Contains($root)) { return $true }
    if ($cl.Contains('ai-career')) { return $true }
    # 在项目目录里用相对路径启动的桥（node scripts/browser-bridge.cjs）命令行不含项目路径，
    # 之前因此既不能被复用也不能被清理，会和桌面启动器起的桥并存导致令牌不一致。
    if ($cl -match 'scripts[\\/]browser-bridge\.cjs') { return $true }
    return $false
}

function Get-ServiceRole([string]$CommandLine) {
    if (-not $CommandLine) { return $null }
    $cl = $CommandLine.ToLowerInvariant()
    if ($cl -match 'browser-bridge') { return 'bridge' }
    if ($cl -match 'uvicorn') { return 'api' }
    if ($cl -match 'next') { return 'web' }
    return $null
}

function Test-UrlOk([string]$Url, [int]$TimeoutMs = 2500) {
    try {
        $req = [System.Net.HttpWebRequest]::Create($Url)
        $req.Proxy = $null          # 忽略系统代理，避免 localhost 被代理拦截
        $req.Timeout = $TimeoutMs
        $req.Method = 'GET'
        $req.UserAgent = 'ai-career-os-launcher'
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $resp.Close()
        return ($code -lt 500)
    } catch {
        return $false
    }
}

function Wait-ForUrl([string]$Url, [int]$TimeoutSec, [string]$Label) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-UrlOk -Url $Url -TimeoutMs 2500) { return $true }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

function Find-OwnedListener([int[]]$Ports, [string]$Role) {
    foreach ($port in $Ports) {
        foreach ($listenerPid in (Get-ListeningPids -Port $port)) {
            $cl = Get-ProcCmdLine -ProcessId $listenerPid
            if ((Test-OwnedByApp -CommandLine $cl) -and ((Get-ServiceRole -CommandLine $cl) -eq $Role)) {
                return @{ Port = $port; Pid = $listenerPid; CommandLine = $cl }
            }
        }
    }
    return $null
}

function Get-ForeignListener([int]$Port) {
    foreach ($listenerPid in (Get-ListeningPids -Port $Port)) {
        $cl = Get-ProcCmdLine -ProcessId $listenerPid
        if (-not (Test-OwnedByApp -CommandLine $cl)) {
            return @{ Port = $Port; Pid = $listenerPid; CommandLine = $cl }
        }
    }
    return $null
}

function Select-FreePort([int[]]$Ports) {
    foreach ($port in $Ports) {
        if ((Get-ListeningPids -Port $port).Count -eq 0) { return $port }
    }
    return $null
}

# ---------------------------------------------------------------- 启动实现
function Start-ApiService([int]$Port, [int]$WebPort, [string]$BridgeUrl) {
    $out = Join-Path $LogDir 'api.out.log'
    $err = Join-Path $LogDir 'api.err.log'
    foreach ($f in @($out, $err)) { Clear-File -Path $f }

    $prevDataDir  = $env:AI_CAREER_DATA_DIR
    $prevDbUrl    = $env:DATABASE_URL
    $prevPyPath   = $env:PYTHONPATH
    $prevOrigins  = $env:FRONTEND_ORIGINS
    $prevBridgeUrl = $env:BROWSER_BRIDGE_URL
    try {
        $env:AI_CAREER_DATA_DIR = $DataDir
        $env:DATABASE_URL       = ''      # 留空 -> 由 active_dataset 指针决定，避免误连旧主库
        $env:PYTHONPATH         = '.'
        $env:FRONTEND_ORIGINS   = "http://127.0.0.1:$WebPort,http://localhost:$WebPort"
        if ($BridgeUrl) { $env:BROWSER_BRIDGE_URL = $BridgeUrl }   # 让后端连到本次实际的桥（否则多桥时令牌对不上）
        $argList = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port")
        $proc = Start-Process -FilePath $PythonExe -ArgumentList $argList `
                    -WorkingDirectory $ApiDir -WindowStyle Hidden `
                    -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
        return $proc
    } finally {
        $env:AI_CAREER_DATA_DIR = $prevDataDir
        $env:DATABASE_URL       = $prevDbUrl
        $env:PYTHONPATH         = $prevPyPath
        $env:FRONTEND_ORIGINS   = $prevOrigins
        $env:BROWSER_BRIDGE_URL = $prevBridgeUrl
    }
}

function Start-WebService([int]$Port, [int]$ApiPort, [bool]$UseDev) {
    $out = Join-Path $LogDir 'web.out.log'
    $err = Join-Path $LogDir 'web.err.log'
    foreach ($f in @($out, $err)) { Clear-File -Path $f }

    $prevApiBase = $env:NEXT_PUBLIC_API_BASE_URL
    $prevDistDir = $env:NEXT_DIST_DIR
    try {
        $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:$ApiPort"
        if ($UseDev) {
            # 关键：dev 产物必须和 production 隔离，否则 next dev 会清空 .next，
            # 把已经构建好的 production 产物删掉
            $env:NEXT_DIST_DIR = '.next-dev'
            $argList = @('--require', $CompatShim, $NextBin, 'dev', '-H', '127.0.0.1', '-p', "$Port")
        } else {
            $env:NEXT_DIST_DIR = ''
            $argList = @('--require', $CompatShim, $NextBin, 'start', '-H', '127.0.0.1', '-p', "$Port")
        }
        $proc = Start-Process -FilePath 'node.exe' -ArgumentList $argList `
                    -WorkingDirectory $WebDir -WindowStyle Hidden `
                    -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
        return $proc
    } finally {
        $env:NEXT_PUBLIC_API_BASE_URL = $prevApiBase
        $env:NEXT_DIST_DIR = $prevDistDir
    }
}

function Start-BridgeService([int]$Port) {
    $out = Join-Path $LogDir 'bridge.out.log'
    $err = Join-Path $LogDir 'bridge.err.log'
    foreach ($f in @($out, $err)) { Clear-File -Path $f }

    $prevPort = $env:BROWSER_BRIDGE_PORT
    try {
        $env:BROWSER_BRIDGE_PORT = "$Port"
        $argList = @($BridgeScript)
        $proc = Start-Process -FilePath 'node.exe' -ArgumentList $argList `
                    -WorkingDirectory $WebDir -WindowStyle Hidden `
                    -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
        return $proc
    } finally {
        $env:BROWSER_BRIDGE_PORT = $prevPort
    }
}

# ---------------------------------------------------------------- 停止实现
function Stop-ProcessTree([int]$ProcessId, [int]$Depth = 0) {
    if ($Depth -gt 6) { return }
    try {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue)
    } catch { $children = @() }
    foreach ($c in $children) { Stop-ProcessTree -ProcessId ([int]$c.ProcessId) -Depth ($Depth + 1) }
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Info "停止进程 $ProcessId ($($proc.ProcessName))"
            Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
        }
    } catch { }
}

function Stop-AppServices {
    Write-Host ''
    Write-Host '停止 AI Career OS 本地服务...' -ForegroundColor Cyan

    # 1) 按状态文件里记录的 PID 停（先二次确认命令行属于本项目）
    if (Test-Path -LiteralPath $StateFile) {
        try {
            $state = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($key in @('api', 'web', 'bridge')) {
                $item = $state.$key
                if ($null -ne $item -and $item.pid) {
                    $cl = Get-ProcCmdLine -ProcessId ([int]$item.pid)
                    if (Test-OwnedByApp -CommandLine $cl) { Stop-ProcessTree -ProcessId ([int]$item.pid) }
                }
            }
        } catch { }
    }

    # 2) 兜底清扫：只杀命令行里带本项目路径的 api / web / bridge 进程
    $ourProcs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { (Test-OwnedByApp -CommandLine $_.CommandLine) -and (Get-ServiceRole -CommandLine $_.CommandLine) })
    foreach ($p in $ourProcs) {
        Stop-ProcessTree -ProcessId ([int]$p.ProcessId)
    }

    Clear-File -Path $StateFile   # 置空即代表“没有在运行的实例”
    Write-Ok '已停止（其他项目的服务未受影响）'
}

# ---------------------------------------------------------------- 受控浏览器桥去重
# 真实踩过：桌面启动器起一个桥、手动 start-browser-bridge.cmd 又起一个，
# 两个桥各自持有不同令牌，而令牌文件只保留最后一个 → 后端按固定端口连到另一个桥，报“令牌不匹配”。
function Get-AllOwnedBridges {
    $found = @()
    foreach ($port in $BridgePorts) {
        foreach ($listenerPid in (Get-ListeningPids -Port $port)) {
            $cl = Get-ProcCmdLine -ProcessId $listenerPid
            if ((Test-OwnedByApp -CommandLine $cl) -and ((Get-ServiceRole -CommandLine $cl) -eq 'bridge')) {
                $found += @{ Port = $port; Pid = $listenerPid }
            }
        }
    }
    return $found
}

function Stop-StrayBridges([int]$KeepPort) {
    foreach ($b in (Get-AllOwnedBridges)) {
        if ([int]$b.Port -ne $KeepPort) {
            Write-Info "清理多余的受控浏览器桥 (127.0.0.1:$($b.Port), pid=$($b.Pid))"
            Stop-ProcessTree -ProcessId ([int]$b.Pid)
        }
    }
}

# ---------------------------------------------------------------- 状态实现
function Show-Status {
    $state = $null
    if (Test-Path -LiteralPath $StateFile) {
        try { $state = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
    }
    $api = Find-OwnedListener -Ports $ApiPorts -Role 'api'
    $web = Find-OwnedListener -Ports $WebPorts -Role 'web'
    $brg = Find-OwnedListener -Ports $BridgePorts -Role 'bridge'

    Write-Host ''
    Write-Host 'AI Career OS 本地服务状态' -ForegroundColor Cyan
    foreach ($pair in @(
            @{ Name = '后端 API'; Obj = $api; Path = '/health' },
            @{ Name = '前端 Web'; Obj = $web; Path = '/' },
            @{ Name = '浏览器桥  '; Obj = $brg; Path = '/health' })) {
        $o = $pair.Obj
        if ($null -eq $o) { Write-Host ("  {0} : 未运行" -f $pair.Name) -ForegroundColor Yellow; continue }
        $url = "http://127.0.0.1:$($o.Port)$($pair.Path)"
        $ok = Test-UrlOk -Url $url
        $color = if ($ok) { 'Green' } else { 'Yellow' }
        Write-Host ("  {0} : {1}  pid={2}  健康={3}" -f $pair.Name, $url, $o.Pid, $ok) -ForegroundColor $color
    }
    if ($state) {
        Write-Host ("  模式      : {0}" -f $state.mode) -ForegroundColor Gray
        Write-Host ("  启动时间  : {0}" -f $state.started_at) -ForegroundColor Gray
    }
    Write-Host ''
}

# ---------------------------------------------------------------- 启动主流程
function Start-App {
    Write-Host ''
    Write-Host 'AI Career OS 启动中...' -ForegroundColor Cyan
    Write-Info "项目目录: $ProjectRoot"
    Write-Info "数据目录: $DataDir"

    # --- 环境自检 ---
    $repaired = Repair-DuplicateEnvironmentVars
    if ($repaired -gt 0) {
        Write-Info "已收敛 $repaired 组重复环境变量（仅大小写不同），避免子进程启动失败"
    }
    if (-not (Test-Path -LiteralPath $PythonExe)) { Show-Fatal "找不到 Python 解释器：$PythonExe"; return 1 }
    if (-not (Test-Path -LiteralPath $NextBin))   { Show-Fatal "找不到 Next.js 入口：$NextBin`n请先在 apps/web 执行 npm install。"; return 1 }
    $nodeCmd = Get-Command 'node.exe' -ErrorAction SilentlyContinue
    if (-not $nodeCmd) { Show-Fatal '找不到 node.exe，请先安装 Node.js。'; return 1 }
    if (-not (Test-Path -LiteralPath $DataDir)) { New-Item -ItemType Directory -Path $DataDir -Force | Out-Null }

    # --- 复用已经属于本项目运行的服务（避免重复启动）---
    $existingWeb = Find-OwnedListener -Ports $WebPorts -Role 'web'
    $reusedWeb = $false
    if ($existingWeb -and (Test-UrlOk -Url "http://127.0.0.1:$($existingWeb.Port)/")) {
        $reusedWeb = $true
        $WebPort = $existingWeb.Port
        $webProc = $null
        Write-Ok "前端已在运行，直接复用: http://127.0.0.1:$WebPort (pid=$($existingWeb.Pid))"
    } else {
        $WebPort = Select-FreePort -Ports $WebPorts
        if ($null -eq $WebPort) {
            $foreign = Get-ForeignListener -Port $WebPorts[0]
            $detail = if ($foreign) { "其中 $($foreign.Port) 属于其他程序：$($foreign.CommandLine)" } else { '占用者不明' }
            Show-Fatal "前端端口 $($WebPorts -join ',') 全部被占用。$detail`nAI Career OS 不会抢占其他项目的端口，请先关闭占用程序后重试。"
            return 1
        }
    }

    $existingApi = Find-OwnedListener -Ports $ApiPorts -Role 'api'
    if ($existingApi -and (Test-UrlOk -Url "http://127.0.0.1:$($existingApi.Port)/health")) {
        $ApiPort = $existingApi.Port
        $apiProc = $null
        Write-Ok "后端已在运行，直接复用: http://127.0.0.1:$ApiPort/health (pid=$($existingApi.Pid))"
    } else {
        $ApiPort = Select-FreePort -Ports $ApiPorts
        if ($null -eq $ApiPort) {
            $foreign = Get-ForeignListener -Port $ApiPorts[0]
            $detail = if ($foreign) { "例如 $($foreign.Port) 被 $($foreign.CommandLine) 占用" } else { '' }
            Show-Fatal "后端端口 $($ApiPorts -join ',') 全部被占用，且都不属于本项目。$detail`n（本机 8000 属于其他项目，AI Career OS 不会抢占。）"
            return 1
        }
    }

    # --- 先起受控浏览器桥：后端要连到它，端口必须早于后端确定 ---
    $bridgePort = $null
    $bridgeProc = $null
    if (-not $SkipBridge) {
        $existingBridge = Find-OwnedListener -Ports $BridgePorts -Role 'bridge'
        if ($existingBridge -and (Test-UrlOk -Url "http://127.0.0.1:$($existingBridge.Port)/health")) {
            $bridgePort = $existingBridge.Port
            Write-Ok "受控浏览器桥已在运行: http://127.0.0.1:$bridgePort (pid=$($existingBridge.Pid))"
        } else {
            $bridgePort = Select-FreePort -Ports $BridgePorts
        }
        if ($bridgePort) {
            Stop-StrayBridges -KeepPort $bridgePort
            if ($null -eq $existingBridge -or -not (Test-UrlOk -Url "http://127.0.0.1:$bridgePort/health")) {
                Write-Info "启动受控浏览器桥 (127.0.0.1:$bridgePort)..."
                $bridgeProc = Start-BridgeService -Port $bridgePort
                if (Wait-ForUrl -Url "http://127.0.0.1:$bridgePort/health" -TimeoutSec 30 -Label 'Bridge') {
                    Write-Ok "浏览器桥就绪 http://127.0.0.1:$bridgePort (pid=$($bridgeProc.Id))"
                } else {
                    Write-Warn "浏览器桥未就绪（网申填表暂不可用），日志: $(Join-Path $LogDir 'bridge.err.log')"
                }
            }
        }
    }

    # --- 决定前端模式：有 production build 就用 next start ---
    $hasBuild = Test-Path -LiteralPath (Join-Path $WebDir '.next\BUILD_ID')
    $useDev = $Dev -or (-not $hasBuild)
    if ($useDev -and -not $Dev) {
        Write-Warn '未检测到 production build（.next/BUILD_ID），本次以【开发模式】启动（不是正式构建）。'
    }

    # --- 启动后端（带上本次实际的桥地址，避免多桥时令牌对不上）---
    if ($null -eq $existingApi -or -not (Test-UrlOk -Url "http://127.0.0.1:$ApiPort/health")) {
        Write-Info "启动后端 API (127.0.0.1:$ApiPort)..."
        $bridgeUrl = if ($bridgePort) { "http://127.0.0.1:$bridgePort" } else { '' }
        $apiProc = Start-ApiService -Port $ApiPort -WebPort $WebPort -BridgeUrl $bridgeUrl
        if (-not (Wait-ForUrl -Url "http://127.0.0.1:$ApiPort/health" -TimeoutSec 60 -Label 'API')) {
            Write-Err "后端启动超时，请查看日志: $(Join-Path $LogDir 'api.err.log')"
            return 1
        }
        Write-Ok "后端就绪 http://127.0.0.1:$ApiPort/health (pid=$($apiProc.Id))"
    }

    # --- 启动前端 ---
    if (-not $reusedWeb) {
        $modeText = if ($useDev) { '开发模式' } else { 'production' }
        Write-Info "启动前端 ($modeText, 127.0.0.1:$WebPort)..."
        $webProc = Start-WebService -Port $WebPort -ApiPort $ApiPort -UseDev $useDev
        $waitSec = if ($useDev) { 150 } else { 90 }
        if (-not (Wait-ForUrl -Url "http://127.0.0.1:$WebPort/" -TimeoutSec $waitSec -Label 'Web')) {
            Write-Err "前端启动超时，请查看日志: $(Join-Path $LogDir 'web.err.log')"
            return 1
        }
        Write-Ok "前端就绪 http://127.0.0.1:$WebPort ($modeText, pid=$($webProc.Id))"
    } else {
        # 复用实例时核对它指向的后端地址，避免前后端端口不一致
        if (Test-Path -LiteralPath $BuildInfo) {
            try {
                $bi = Get-Content -LiteralPath $BuildInfo -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($bi.api_base_url -and ($bi.api_base_url -ne "http://127.0.0.1:$ApiPort")) {
                    Write-Warn "前端构建时指向 $($bi.api_base_url)，当前后端是 http://127.0.0.1:$ApiPort，可能出现请求失败。"
                }
            } catch { }
        }
    }

    # --- 打开 Edge 独立应用窗口（结果写入状态文件，便于事后核对）---
    $browserInfo = [pscustomobject]@{ opened = $false; app_window = $false; url = "http://127.0.0.1:$WebPort" }
    if (-not $NoBrowser) { $browserInfo = Open-AppWindow -Url "http://127.0.0.1:$WebPort" }

    # --- 写状态文件 ---
    $state = [ordered]@{
        started_at = (Get-Date).ToString('s')
        mode       = if ($useDev) { 'dev' } else { 'production' }
        data_dir   = $DataDir
        api        = @{ port = $ApiPort; pid = if ($apiProc) { $apiProc.Id } else { $existingApi.Pid }; url = "http://127.0.0.1:$ApiPort" }
        web        = @{ port = $WebPort; pid = if ($webProc) { $webProc.Id } else { $existingWeb.Pid }; url = "http://127.0.0.1:$WebPort" }
        bridge     = @{ port = $bridgePort; pid = if ($bridgeProc) { $bridgeProc.Id } elseif ($existingBridge) { $existingBridge.Pid } else { $null } }
        reused     = @{ api = [bool]$existingApi; web = $reusedWeb }
        browser    = $browserInfo
    }
    ($state | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath $StateFile -Encoding UTF8

    Write-Host ''
    Write-Host '  AI Career OS 已就绪' -ForegroundColor Green
    Write-Host ("    前端 : http://127.0.0.1:{0}" -f $WebPort) -ForegroundColor White
    Write-Host ("    后端 : http://127.0.0.1:{0}/health" -f $ApiPort) -ForegroundColor White
    Write-Host ("    数据 : {0}" -f $DataDir) -ForegroundColor White
    Write-Host ("    模式 : {0}" -f $(if ($useDev) { '开发模式（非 production 构建）' } else { 'production 构建' })) -ForegroundColor White
    Write-Host ''
    Write-Host '    需要停止服务时运行 stop-career.cmd（只停止本项目进程）。' -ForegroundColor Gray
    Write-Host ''
    return 0
}

function Open-AppWindow([string]$Url) {
    <#
    用 Edge --app 打开独立应用窗口（没有地址栏/标签页，外观等同桌面软件）。
    不指定 --user-data-dir：复用你日常登录的 Edge 配置，BOSS 直聘登录态可继续使用。
    返回值写入状态文件，作为「本次启动确实调用过独立窗口」的可核对证据 ——
    因为 Edge 在本机已有实例时会把窗口委托给既有进程，新进程随即退出，
    事后在进程列表里查不到 --app 参数，不能以此判定失败。
    #>
    $edgeCandidates = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe')
    )
    $edge = $edgeCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $edge) {
        $chrome = Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
        if (Test-Path -LiteralPath $chrome) { $edge = $chrome }
    }
    $appUrl = '--app=' + $Url
    if (-not $edge) {
        Write-Warn "未找到 Microsoft Edge，改用默认浏览器打开 $Url"
        Start-Process $Url
        return [pscustomobject]@{ opened = $true; app_window = $false; exe = $null; url = $Url; at = (Get-Date).ToString('s') }
    }
    $proc = Start-Process -FilePath $edge -ArgumentList @($appUrl, '--window-size=1440,900', '--no-first-run', '--no-default-browser-check') -PassThru
    Write-Ok "已用 Edge 独立窗口打开 $Url"
    return [pscustomobject]@{
        opened     = $true
        app_window = $true
        exe        = $edge
        url        = $Url
        args       = @($appUrl, '--window-size=1440,900')
        pid        = if ($proc) { $proc.Id } else { $null }
        at         = (Get-Date).ToString('s')
    }
}

# ---------------------------------------------------------------- 入口
switch ($Action) {
    'stop'    { Stop-AppServices; exit 0 }
    'status'  { Show-Status; exit 0 }
    'restart' { Stop-AppServices; Start-Sleep -Seconds 2; exit (Start-App) }
    default   { exit (Start-App) }
}
