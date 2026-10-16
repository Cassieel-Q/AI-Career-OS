@echo off
setlocal
REM ============================================================
REM  AI Career OS - 一键启动全部（本地优先）
REM  = 本地数据库初始化 + 后端 API + 前端 + 受控浏览器桥
REM ============================================================

set "ROOT=%~dp0"
if "%AI_CAREER_DATA_DIR%"=="" set "AI_CAREER_DATA_DIR=%LOCALAPPDATA%\AICareerOS"

call "%ROOT%start-local.cmd"
echo 启动受控浏览器桥...
start "aios-bridge" cmd /k "cd /d %ROOT% && start-browser-bridge.cmd"
echo.
echo 全部已启动：Web 127.0.0.1:3000 / API 127.0.0.1:8000 / 浏览器桥 127.0.0.1:8770
endlocal
