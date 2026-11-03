@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title HealthResearch AI - setup

echo ==================================================
echo   HealthResearch AI - one-click start
echo ==================================================
echo.

rem ---------- 1. Check Python (3.10 or newer) ----------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY goto :nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto :nopython

rem ---------- 2. Check Node.js ----------
where node >nul 2>nul
if errorlevel 1 goto :nonode
where npm >nul 2>nul
if errorlevel 1 goto :nonode

rem ---------- 3. Backend: virtual environment + packages (first run only) ----------
if not exist "backend\.venv\Scripts\python.exe" (
  echo [1/3] Creating the Python environment - first run only...
  %PY% -m venv backend\.venv
  if errorlevel 1 goto :fail
)
if not exist "backend\.venv\.deps-installed" (
  echo [2/3] Installing backend packages - this can take a minute...
  "backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
  "backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
  if errorlevel 1 goto :fail
  echo done> "backend\.venv\.deps-installed"
)

rem ---------- 4. Settings file ----------
if not exist "backend\.env" (
  copy "backend\.env.example" "backend\.env" >nul
  echo.
  echo Created backend\.env from the template.
  echo The app works right away without an AI key - in basic extractive mode.
  echo To turn on AI writing, edit backend\.env - see README.md, section "API keys".
  echo.
)

rem ---------- 5. Frontend packages (first run only) ----------
if not exist "frontend\node_modules" (
  echo [3/3] Installing frontend packages - this can take a minute...
  pushd frontend
  call npm install
  if errorlevel 1 (
    popd
    goto :fail
  )
  popd
)

rem ---------- 6. Launch both servers in their own windows ----------
echo.
echo Starting the backend on http://127.0.0.1:8000 and the app on http://localhost:5173
start "HealthResearch AI - Backend" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000"
start "HealthResearch AI - Frontend" /D "%~dp0frontend" cmd /k "npm run dev"

echo Waiting a few seconds, then opening your browser...
timeout /t 7 /nobreak >nul
start "" "http://localhost:5173"
echo.
echo Done. Keep the two black windows open while you use the app.
echo Close them - or press Ctrl+C in each - to stop.
timeout /t 5 >nul
exit /b 0

:nopython
echo [ERROR] Python 3.10 or newer was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
echo Then run start.bat again.
pause
exit /b 1

:nonode
echo [ERROR] Node.js was not found.
echo Install the LTS version from https://nodejs.org/ and run start.bat again.
pause
exit /b 1

:fail
echo.
echo [ERROR] Setup failed - read the messages above. See README.md, section "Troubleshooting".
pause
exit /b 1
