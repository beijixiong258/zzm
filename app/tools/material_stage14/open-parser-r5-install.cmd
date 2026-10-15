@echo off
title AIcademiya Parser R5 - Offline CPU Verification
echo Install the new isolated parser and four missing CPU OCR packages.
echo This does NOT restart teaching models, switch the website, or restore the production document inlet.
echo Enter your Ubuntu sudo password ONLY at the masked prompt below.
ssh.exe -tt -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/operations/stage14-worker-r5/install_parser_r5.py"
echo Installer exit code: %ERRORLEVEL%
echo Finished. Do not type a password here. Press any key to close.
pause >nul
