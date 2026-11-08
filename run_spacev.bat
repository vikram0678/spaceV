@echo off
title SpaceV Cybernetic Desktop Assistant
cd /d "%~dp0"

if exist ".\venv\Scripts\python.exe" (
    echo [SpaceV] Starting natively on Windows via venv...
    call .\venv\Scripts\python.exe main.py
) else (
    echo [SpaceV] Windows venv not found. Attempting WSL fallback...
    wsl.exe -e bash -lic "cd \"$(wslpath '%~dp0')\" && (python3 main.py || .venv/bin/python main.py)"
)
pause
