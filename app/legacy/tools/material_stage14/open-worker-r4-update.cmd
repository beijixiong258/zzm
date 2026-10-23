@echo off
title AIcademiya Document Worker Update
echo Update the isolated Stage14 worker port check; existing production key stays unchanged.
echo No model will be stopped by this installer. Enter sudo password only at the masked prompt.
ssh.exe -tt -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/operations/stage14-gpu-migration-r1/install_worker_candidate.py --source /home/adminz/llm/operations/stage14-gpu-migration-r1/worker-r4 --manifest-sha256 8582eef6a4746dcc75e67f0c968eff26e995fa8c2ee86c17ca6f8c6b6ab38c04 --public-key /home/adminz/llm/operations/stage14-gpu-migration-r1/worker-r4/ct255-worker.pub --replace-bound-release stage14-materials-r3"
echo Installer exit code: %ERRORLEVEL%
echo Finished. Do not type a password here. Press any key to close.
pause >nul
