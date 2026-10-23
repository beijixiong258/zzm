@echo off
title AIcademiya Stage15 - Vision Runtime Install
echo Install verified immutable router code and pinned T10-B vision config.
echo This step does NOT restart models, activate the router or promote the website.
echo Enter your Ubuntu sudo password ONLY at the masked prompt below.
ssh.exe -4 -tt -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/operations/stage15-deploy-r1/install_vision_candidate.py --manifest-sha256 292a652a0de0ab63e525106e9c08ac22fcbf2f64a9c3ad7b665fa063dc5b0cfb"
echo Installer exit code: %ERRORLEVEL%
echo Finished. Do not type a password here. Press any key to close.
pause >nul
