@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\..\.."
set "ROOT=%CD%"
set "VENV=%ROOT%\.build-venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "SETUP_EXE=%ROOT%\release\SDM_v3.2.0_Setup_x64.exe"
set "ISCC="

call :find_inno_setup
if not defined ISCC (
  call :fatal "Inno Setup 6 was not found." "The Portable and Browser Extension packages cannot be published as a complete Windows release without the Setup EXE. Install Inno Setup 6, then run build_release.bat again. You can install it with: winget install --id JRSoftware.InnoSetup -e"
)

echo [INFO] Inno Setup compiler: %ISCC%

where py >nul 2>&1 || call :fatal "Python Launcher was not found." "Install Python 3 for Windows and enable the Python Launcher, then run the build again."

if not exist "%PYTHON%" (
  echo [INFO] Creating build virtual environment...
  py -3 -m venv "%VENV%" || call :fatal "Virtual environment creation failed." "Python could not create .build-venv."
)

"%PYTHON%" -m pip install --upgrade pip || call :fatal "pip upgrade failed." "Check your internet connection and Python installation."
"%PYTHON%" -m pip install -r requirements.txt pyinstaller || call :fatal "Dependency installation failed." "Review the pip output above."

if exist "build\windows" rmdir /s /q "build\windows"
if not exist "release" mkdir "release"
if exist "%SETUP_EXE%" del /f /q "%SETUP_EXE%"

powershell -NoProfile -ExecutionPolicy Bypass -File packaging\windows\download_tools.ps1 || call :fatal "Bundled tools download failed." "yt-dlp or FFmpeg tools could not be prepared."

"%PYTHON%" -m unittest discover -s tests -v || call :fatal "Automated tests failed." "The release was stopped before packaging. Review the failed tests above."
"%PYTHON%" -m PyInstaller --noconfirm --clean --distpath build\windows --workpath build\pyinstaller packaging\windows\SDM.spec || call :fatal "SDM executable build failed." "PyInstaller could not build SDM.exe."
"%PYTHON%" -m PyInstaller --noconfirm --clean --distpath build\windows\native_host --workpath build\pyinstaller-host packaging\windows\SDMNativeHost.spec || call :fatal "Native Host build failed." "PyInstaller could not build SDMNativeHost.exe."

powershell -NoProfile -ExecutionPolicy Bypass -File packaging\windows\prepare_release.ps1 || call :fatal "Portable package preparation failed." "PowerShell could not prepare the release files."

"%ISCC%" packaging\windows\installer.iss || call :fatal "Windows Setup compilation failed." "Inno Setup returned an error. Review the compiler output above."

if not exist "%SETUP_EXE%" (
  call :fatal "Windows Setup file was not created." "Expected file: %SETUP_EXE%"
)

powershell -NoProfile -ExecutionPolicy Bypass -File packaging\windows\hash_release.ps1 || call :fatal "SHA-256 generation failed." "The release files were built, but checksums could not be generated."

echo.
echo ============================================================
echo [SUCCESS] COMPLETE WINDOWS RELEASE CREATED
echo ============================================================
echo Setup    : %SETUP_EXE%
echo Portable : %ROOT%\release\SDM_v3.2.0_Portable_x64.zip
echo Extension: %ROOT%\release\SDM_Browser_Extension_v3.2.0.zip
echo Hashes   : %ROOT%\release\SHA256SUMS.txt
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('SDM v3.2.0 Windows release was created successfully.','SDM Build Success','OK','Information')" >nul 2>&1
exit /b 0

:find_inno_setup
for %%I in (iscc.exe ISCC.exe) do (
  for /f "delims=" %%P in ('where %%I 2^>nul') do if not defined ISCC set "ISCC=%%P"
)
if defined ISCC exit /b 0

for %%P in (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
) do (
  if not defined ISCC if exist "%%~P" set "ISCC=%%~P"
)
exit /b 0

:fatal
set "ERROR_TITLE=%~1"
set "ERROR_DETAIL=%~2"
echo.
echo ============================================================
echo [FAILED] %ERROR_TITLE%
echo ============================================================
echo %ERROR_DETAIL%
echo.
echo No complete Windows release was created.
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show($env:ERROR_DETAIL,$env:ERROR_TITLE,'OK','Error')" >nul 2>&1
pause
endlocal
exit 1
