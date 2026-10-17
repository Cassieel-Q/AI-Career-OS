@echo off
chcp 65001 >nul
setlocal
REM ============================================================
REM  AI Career OS - one-click desktop launcher
REM  Starts API + Web + controlled browser bridge, then opens
REM  Microsoft Edge in a standalone app window.
REM  Safe: only manages processes that belong to THIS project.
REM ============================================================
set "ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\local-app\career-app.ps1" -Action start
endlocal
