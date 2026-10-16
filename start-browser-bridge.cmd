@echo off
setlocal
REM ============================================================
REM  AI Career OS - 受控浏览器桥（网申填表用）
REM  - 由用户显式启动的本地浏览器会话（Playwright + Chromium）
REM  - 仅监听 127.0.0.1；只读表单 / 只填表单，永不提交
REM ============================================================

set "ROOT=%~dp0"
echo 启动受控浏览器桥 (127.0.0.1:8770)...
echo 关闭本窗口即可结束会话。
echo.
cd /d "%ROOT%apps\web"
node "scripts\browser-bridge.cjs"
endlocal
