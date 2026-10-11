@echo off
REM AI Career OS demo launcher: API (8000) + Web (3000), SQLite demo DB
start "aios-api" cmd /k "cd /d %~dp0apps\api && set DATABASE_URL=sqlite:///G:/myself/ai-career/.runtime/demo-career.db&& set PYTHONPATH=.&& .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
timeout /t 2 /nobreak >nul
start "aios-web" cmd /k "cd /d %~dp0apps\web && set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000&& npm run dev -- -H 127.0.0.1 -p 3000"
echo.
echo   API  http://127.0.0.1:8000/health
echo   Web  http://127.0.0.1:3000/missions
if not exist "%~dp0.runtime\typst-0.15.1\typst-x86_64-pc-windows-msvc\typst.exe" (
  echo   [提醒] 未检测到 Typst，简历工作台的预览/PDF 将不可用。
  echo          下载 typst-x86_64-pc-windows-msvc.zip 解压到 .runtime\typst-0.15.1\ 即可。
)
echo.
