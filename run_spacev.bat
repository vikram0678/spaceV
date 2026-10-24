@echo off
title SpaceV Cybernetic Desktop Assistant
wsl.exe -d Ubuntu -e bash -lic "cd /home/vikram/agentSpace && .venv/bin/python main.py"
pause


@REM @echo off
@REM title SpaceV Cybernetic Desktop Assistant
@REM cd /d "%~dp0"
@REM call .\venv\Scripts\python.exe main.py
@REM pause
