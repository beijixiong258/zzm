@echo off
title AIcademiya Parser R6 - Verified Candidate
echo Install combined parser fixes and verify them as the restricted worker.
echo Also preserve exact live scheduler code in a root-owned immutable release.
echo No teaching model restart, no router activation, no website promotion.
echo Enter your Ubuntu sudo password ONLY at the masked prompt below.
ssh.exe -4 -tt -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/operations/stage14-worker-r6/install_parser_r6.py"
echo Installer exit code: %ERRORLEVEL%
echo Finished. Do not type a password here. Press any key to close.
pause >nul
