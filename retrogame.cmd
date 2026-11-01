@echo off
setlocal
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0retrogame.ps1" %*
exit /b %ERRORLEVEL%
