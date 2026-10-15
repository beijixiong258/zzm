@echo off
title AIcademiya Stage16 - Document Worker Upgrade
echo Install 21 verified worker files, CPU-check as UID999, then upgrade its existing restricted SSH binding.
echo Original worker release is retained. No website, teaching-model or router restart.
echo Enter Ubuntu sudo password ONLY at the masked prompt below.
ssh.exe -4 -tt -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/operations/stage16-worker-r1/install_worker.py --manifest-sha256 ba9167a0862314dcf3f0373fe456d5e8704fa2d73fbaa5ad8c73468f3c389e70"
echo Installer exit code: %ERRORLEVEL%
echo Finished. Do not type a password here. Press any key to close.
pause >nul
