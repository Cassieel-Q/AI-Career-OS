@echo off
setlocal
REM ============================================================
REM  AI Career OS - 本地优先模式启动（Windows）
REM  - 免登录、单用户，仅监听 127.0.0.1，不暴露公网
REM  - 数据保存在稳定的本地目录（默认 %LOCALAPPDATA%\AICareerOS）
REM  - 不依赖临时演示数据库，重启后数据完整
REM ============================================================

set "ROOT=%~dp0"
if "%AI_CAREER_DATA_DIR%"=="" set "AI_CAREER_DATA_DIR=%LOCALAPPDATA%\AICareerOS"

set "DATA_DIR_FWD=%AI_CAREER_DATA_DIR:\=/%"
set "DB_URL=sqlite:///%DATA_DIR_FWD%/career.db"

echo [1/3] 初始化本地数据库...
pushd "%ROOT%apps\api"
set "PYTHONPATH=."
".venv\Scripts\python.exe" "scripts\init_local_db.py"
if errorlevel 1 (
  echo [!] 数据库初始化未完全成功，继续启动，缺失项会在页面上提示。
)
popd

echo [2/3] 启动后端 API (127.0.0.1:8000)...
start "aios-api" cmd /k "cd /d %ROOT%apps\api && set AI_CAREER_DATA_DIR=%AI_CAREER_DATA_DIR%&& set DATABASE_URL=%DB_URL%&& set PYTHONPATH=.&& .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [3/3] 启动前端 (127.0.0.1:3000)...
timeout /t 2 /nobreak >nul
start "aios-web" cmd /k "cd /d %ROOT%apps\web && set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000&& npm run dev -- -H 127.0.0.1 -p 3000"

echo.
echo   Web  http://127.0.0.1:3000
echo   API  http://127.0.0.1:8000/health
echo   数据 %AI_CAREER_DATA_DIR%
echo.
echo   网申填表还需要单独启动受控浏览器桥：start-browser-bridge.cmd
echo   配置模型：在项目根目录建 .env（OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL）。
echo.
endlocal
