@echo off
setlocal
REM AI Career OS demo launcher: API (8000) + Web (3000), SQLite demo DB
REM 说明：演示库位于仓库内 .runtime/，随仓库迁移不会自动跟走。
REM       长期使用请改用 start-local.cmd（稳定的本地数据目录）。
set "ROOT=%~dp0"
set "DEMO_DB=%ROOT%.runtime\demo-career.db"
set "DEMO_DB_FWD=%DEMO_DB:\=/%"

start "aios-api" cmd /k "cd /d %ROOT%apps\api && set DATABASE_URL=sqlite:///%DEMO_DB_FWD%&& set PYTHONPATH=.&& .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
timeout /t 2 /nobreak >nul
start "aios-web" cmd /k "cd /d %ROOT%apps\web && set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000&& npm run dev -- -H 127.0.0.1 -p 3000"
echo.
echo   API  http://127.0.0.1:8000/health
echo   Web  http://127.0.0.1:3000/missions
if not exist "%ROOT%.runtime\typst-0.15.1\typst-x86_64-pc-windows-msvc\typst.exe" (
  echo   [提醒] 未检测到 Typst，简历工作台的预览/PDF 将不可用。
  echo          下载 typst-x86_64-pc-windows-msvc.zip 解压到 .runtime\typst-0.15.1\ 即可。
)
echo.
endlocal
