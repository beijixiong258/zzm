@echo off
title AIcademiya GPU Worker Installation
echo Install fixed independent teaching service definitions and an isolated leased document worker.
echo This installer does NOT start, stop or restart models and does NOT switch the website.
echo Enter your sudo password only at the masked prompt.
ssh.exe -tt -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/operations/stage14-gpu-migration-r1/install_gpu_scheduler.py --source /home/adminz/llm/operations/stage14-gpu-migration-r1 --manifest-sha256 43750ae4c65a958e7ed88547ee7969c89addfdbb49fba3cd3e80dbbcd8746ba1 && sudo /usr/bin/python3 /home/adminz/llm/operations/stage14-gpu-migration-r1/install_worker_candidate.py --source /home/adminz/llm/operations/stage14-gpu-migration-r1/worker --manifest-sha256 8537783f7eca04899155c7da191f9b3e523e6cb51de4305f93c2b83fc816dd7c --public-key /home/adminz/llm/operations/stage14-gpu-migration-r1/worker/ct255-worker.pub"
echo Installer exit code: %ERRORLEVEL%
echo Finished. Do not type a password here. Press any key to close.
pause >nul
