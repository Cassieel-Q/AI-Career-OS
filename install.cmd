@echo off
rem AI Career OS one-click installer (Windows).
rem Steps: check env -> create venv + install backend deps -> install frontend deps -> create desktop shortcuts.
rem Safe to re-run (idempotent). See docs/操作手册.md for the Chinese manual.
setlocal
cd /d "%~dp0"

echo.
echo ==============================================
echo   AI Career OS - First-time Setup
echo ==============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [X] Python not found. Install Python 3.11+ from https://www.python.org/downloads/
  echo     and check "Add python.exe to PATH" during setup.
  pause & exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo [X] Node.js not found. Install Node.js 18+ LTS from https://nodejs.org/
  pause & exit /b 1
)

if not exist "apps\api\.venv\Scripts\python.exe" (
  echo [1/4] Creating Python virtual environment...
  python -m venv apps\api\.venv
  if errorlevel 1 ( echo [X] Failed to create venv & pause & exit /b 1 )
) else (
  echo [1/4] Python venv already exists, skip.
)

echo [2/4] Installing backend dependencies...
apps\api\.venv\Scripts\python -m pip install -r apps\api\requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 ( echo [X] Backend dependency install failed & pause & exit /b 1 )

if not exist "apps\web\node_modules\next" (
  echo [3/4] Installing frontend dependencies - first run takes a few minutes...
  pushd apps\web
  call npm install
  popd
  if errorlevel 1 ( echo [X] Frontend dependency install failed & pause & exit /b 1 )
) else (
  echo [3/4] Frontend dependencies already exist, skip.
)

echo [4/4] Creating desktop shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -File "create-desktop-shortcut.ps1"
if errorlevel 1 ( echo [X] Failed to create desktop shortcuts & pause & exit /b 1 )

echo.
echo ==============================================
echo   Setup done!
echo   1. Create a .env file in this folder with your model key
echo      (see README "Model config").
echo   2. Double-click the "AI Career OS" desktop icon to start.
echo ==============================================
echo.
pause
