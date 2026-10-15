@echo off
setlocal
cd /d "%~dp0"
title AIcademiya Setup
where uv >nul 2>nul
if errorlevel 1 (
  echo uv is required. Install uv and Node.js, then run this file again.
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo Node.js and npm are required.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  uv venv --python 3.13 .venv
  if errorlevel 1 goto failed
)
uv pip install --python ".venv\Scripts\python.exe" -r backend
equirements.txt
if errorlevel 1 goto failed
pushd frontend
call npm ci --include=dev
if errorlevel 1 (
  popd
  goto failed
)
call npm run build
if errorlevel 1 (
  popd
  goto failed
)
popd
".venv\Scripts\python.exe" tools\launch.py --check
if errorlevel 1 goto failed
echo Setup complete. Double-click start.cmd to open AIcademiya.
pause
exit /b 0
:failed
echo Setup failed. See the message above. Existing data has not been reset.
pause
exit /b 1
