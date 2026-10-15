@echo off
title AIcademiya Stage16 - Install Calc
echo Add the missing same-version LibreOffice Calc component and dependencies.
echo Expected: 5 new packages, no existing package upgrades or removals.
echo No teaching model, router, worker or website activation in this step.
echo Enter your Ubuntu sudo password ONLY at the masked remote prompt below.
ssh.exe -4 -tt -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/operations/stage16-calc-r1/install_calc.py --version 4:24.2.7-0ubuntu0.24.04.7"
echo Installer exit code: %ERRORLEVEL%
echo Finished. Do not type a password here. Press any key to close.
pause >nul
