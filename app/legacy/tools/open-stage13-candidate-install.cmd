@echo off
title AIcademiya Stage13 Candidate Setup
echo Install an isolated, versioned Office document worker candidate.
echo Existing Stage12 production code/key and teaching services remain unchanged.
echo Enter password only at the sudo prompt. Input is not echoed.
ssh.exe -tt -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/ocr-stage1-20261009/stage13-worker-src/stage13_install_candidate.py --source /home/adminz/llm/ocr-stage1-20261009/stage13-worker-src --manifest-sha256 078d0a6b41fc6bcafbf1d54409a8c30ed94217b21b26c121b3bea598291b0b8e --public-key /home/adminz/llm/ocr-stage1-20261009/stage13-worker-src/ct255-stage13-worker.pub"
echo Candidate installer exit code: %ERRORLEVEL%
echo Finished. Do not type a password here. Press any key to close.
pause >nul
