@echo off
setlocal EnableExtensions
title SDM - Install Browser Integration

for %%I in ("%~dp0.") do set "SDM_PROJECT_ROOT=%%~fI"
set "SDM_PYTHON=%SDM_PROJECT_ROOT%\.venv\Scripts\python.exe"
set "SDM_HOST_SCRIPT=%SDM_PROJECT_ROOT%\browser_host\native_host.py"
cd /d "%SDM_PROJECT_ROOT%"

if not exist "%SDM_PYTHON%" (
    echo.
    echo [ERROR] The SDM Python environment was not found.
    echo Run START_SDM.bat once, close SDM, then run this installer again.
    echo.
    pause
    exit /b 1
)

if not exist "%SDM_HOST_SCRIPT%" (
    echo.
    echo [ERROR] The Native Host source file was not found:
    echo %SDM_HOST_SCRIPT%
    echo Extract the complete SDM package, then run this installer again.
    echo.
    pause
    exit /b 1
)

"%SDM_PYTHON%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [SETUP] Installing the Native Host builder...
    "%SDM_PYTHON%" -m pip install "pyinstaller>=6.0,<7.0"
    if errorlevel 1 goto :install_failed
)

echo.
echo [BUILD] Building SDM Native Messaging host...
"%SDM_PYTHON%" -m PyInstaller --noconfirm --clean --onefile --console --name SDMNativeHost --paths "%SDM_PROJECT_ROOT%\." --exclude-module PySide6 --distpath "%SDM_PROJECT_ROOT%\browser_host\dist" --workpath "%SDM_PROJECT_ROOT%\browser_host\build" --specpath "%SDM_PROJECT_ROOT%\browser_host" "%SDM_HOST_SCRIPT%"
if errorlevel 1 goto :install_failed

echo.
echo [INSTALL] Registering the host for Chrome and Edge...
"%SDM_PYTHON%" "%SDM_PROJECT_ROOT%\browser_host\install_host.py"
if errorlevel 1 goto :install_failed

echo.
echo ================================================================
echo [SUCCESS] Browser integration is ready.
echo.
echo Next:
echo   1. Open chrome://extensions or edge://extensions
echo   2. Enable Developer mode
echo   3. Click Load unpacked
echo   4. Select: %SDM_PROJECT_ROOT%\browser_extension
echo   5. Click Reload if the extension was already loaded
echo ================================================================
echo.
pause
exit /b 0

:install_failed
echo.
echo [ERROR] Browser integration installation failed.
echo Review the first error shown above, then run this file again.
echo Internet access is required only if PyInstaller must be installed.
echo.
pause
exit /b 1
