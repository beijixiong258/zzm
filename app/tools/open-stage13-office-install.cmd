@echo off
title AIcademiya Office Conversion Setup
echo Install the server-side Office renderer and fonts for complete PPTX/Word processing.
echo Existing packages, GPU drivers and teaching services will not be upgraded or restarted.
echo Enter the password only at the sudo prompt; input is not echoed.
ssh.exe -tt -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/ocr-stage1-20261009/stage13-setup/stage13_install_office.py"
echo.
echo Installer exit code: %ERRORLEVEL%
echo Finished. Do not type a password here. Press any key to close.
pause >nul
