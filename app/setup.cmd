@echo off
setlocal
cd /d "%~dp0"
title AIcademiya Setup
pwsh.exe -NoProfile -File "%~dp0setup.ps1"
set "setupResult=%errorlevel%"
pause
exit /b %setupResult%
