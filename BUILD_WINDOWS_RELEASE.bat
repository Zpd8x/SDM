@echo off
cd /d "%~dp0"
call packaging\windows\build_release.bat
exit /b %ERRORLEVEL%
