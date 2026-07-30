@echo off
setlocal
title SDM - Smart Download Manager
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
    set "SDM_PYTHON=py -3"
    goto :python_found
)

where python >nul 2>&1
if not errorlevel 1 (
    set "SDM_PYTHON=python"
    goto :python_found
)

echo.
echo [ERROR] Python 3 was not found.
echo Install Python from https://www.python.org/downloads/windows/
echo During installation, enable "Add Python to PATH".
echo.
pause
exit /b 1

:python_found
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [SETUP] Creating the SDM Python environment...
    %SDM_PYTHON% -m venv .venv
    if errorlevel 1 goto :setup_failed
)

call ".venv\Scripts\activate.bat"

python -c "import PySide6, yt_dlp" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [SETUP] Installing SDM requirements...
    python -m pip install --upgrade pip
    if errorlevel 1 goto :setup_failed
    python -m pip install -r requirements.txt
    if errorlevel 1 goto :setup_failed
)

echo.
echo [START] Launching SDM...
python main.py
set "SDM_EXIT=%ERRORLEVEL%"
if not "%SDM_EXIT%"=="0" (
    echo.
    echo [ERROR] SDM closed with exit code %SDM_EXIT%.
    pause
)
exit /b %SDM_EXIT%

:setup_failed
echo.
echo [ERROR] SDM setup failed.
echo Check your internet connection and try START_SDM.bat again.
echo.
pause
exit /b 1
