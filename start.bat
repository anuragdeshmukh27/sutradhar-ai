@echo off
REM Sutradhar AI: one double-click launcher (backend :8000 + frontend :5173)
cd /d "%~dp0"
if not exist backend\.venv\Scripts\python.exe (
  echo Backend venv missing. See README.md setup.
  pause
  exit /b 1
)
start "Sutradhar backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
start "Sutradhar frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
echo Waiting for servers...
timeout /t 6 /nobreak >nul
start http://localhost:5173
