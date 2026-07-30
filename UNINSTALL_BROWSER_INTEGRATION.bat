@echo off
setlocal
title SDM - Remove Browser Integration
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "%~dp0browser_host\uninstall_host.py"
) else (
    py -3 "%~dp0browser_host\uninstall_host.py"
)

echo.
pause
