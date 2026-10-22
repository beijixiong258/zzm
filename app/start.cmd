@echo off
setlocal
cd /d "%~dp0"
pwsh.exe -NoProfile -File "%~dp0start.ps1" %*
exit /b %errorlevel%
