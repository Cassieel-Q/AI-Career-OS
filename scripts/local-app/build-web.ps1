#Requires -Version 5.1
<#
.SYNOPSIS
    构建 AI Career OS 前端 production 产物（.next）。

.DESCRIPTION
    优先在 G 盘原地构建；若遇到 G 盘文件系统 EPERM（readlink EISDIR / trace 写入），
    自动切换到 NTFS 隔离目录（默认 D:\ai-career-web-build）真实构建，
    再把 .next 复制回 G 盘。全过程不删除任何用户数据。

    构建时会把后端地址烧进客户端包：NEXT_PUBLIC_API_BASE_URL。
#>
[CmdletBinding()]
param(
    [int]$ApiPort = 8100,
    [string]$IsolatedRoot = 'D:\ai-career-web-build'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$WebDir      = Join-Path $ProjectRoot 'apps\web'
$CompatShim  = Join-Path $WebDir 'scripts\next-g-drive-fs-compat.cjs'
$NextBin     = Join-Path $WebDir 'node_modules\next\dist\bin\next'

if (-not (Test-Path -LiteralPath $NextBin)) {
    Write-Host '[X] 找不到 Next.js 入口，请先执行 npm install。' -ForegroundColor Red
    exit 1
}

$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:$ApiPort"
$env:NEXT_TELEMETRY_DISABLED  = '1'

function Invoke-Build([string]$WorkDir) {
    Write-Host "  构建目录: $WorkDir" -ForegroundColor Gray
    $shim = if ($WorkDir -eq $WebDir) { $CompatShim } else { (Join-Path $WorkDir 'scripts\next-g-drive-fs-compat.cjs') }
    $bin  = if ($WorkDir -eq $WebDir) { $NextBin } else { (Join-Path $WorkDir 'node_modules\next\dist\bin\next') }
    $prev = Get-Location
    try {
        Set-Location -LiteralPath $WorkDir
        & node.exe --require $shim $bin build
        return $LASTEXITCODE
    } finally {
        Set-Location -LiteralPath $prev
    }
}

Write-Host ''
Write-Host '构建前端 production 产物...' -ForegroundColor Cyan
Write-Host "  后端地址: http://127.0.0.1:$ApiPort" -ForegroundColor Gray

$code = Invoke-Build -WorkDir $WebDir
$builtIn = $WebDir

if ($code -ne 0) {
    Write-Host '  [!] G 盘原地构建失败，切换到 NTFS 隔离目录重试...' -ForegroundColor Yellow
    $iso = Join-Path $IsolatedRoot 'web'
    if (-not (Test-Path -LiteralPath $iso)) { New-Item -ItemType Directory -Path $iso -Force | Out-Null }
    # 排除 .next / 运行期缓存；其余真实复制
    $robocopyArgs = @(
        $WebDir, $iso, '/MIR', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:1', '/W:1',
        '/XD', '.next', 'node_modules\.cache', '.git',
        '/XF', 'tsconfig.tsbuildinfo'
    )
    & robocopy @robocopyArgs | Out-Null
    if ($LASTEXITCODE -ge 8) {
        Write-Host "[X] 复制到隔离目录失败 (robocopy=$LASTEXITCODE)。" -ForegroundColor Red
        exit 1
    }
    $code = Invoke-Build -WorkDir $iso
    $builtIn = $iso
    if ($code -ne 0) {
        Write-Host '[X] 隔离目录构建同样失败，请查看上方报错。' -ForegroundColor Red
        exit 1
    }
    # 把产物复制回 G 盘
    $srcNext = Join-Path $iso '.next'
    $dstNext = Join-Path $WebDir '.next'
    if (Test-Path -LiteralPath $dstNext) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $bak = Join-Path $WebDir ".next.bak-$stamp"
        Write-Host "  备份旧 .next -> $bak" -ForegroundColor Gray
        Move-Item -LiteralPath $dstNext -Destination $bak -Force
    }
    & robocopy $srcNext $dstNext '/E' '/NFL' '/NDL' '/NJH' '/NJS' '/NP' '/R:1' '/W:1' | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $dstNext 'BUILD_ID'))) {
        Write-Host '[X] 复制回 G 盘后缺少 .next/BUILD_ID，构建失败。' -ForegroundColor Red
        exit 1
    }
}

# 记录本次构建使用的后端地址，供启动器核对前后端端口是否一致
$buildInfo = Join-Path $WebDir '.next\ai-career-build.json'
$payload = @{
    api_base_url = "http://127.0.0.1:$ApiPort"
    built_at     = (Get-Date).ToString('s')
    built_in     = $builtIn
    next_build_id = (Get-Content -LiteralPath (Join-Path $WebDir '.next\BUILD_ID') -Raw -ErrorAction SilentlyContinue)
}
($payload | ConvertTo-Json) | Set-Content -LiteralPath $buildInfo -Encoding UTF8

Write-Host ''
Write-Host '  [OK] 前端 production 构建完成' -ForegroundColor Green
Write-Host "       BUILD_ID: $($payload.next_build_id)" -ForegroundColor Gray
Write-Host "       API     : $($payload.api_base_url)" -ForegroundColor Gray
Write-Host ''
exit 0
