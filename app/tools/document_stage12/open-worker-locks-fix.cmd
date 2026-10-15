@echo off
title AIcademiya Document Worker Permission Fix
echo AIcademiya: repair the model lock cache permission
echo Only the .locks cache becomes writable. Model weights stay read-only.
echo Enter your password only at the sudo prompt. Input is not echoed.
echo.
ssh.exe -tt -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/ocr-stage1-20261009/stage12-parser/install_worker_linux.py --public-key /home/adminz/llm/ocr-stage1-20261009/stage12-parser/ct255-document-worker.pub --repair-model-locks"
echo.
echo Permission repair exit code: %ERRORLEVEL%
echo Finished. Do not type a password here. Press any key to close this window.
pause >nul
