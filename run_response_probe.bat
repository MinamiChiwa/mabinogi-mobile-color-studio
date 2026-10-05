@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_response_probe.ps1" %*
exit /b %errorlevel%
