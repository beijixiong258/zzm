@echo off
setlocal
cd /d "%~dp0"
title AIcademiya
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.cmd once before starting AIcademiya.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" tools\launch.py
if errorlevel 1 pause
