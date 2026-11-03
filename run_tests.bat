@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo Please run start.bat once first so the Python environment exists.
  pause
  exit /b 1
)
echo === Backend tests ===
pushd backend
".venv\Scripts\python.exe" -m pip install -q -r requirements-dev.txt
".venv\Scripts\python.exe" -m pytest
set "BACKEND_RESULT=%errorlevel%"
popd
echo.
echo === Frontend tests and type check ===
pushd frontend
if not exist node_modules call npm install
call npm run typecheck
call npm test
popd
echo.
if "%BACKEND_RESULT%"=="0" (echo Backend tests passed.) else (echo Backend tests FAILED.)
pause
