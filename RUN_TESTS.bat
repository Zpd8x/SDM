@echo off
setlocal
title SDM - Automated Tests
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
    py -3 -m unittest discover -s tests -v
) else (
    python -m unittest discover -s tests -v
)

if errorlevel 1 (
    echo.
    echo [FAILED] One or more SDM tests failed.
) else (
    echo.
    echo [PASSED] All SDM tests passed.
)
echo.
pause
