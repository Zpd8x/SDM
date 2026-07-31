@echo off
setlocal EnableExtensions EnableDelayedExpansion
title SDM - Smart Download Manager
cd /d "%~dp0"

set "SDM_VENV_PY=.venv\Scripts\python.exe"
set "SDM_PIP_TIMEOUT=120"
set "SDM_PIP_RETRIES=5"

call :find_python
if errorlevel 1 exit /b 1

if not exist "%SDM_VENV_PY%" (
    echo.
    echo [SETUP] Creating the SDM Python environment...
    %SDM_PYTHON% -m venv .venv
    if errorlevel 1 goto :setup_failed
)

call :check_runtime
if errorlevel 1 call :install_requirements
if errorlevel 1 goto :setup_failed

:launch
echo.
echo [START] Launching SDM...
"%SDM_VENV_PY%" main.py
set "SDM_EXIT=%ERRORLEVEL%"
if not "%SDM_EXIT%"=="0" (
    echo.
    echo [ERROR] SDM closed with exit code %SDM_EXIT%.
    pause
)
exit /b %SDM_EXIT%

:find_python
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
%SDM_PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] SDM requires Python 3.10 or newer.
    echo.
    pause
    exit /b 1
)
exit /b 0

:check_runtime
"%SDM_VENV_PY%" -c "import PySide6, yt_dlp" >nul 2>&1
exit /b %ERRORLEVEL%

:install_requirements
echo.
echo [SETUP] Installing missing SDM requirements...
echo [SETUP] Timeout: %SDM_PIP_TIMEOUT%s  Retries: %SDM_PIP_RETRIES%
"%SDM_VENV_PY%" -m pip install -r requirements.txt --disable-pip-version-check --timeout %SDM_PIP_TIMEOUT% --retries %SDM_PIP_RETRIES%
if not errorlevel 1 (
    call :check_runtime
    exit /b !ERRORLEVEL!
)

rem A failed network request may still leave every required package installed.
call :check_runtime
if not errorlevel 1 (
    echo.
    echo [SETUP] Required packages are available. Continuing offline...
    exit /b 0
)

:setup_choice
echo.
echo [ERROR] SDM could not install its required Python packages.
echo Check your Internet, firewall, VPN, proxy, or DNS settings.
echo.
echo [R] Retry installation
echo [O] Try offline launch
echo [X] Exit
choice /C ROX /N /M "Select an option [R/O/X]: "
if errorlevel 3 exit /b 1
if errorlevel 2 (
    call :check_runtime
    if not errorlevel 1 exit /b 0
    echo.
    echo [ERROR] Offline launch is unavailable because required packages are missing.
    goto :setup_choice
)
if errorlevel 1 goto :install_requirements
exit /b 1

:setup_failed
echo.
echo [ERROR] SDM setup failed.
echo Review the message above, then run START_SDM.bat again.
echo.
pause
exit /b 1
