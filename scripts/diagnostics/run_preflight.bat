@echo off
setlocal
cd /d "%~dp0..\.."
set "PYTHONPATH=%~dp0..\..\work\studio"
set "PYTHON=%~dp0..\..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Project Python is missing. Set up .venv before entering dye mode.
  pause
  exit /b 1
)
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss-fff"') do set "STAMP=%%t"
set "OUT=%~dp0..\..\runtime\diagnostics\preflight-%STAMP%"
"%PYTHON%" "%~dp0..\..\work\studio\live_atlas_capture.py" preflight "%OUT%"
if errorlevel 1 (
  echo.
  echo Preflight failed. Check the report before entering dye mode:
  echo %OUT%\preflight.json
)
echo Report: %OUT%\preflight.json
pause
