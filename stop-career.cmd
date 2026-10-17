@echo off
chcp 65001 >nul
setlocal
REM ============================================================
REM  AI Career OS - stop local services
REM  Stops ONLY processes launched from THIS project directory.
REM  Never touches ports/processes owned by other projects.
REM ============================================================
set "ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\local-app\career-app.ps1" -Action stop
endlocal
