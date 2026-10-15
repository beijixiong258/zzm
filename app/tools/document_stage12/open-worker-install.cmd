@echo off
title AIcademiya Document Worker Setup
echo AIcademiya document worker: one-time administrator installation
echo Enter the Ubuntu sudo password in this window only. Input is not echoed.
echo This installs an isolated worker. It does not restart teaching services.
echo.
ssh.exe -tt -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/ocr-stage1-20261009/stage12-parser/install_worker_linux.py --public-key /home/adminz/llm/ocr-stage1-20261009/stage12-parser/ct255-document-worker.pub"
echo.
echo Installer exit code: %ERRORLEVEL%
echo You can leave this window open for inspection or close it.
