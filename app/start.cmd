@echo off
setlocal
cd /d "%~dp0"
title AIcademiya
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.cmd once before starting AIcademiya.
  pause
  exit /b 1
)
pwsh.exe -NoProfile -File "%~dp0start.ps1"
if errorlevel 1 pause
