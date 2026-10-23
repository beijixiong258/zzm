@echo off
title AIcademiya GPU Document Worker Setup
echo AIcademiya: enable the tested GPU document worker
echo This copies existing offline CUDA libraries and updates only the document worker.
echo Teaching services and drivers are not restarted or changed.
echo Enter the Ubuntu sudo password here only. Input is not echoed.
echo.
ssh.exe -tt -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/ocr-stage1-20261009/stage12-parser/install_worker_linux.py --public-key /home/adminz/llm/ocr-stage1-20261009/stage12-parser/ct255-document-worker.pub --gpu-uuid GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313"
echo.
echo Installer exit code: %ERRORLEVEL%
echo Leave this window open to inspect the result, or close it when finished.
