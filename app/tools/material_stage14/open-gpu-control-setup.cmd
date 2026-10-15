@echo off
title AIcademiya Private GPU Control Setup
echo Create the private GPU lease socket directory and boot-time permission rule.
echo No teaching model, router configuration or application data will be changed.
echo Enter your sudo password only at the masked prompt below.
ssh.exe -tt -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/ocr-stage1-20261009/stage14-parent/provision_gpu_control.py"
echo Setup exit code: %ERRORLEVEL%
echo Finished. Do not type a password here. Press any key to close.
pause >nul
