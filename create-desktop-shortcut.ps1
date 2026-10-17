#Requires -Version 5.1
<#
.SYNOPSIS
    在 Windows 桌面创建「AI Career OS」一键启动 / 停止快捷方式。

.DESCRIPTION
    - 启动快捷方式直接调用 powershell -WindowStyle Hidden 运行启停器，不弹控制台黑窗；
    - 自动生成应用图标（%LOCALAPPDATA%\AICareerOS\app.ico），失败时回退到 Edge 图标；
    - 已存在同名快捷方式会被覆盖更新，不会重复创建。
#>
[CmdletBinding()]
param(
    [string]$DesktopPath,
    [switch]$AlsoStartMenu
)

$ErrorActionPreference = 'Stop'

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = $ScriptDir
$Launcher    = Join-Path $ProjectRoot 'scripts\local-app\career-app.ps1'

if (-not $DesktopPath) { $DesktopPath = [Environment]::GetFolderPath('Desktop') }
if (-not (Test-Path -LiteralPath $Launcher)) {
    Write-Host "[X] 找不到启停脚本: $Launcher" -ForegroundColor Red
    exit 1
}

if ($env:AI_CAREER_DATA_DIR -and $env:AI_CAREER_DATA_DIR.Trim()) {
    $DataDir = $env:AI_CAREER_DATA_DIR.Trim()
} else {
    $DataDir = Join-Path $env:LOCALAPPDATA 'AICareerOS'
}
if (-not (Test-Path -LiteralPath $DataDir)) { New-Item -ItemType Directory -Path $DataDir -Force | Out-Null }

# ---------------------------------------------------------------- 生成图标
function New-AppIcon([string]$OutPath) {
    try {
        Add-Type -AssemblyName System.Drawing
        $size = 128
        $bmp = New-Object System.Drawing.Bitmap $size, $size
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.Clear([System.Drawing.Color]::Transparent)

        $brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
            (New-Object System.Drawing.Point 0, 0),
            (New-Object System.Drawing.Point $size, $size),
            [System.Drawing.Color]::FromArgb(255, 37, 99, 235),
            [System.Drawing.Color]::FromArgb(255, 14, 165, 233))
        $path = New-Object System.Drawing.Drawing2D.GraphicsPath
        $r = 26
        $path.AddArc(0, 0, $r, $r, 180, 90)
        $path.AddArc($size - $r, 0, $r, $r, 270, 90)
        $path.AddArc($size - $r, $size - $r, $r, $r, 0, 90)
        $path.AddArc(0, $size - $r, $r, $r, 90, 90)
        $path.CloseAllFigures()
        $g.FillPath($brush, $path)

        $font = New-Object System.Drawing.Font('Segoe UI', 52, [System.Drawing.FontStyle]::Bold)
        $sf = New-Object System.Drawing.StringFormat
        $sf.Alignment = [System.Drawing.StringAlignment]::Center
        $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
        $rect = New-Object System.Drawing.RectangleF 0, 4, $size, $size
        $g.DrawString('AI', $font, [System.Drawing.Brushes]::White, $rect, $sf)
        $g.Flush()

        $hIcon = $bmp.GetHicon()
        $icon = [System.Drawing.Icon]::FromHandle($hIcon)
        $fs = [System.IO.File]::Open($OutPath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
        try { $icon.Save($fs) } finally { $fs.Close() }
        $g.Dispose(); $bmp.Dispose(); $font.Dispose(); $brush.Dispose(); $path.Dispose()
        return $true
    } catch {
        return $false
    }
}

$iconPath = Join-Path $DataDir 'app.ico'
if (-not (Test-Path -LiteralPath $iconPath)) {
    if (-not (New-AppIcon -OutPath $iconPath)) { $iconPath = $null }
}
if (-not $iconPath) {
    $edge = Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
    if (Test-Path -LiteralPath $edge) { $iconPath = $edge } else { $iconPath = "$env:SystemRoot\System32\shell32.dll" }
}

# ---------------------------------------------------------------- 建快捷方式
$psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $psExe)) { $psExe = 'powershell.exe' }

function New-Shortcut([string]$Path, [string]$Name, [string]$Action, [string]$Description) {
    $lnk = Join-Path $Path ($Name + '.lnk')
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($lnk)
    $sc.TargetPath       = $psExe
    $sc.Arguments        = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Launcher`" -Action $Action"
    $sc.WorkingDirectory = $ProjectRoot
    $sc.Description      = $Description
    $sc.IconLocation     = "$iconPath,0"
    $sc.Save()
    return $lnk
}

Write-Host ''
Write-Host '创建桌面快捷方式...' -ForegroundColor Cyan
$targets = @()
if ($AlsoStartMenu) {
    $sm = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
    if (Test-Path -LiteralPath $sm) { $targets += $sm }
}
$targets += $DesktopPath

foreach ($dir in $targets) {
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $a = New-Shortcut -Path $dir -Name 'AI Career OS' -Action 'start' -Description '启动 AI Career OS（后端 + 前端 + Edge 独立窗口）'
    $b = New-Shortcut -Path $dir -Name '停止 AI Career OS' -Action 'stop' -Description '停止 AI Career OS 本地服务（不影响其他项目）'
    Write-Host "  [OK] $a" -ForegroundColor Green
    Write-Host "  [OK] $b" -ForegroundColor Green
}

Write-Host ''
Write-Host '  桌面已创建：' -ForegroundColor White
Write-Host '    · AI Career OS      双击即可启动（无黑窗）' -ForegroundColor White
Write-Host '    · 停止 AI Career OS 退出时用来停止本项目服务' -ForegroundColor White
Write-Host ''
exit 0
