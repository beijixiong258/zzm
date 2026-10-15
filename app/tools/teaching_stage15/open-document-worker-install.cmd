@echo off
title AIcademiya Stage15 - Document Worker Install
echo Install the new isolated document-worker candidate and verified model copies.
echo No model restart, no router activation, no website promotion.
echo Enter your Ubuntu sudo password ONLY at the masked prompt below.
ssh.exe -4 -tt -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu-gpu "sudo /usr/bin/python3 /home/adminz/llm/operations/stage15-worker-r1/install_document_worker.py --package-sha256 97ce10c8f4236c7c6a31eb6317337fb27a69d95261df2d84421801fe9176f919 --assets-sha256 fe06a726753c50d040397d9b916e73894ecba7ad538f74654a05b30785a38215 --profile-sha256 ead3e11f54de18babe797be16383ed797f4bb16fc44cf2a9e32cce5072276425 --public-key-sha256 65db49deaa94f9b6d963229d04bb611491b156824818f26b0228ab3ffa55a27f"
echo Installer exit code: %ERRORLEVEL%
echo Finished. Do not type a password here. Press any key to close.
pause >nul
